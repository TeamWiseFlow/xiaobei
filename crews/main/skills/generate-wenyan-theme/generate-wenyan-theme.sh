#!/usr/bin/env bash
# generate-wenyan-theme.sh — generate-wenyan-theme 顶层 wrapper（薄转发）
# 让 agent 用 `generate-wenyan-theme <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/collect-theme-sources.js；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$SCRIPT_DIR/scripts/collect-theme-sources.js" "$@"
