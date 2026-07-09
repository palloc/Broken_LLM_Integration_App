#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="/etc/skel/student_workspace"
USER_NAME=""
HOME_DIR=""
RESET_RUNTIME=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      USER_NAME="$2"
      shift 2
      ;;
    --home)
      HOME_DIR="$2"
      shift 2
      ;;
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --reset-runtime)
      RESET_RUNTIME=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  # ユーザー名から復旧
  sudo bash course/ops/reset_student_workspace_for_user.sh --user jupyter-foo

  # ホームディレクトリを直接指定して復旧
  sudo bash course/ops/reset_student_workspace_for_user.sh --home /home/jupyter-foo

  # runtime も削除して復旧
  sudo bash course/ops/reset_student_workspace_for_user.sh --user jupyter-foo --reset-runtime
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$USER_NAME" && -z "$HOME_DIR" ]]; then
  echo "either --user or --home is required" >&2
  exit 1
fi
if [[ -n "$USER_NAME" && -n "$HOME_DIR" ]]; then
  echo "use only one of --user or --home" >&2
  exit 1
fi
if [[ ! -d "$SOURCE_DIR/notebooks" || ! -d "$SOURCE_DIR/edit_targets" ]]; then
  echo "invalid source template: $SOURCE_DIR" >&2
  exit 1
fi

if [[ -n "$USER_NAME" ]]; then
  HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6 || true)"
  if [[ -z "$HOME_DIR" ]]; then
    echo "user not found: $USER_NAME" >&2
    exit 1
  fi
fi

WORKSPACE_DIR="$HOME_DIR/student_workspace"
if [[ ! -d "$WORKSPACE_DIR" ]]; then
  echo "student_workspace not found: $WORKSPACE_DIR" >&2
  exit 1
fi

mkdir -p "$WORKSPACE_DIR/notebooks" "$WORKSPACE_DIR/edit_targets"
rsync -a --delete "$SOURCE_DIR/notebooks/" "$WORKSPACE_DIR/notebooks/"
rsync -a --delete "$SOURCE_DIR/edit_targets/" "$WORKSPACE_DIR/edit_targets/"

if [[ $RESET_RUNTIME -eq 1 ]]; then
  rm -rf "$WORKSPACE_DIR/.runtime"
  echo "runtime removed: $WORKSPACE_DIR/.runtime"
fi

owner="$(stat -c '%u:%g' "$HOME_DIR")"
chown -R "$owner" "$WORKSPACE_DIR/notebooks" "$WORKSPACE_DIR/edit_targets"
if [[ -d "$WORKSPACE_DIR/.runtime" ]]; then
  chown -R "$owner" "$WORKSPACE_DIR/.runtime"
fi

echo "reset completed: $WORKSPACE_DIR"
