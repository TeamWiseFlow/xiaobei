#!/usr/bin/env bash
# exp-invite — 体验群邀请 wrapper
# 让 agent 用 `exp-invite <cmd>` 走 PATH，零路径拼接。
# 转发到 scripts/invite.sh（真业务脚本）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
exec "$SCRIPT_DIR/scripts/invite.sh" "$@"
