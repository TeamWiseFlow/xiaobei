#!/usr/bin/env bash
# twitter-interact.sh — twitter-interact 顶层 wrapper（薄转发）
# 让 agent 用 `twitter-interact <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/twitter_interact.sh（已是 twitter_interact.py 的薄转发）；
# wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec "$SCRIPT_DIR/scripts/twitter_interact.sh" "$@"
