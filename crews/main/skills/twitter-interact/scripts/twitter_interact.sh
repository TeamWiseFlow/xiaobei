#!/usr/bin/env bash
# twitter_interact.sh — Twitter/X 互动操作 wrapper
#
# 委托给 twitter_interact.py（Python 3 stdlib + camoufox-cli）。
# 用法：twitter_interact.sh <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/twitter_interact.py"

exec python3 "$PY_SCRIPT" "$@"
