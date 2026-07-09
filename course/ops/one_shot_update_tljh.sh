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
  4) 既存ユーザーへ段階配布（先行配布 -> 全体配布）
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

echo "[3/4] update /etc/skel template: $REMOTE_SKEL_DIR"
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/install_student_workspace_template.sh' --source '$REMOTE_MASTER_DIR/student_workspace' --target '$REMOTE_SKEL_DIR'"

echo "[4/4] staged distribution for existing users"
if [[ -n "${PILOT_HOME_GLOB:-}" ]]; then
  PILOT_MATCH_COUNT="$(
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "bash -lc 'shopt -s nullglob; homes=($PILOT_HOME_GLOB); echo \${#homes[@]}'"
  )"
  if [[ "$PILOT_MATCH_COUNT" -gt 0 ]]; then
    echo "  - pilot rollout: $PILOT_HOME_GLOB ($PILOT_MATCH_COUNT users)"
    ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "sudo bash '$REMOTE_MASTER_DIR/course/ops/distribute_student_workspace.sh' --source '$REMOTE_SKEL_DIR' --home-glob '$PILOT_HOME_GLOB' --overwrite"
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
else
  echo "  - full rollout skipped (ROLLOUT_TO_ALL=false)"
fi

echo "done."
