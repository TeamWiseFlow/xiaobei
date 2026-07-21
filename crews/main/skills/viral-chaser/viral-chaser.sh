#!/usr/bin/env bash
# viral-chaser.sh — viral-chaser 顶层 wrapper（薄转发）
# 让 agent 用 `viral-chaser <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/viral_chaser.sh（已是 viral_chaser.ts 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec "$SCRIPT_DIR/scripts/viral_chaser.sh" "$@"
