#!/usr/bin/env bash
# wx-mp-hunter.sh — wx-mp-hunter 顶层 wrapper（薄转发）
# 让 agent 用 `wx-mp-hunter <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/wx-mp-hunter.sh（已是 wx_mp_hunter.ts 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/wx-mp-hunter.sh" "$@"
