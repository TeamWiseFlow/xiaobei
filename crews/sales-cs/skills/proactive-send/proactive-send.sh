#!/usr/bin/env bash
# proactive-send — 主动发送 wrapper
# 让 agent 用 `proactive-send <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/send.mjs（HTTP 网关 transport）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec node "$SCRIPT_DIR/scripts/send.mjs" "$@"
