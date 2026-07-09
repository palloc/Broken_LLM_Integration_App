"""起動・表示ヘルパ（Colab / JupyterHub / ローカル Jupyter 共通）。

典型的な使い方（ノートブック）::

    from broken_handson import launcher
    launcher.seed()                 # SQLite 作成 + サンプルデータ投入（初回のみ）
    proc = launcher.start()         # uvicorn を --reload 付きで起動
    launcher.show()                 # Colab は iframe、それ以外は URL を表示

防御ファイルは `student_workspace/edit_targets/` を編集し、
`launcher.sync_edit_targets()` で反映する。停止は ``launcher.stop(proc)``。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import EDITABLE_FILES, PATHS, prepare_env

DEFAULT_PORT = 8000
_ACTIVE_PORT = DEFAULT_PORT


# ── 環境検出 ─────────────────────────────────────────────────────────────────
def in_colab() -> bool:
    return importlib.util.find_spec("google.colab") is not None


# ── LLM 設定の補助 ───────────────────────────────────────────────────────────
def use_openai(api_key: str, model: str = "gpt-4o-mini", base_url: str = "") -> None:
    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_MODEL_NAME"] = model
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url
    print(f"[llm] provider=openai model={model}")


def use_ollama(base_url: str, model: str) -> None:
    os.environ["LLM_PROVIDER"] = "ollama"
    os.environ["OLLAMA_BASE_URL"] = base_url
    os.environ["OLLAMA_MODEL_NAME"] = model
    print(f"[llm] provider=ollama model={model} base_url={base_url}")


def configure_llm(interactive: bool = True) -> None:
    """LLM 設定を解決する。優先順位:

      1. `.env`（course/.env 等）／既存の環境変数
      2. Colab の「シークレット」（OPENAI_API_KEY）
      3. `getpass` による対話入力（interactive=True のとき）

    `.env` に `OPENAI_API_KEY` を書いておけば、このセルは何も尋ねずに完了する。
    Ollama を使う場合は `.env` に `LLM_PROVIDER=ollama` と `OLLAMA_BASE_URL` /
    `OLLAMA_MODEL_NAME` を設定しておく。
    """
    prepare_env()  # ここで .env を読み込む
    ensure_edit_targets()
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "ollama":
        if os.environ.get("OLLAMA_BASE_URL") and os.environ.get("OLLAMA_MODEL_NAME"):
            print(f"[llm] provider=ollama model={os.environ['OLLAMA_MODEL_NAME']} "
                  f"base_url={os.environ['OLLAMA_BASE_URL']}（.env/環境変数）")
            return
        raise RuntimeError("LLM_PROVIDER=ollama ですが OLLAMA_BASE_URL/OLLAMA_MODEL_NAME が未設定です。"
                           " course/.env に設定してください。")

    # provider == openai（既定）
    if os.environ.get("OPENAI_API_KEY"):
        model = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        print(f"[llm] provider=openai model={model}（.env/環境変数の OPENAI_API_KEY を使用）")
        return

    # Colab シークレット
    try:
        from google.colab import userdata  # type: ignore
        key = userdata.get("OPENAI_API_KEY")
        if key:
            use_openai(key, model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"))
            return
    except Exception:
        pass

    if interactive:
        import getpass
        key = getpass.getpass("OPENAI_API_KEY: ")
        use_openai(key, model=os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini"))
        return

    raise RuntimeError("OPENAI_API_KEY が見つかりません。course/.env に記載するか、"
                       "環境変数 / Colab シークレットで設定してください。")


# ── DB 投入 ──────────────────────────────────────────────────────────────────
def seed(verbose: bool = True) -> str:
    ensure_edit_targets()
    sync_edit_targets()
    from .seed import seed as _seed
    return _seed(verbose=verbose)


# ── サーバ起動 ───────────────────────────────────────────────────────────────
def active_port() -> int:
    return _ACTIVE_PORT


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PATHS.course_dir), str(PATHS.backend_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return env


def _editable_pairs() -> list[tuple[Path, Path, Path]]:
    pairs: list[tuple[Path, Path, Path]] = []
    for filename in EDITABLE_FILES:
        pairs.append((
            PATHS.app_dir / filename,
            PATHS.edit_targets_dir / filename,
            PATHS.baseline_dir / filename,
        ))
    return pairs


def ensure_edit_targets() -> None:
    prepare_env()
    for app_file, edit_file, baseline_file in _editable_pairs():
        if not app_file.is_file():
            raise FileNotFoundError(f"編集対象の元ファイルが見つかりません: {app_file}")
        if not baseline_file.exists():
            baseline_file.write_text(app_file.read_text(encoding="utf-8"), encoding="utf-8")
        if not edit_file.exists():
            edit_file.write_text(baseline_file.read_text(encoding="utf-8"), encoding="utf-8")


def sync_edit_targets() -> None:
    ensure_edit_targets()
    for app_file, edit_file, _baseline_file in _editable_pairs():
        app_file.write_text(edit_file.read_text(encoding="utf-8"), encoding="utf-8")


def reset_edit_targets() -> None:
    ensure_edit_targets()
    for _app_file, edit_file, baseline_file in _editable_pairs():
        edit_file.write_text(baseline_file.read_text(encoding="utf-8"), encoding="utf-8")
    sync_edit_targets()


def start(port: int = DEFAULT_PORT, reload: bool = True, wait: bool = True) -> subprocess.Popen:
    """uvicorn を別プロセスで起動する。プロセスハンドルを返す。"""
    global _ACTIVE_PORT
    prepare_env()
    sync_edit_targets()
    _ACTIVE_PORT = port
    cmd = [
        sys.executable, "-m", "uvicorn", "broken_handson.server:app",
        "--host", "0.0.0.0", "--port", str(port),
    ]
    if reload:
        cmd += [
            "--reload",
            "--reload-dir", str(PATHS.app_dir),
            "--reload-dir", str(PATHS.edit_targets_dir),
        ]

    print("[server] launching:", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(PATHS.backend_dir),   # secret.md / inspect_result.json をここに置く
        env=_child_env(),
    )
    if wait and not wait_until_up(port):
        print("[server] WARNING: health check timed out（ログを確認してください）")
    return proc


def wait_until_up(port: int = DEFAULT_PORT, timeout: float = 40.0) -> bool:
    url = f"http://127.0.0.1:{port}/healthcheck"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    print(f"[server] up: {url}")
                    return True
        except Exception:
            time.sleep(0.8)
    return False


def stop(proc: subprocess.Popen) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[server] stopped")


# ── UI 表示 ──────────────────────────────────────────────────────────────────
def show(port: int = DEFAULT_PORT, height: int = 720) -> None:
    if in_colab():
        from google.colab.output import serve_kernel_port_as_iframe  # type: ignore
        serve_kernel_port_as_iframe(port, path="/", height=str(height))
        return

    local = f"http://localhost:{port}/"
    service_prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    proxy_path = f"/proxy/{port}/"
    if service_prefix:
        proxy_path = f"{service_prefix}proxy/{port}/"
        if not proxy_path.startswith("/"):
            proxy_path = f"/{proxy_path}"
    proxy = f"（JupyterHub の場合）{proxy_path}"
    print("Web UI:")
    print("  ローカル:", local)
    print("  JupyterHub:", proxy)
    iframe_src = local if not service_prefix else proxy_path
    try:
        from IPython.display import IFrame, display  # type: ignore
        display(IFrame(src=iframe_src, width="100%", height=height))
    except Exception:
        pass
