#!/usr/bin/env bash
# exp-invite — 体验群邀请 wrapper
# 让 agent 用 `exp-invite <cmd>` 走 PATH，零路径拼接。
# 转发到 scripts/invite.sh（真业务脚本）。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/scripts/invite.sh" "$@"
