#!/usr/bin/env bash
# wx-mp-engagement.sh — 微信公众号 engagement 数据抓取 wrapper
#
# 委托给 fetch_engagement.py（Python 3 stdlib + camoufox-cli）。
# Phase 4.6 方案 A 骨架。spike 验证待真机测试。
# 用法：wx-mp-engagement.sh <command> [args...]
#
# 命令：
#   fetch   --row-id <id> | --source-folder <folder>
#   fetch-all --days <N>
#
# 依赖：
#   - login-manager skill（同 crew 私有，用于 cookie 探活 + cookie-import）
#   - published-track skill（同 crew 私有，用于 DB 读写）
#   - camoufox-cli（npm 全局）
#
# 退出码：
#   0  成功
#   1  通用错误
#   2  cookie 失效 → 触发 login-manager qr-headless + qr-confirm

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/fetch_engagement.py"

exec python3 "$PY_SCRIPT" "$@"
