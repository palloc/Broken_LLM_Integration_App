#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="/opt/broken-src/student_workspace"
TARGET_DIR="/etc/skel/student_workspace"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  sudo bash course/ops/install_student_workspace_template.sh \
    [--source /opt/broken-src/student_workspace] \
    [--target /etc/skel/student_workspace]
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "source dir not found: $SOURCE_DIR" >&2
  exit 1
fi
if [[ ! -d "$SOURCE_DIR/notebooks" || ! -d "$SOURCE_DIR/edit_targets" ]]; then
  echo "source dir is not a valid student_workspace: $SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR"

rsync -a --delete \
  --exclude '.runtime/' \
  --exclude '.env' \
  --exclude '**/.ipynb_checkpoints/' \
  --exclude '**/__pycache__/' \
  "$SOURCE_DIR/" "$TARGET_DIR/"

chmod -R go-w "$TARGET_DIR"
echo "installed template: $SOURCE_DIR -> $TARGET_DIR"
