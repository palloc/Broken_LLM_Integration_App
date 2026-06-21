"""ハンズオン用 FastAPI アプリ。

既存 `app.main:app` を無改変で読み込み、次の 2 点だけを上書きする:

1. 認証バイパス … `get_current_active_user` 依存を差し替え、JWT/BASIC 無しで全
   エンドポイントにアクセスできるようにする（ハンズオンの導線簡略化）。
2. Web UI 配信 … 現行 React デザインを移植した軽量 UI を同一オリジンで配信する。

uvicorn からは `broken_handson.server:app` として起動する。
"""

from __future__ import annotations

from types import SimpleNamespace

from .config import prepare_env, patch_sqlite_url, PATHS

# ── 1) 既存 app を import する前の下準備 ──────────────────────────────────────
prepare_env()
patch_sqlite_url()

# patch 後に import（engine が SQLite で構築される）。
from app.main import app as app          # noqa: E402  既存の FastAPI インスタンス
from app.auth import get_current_active_user  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse   # noqa: E402


# ── 2) 認証バイパス ──────────────────────────────────────────────────────────
def _handson_user() -> SimpleNamespace:
    """エンドポイントは値を使わないため、ダミーの「ログイン済みユーザ」を返す。"""
    return SimpleNamespace(
        id=0,
        username="handson",
        email="handson@example.com",
        full_name="Handson User",
        is_active=True,
        is_superuser=True,
    )


app.dependency_overrides[get_current_active_user] = _handson_user


# ── 3) Web UI 配信 ──────────────────────────────────────────────────────────
_assets_dir = PATHS.webui_dir / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/", include_in_schema=False)
def _index() -> FileResponse:
    return FileResponse(str(PATHS.webui_dir / "index.html"))
