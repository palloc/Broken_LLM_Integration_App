"""起動・表示ヘルパ（Colab / JupyterHub / ローカル Jupyter 共通）。

典型的な使い方（ノートブック）::

    from broken_handson import launcher
    launcher.seed()                 # SQLite 作成 + サンプルデータ投入（初回のみ）
    proc = launcher.start()         # uvicorn を --reload 付きで起動
    launcher.show()                 # Colab は iframe、それ以外は URL を表示

防御ファイル（blacklists.py / filters.py / llm_prompt_templates.py）を編集すると
`--reload` により自動でサーバへ反映される。停止は ``launcher.stop(proc)``。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
import urllib.request

from .config import prepare_env, PATHS

DEFAULT_PORT = 8000


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
    from .seed import seed as _seed
    return _seed(verbose=verbose)


# ── サーバ起動 ───────────────────────────────────────────────────────────────
def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PATHS.course_dir), str(PATHS.backend_dir), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return env


def start(port: int = DEFAULT_PORT, reload: bool = True, wait: bool = True) -> subprocess.Popen:
    """uvicorn を別プロセスで起動する。プロセスハンドルを返す。"""
    prepare_env()
    cmd = [
        sys.executable, "-m", "uvicorn", "broken_handson.server:app",
        "--host", "0.0.0.0", "--port", str(port),
    ]
    if reload:
        cmd += ["--reload", "--reload-dir", str(PATHS.app_dir)]

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
    proxy = f"（JupyterHub の場合）/proxy/{port}/ または /user/<name>/proxy/{port}/"
    print("Web UI:")
    print("  ローカル:", local)
    print("  JupyterHub:", proxy)
    try:
        from IPython.display import IFrame, display  # type: ignore
        display(IFrame(src=local, width="100%", height=height))
    except Exception:
        pass
