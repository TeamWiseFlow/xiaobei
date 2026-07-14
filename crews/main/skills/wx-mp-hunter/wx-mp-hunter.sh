#!/usr/bin/env bash
# wx-mp-hunter — 公众号 Hunter wrapper
# 让 agent 用 `wx-mp-hunter <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/wx_mp_hunter.ts（Node 22+ strip-types）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node --experimental-strip-types "$SCRIPT_DIR/scripts/wx_mp_hunter.ts" "$@"
