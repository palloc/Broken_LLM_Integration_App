#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

CONFIG_FILE="$SCRIPT_DIR/tljh_rollout.conf"

REMOTE_HOST=""
SSH_KEY_PATH=""
REMOTE_STAGING_DIR="/tmp/broken-src"
REMOTE_MASTER_DIR="/opt/broken-src"
REMOTE_SKEL_DIR="/etc/skel/student_workspace"
PILOT_HOME_GLOB=""
ROLLOUT_TO_ALL="false"
CONFIGURE_TLJH_START_DIR="true"
TLJH_NOTEBOOK_DIR="~/student_workspace/notebooks"
ENABLE_HOME_UX="true"
WORKSPACE_DIR_NAME="student_workspace"
LEGACY_DIR_NAME="Broken_LLM_Integration_App"
RENAMED_LEGACY_DIR_NAME="no_edit_Broken_LLM_Integration_App"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  bash course/ops/one_shot_update_tljh.sh [--config course/ops/tljh_rollout.conf]

Flow:
  1) 教材をリモートへ転送（/tmp）
  2) /opt/broken-src を更新
  3) /etc/skel/student_workspace を更新
  4) TLJH の開始ディレクトリを student_workspace/notebooks に固定
  5) 既存ユーザーへ段階配布（先行配布 -> 全体配布）
  6) UX調整（home README生成 + Broken_LLM_Integration_App を no_edit_* へ退避）
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

if [[ -z "${REMOTE_HOST:-}" ]]; then
  echo "REMOTE_HOST is required (e.g. ubuntu@203.0.113.10)" >&2
  exit 1
fi
if [[ -z "${SSH_KEY_PATH:-}" ]]; then
  echo "SSH_KEY_PATH is required (e.g. \$HOME/.ssh/your-key.pem)" >&2
  exit 1
fi
if [[ ! -f "$SSH_KEY_PATH" ]]; then
  echo "SSH key not found: $SSH_KEY_PATH" >&2
  exit 1
fi

SSH_OPTS=(-i "$SSH_KEY_PATH" -o StrictHostKeyChecking=accept-new)

echo "[1/4] upload repo to $REMOTE_HOST:$REMOTE_STAGING_DIR"
rsync -avz --delete \
  --exclude '.git/' \
  --exclude '**/__pycache__/' \
  --exclude '**/.ipynb_checkpoints/' \
  --exclude '.env' \
  --exclude 'course/.env' \
  --exclude 'chatapp/backend/.env' \
  --exclude 'course/.runtime/' \
  --exclude 'student_workspace/.runtime/' \
  -e "ssh ${SSH_OPTS[*]}" \
  "$REPO_ROOT/" "$REMOTE_HOST:$REMOTE_STAGING_DIR/"

echo "[2/4] update remote master: $REMOTE_MASTER_DIR"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo mkdir -p '$REMOTE_MASTER_DIR' && sudo rsync -a --delete '$REMOTE_STAGING_DIR/' '$REMOTE_MASTER_DIR/'"

echo "[3/6] update /etc/skel template: $REMOTE_SKEL_DIR"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/install_student_workspace_template.sh' --source '$REMOTE_MASTER_DIR/student_workspace' --target '$REMOTE_SKEL_DIR'"

CONFIGURE_TLJH_START_DIR_NORMALIZED="$(printf '%s' "$CONFIGURE_TLJH_START_DIR" | tr '[:upper:]' '[:lower:]')"
if [[ "$CONFIGURE_TLJH_START_DIR_NORMALIZED" == "true" ]]; then
  echo "[4/6] configure TLJH start directory: $TLJH_NOTEBOOK_DIR"
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/configure_tljh_start_dir.sh' --notebook-dir '$TLJH_NOTEBOOK_DIR'"
else
  echo "[4/6] skip TLJH start directory configuration"
fi

echo "[5/6] staged distribution for existing users"
UX_HOME_GLOB=""
if [[ -n "${PILOT_HOME_GLOB:-}" ]]; then
  PILOT_MATCH_COUNT="$(
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "bash -lc 'shopt -s nullglob; homes=($PILOT_HOME_GLOB); echo \${#homes[@]}'"
  )"
  if [[ "$PILOT_MATCH_COUNT" -gt 0 ]]; then
    echo "  - pilot rollout: $PILOT_HOME_GLOB ($PILOT_MATCH_COUNT users)"
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/distribute_student_workspace.sh' --source '$REMOTE_SKEL_DIR' --home-glob '$PILOT_HOME_GLOB' --overwrite"
    UX_HOME_GLOB="$PILOT_HOME_GLOB"
  else
    echo "  - pilot rollout skipped (no matches): $PILOT_HOME_GLOB"
  fi
else
  echo "  - pilot rollout skipped (PILOT_HOME_GLOB is empty)"
fi

ROLLOUT_TO_ALL_NORMALIZED="$(printf '%s' "$ROLLOUT_TO_ALL" | tr '[:upper:]' '[:lower:]')"
if [[ "$ROLLOUT_TO_ALL_NORMALIZED" == "true" ]]; then
  echo "  - full rollout: /home/jupyter-*"
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/distribute_student_workspace.sh' --source '$REMOTE_SKEL_DIR' --home-glob '/home/jupyter-*' --overwrite"
  UX_HOME_GLOB="/home/jupyter-*"
else
  echo "  - full rollout skipped (ROLLOUT_TO_ALL=false)"
fi

ENABLE_HOME_UX_NORMALIZED="$(printf '%s' "$ENABLE_HOME_UX" | tr '[:upper:]' '[:lower:]')"
if [[ "$ENABLE_HOME_UX_NORMALIZED" == "true" ]]; then
  if [[ -z "$UX_HOME_GLOB" ]]; then
    UX_HOME_GLOB="/home/jupyter-*"
  fi
  echo "[6/6] apply student UX improvements (glob: $UX_HOME_GLOB)"
  ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/improve_student_home_ux.sh' --home-glob '$UX_HOME_GLOB' --workspace-dir-name '$WORKSPACE_DIR_NAME' --legacy-dir-name '$LEGACY_DIR_NAME' --renamed-legacy-dir-name '$RENAMED_LEGACY_DIR_NAME' --include-skel"
else
  echo "[6/6] skip student UX improvements"
fi

echo "done."
