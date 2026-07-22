#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

HOME_GLOB="/home/jupyter-*"
WORKSPACE_DIR_NAME="student_workspace"
LEGACY_DIR_NAME="Broken_LLM_Integration_App"
RENAMED_LEGACY_DIR_NAME="no_edit_Broken_LLM_Integration_App"
README_NAME="README_FIRST.md"
README_TEMPLATE="$SCRIPT_DIR/templates/README_FIRST.md"
MOVE_LEGACY_DIR=1
WRITE_HOME_README=1
INCLUDE_SKEL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home-glob)
      HOME_GLOB="$2"
      shift 2
      ;;
    --workspace-dir-name)
      WORKSPACE_DIR_NAME="$2"
      shift 2
      ;;
    --legacy-dir-name)
      LEGACY_DIR_NAME="$2"
      shift 2
      ;;
    --renamed-legacy-dir-name)
      RENAMED_LEGACY_DIR_NAME="$2"
      shift 2
      ;;
    --readme-name)
      README_NAME="$2"
      shift 2
      ;;
    --readme-template)
      README_TEMPLATE="$2"
      shift 2
      ;;
    --no-move-legacy)
      MOVE_LEGACY_DIR=0
      shift
      ;;
    --no-readme)
      WRITE_HOME_README=0
      shift
      ;;
    --include-skel)
      INCLUDE_SKEL=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  sudo bash course/ops/improve_student_home_ux.sh \
    [--home-glob /home/jupyter-*] \
    [--workspace-dir-name student_workspace] \
    [--legacy-dir-name Broken_LLM_Integration_App] \
    [--renamed-legacy-dir-name no_edit_Broken_LLM_Integration_App] \
    [--readme-template /path/to/README_FIRST.md] \
    [--include-skel]
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$WRITE_HOME_README" -eq 1 && ! -f "$README_TEMPLATE" ]]; then
  echo "readme template not found: $README_TEMPLATE" >&2
  exit 1
fi

shopt -s nullglob
targets=($HOME_GLOB)
shopt -u nullglob

if [[ "$INCLUDE_SKEL" -eq 1 && -d "/etc/skel" ]]; then
  targets+=("/etc/skel")
fi

if [[ ${#targets[@]} -eq 0 ]]; then
  echo "no targets matched (glob: $HOME_GLOB)"
  exit 0
fi

for base in "${targets[@]}"; do
  [[ -d "$base" ]] || continue
  owner="$(stat -c '%u:%g' "$base")"
  workspace="$base/$WORKSPACE_DIR_NAME"
  legacy="$base/$LEGACY_DIR_NAME"
  renamed="$base/$RENAMED_LEGACY_DIR_NAME"
  readme="$base/$README_NAME"

  if [[ "$MOVE_LEGACY_DIR" -eq 1 && -d "$legacy" ]]; then
    if [[ -e "$renamed" ]]; then
      echo "skip rename (target exists): $renamed"
    else
      mv "$legacy" "$renamed"
      echo "renamed: $legacy -> $renamed"
    fi
  fi

  if [[ "$WRITE_HOME_README" -eq 1 ]]; then
    cp "$README_TEMPLATE" "$readme"
    chown "$owner" "$readme"
    echo "updated readme: $readme"
  fi

  if [[ -d "$workspace" ]]; then
    chown -R "$owner" "$workspace"
  fi
done
