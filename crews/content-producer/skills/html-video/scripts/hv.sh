#!/usr/bin/env bash
# hv.sh — html-video CLI wrapper for content-producer
# Usage: hv.sh <command> [options]
#   hv.sh doctor
#   hv.sh search-templates --intent "title animation"
#   hv.sh project-create --name "my-video" --aspect "9:16"
#   hv.sh project-set-template <id> --template <template-id>
#   hv.sh project-set-var <id> --key title --value '"Hello"'
#   hv.sh project-render <id> --output /path/to/output.mp4
#   hv.sh project-list
#   hv.sh project-show <id>
#   hv.sh project-delete <id>

set -euo pipefail

# Resolve html-video CLI path
# Priority: env var > workspace-level clone > fail
HV_CLI="${HTML_VIDEO_CLI:-}"

if [ -z "$HV_CLI" ]; then
  # Look for html-video in the wiseflow-pro workspace
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  # Traverse up to find workspace root (contains html-video/)
  SEARCH_DIR="$SCRIPT_DIR"
  for _ in {1..10}; do
    if [ -d "$SEARCH_DIR/html-video/packages/cli/dist" ]; then
      HV_CLI="$SEARCH_DIR/html-video/packages/cli/dist/bin.js"
      break
    fi
    SEARCH_DIR="$(dirname "$SEARCH_DIR")"
  done
fi

if [ -z "$HV_CLI" ] || [ ! -f "$HV_CLI" ]; then
  echo "ERROR: html-video CLI not found. Set HTML_VIDEO_CLI env var or clone html-video to workspace." >&2
  exit 1
fi

# Set CWD to html-video project root (where templates/ and projects/ live)
HV_ROOT="$(dirname "$(dirname "$(dirname "$HV_CLI")")")"

exec node "$HV_CLI" --cwd "$HV_ROOT" "$@"
