#!/usr/bin/env bash
# douyin-publish.sh — douyin-publish 顶层 wrapper（薄转发）
# 让 agent 用 `douyin-publish <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/publish_douyin.sh（已是 publish_douyin.py 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/publish_douyin.sh" "$@"
