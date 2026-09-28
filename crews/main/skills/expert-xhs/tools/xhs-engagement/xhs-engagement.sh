#!/usr/bin/env bash
# xhs-engagement — 小红书 creator 后台互动数抓取 wrapper
# 让 agent 用 `xhs-engagement <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/xhs_engagement.py（Creator HTTP 会话）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/xhs_engagement.py" "$@"
