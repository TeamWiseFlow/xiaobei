#!/usr/bin/env bash
# design-system-picker.sh — design-system-picker 顶层 wrapper（薄转发）
# 让 agent 用 `design-system-picker <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/pick.sh；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec "$SCRIPT_DIR/scripts/pick.sh" "$@"
