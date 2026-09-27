"""パス解決と環境変数の準備。

既存 `app` パッケージを import する前に必ず `prepare_env()` を呼ぶこと。
`app.settings.Settings` は DB / SECRET / DeepKeep 関連を必須フィールドとして
要求するため、import 時に値が無いと例外になる。ここでダミー値を含む全ての
必須 env を注入し、同時に SQLite 用の DB URL を `HANDSON_DB_URL` として確定する。

受講者が直接編集するファイルは `student_workspace/edit_targets/` に集約し、
起動時に `chatapp/backend/app/` へ同期する。
"""

from __future__ import annotations

import os
import hashlib
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

EDITABLE_FILES = (
    "blacklists.py",
    "filters.py",
    "llm_prompt_templates.py",
)


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    source_backend_dir: Path
    backend_dir: Path          # student_workspace/.runtime/chatapp_backend
    app_dir: Path              # student_workspace/.runtime/chatapp_backend/app（reload 監視対象）
    course_dir: Path           # course
    student_workspace_dir: Path
    notebooks_dir: Path
    edit_targets_dir: Path
    baseline_dir: Path
    runtime_dir: Path
    webui_dir: Path            # course/webui
    sample_data_dir: Path      # assets/sample_data
    secret_src: Path           # chatapp/backend/secret.md
    db_path: Path
    env_file: Path


def _resolve_paths() -> Paths:
    course_dir = Path(__file__).resolve().parents[1]
    repo_root = course_dir.parent
    source_backend_dir = repo_root / "chatapp" / "backend"
    student_workspace_dir = Path(
        os.environ.get("BROKEN_HANDSON_STUDENT_WORKSPACE", str(Path.home() / "student_workspace"))
    ).expanduser()
    runtime_dir = student_workspace_dir / ".runtime"
    edit_targets_dir = student_workspace_dir / "edit_targets"
    return Paths(
        repo_root=repo_root,
        source_backend_dir=source_backend_dir,
        backend_dir=runtime_dir / "chatapp_backend",
        app_dir=(runtime_dir / "chatapp_backend" / "app"),
        course_dir=course_dir,
        student_workspace_dir=student_workspace_dir,
        notebooks_dir=student_workspace_dir / "notebooks",
        edit_targets_dir=edit_targets_dir,
        baseline_dir=runtime_dir / "baseline_edit_targets",
        runtime_dir=runtime_dir,
        webui_dir=course_dir / "webui",
        sample_data_dir=repo_root / "assets" / "sample_data",
        secret_src=source_backend_dir / "secret.md",
        db_path=runtime_dir / "broken_chatbot.db",
        env_file=student_workspace_dir / ".env",
    )


PATHS = _resolve_paths()


def edit_targets_revision() -> str:
    digest = hashlib.sha256()
    for filename in EDITABLE_FILES:
        digest.update((PATHS.app_dir / filename).read_bytes())
    return digest.hexdigest()


def load_env_files(verbose: bool = False) -> list[str]:
    """`.env` を探して環境変数へ読み込む（冪等・既存の環境変数は上書きしない）。

    探索順（先に見つかったものが優先）:
      1. student_workspace/.env
      2. course/.env
      3. リポジトリ直下 /.env
      4. chatapp/backend/.env  … 既存 Docker 構成と共通の設定

    Colab では「シークレット」や `getpass` を併用できるため、`.env` が無くても問題ない。
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        if verbose:
            print("[env] python-dotenv 未インストールのため .env 読み込みをスキップ")
        return []

    candidates = [
        PATHS.env_file,
        PATHS.course_dir / ".env",
        PATHS.repo_root / ".env",
        PATHS.source_backend_dir / ".env",
    ]
    loaded: list[str] = []
    for path in candidates:
        if path.is_file():
            # override=False: 既に設定済みの環境変数（Colab userdata 等）を尊重する。
            load_dotenv(dotenv_path=str(path), override=False)
            loaded.append(str(path))
            if verbose:
                print(f"[env] loaded: {path}")
    if verbose and not loaded:
        print("[env] .env は見つかりませんでした（環境変数 / getpass を使用）")
    return loaded


def prepare_env() -> Paths:
    """`app` を import 可能にし、必須 env を注入する。冪等。"""
    p = PATHS
    p.runtime_dir.mkdir(parents=True, exist_ok=True)
    p.edit_targets_dir.mkdir(parents=True, exist_ok=True)
    p.baseline_dir.mkdir(parents=True, exist_ok=True)
    if not p.backend_dir.exists():
        shutil.copytree(p.source_backend_dir, p.backend_dir)

    # `.env`（LLM API キー等）を最初に読み込む。既存の環境変数は上書きしない。
    load_env_files()

    # `import app...`（既存パッケージ）と `import broken_handson...` の両方を可能にする。
    for path in (str(p.backend_dir), str(p.course_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)

    # SQLite の DB URL を確定（server / seed が共有）。
    os.environ.setdefault("HANDSON_DB_URL", f"sqlite:///{p.db_path}")

    # app.settings.Settings の必須フィールド（ハンズオンでは未使用のダミー可）。
    defaults = {
        "DB_USERNAME": "handson",
        "DB_PASSWORD": "handson",
        "DB_HOST": "localhost",
        "DB_NAME": "broken_chatbot",
        "SECRET_KEY": "handson-not-secret",
        "ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
        "DK_API_URL": "",
        "DK_FIREWALL_ID": "",
        "DK_TOKEN": "",
        # LLM（既定は Bedrock Mantle。`LLM_PROVIDER` で切り替え可能）。
        "LLM_PROVIDER": "bedrock",
        "SQL_CHAIN_VERBOSE": "false",
        "BEDROCK_BASE_URL": "https://bedrock-mantle.us-east-2.api.aws/v1",
        "BEDROCK_MODEL_NAME": "google.gemma-3-27b-it",
        "BEDROCK_MAX_TOKENS": "256",
        "BEDROCK_TEMPERATURE": "0.9",
        "OPENAI_MODEL_NAME": "gpt-4o-mini",
        "OPENAI_MAX_TOKENS": "256",
        "OPENAI_TEMPERATURE": "0.9",
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)

    return p


def patch_sqlite_url() -> None:
    """`app.settings.Settings.DB_DATABASE_URL`（MySQL 固定の property）を
    SQLite URL に差し替える。`app.db_settings` を import する前に呼ぶこと。
    """
    import app.settings as app_settings

    app_settings.Settings.DB_DATABASE_URL = property(  # type: ignore[assignment]
        lambda self: os.environ["HANDSON_DB_URL"]
    )
