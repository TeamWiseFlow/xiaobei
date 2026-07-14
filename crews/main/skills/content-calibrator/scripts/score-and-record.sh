#!/usr/bin/env bash
# score-and-record.sh — 已合并入 published-track/scripts/record.sh（薄 wrapper）
#
# record.sh 现在统一处理：默认从 <source-folder>/calibration/score.json 读分（cal_enabled=1）；
# 缺失则报错；--no-cal 显式跳过（cal_enabled=0）。本脚本保留为兼容入口，转调 record.sh。
#
# 打分的强制门（blind sub-agent + 阈值）在发布技能流程里执行，见各发布技能
# SKILL.md 的"打分+盲预测"段与 published-track/SKILL.md 块一·流程 1A。
set -euo pipefail

echo "ℹ️  score-and-record.sh 已合并入 record.sh，本调用转调 record.sh（兼容保留）" >&2
exec bash "$(dirname "$0")/../../published-track/scripts/record.sh" "$@"
