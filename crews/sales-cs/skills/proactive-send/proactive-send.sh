#!/usr/bin/env bash
# proactive-send — 主动发送 wrapper
# 让 agent 用 `proactive-send <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/send.mjs（HTTP 网关 transport）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/scripts/send.mjs" "$@"
