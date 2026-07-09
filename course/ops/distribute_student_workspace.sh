#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="/etc/skel/student_workspace"
HOME_GLOB="/home/jupyter-*"
DEST_BASENAME="student_workspace"
OVERWRITE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --home-glob)
      HOME_GLOB="$2"
      shift 2
      ;;
    --dest-basename)
      DEST_BASENAME="$2"
      shift 2
      ;;
    --overwrite)
      OVERWRITE=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  # 未配布ユーザーへ配布（既存はスキップ）
  sudo bash course/ops/distribute_student_workspace.sh

  # 既存ユーザーにも上書き配布
  sudo bash course/ops/distribute_student_workspace.sh --overwrite
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

shopt -s nullglob
homes=($HOME_GLOB)
shopt -u nullglob

if [[ ${#homes[@]} -eq 0 ]]; then
  echo "no target homes matched: $HOME_GLOB" >&2
  exit 1
fi

for home in "${homes[@]}"; do
  [[ -d "$home" ]] || continue
  dest="$home/$DEST_BASENAME"
  owner="$(stat -c '%u:%g' "$home")"

  if [[ -d "$dest" && $OVERWRITE -eq 0 ]]; then
    echo "skip (already exists): $dest"
    continue
  fi

  mkdir -p "$dest"
  rsync -a --delete \
    --exclude '.runtime/' \
    --exclude '.env' \
    --exclude '**/.ipynb_checkpoints/' \
    --exclude '**/__pycache__/' \
    "$SOURCE_DIR/" "$dest/"
  chown -R "$owner" "$dest"
  echo "deployed: $dest"
done
