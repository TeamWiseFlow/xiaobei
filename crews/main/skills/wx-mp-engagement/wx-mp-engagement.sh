#!/usr/bin/env bash
# wx-mp-engagement.sh — wx-mp-engagement 顶层 wrapper（薄转发）
# 让 agent 用 `wx-mp-engagement <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/wx-mp-engagement.sh（已是 fetch_engagement.py 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/wx-mp-engagement.sh" "$@"
