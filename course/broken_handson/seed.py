"""SQLite データベースの作成とサンプルデータ投入。

既存 `assets/sample_data/*.csv`（ヘッダ無し・列順は SQLAlchemy モデル定義に一致）を
SQLite に読み込む。`app` パッケージは無改変で再利用する。

通常はサーバ起動前に 1 度だけ実行すればよい（`create_all` は冪等）。
"""

from __future__ import annotations

import csv
from typing import Any

from .config import prepare_env, patch_sqlite_url, PATHS


# (CSV ファイル名, モデルクラス名, 列名の順序) — FK 順に並べる。
_TABLES: list[tuple[str, str, list[str]]] = [
    ("users", "User",
     ["id", "username", "email", "full_name", "hashed_password", "is_active", "is_superuser"]),
    ("user_settings", "UserSettings",
     ["id", "user_id", "theme", "notifications_enabled", "language"]),
    ("chats", "Chat",
     ["id", "name", "created_at", "created_by"]),
    ("memberships", "Membership",
     ["id", "user_id", "chat_id", "role", "joined_at"]),
    ("messages", "Message",
     ["id", "chat_id", "user_id", "content", "timestamp"]),
]


def _coerce(value: str, column) -> Any:
    """CSV の文字列値を、モデルのカラム型に合わせて変換する。"""
    from sqlalchemy import Boolean, Integer

    col_type = type(column.type)
    if value == "" or value is None:
        return None
    if col_type is Boolean:
        return bool(int(value))
    if col_type is Integer:
        return int(value)
    return value


def seed(verbose: bool = True) -> str:
    """テーブルを作成し、サンプルデータを投入する。SQLite ファイルパスを返す。"""
    prepare_env()
    patch_sqlite_url()

    # patch 後に import すること（engine が SQLite で構築される）。
    from app.db_settings import engine, Base, SessionLocal
    from app import db_models

    Base.metadata.create_all(bind=engine)

    # secret.md を実行時 cwd（chatapp/backend）に確実に置く（LLM4Shell の標的ファイル）。
    # 既に同梱されているが、念のため runtime にもコピーしておく。
    if PATHS.secret_src.exists():
        (PATHS.runtime_dir / "secret.md").write_text(
            PATHS.secret_src.read_text(encoding="utf-8"), encoding="utf-8"
        )

    session = SessionLocal()
    try:
        for filename, model_name, columns in _TABLES:
            csv_path = PATHS.sample_data_dir / f"{filename}.csv"
            if not csv_path.exists():
                if verbose:
                    print(f"[seed] skip (not found): {csv_path}")
                continue

            model = getattr(db_models, model_name)
            # 冪等性: 既存行を消してから投入する。
            session.query(model).delete()

            rows = 0
            with csv_path.open(newline="", encoding="utf-8") as f:
                for record in csv.reader(f):
                    if not record:
                        continue
                    obj = model(**{
                        col: _coerce(val, getattr(model, col).property.columns[0])
                        for col, val in zip(columns, record)
                    })
                    session.add(obj)
                    rows += 1
            session.commit()
            if verbose:
                print(f"[seed] {filename}: {rows} rows")
    finally:
        session.close()

    if verbose:
        print(f"[seed] done -> {PATHS.db_path}")
    return str(PATHS.db_path)


if __name__ == "__main__":
    seed()
