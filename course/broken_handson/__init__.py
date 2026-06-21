"""Broken Chatbot ハンズオン用のネイティブ起動レイヤ。

既存の `chatapp/backend/app`（Docker 用 FastAPI アプリ）を一切改変せずに
import し、以下を行う薄いラッパを提供する:

- DB を MySQL から SQLite に差し替え（`config.prepare_env`）
- JWT / BASIC 認証をバイパス（`server`）
- 現行 React デザインを移植した軽量 Web UI を同一オリジンで配信（`server`）
- Colab / JupyterHub / ローカル Jupyter からの起動・表示ヘルパ（`launcher`）
"""

from .config import prepare_env, PATHS  # noqa: F401
