#!/usr/bin/env bash
# wxwork-moments.sh — wxwork-moments 顶层 wrapper（薄转发）
# 让 agent 用 `wxwork-moments <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/post_moments.py；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/post_moments.py" "$@"
