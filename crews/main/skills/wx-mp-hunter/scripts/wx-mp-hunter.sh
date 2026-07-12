#!/usr/bin/env bash
# wx-mp-hunter — WeChat Official Account Hunter wrapper
#
# Simplifies invocation by wrapping the TypeScript implementation.
# Usage: ./wx-mp-hunter.sh <command> [args...]
#
# Commands:
#   check                                 探活（camoufox open + snapshot 看跳登录页）；exit 0=有效 / 2=失效
#   login                                  无头截 QR 登录第一步（camoufox screenshot /tmp/qr-wx-mp.png）
#   login-confirm [--timeout 120]          确认登录第二步（验登录态就位 → 导出 cookie+UA+token 落中央存储）
#   search <keyword> [--begin N] [--size N]
#   account-posts <fakeid> [--begin N] [--size N] [--keyword K]
#   fetch <url> [--html]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TS_SCRIPT="${SCRIPT_DIR}/wx_mp_hunter.ts"

exec node --experimental-strip-types "$TS_SCRIPT" "$@"
