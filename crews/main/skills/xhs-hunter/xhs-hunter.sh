#!/usr/bin/env bash
set -euo pipefail
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
SKILL_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec python3 "$SKILL_DIR/scripts/xhs_hunter.py" "$@"
