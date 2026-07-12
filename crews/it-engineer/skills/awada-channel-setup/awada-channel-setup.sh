#!/usr/bin/env bash
# awada-channel-setup.sh — awada-channel-setup 顶层 wrapper（薄转发）
# 让 agent 用 `awada-channel-setup <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/apply-awada-config.py；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/apply-awada-config.py" "$@"
