#!/usr/bin/env bash
# xhs-content-ops.sh — xhs-content-ops 顶层 wrapper（薄转发）
# 让 agent 用 `xhs-content-ops <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/fetch_note_content.sh（已是 fetch_note_content.ts 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/fetch_note_content.sh" "$@"
