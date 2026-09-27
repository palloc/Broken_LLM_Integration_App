# Broken Chatbot ハンズオン e-learning 講座

LLM アプリケーション固有の脆弱性 — **Prompt Leaking / P2SQL Injection / LLM4Shell** — を、
実際に動く脆弱なチャットボットで「攻撃 → 防御実装 → 再検証」する体験型の講座です。

Google Colab / JupyterHub / ローカル Jupyter のいずれでも、**Docker 不要**・notebook の
セルだけで完結するように作られています（既存の `chatapp/` Docker 構成はそのまま温存）。

---

## 📚 講座の流れ（ノートブック）

| ノートブック | 内容 |
|---|---|
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
1. 対象ノートブック（例: `notebooks/10_prompt_leaking.ipynb`）を Colab で開く。
2. API キーを設定（どちらか）:
  - Colab の「シークレット」に `BEDROCK_API_KEY` を登録（鍵アイコン）、または
   - `student_workspace/.env` を作成して記載（下記「`.env` で設定する」を参照）。
3. セルを上から順に実行。`launcher.show()` でチャット UI が iframe 表示されます。

### ローカル Jupyter
```bash
cd Broken_LLM_Integration_App
pip install -r course/requirements.txt
pip install jupyterlab "lark==1.1.9"   # ローカル実行用（Colab には不要）
cp course/.env.example student_workspace/.env   # BEDROCK_API_KEY を編集
jupyter lab   # student_workspace/notebooks/ を開いて上から実行
```
`launcher.show()` は `http://localhost:8000/` を案内します。

> **メモ**: `jupyter lab` 実行時に `pyenv: jupyter: command not found` が出る場合は
> JupyterLab が未インストールです。上記の `pip install jupyterlab` を実行してください。
> JupyterLab は `lark>=1.2.2` を間接的に要求しますが、防御で使う `nemoguardrails` は
> `lark~=1.1.7` が必要です。`lark==1.1.9` を明示インストールすれば両方とも動作します
> （pip が依存競合の警告を出しますが実害はありません）。Python は **3.12 系**を使ってください。

### JupyterHub
受講者には `student_workspace/notebooks/` を開始ディレクトリとして提供し、
最初は `10_prompt_leaking.ipynb` から開始します。`launcher.show()` は
`jupyter-server-proxy` 経由の `/user/<name>/proxy/<port>/` を iframe 表示します。

---

## 🔑 `.env` で API キーを設定する

`student_workspace/.env` に書いた値は notebook 実行時に自動で読み込まれます（`python-dotenv`）。

```bash
cp course/.env.example student_workspace/.env
```

`student_workspace/.env` の例（Bedrock Mantle / Gemma 3 4B IT）:
```bash
LLM_PROVIDER=bedrock
BEDROCK_API_KEY=...
BEDROCK_BASE_URL=https://bedrock-mantle.us-east-2.api.aws/v1
BEDROCK_MODEL_NAME=google.gemma-3-4b-it
# OpenAI を使う場合:
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-xxxxxxxx
# OPENAI_MODEL_NAME=gpt-4o-mini
# Ollama を使う場合:
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL_NAME=llama3.2
```

ノートブックの LLM 設定セルは `launcher.configure_llm()` を呼び、次の優先順位で
キーを解決します（先に見つかったものを使用）:

1. `student_workspace/.env` ／既存の環境変数
2. Colab の「シークレット」
3. `getpass` による対話入力

> `student_workspace/.env` は `.gitignore` 済みのためコミットされません。探索先は
> `student_workspace/.env` → `course/.env` → リポジトリ直下 `.env` → `chatapp/backend/.env` の順です。

---

## 🧩 仕組み（アーキテクチャ）

```
notebook (Colab/Jupyter)
  └─ broken_handson.launcher.start()
       └─ uvicorn broken_handson.server:app  (--reload)
            ├─ 既存 chatapp/backend/app  ← 無改変で import（攻撃/防御の本体）
            ├─ DB: MySQL → SQLite に差し替え（student_workspace/.runtime/broken_chatbot.db）
            ├─ 認証: JWT/BASIC をバイパス（dependency_overrides）
            └─ Web UI: course/webui/ を同一オリジンで配信（現行デザイン移植）
```

- `broken_handson/config.py` … パス解決・`.env` 読込・必須 env 注入・SQLite URL への monkeypatch
- `broken_handson/seed.py` … `assets/sample_data/*.csv` を SQLite へ投入
- `broken_handson/server.py` … 既存 `app.main` を import し、認証バイパス＋UI 配信
- `broken_handson/launcher.py` … 起動・表示・停止・LLM 設定（`configure_llm`）のヘルパ
- `webui/index.html` … 軽量チャット UI（同一オリジン・相対パス fetch）

### 防御の編集 → 自動反映
受講者が編集する防御コードは `student_workspace/edit_targets/` に集約します。

- `student_workspace/edit_targets/blacklists.py` … 正規表現ブラックリスト（Lv.2 の主役）
- `student_workspace/edit_targets/filters.py` … 入出力フィルタ本体
- `student_workspace/edit_targets/llm_prompt_templates.py` … 防御プロンプト（Lv.3）

編集後に `launcher.sync_edit_targets()` を実行すると、実行中アプリへ同期され
`uvicorn --reload` により変更が反映されます。既定の `reload=True` で起動したサーバーでは、
読み込み済みの防御ファイルの版を確認してから同期が完了します（最大40秒）。
`reload=False` の場合はファイルコピーのみ行うため、反映にはサーバーの再起動が必要です。各演習ノートブックには
「現状表示」セルと「解答例（ファイル上書き）」セルがあります。

---

## 🔌 LLM プロバイダ

Bedrock Mantle（Gemma 3 27B IT）を既定にし、OpenAI と Ollama も選択できます。
推奨は `student_workspace/.env` での設定です（上記「`.env` で API キーを設定する」を参照）。

ノートブック内では `.env` を読み込んで自動解決します:
```python
from broken_handson import launcher
launcher.configure_llm()   # .env → 環境変数 → Colab シークレット → 対話入力
```

コードから明示的に指定することもできます:
```python
launcher.use_bedrock(api_key, model="google.gemma-3-27b-it")           # Bedrock Mantle
launcher.use_openai(api_key, model="gpt-4o-mini")                     # OpenAI
launcher.use_ollama(base_url="http://host:11434", model="llama3.2")  # Ollama
```

---

## ⚠️ 安全に関する注意

- 本教材は **意図的に脆弱** です。**インターネットに公開しないでください**。
- **LLM4Shell は実際にコードを実行（RCE）** します。**使い捨ての Colab ランタイム**での
  実行を強く推奨します。共有 JupyterHub や個人 PC では自分・他者の環境に影響し得ます。
- DB は SQLite（`student_workspace/.runtime/`、git 管理外）に隔離され、サンプルデータのみを含みます。

---

## 🛠 トラブルシュート

- **`BEDROCK_API_KEY` エラー**: `LLM_PROVIDER=bedrock` のときのキー未設定。`student_workspace/.env` に記載するか、Colab シークレット／`getpass` で設定。
- **`OPENAI_API_KEY` エラー**: `LLM_PROVIDER=openai` のときのキー未設定。`student_workspace/.env` に記載するか、Colab シークレット／`getpass` で設定。
- **UI が表示されない**: 各ノートブックの `ask("...mode...", "...")` ヘルパで API 直接確認。
- **編集が反映されない**: `launcher.sync_edit_targets()` の完了を確認。タイムアウト時はサーバーログを確認し、再起動してください。
- **ポート競合**: `launcher.start(port=8001)` のように変更。

### SQL 演習の出力とログ

コースでは `SQL_CHAIN_VERBOSE=false` を既定値とし、SQL チェーンの内部プロンプト全文の
ログを抑制します。調査時は起動前に `SQL_CHAIN_VERBOSE=true` を設定できます。
スタンドアロンアプリの既定値は従来どおり `true` です。

SQL 教材の `ask()` は、実行した複数行の `SQLQuery:` と DB 由来の `SQLResult:` を保持し、
モデルによる説明 `Answer:` は省きます。改ざん例は読み取り専用接続で `admin` の email を
実行前後に確認します。生成文へのメールアドレスの出現だけでは成功と判定しません。
`launcher.seed()` は改ざん箇所だけでなく演習 DB 全体を初期化します。

### バックエンド更新後に古いエラーが残る場合

生成済みの `PATHS.backend_dir` は初回だけコピーされます。カーネル再起動や
`sync_edit_targets()` だけでは、`llm_db_chain.py` などの更新は反映されません。

1. 起動中のサーバーを `launcher.stop(proc)` で停止します。
2. 同じカーネルで次を実行し、生成済みバックエンドだけを退避します。

```python
from datetime import datetime
from broken_handson.config import PATHS

backend = PATHS.backend_dir
if backend.exists():
  backup = backend.with_name("chatapp_backend.backup-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
  backend.rename(backup)
```

3. `pip install -r course/requirements.txt` で依存関係を更新し、カーネルを再起動します。
4. ノートブックを先頭から実行します。バックエンドが最新ソースから再生成されます。

この退避では `edit_targets/`・SQLite・リセット用 baseline は保持されます。
`launcher.seed()` を実行すると SQLite の演習データは初期化されます。

## 実行検証（2026-09-27）

Python 3.12.9 の使い捨て Linux コンテナーで、受講生用ノートブックを各々新しい
Jupyter カーネルから nbclient で実行しました。実際の Bedrock Mantle API
（`us-east-2` / `google.gemma-3-4b-it`）を使用しています。

| ノートブック | コードセル | 結果 |
|---|---:|---|
| `student_workspace/notebooks/10_prompt_leaking.ipynb` | 13 | 全セル成功 |
| `student_workspace/notebooks/20_p2sql.ipynb` | 14 | 全セル成功 |
| `student_workspace/notebooks/30_llm4shell.ipynb` | 14 | 全セル成功 |

設定・SQLite seed・起動・healthcheck・Web UI の HTML 配信・実 API 応答・解答セルによる
防御更新・更新直後の入力ブロック・reset・停止を確認しました。
SQL/Python の Markdown 外枠の処理、PAL の import 名前空間、SQL の `REFUSE` 処理と
実行結果表示、防御同期の競合を修正しています。

バックエンド pytest は27件、コース pytest は4件成功しました。
旧 Starlette の TestClient と互換性のある `httpx==0.27.2` を使用します。

LLM の攻撃成功率は保証しません。今回も漏えいの拒否や指定と異なる SQL 生成がありました。
SQL 演習では実際の `SQLQuery:` と `SQLResult:` を確認してください。
Colab/TLJH 上の iframe 表示とブラウザー操作は今回の検証対象外です。

### レビュー反映後の再検証

SQL 表示の欠落修正・改ざんの実値判定・コースの冗長ログ抑制を反映後、同じ隔離環境で
`20_p2sql.ipynb` を新規カーネルから再実行し、14コードセルすべて成功しました。
バックエンド29件、コース23件の pytest も成功しています。両配布先の改ざんセルについて、
対象利用者の更新・別利用者の更新・変更なし・実行前から変更済みを SQLite で検証しました。
6冊の形式確認とソース・配布版の全セル一致も確認しています。他の2教材の今回の変更は
本文のみで、API 接続による再実行は SQL 教材に限定しています。
