#!/usr/bin/env bash
# wx-mp-engagement — 公众号 engagement 抓取 wrapper
# 让 agent 用 `wx-mp-engagement <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/fetch_engagement.py（Python 3 stdlib + camoufox-cli）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/fetch_engagement.py" "$@"
