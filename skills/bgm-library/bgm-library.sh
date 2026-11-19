#!/usr/bin/env bash
# bgm-library.sh — bgm-library 顶层 wrapper（薄转发）
# 让 agent 用 `bgm-library <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/bgm.js；wrapper 自身只是 exec 转发，不改语义。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
# ccMixter 的旧 PHP API 会把整个 JSON 结果回显进 X-JSON 响应头（limit=10 时约 20KB），
# 超过 Node 默认 16KB 头部上限导致 HPE_HEADER_OVERFLOW（确定性错误，重试无效）。
# 仅对本 CLI 进程放宽到 128KB，不影响 gateway 或其他进程。
exec node --max-http-header-size=131072 "$SCRIPT_DIR/scripts/bgm.js" "$@"
