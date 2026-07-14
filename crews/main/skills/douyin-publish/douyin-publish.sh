#!/usr/bin/env bash
# douyin-publish — 抖音发布 wrapper
# 让 agent 用 `douyin-publish <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/publish_douyin.py（Python 3 stdlib + camoufox-cli）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/publish_douyin.py" "$@"
