#!/usr/bin/env bash
# wx-mp-engagement — 公众号 engagement 抓取 wrapper
# 让 agent 用 `wx-mp-engagement <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/fetch_engagement.py（Python 3 stdlib + camoufox-cli）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/fetch_engagement.py" "$@"
