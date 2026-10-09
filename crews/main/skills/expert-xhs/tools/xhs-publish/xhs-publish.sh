#!/usr/bin/env bash
# xhs-publish — Creator HTTP publish and session management.
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
case "${1:-}" in
  login|login-confirm|check)
    exec python3 "$SCRIPT_DIR/scripts/creator_local_cli.py" "$@"
    ;;
esac
exec python3 "$SCRIPT_DIR/scripts/publish_xhs.py" "$@"
