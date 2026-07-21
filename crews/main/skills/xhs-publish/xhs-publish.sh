#!/usr/bin/env bash
# xhs-publish.sh — xhs-publish 顶层 wrapper（薄转发）
# 让 agent 用 `xhs-publish <cmd>` 走 PATH，零路径拼接。
# 子命令 check / login-verify 路由到自管探活 / 导出+验证脚本；其余转发到 publish_xhs.py。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"

case "${1:-}" in
  check)
    shift || true
    exec node --experimental-strip-types "$SCRIPT_DIR/scripts/check-login.ts" "$@"
    ;;
  login-verify)
    shift || true
    exec node --experimental-strip-types "$SCRIPT_DIR/scripts/login-and-verify.ts" "$@"
    ;;
esac

exec python3 "$SCRIPT_DIR/scripts/publish_xhs.py" "$@"
