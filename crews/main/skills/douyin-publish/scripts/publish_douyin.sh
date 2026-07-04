#!/usr/bin/env bash
# publish_douyin.sh — 抖音发布 wrapper
#
# 委托给 publish_douyin.py（Python 3 stdlib + camoufox-cli）。
# Phase 3.2 浏览器模拟方案。spike 验证待真机测试。
# 用法：publish_douyin.sh <command> [args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/publish_douyin.py"

exec python3 "$PY_SCRIPT" "$@"
