#!/usr/bin/env bash
# viral-chaser.sh — viral-chaser 顶层 wrapper（薄转发）
# 让 agent 用 `viral-chaser <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/viral_chaser.sh（已是 viral_chaser.ts 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/viral_chaser.sh" "$@"
