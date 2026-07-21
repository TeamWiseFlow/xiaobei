#!/usr/bin/env bash
# wx-mp-hunter — 公众号 Hunter wrapper
# 让 agent 用 `wx-mp-hunter <cmd>` 走 PATH，零路径拼接。
# 直调 scripts/wx_mp_hunter.ts（Node 22+ strip-types）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec node --experimental-strip-types "$SCRIPT_DIR/scripts/wx_mp_hunter.ts" "$@"
