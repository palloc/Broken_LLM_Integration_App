"""パス解決と環境変数の準備。

既存 `app` パッケージを import する前に必ず `prepare_env()` を呼ぶこと。
`app.settings.Settings` は DB / SECRET / DeepKeep 関連を必須フィールドとして
要求するため、import 時に値が無いと例外になる。ここでダミー値を含む全ての
必須 env を注入し、同時に SQLite 用の DB URL を `HANDSON_DB_URL` として確定する。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    backend_dir: Path          # chatapp/backend   … `app` パッケージの親
    app_dir: Path              # chatapp/backend/app（reload 監視対象）
    course_dir: Path           # course
    runtime_dir: Path          # course/.runtime（SQLite / コピーした secret.md 等）
    webui_dir: Path            # course/webui
    sample_data_dir: Path      # assets/sample_data
    secret_src: Path           # chatapp/backend/secret.md
    db_path: Path              # course/.runtime/broken_chatbot.db
    env_file: Path             # course/.env（受講者が OPENAI_API_KEY 等を記載）


def _resolve_paths() -> Paths:
    course_dir = Path(__file__).resolve().parents[1]
    repo_root = course_dir.parent
    backend_dir = repo_root / "chatapp" / "backend"
    runtime_dir = course_dir / ".runtime"
    return Paths(
        repo_root=repo_root,
        backend_dir=backend_dir,
        app_dir=backend_dir / "app",
        course_dir=course_dir,
        runtime_dir=runtime_dir,
        webui_dir=course_dir / "webui",
        sample_data_dir=repo_root / "assets" / "sample_data",
        secret_src=backend_dir / "secret.md",
        db_path=runtime_dir / "broken_chatbot.db",
        env_file=course_dir / ".env",
    )


PATHS = _resolve_paths()


def load_env_files(verbose: bool = False) -> list[str]:
    """`.env` を探して環境変数へ読み込む（冪等・既存の環境変数は上書きしない）。

    探索順（先に見つかったものが優先）:
      1. course/.env           … 本講座用（推奨）
      2. リポジトリ直下 /.env
      3. chatapp/backend/.env  … 既存 Docker 構成と共通の設定

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
        PATHS.repo_root / ".env",
        PATHS.backend_dir / ".env",
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

    # `.env`（OPENAI_API_KEY 等）を最初に読み込む。既存の環境変数は上書きしない。
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
        # LLM（既定は OpenAI。受講者が OPENAI_API_KEY を設定する）。
        "LLM_PROVIDER": "openai",
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
