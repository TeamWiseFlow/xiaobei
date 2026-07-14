#!/usr/bin/env bash
# init-workspace — 为 designer 单项任务创建标准目录结构
# 用法: ./skills/init-workspace/scripts/init.sh <任务名>
# 示例: ./skills/init-workspace/scripts/init.sh wiseflow-official-website

set -euo pipefail

TASK_NAME="${1:?用法: init.sh <任务名>}"

# 任务目录命名: design_assets/YYYY-MM-DD-<任务名>
TODAY="$(date +%Y-%m-%d)"
TASK_DIR="design_assets/${TODAY}-${TASK_NAME}"

# 确保设计资产根目录存在
mkdir -p design_assets/references design_assets/brand

# 创建任务目录（含子目录）
mkdir -p "${TASK_DIR}/source" "${TASK_DIR}/output"

# 初始化 brief.md 模板
if [ ! -f "${TASK_DIR}/brief.md" ]; then
  cat > "${TASK_DIR}/brief.md" <<'BRIEF'
# 设计 Brief

## 需求摘要
<!-- 简述本次设计任务 -->

## 产品类型与目标用户
<!-- 网站/APP/管理后台... 及目标用户画像 -->

## 页面/界面清单
<!-- 需要设计的页面或界面列表 -->

## 功能范围
<!-- 纯静态展示/含表单/含轮播/含交互... -->

## 风格方向
<!-- 品牌名参考或风格描述词，如"类似 Stripe 的科技感暗色主题" -->

## 品牌约束
<!-- 品牌色、字体、LOGO 等（从 MEMORY.md 获取） -->

## 参考素材
<!-- 灵感参考、竞品截图等，附来源 -->
BRIEF
fi

echo "✅ 任务目录已创建: ${TASK_DIR}/"
echo "   brief.md 模板已就绪，请填写后发送确认"
