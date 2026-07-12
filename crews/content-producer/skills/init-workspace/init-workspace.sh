#!/usr/bin/env bash
# init-workspace.sh — init-workspace 顶层 wrapper（薄转发）
# 让 agent 用 `init-workspace <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/init.sh；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/init.sh" "$@"
