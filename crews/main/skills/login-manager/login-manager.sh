#!/usr/bin/env bash
# login-manager — 平台登录态管理 wrapper
# Agent 有头打开登录页 + 通知用户登录 + 确认登录完成后，调本脚本导出+验证。
# 直调 scripts/export-and-verify.ts（Node 22+ strip-types）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node --experimental-strip-types "$SCRIPT_DIR/scripts/export-and-verify.ts" "$@"
