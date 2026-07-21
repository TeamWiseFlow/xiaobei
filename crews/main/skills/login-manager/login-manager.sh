#!/usr/bin/env bash
# login-manager — 平台登录态管理 wrapper
# Agent 有头打开登录页 + 通知用户登录 + 确认登录完成后，调本脚本导出+验证。
# 直调 scripts/export-and-verify.ts（Node 22+ strip-types）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec node --experimental-strip-types "$SCRIPT_DIR/scripts/export-and-verify.ts" "$@"
