# EC2 (Ubuntu) + The Littlest JupyterHub で Broken Chatbot ハンズオン演習環境を構築する

本書は、1 台の EC2 (Ubuntu) 上に **The Littlest JupyterHub (TLJH)** を立て、
`student_workspace/notebooks/` の演習を複数の受講者に提供するためのデプロイ手順です。

> ⚠️ **この教材は意図的に脆弱です。インターネットに公開しないでください。**
> Security Group は受講者の固定 IP / VPN からのみに限定してください（[セキュリティ](#9-セキュリティ必読) 参照）。

---

## 0. 構成サマリ（今回の方針）

| 項目 | 採用 |
|---|---|
| JupyterHub | The Littlest JupyterHub (TLJH) を単一 EC2 に直接インストール |
| 規模 / インスタンス | 〜5 名同時 / `t3.large`（2 vCPU / 8 GB）|
| OS | **Ubuntu 24.04 LTS**（Python 3.12 が標準搭載）|
| 認証 | FirstUseAuthenticator（TLJH 既定・初回ログイン時に各自パスワード設定。自己登録のため `create_users true` と `allow_all true` を設定）|
| LLM | 共通 Bedrock Mantle API キー 1 つをシステム全体に注入（受講者は設定不要）|
| 教材配布 | ローカルのこのリポジトリを EC2 へ rsync → `/etc/skel` に配置 → 新規ユーザー作成時に各ホームへ自動コピー（GitHub 非経由）|
| 演習用 Python | TLJH とは別に **Python 3.12 の専用カーネル env** を作成（依存衝突回避）|

### アーキテクチャ

```
受講者ブラウザ ──HTTPS/HTTP──> EC2:80/443 (Traefik)
                                   └─ JupyterHub (TLJH user env: /opt/tljh/user)
                                        ├─ jupyter-server-proxy  ← /user/<name>/proxy/<port>/ を提供
                                        └─ 単一ユーザーサーバ（各 Unix ユーザー）
                                             └─ Notebook カーネル: broken312 (Python 3.12, /opt/broken/venv)
                                                  └─ launcher.start() が uvicorn を起動（空きポート自動選択）
                                                       └─ 既存 chatapp/backend/app（攻撃/防御の本体・無改変 import）
教材コピー: 各ユーザー ~/student_workspace/（防御 .py と SQLite を個別に編集）
```

なぜ専用カーネル env を分けるのか:
`nemoguardrails`（防御 Lv で使用）は `lark~=1.1.7` を要求しますが、JupyterLab は
`lark>=1.2.2` を要求します。TLJH の user 環境には JupyterLab が含まれるため、そこへ
講座依存を入れると衝突します。**講座依存を独立 env に隔離**することで Hub 本体を汚さず、
Python 3.12 要件も満たせます。

---

## 1. EC2 インスタンスの用意

1. **AMI**: Ubuntu Server 24.04 LTS (x86_64)
2. **インスタンスタイプ**: `t3.large`（2 vCPU / 8 GB）。同時 6 名以上なら `t3.xlarge` 以上。
3. **ストレージ**: gp3 30 GB 以上（依存パッケージが数 GB）。
4. **ネットワーク / Security Group（重要）**:
   | 用途 | ポート | ソース |
   |---|---|---|
   | SSH | 22 | 管理者の固定 IP のみ |
   | HTTP | 80 | **受講者の固定 IP / VPN のみ**（全公開禁止）|
   | HTTPS | 443 | 同上（HTTPS を使う場合）|
   - uvicorn が使う 8000 番台は **SG で開けない**（proxy 経由でのみアクセス）。
5. **Elastic IP** を割り当て（再起動で IP が変わらないように）。
6. キーペアで SSH 接続できることを確認:
   ```bash
   ssh -i <your-key.pem> ubuntu@<ELASTIC_IP>
   ```

---

## 2. TLJH のインストール

EC2 に SSH し、管理者ユーザーを指定してブートストラップを実行します（`<ADMIN>` は管理者名）。

```bash
sudo apt-get update
curl -fsSL https://tljh.jupyter.org/bootstrap.py \
  | sudo python3 - \
      --admin <ADMIN>:<ADMIN_PASSWORD> \
      --show-progress-page
```

- 進捗は `http://<ELASTIC_IP>/index.html` で確認できます。
- 完了後 `http://<ELASTIC_IP>/` にアクセスし、`<ADMIN>` / `<ADMIN_PASSWORD>` でログインできれば成功です。
- 認証は TLJH 既定の **FirstUseAuthenticator**。受講者は初回ログイン時に入力したパスワードが
  そのまま登録されます（事前のアカウント作成は不要）。

> 補足: パスワードを後から変えたい / 管理者を追加したい場合は
> `sudo tljh-config ...` ではなく、JupyterHub の Admin パネル、または FirstUseAuthenticator の
> 仕様（初回入力パスワードを保存）に従います。

### 2-1. 受講者の自己登録（自動アカウント作成）を許可する【重要】

TLJH の既定では、受講者が新しいユーザー名で初回ログインしても
**「Invalid username or password」となり、アカウントが作成されません**（管理者だけはログインできます）。
これは次の 2 つの既定値が原因です。両方を変更する必要があります。

1. **`create_users: false`**（TLJH 既定）… FirstUseAuthenticator が「事前登録済みユーザーしか
   受け付けない」モードになっており、新しいユーザー名を受理しません。
2. **`allow_all: false`**（JupyterHub 5.0 以降）… 管理者を指定すると `allowed_users` が空でなくなり、
   許可リストに無いユーザーは認可されません。

受講者が自分でユーザー名・パスワードを決めて利用できるよう、両方を許可します。

```bash
# 新しいユーザー名を初回ログインで受理（自己登録を有効化）
sudo tljh-config set auth.FirstUseAuthenticator.create_users true
# 許可リストに無いユーザーも利用可に（JupyterHub 5 の認可）
sudo tljh-config set auth.FirstUseAuthenticator.allow_all true
sudo tljh-config reload
```

- 設定後、シークレットウィンドウで **新しいユーザー名＋7 文字以上のパスワード**を入力すると、
  その場でアカウントが作成され、JupyterLab が開けば成功です。
- これらは「接続できた人は誰でも自己登録可」という設定です。本教材は意図的に脆弱なため、
  **必ず [手順 9](#9-セキュリティ必読) のとおり Security Group で接続元 IP を限定**してください
  （IP 制限が実質的なアクセス制御になります）。

> うまくいかない場合は `sudo journalctl -u jupyterhub -f` でログを見ながらログインを試します。
> ログイン直前に `Authenticator.db is deprecated` 警告が出る場合は `create_users` が
> まだ `false` です（[手順 11](#11-運用トラブルシュート) 参照）。

---

## 3. jupyter-server-proxy を user 環境へ導入

チャット UI をノートブック内 iframe（`/user/<name>/proxy/<port>/`）で表示するために必要です。
**TLJH の user 環境**（単一ユーザーサーバを動かす env）に入れます。

```bash
sudo /opt/tljh/user/bin/pip install jupyter-server-proxy
sudo tljh-config reload hub
```

---

## 4. 教材リポジトリを EC2 へ転送（GitHub 非経由）

### 4-0. 講師向け「一発更新」コマンド（推奨）

ローカル（このリポジトリ）から、**教材更新 → `/etc/skel` 更新 → 開始ディレクトリ固定 → 既存ユーザー段階配布 → 受講生UX整理**までを
1 コマンドで実行できます。

```bash
cd Broken_LLM_Integration_App
cp course/ops/tljh_rollout.conf.example course/ops/tljh_rollout.conf
```

`course/ops/tljh_rollout.conf` の主な変数:

- `REMOTE_HOST="ubuntu@203.0.113.10"` … 配布先サーバー（IP or DNS）
- `SSH_KEY_PATH="$HOME/.ssh/your-key.pem"` … SSH 秘密鍵
- `PILOT_HOME_GLOB="/home/jupyter-teamA-*"` … 先行配布対象
- `ROLLOUT_TO_ALL="true"` … `true` なら先行配布後に全体配布
- `CONFIGURE_TLJH_START_DIR="true"` … JupyterLab の開始ディレクトリ固定を有効化
- `TLJH_NOTEBOOK_DIR="~/student_workspace/notebooks"` … 開始ディレクトリ
- `ENABLE_HOME_UX="true"` … ホームREADME生成と legacy ディレクトリ整理を有効化
- `RENAMED_LEGACY_DIR_NAME="no_edit_Broken_LLM_Integration_App"` … 退避後の名称

実行:

```bash
bash course/ops/one_shot_update_tljh.sh
```

> 先行配布だけで止めたい場合は、`ROLLOUT_TO_ALL="false"` にします。
> `PILOT_HOME_GLOB` に一致するユーザーが 0 件でも、処理は継続して全体配布へ進みます。
> `ENABLE_HOME_UX="true"` の場合、`course/ops/templates/README_FIRST.md` テンプレートを受講生ホームへ配置し、既存の `Broken_LLM_Integration_App` は `no_edit_*` 名へ退避します。

---

### 4-1. ローカル（このリポジトリのある Mac）から rsync で転送

不要・秘密ファイルを除外してアップロードします（`<ELASTIC_IP>` と鍵を置換）。

```bash
# ローカルのリポジトリ直下で実行
rsync -avz --delete \
  --exclude '.git/' \
  --exclude '**/__pycache__/' \
  --exclude '**/.ipynb_checkpoints/' \
  --exclude '.env' --exclude 'course/.env' \
  --exclude 'chatapp/backend/.env' \
  --exclude 'course/.runtime/' \
  --exclude 'student_workspace/.runtime/' \
  -e "ssh -i <your-key.pem>" \
  ./ ubuntu@<ELASTIC_IP>:/tmp/broken-src/
```

> `.env`（API キー）は配布しません。キーは [手順 6](#6-共通-bedrock-mantle-api-キーをシステムへ注入) で
> システム側に注入します。

### 4-2. EC2 側でマスター配置（`/opt`）と配布元（`/etc/skel`）に展開

```bash
# マスターコピー（カーネル env の依存インストール元・更新の起点）
sudo mkdir -p /opt/broken-src
sudo rsync -a --delete /tmp/broken-src/ /opt/broken-src/

# 新規ユーザーへ配布する雛形（/etc/skel）を運用スクリプトで更新
sudo bash /opt/broken-src/course/ops/install_student_workspace_template.sh \
  --source /opt/broken-src/student_workspace \
  --target /etc/skel/student_workspace
```

これで **新規に作成される受講者ユーザー**のホームに
`~/student_workspace/`（`notebooks/` と `edit_targets/`）が自動コピーされます。
各受講者はこの配下だけを編集し、SQLite も個別に持ちます。

> ⚠️ TLJH ユーザーは「初回ログイン時」に作成されます。**手順 3〜7 を先に済ませてから**
> 受講者にログインしてもらってください。既にログイン済みの受講者がいる場合は
> [手順 8](#8-既にログイン済みの受講者へ後から配布する場合) を使います。

---

## 5. 演習用 Python 3.12 カーネル env を作成

TLJH の user 環境とは別に、講座依存を隔離した venv を作りカーネル登録します。

```bash
sudo apt-get install -y python3.12-venv

# 専用 venv（Ubuntu 24.04 標準の Python 3.12 を使用）
sudo python3.12 -m venv /opt/broken/venv
sudo /opt/broken/venv/bin/pip install --upgrade pip wheel

# 講座依存をインストール（相対 -r ../chatapp/backend/requirements.txt も解決される）
sudo /opt/broken/venv/bin/pip install -r /opt/broken-src/course/requirements.txt

# Jupyter カーネルとして全ユーザーに公開（/usr/local/share/jupyter/kernels に登録）
sudo /opt/broken/venv/bin/pip install ipykernel
sudo /opt/broken/venv/bin/python -m ipykernel install \
  --name broken312 --display-name "Python 3.12 (Broken Chatbot)"
```

- 依存解決には数分かかります。`pip` が `lark` の警告を出しても、この env には
  JupyterLab を入れていないため実害はありません。
- ノートブックの `launcher.start()` は `sys.executable`（= このカーネルの Python）で
  uvicorn を起動するため、講座依存はこの env にあれば十分です。

> 受講者は各ノートブックを開いたら、右上のカーネル選択で
> **「Python 3.12 (Broken Chatbot)」** を選びます（[手順 7](#7-受講者オンボーディング手順) に明記）。

### 5-1. 依存の取りこぼしを検証する【推奨】

`pip` の依存解決の都合で、ごく一部のパッケージ（例: `pydantic-settings`）が
取りこぼされることがあります。受講者に配る前に、**アプリ全体を import して**
不足が無いことを確認します。

```bash
sudo /opt/broken/venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/broken-src/course')
from broken_handson.config import prepare_env, patch_sqlite_url
prepare_env(); patch_sqlite_url()
import app.main
print('FULL IMPORT OK')
"
```

- `FULL IMPORT OK` と表示されれば、`launcher.seed()` / `start()` に必要な依存はすべて揃っています。
- `ModuleNotFoundError: No module named 'xxx'` が出た場合は、その env に不足があります。
  まず全 pin を入れ直してから、再度この検証を実行してください。

  ```bash
  sudo /opt/broken/venv/bin/pip install -r /opt/broken-src/course/requirements.txt
  # 個別に入れる場合の例
  sudo /opt/broken/venv/bin/pip install pydantic-settings==2.7.1
  ```

---

## 6. 共通 Bedrock Mantle API キーをシステムへ注入

単一ユーザーサーバ（とその子プロセス・カーネル）に環境変数を渡すため、TLJH の
config スニペットを追加します。

```bash
sudo mkdir -p /opt/tljh/config/jupyterhub_config.d
sudo tee /opt/tljh/config/jupyterhub_config.d/10-broken-env.py >/dev/null <<'PY'
# 受講者の単一ユーザーサーバへ環境変数を注入する。
c.Spawner.environment = {
  "LLM_PROVIDER": "bedrock",
  "BEDROCK_API_KEY": "xxxxxxxxxxxxxxxxxxxxxxxx",  # ← 実際のキーに置換
  "BEDROCK_BASE_URL": "https://bedrock-mantle.us-east-2.api.aws/v1",
  "BEDROCK_MODEL_NAME": "google.gemma-3-27b-it",
}
PY

# 平文キーを含むため権限を絞る
sudo chmod 600 /opt/tljh/config/jupyterhub_config.d/10-broken-env.py
sudo tljh-config reload hub
```

- これにより `launcher.configure_llm()` は何も尋ねずにキーを解決します（`.env` 不要）。
- Ollama を使う場合は代わりに
  `LLM_PROVIDER=ollama` / `OLLAMA_BASE_URL` / `OLLAMA_MODEL_NAME` を設定します。
- OpenAI を使う場合は `LLM_PROVIDER=openai` / `OPENAI_API_KEY` / `OPENAI_MODEL_NAME` を設定します。

> ⚠️ 共通キーは JupyterHub の環境変数注入でのみ渡し、受講者向けファイルには保存しません。
> 使用後はキーをローテーションし、Bedrock 側の利用量・制限を確認してください。

---

## 7. 受講者オンボーディング手順

> ⚠️ 受講者がログインする前に、[手順 2-1](#2-1-受講者の自己登録自動アカウント作成を許可する重要) の
> `create_users true` / `allow_all true` 設定と、[手順 4](#4-教材リポジトリを-ec2-へ転送github-非経由) までの教材配置を必ず済ませてください。
> 未設定だと「Invalid username or password」でアカウントが作成できません。

受講者へは次を案内します。

1. ブラウザで `http://<ELASTIC_IP>/`（HTTPS 設定済みなら `https://<ドメイン>/`）にアクセス。
2. **ユーザー名**を入力し、**初回ログイン時に任意のパスワードを設定**（7 文字以上。次回以降そのパスワード）。
3. ファイルブラウザで `student_workspace/notebooks/10_prompt_leaking.ipynb` を開く。
4. カーネルは自動的に **「Python 3.12 (Broken Chatbot)」** が選択されます（ノートブックに既定設定済み）。
   もし右上のカーネル名が違う場合や `No module named ...` が出る場合は、右上のカーネル名をクリックして
   **「Python 3.12 (Broken Chatbot)」** を選び直してください。
5. セルを上から順に実行:
   - `launcher.configure_llm()` … 共通キーで自動設定（入力不要）
   - `launcher.seed()` … SQLite 作成＋サンプル投入（初回のみ）
   - `proc = launcher.start()` → `launcher.show()` … サーバ起動＋UI が iframe 表示
6. チャット UI で攻撃を試し、`student_workspace/edit_targets/blacklists.py` などを編集したら
   `launcher.sync_edit_targets()` を実行すると `--reload` で反映。
7. 終了時は `launcher.stop(proc)` を実行。

> 同時実行: `launcher.start()` は**空きポートを自動選択**するため、複数受講者が同時に
> 実行してもポート競合しません。`launcher.show()` と `ask()` は自動的にそのポートを使います。

---

## 8. 既にログイン済みの受講者へ後から配布する場合

`/etc/skel` への配置は「新規ユーザー」にしか効きません。既にホームがあるユーザーには手動配布します。

```bash
# 既存ユーザーへ配布（既に存在する user はスキップ）
sudo bash /opt/broken-src/course/ops/distribute_student_workspace.sh

# 教材更新を全員へ上書き反映する場合
sudo bash /opt/broken-src/course/ops/distribute_student_workspace.sh --overwrite
```

受講者 1 名だけを初期状態へ戻す場合は、次を実行します。

```bash
sudo bash /opt/broken-src/course/ops/reset_student_workspace_for_user.sh --user <jupyter-username>
```

`.runtime` も含めて完全に戻したい場合は `--reset-runtime` を付けます。

---

## 9. セキュリティ（必読）

- **公開禁止**: 意図的に脆弱な教材です。SG で 80/443 を受講者 IP / VPN に限定し、全公開しない。
- **LLM4Shell は実際に RCE** します。TLJH は各受講者を別 Unix ユーザーで動かすため影響は
  原則そのユーザーのホームに限定されますが、次に留意:
  - 共通 Bedrock キーは各ユーザー env から読めます（前述）。
  - uvicorn は **`127.0.0.1`（ループバック）に bind** するため、同一ホスト内の他受講者からは
    到達できません（proxy = 同一ユーザーのサーバ経由のみ）。SG で外部公開もされません。
- **使用後**: インスタンスを停止/終了し、Bedrock API キーをローテーションしてコストと露出を最小化。
- DB は SQLite（`student_workspace/.runtime/`・各ユーザー個別）でサンプルデータのみを含みます。

---

## 10. （任意）HTTPS 化

独自ドメインがある場合、Let's Encrypt を有効化できます。

```bash
sudo tljh-config set https.enabled true
sudo tljh-config set https.letsencrypt.email you@example.com
sudo tljh-config add-item https.letsencrypt.domains <your.domain>
sudo tljh-config reload proxy
```

DNS の A レコードを `<ELASTIC_IP>` に向け、SG で 443 を許可しておきます。

ただし、接続元を受講者 IP に限定していると、認証局からの接続も遮断され、
この自動発行はタイムアウトすることがあります。証明書発行のために教材を全公開せず、
その場合は DNS-01 認証を使用してください。EC2 の標準公開 DNS 名
（`*.compute.amazonaws.com`）は、今回 Let's Encrypt に発行ポリシーで拒否されました。

### DNS 認証での設定記録（2026-09-27）

- 接続先: `https://93nakzia.jpsec.ai/`。A レコードは `3.131.128.117`。
- Certbot は教材・Hub とは独立した `/opt/broken-acme/` に導入。
- DNS TXT レコードを手動で登録し、Let's Encrypt 証明書を発行済み。
- 証明書の有効期限: **2026-12-26 07:40:55 UTC**。
- TLJH の `https.tls.cert` は `/etc/letsencrypt/live/93nakzia.jpsec.ai/fullchain.pem`、
  `https.tls.key` は同ディレクトリの `privkey.pem` を参照。
- 接続に失敗していた `https.letsencrypt` 設定は解除し、接続元制限は維持。
- 変更前の設定は `/var/backups/broken-https-20260927/config.yaml` に退避。

**自動更新は未設定です。** 手動 DNS 認証では、期限前に管理者が新しい TXT 値を登録して
更新する必要があります。2026年11月末までを目安に更新作業を行ってください。
保存した TXT 値を残すだけでは次回更新できません。完全自動化には DNS API 連携または
認証用 DNS の委任が必要です。更新成功後は `sudo tljh-config reload proxy` で反映します。
期限は `sudo /opt/broken-acme/bin/certbot certificates` で確認できます。

新ドメインで証明書検証付きの HTTPS 接続が HTTP 200 を返すことを確認済みです。
Chrome でも最初のコードセルが数秒以内に実行できることを受講者側で確認しました。

---

## 11. 運用・トラブルシュート

- **Hub ログ**: `sudo journalctl -u jupyterhub -f`
- **設定反映**: 設定変更後は `sudo tljh-config reload hub`（proxy 変更時は `reload proxy`）。
- **新規ユーザーが作成できない / 「Invalid username or password」**: 管理者はログインできるのに
  受講者だけ弾かれる場合は、TLJH 既定の `create_users: false` と JupyterHub 5 の `allow_all: false` が
  原因です。ログイン直前に `Authenticator.db is deprecated` 警告が出るのは `create_users` が
  `false` の典型サインです。[手順 2-1](#2-1-受講者の自己登録自動アカウント作成を許可する重要) の
  `create_users true` と `allow_all true` を**両方**設定し、`sudo tljh-config reload` を実行。
- **カーネルが見えない**: 手順 5 の `ipykernel install` を再実行し、Hub をリロード。
- **最初のセルが長時間 `[*]` のまま**: Chrome の Console で
  `ERR_CERT_AUTHORITY_INVALID` と WebSocket 接続失敗が出ていないか確認。
  今回はサーバー起動約6.2秒、カーネル準備約0.78秒、セル実行約0.009秒でしたが、
  証明書エラーでブラウザーからの接続が遮断されていました。
  旧 IP のタブを閉じ、証明書に対応する `https://93nakzia.jpsec.ai/` からログインし直します。
  ブラウザーの証明書検証を無効にしないでください。
- **`ModuleNotFoundError`（例: `No module named 'pydantic_settings'`）**: 多くは
  **カーネルの取り違え**が原因です。ノートブックで `import sys; print(sys.executable)` を実行し、
  `/opt/broken/venv/bin/python` でなければ、右上のカーネルを **「Python 3.12 (Broken Chatbot)」**
  に切り替えてください（再配布後のノートブックは既定でこのカーネルを選びます）。
  カーネルが正しいのに不足する場合は、[手順 5-1](#5-1-依存の取りこぼしを検証する推奨) の検証を実行し、
  `sudo /opt/broken/venv/bin/pip install -r /opt/broken-src/course/requirements.txt` で入れ直してください。
- **`BEDROCK_API_KEY` エラー**: 手順 6 のキー値とファイル権限、`reload hub` を確認。
- **UI が出ない**: `launcher.show()` の出力 URL（`/user/<name>/proxy/<port>/`）を直接開く。
  `jupyter-server-proxy` が user 環境に入っているか（手順 3）を確認。
- **`launcher.start()` が起動しない**: カーネルが「Python 3.12 (Broken Chatbot)」か確認。
- **依存の再インストール**: `sudo /opt/broken/venv/bin/pip install -r /opt/broken-src/course/requirements.txt`
- **新規ユーザーに教材が配布されない**: `install_student_workspace_template.sh` を再実行し、`/etc/skel/student_workspace` の中身を確認。
- **既存ユーザーへ再配布したい**: `distribute_student_workspace.sh`（必要なら `--overwrite`）を実行。
- **受講者が教材を壊した**: `reset_student_workspace_for_user.sh --user <name>` で notebooks/edit_targets を復旧。
- **講師向けに一発更新したい**: `one_shot_update_tljh.sh` を使用し、`tljh_rollout.conf` の `REMOTE_HOST` / `SSH_KEY_PATH` / `PILOT_HOME_GLOB` を設定。
- **受講者が起動後に迷う**: `configure_tljh_start_dir.sh` で `~/student_workspace/notebooks` を開始ディレクトリに固定。
- **`Broken_LLM_Integration_App` を見せたくない**: `improve_student_home_ux.sh` で `no_edit_Broken_LLM_Integration_App` に退避し、`README_FIRST.md` を再生成。
- **コスト管理**: 演習時間外はインスタンスを停止（Elastic IP は維持されます）。

---

## 付録: 本ハンズオン用に行ったソース変更

共有 JupyterHub で**同時実行**と**UI 表示**を成立させるため、以下を変更済みです
（Colab / ローカル実行には後方互換）。

- `course/broken_handson/launcher.py`
  - `start()` が `HANDSON_PORT`（任意）を起点に**空きポートを自動選択**し、選択ポートを記憶。
  - `active_port()` を追加。`show()` / `wait_until_up()` が記憶ポートを使用。
  - `show()` が JupyterHub（`JUPYTERHUB_SERVICE_PREFIX`）検出時に
    `{prefix}proxy/{port}/` の iframe を描画。
  - uvicorn の bind を **`127.0.0.1`（`BIND_HOST`）に限定**し、同一ホスト内の他受講者からの
    到達を遮断（アクセスは proxy / localhost / Colab kernel proxy 経由のみ）。
- `student_workspace/notebooks/*.ipynb`（3 冊を直接編集。生成スクリプトは廃止）
  - `ask()` ヘルパの既定ポートを `launcher.active_port()` に変更。
  - GitHub クローン / Colab 関連の記述を撤廃し、受講者向けの日本語表現に統一。
  - 既定カーネルを **`broken312`（表示名「Python 3.12 (Broken Chatbot)」）** に設定。
    これにより受講者が開いた時点で正しいカーネル（講座依存入りの `/opt/broken/venv`）が選ばれ、
    `ModuleNotFoundError`（カーネル取り違え）を防ぐ。デプロイ手順 5 の `--name broken312` と一致させること。
  - ※以前あった生成スクリプト `_generate.py` は、受講者から見えること・手編集との二重管理を避けるため削除。
    3 冊は各 `.ipynb` を正として直接編集する（共通セルを変える際は 3 ファイルへ手動同期）。
