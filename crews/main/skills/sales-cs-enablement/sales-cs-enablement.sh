#!/usr/bin/env bash
# sales-cs-enablement.sh — sales-cs-enablement 顶层 wrapper（薄转发）
# 让 agent 用 `sales-cs-enablement <cmd>` 走 PATH，零路径拼接。
# 内部转发到 scripts/symlink_business_knowledge.py；wrapper 自身只是 exec 转发，不改语义。
# ⚠️ 本 skill scripts 下其实有两个并列脚本：
#   - symlink_business_knowledge.py（主入口，被本 wrapper 转发）
#   - check_awada_channel.py（备用诊断脚本）
# 旒脚本调 check_awada_channel 时按绝对路径直调 scripts/check_awada_channel.py。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/scripts/symlink_business_knowledge.py" "$@"
