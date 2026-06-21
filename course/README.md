# Broken Chatbot ハンズオン e-learning 講座

LLM アプリケーション固有の脆弱性 — **Prompt Leaking / P2SQL Injection / LLM4Shell** — を、
実際に動く脆弱なチャットボットで「攻撃 → 防御実装 → 再検証」する体験型の講座です。

Google Colab / JupyterHub / ローカル Jupyter のいずれでも、**Docker 不要**・notebook の
セルだけで完結するように作られています（既存の `chatapp/` Docker 構成はそのまま温存）。

---

## 📚 講座の流れ（ノートブック）

| ノートブック | 内容 |
|---|---|
| `notebooks/00_setup.ipynb` | 環境構築・動作確認（最初に実行） |
| `notebooks/10_prompt_leaking.ipynb` | システムプロンプト／API キーの窃取と防御 |
| `notebooks/20_p2sql.ipynb` | DB からのデータ窃取・改ざんと防御 |
| `notebooks/30_llm4shell.ipynb` | リモートコード実行（RCE）と防御 |

各脆弱性は **Lv.1 ガードなし → Lv.2 入出力フィルタ → Lv.3 プロンプトハードナー** の
3 段階で、攻撃の成功と防御の効果を段階的に体験します。

> **Colab のヒント**: Colab はノートブックごとに別ランタイムです。各ノートブックは
> 冒頭のセットアップセル（クローン／インストール／キー設定／DB 投入）を含み、単体で完結します。

---

## 🚀 使い方（最短手順）

### Google Colab（推奨・最優先サポート）
1. 対象ノートブック（例: `notebooks/00_setup.ipynb`）を Colab で開く。
2. API キーを設定（どちらか）:
   - Colab の「シークレット」に `OPENAI_API_KEY` を登録（鍵アイコン）、または
   - `course/.env` を作成して記載（下記「`.env` で設定する」を参照）。
3. セルを上から順に実行。`launcher.show()` でチャット UI が iframe 表示されます。

### ローカル Jupyter
```bash
cd Broken_LLM_Integration_App
pip install -r course/requirements.txt
pip install jupyterlab "lark==1.1.9"   # ローカル実行用（Colab には不要）
cp course/.env.example course/.env   # OPENAI_API_KEY を編集
jupyter lab   # course/notebooks/ を開いて上から実行
```
`launcher.show()` は `http://localhost:8000/` を案内します。

> **メモ**: `jupyter lab` 実行時に `pyenv: jupyter: command not found` が出る場合は
> JupyterLab が未インストールです。上記の `pip install jupyterlab` を実行してください。
> JupyterLab は `lark>=1.2.2` を間接的に要求しますが、防御で使う `nemoguardrails` は
> `lark~=1.1.7` が必要です。`lark==1.1.9` を明示インストールすれば両方とも動作します
> （pip が依存競合の警告を出しますが実害はありません）。Python は **3.12 系**を使ってください。

### JupyterHub
`jupyter-server-proxy` 経由で `/proxy/8000/` にアクセスします（環境により
`/user/<name>/proxy/8000/`）。`launcher.show()` が URL を表示します。

---

## 🔑 `.env` で API キーを設定する

`course/.env` に書いた値は notebook 実行時に自動で読み込まれます（`python-dotenv`）。

```bash
cp course/.env.example course/.env
```

`course/.env` の例:
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_MODEL_NAME=gpt-4o-mini
# Ollama を使う場合:
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL_NAME=llama3.2
```

ノートブックの LLM 設定セルは `launcher.configure_llm()` を呼び、次の優先順位で
キーを解決します（先に見つかったものを使用）:

1. `course/.env` ／既存の環境変数
2. Colab の「シークレット」
3. `getpass` による対話入力

> `course/.env` は `.gitignore` 済みのためコミットされません。探索先は
> `course/.env` → リポジトリ直下 `.env` → `chatapp/backend/.env` の順です。

---

## 🧩 仕組み（アーキテクチャ）

```
notebook (Colab/Jupyter)
  └─ broken_handson.launcher.start()
       └─ uvicorn broken_handson.server:app  (--reload)
            ├─ 既存 chatapp/backend/app  ← 無改変で import（攻撃/防御の本体）
            ├─ DB: MySQL → SQLite に差し替え（course/.runtime/broken_chatbot.db）
            ├─ 認証: JWT/BASIC をバイパス（dependency_overrides）
            └─ Web UI: course/webui/ を同一オリジンで配信（現行デザイン移植）
```

- `broken_handson/config.py` … パス解決・`.env` 読込・必須 env 注入・SQLite URL への monkeypatch
- `broken_handson/seed.py` … `assets/sample_data/*.csv` を SQLite へ投入
- `broken_handson/server.py` … 既存 `app.main` を import し、認証バイパス＋UI 配信
- `broken_handson/launcher.py` … 起動・表示・停止・LLM 設定（`configure_llm`）のヘルパ
- `webui/index.html` … 軽量チャット UI（同一オリジン・相対パス fetch）

### 防御の編集 → 自動反映
受講者が編集する「防御コード」は **本物のアプリのファイル** です。

- `chatapp/backend/app/blacklists.py` … 正規表現ブラックリスト（Lv.2 の主役）
- `chatapp/backend/app/filters.py` … 入出力フィルタ本体
- `chatapp/backend/app/llm_prompt_templates.py` … 防御プロンプト（Lv.3）

これらを保存すると `uvicorn --reload` がサーバを自動再起動し、変更が即反映されます。
各演習ノートブックには「現状表示」セルと「解答例（ファイル上書き）」セルがあります。

---

## 🔌 LLM プロバイダ

OpenAI を主、Ollama を選択可（既存の `LLM_PROVIDER` 抽象を流用）。
推奨は `course/.env` での設定です（上記「`.env` で API キーを設定する」を参照）。

ノートブック内では `.env` を読み込んで自動解決します:
```python
from broken_handson import launcher
launcher.configure_llm()   # .env → 環境変数 → Colab シークレット → 対話入力
```

コードから明示的に指定することもできます:
```python
launcher.use_openai(api_key, model="gpt-4o-mini")                     # OpenAI
launcher.use_ollama(base_url="http://host:11434", model="llama3.2")  # Ollama
```

---

## ⚠️ 安全に関する注意

- 本教材は **意図的に脆弱** です。**インターネットに公開しないでください**。
- **LLM4Shell は実際にコードを実行（RCE）** します。**使い捨ての Colab ランタイム**での
  実行を強く推奨します。共有 JupyterHub や個人 PC では自分・他者の環境に影響し得ます。
- DB は SQLite（`course/.runtime/`、git 管理外）に隔離され、サンプルデータのみを含みます。

---

## 🛠 トラブルシュート

- **`OPENAI_API_KEY` エラー**: キー未設定。`course/.env` に記載するか、Colab シークレット／`getpass` で設定。
- **UI が表示されない**: 各ノートブックの `ask("...mode...", "...")` ヘルパで API 直接確認。
- **編集が反映されない**: `--reload` 監視対象は `chatapp/backend/app/`。保存後に数秒待つ。
- **ポート競合**: `launcher.start(port=8001)` のように変更。
