#!/usr/bin/env bash
# content-calibrator init — 为指定平台创建校准数据目录（baseline / audience / benchmark）
# 用法: init.sh --platform <platform_id>
#   platform_id: wx_mp | wx_channel | xhs | zhihu | bilibili | douyin | kuaishou | toutiao | youtube
# 幂等：已存在的文件跳过。
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"

PLATFORM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

VALID_PLATFORMS="wx_mp wx_channel xhs zhihu bilibili douyin kuaishou toutiao youtube"

if [[ -z "$PLATFORM" ]]; then
  echo "用法: init.sh --platform <platform_id>"
  echo ""
  echo "支持的平台:"
  echo "  wx_mp       微信公众号"
  echo "  wx_channel  微信视频号"
  echo "  xhs         小红书"
  echo "  zhihu       知乎"
  echo "  bilibili    B站"
  echo "  douyin      抖音"
  echo "  kuaishou    快手"
  echo "  toutiao     今日头条"
  echo "  youtube     YouTube"
  exit 1
fi

if ! echo "$VALID_PLATFORMS" | grep -qw "$PLATFORM"; then
  echo "❌ 不支持的平台: $PLATFORM"
  echo "   支持的平台: $VALID_PLATFORMS"
  exit 1
fi

CAL_DIR="$WORKSPACE/$PLATFORM/calibration"

echo "🔧 初始化 Content Calibrator（DNA 表现评估）— $PLATFORM"
echo "   工作区: $WORKSPACE"
echo "   校准目录: $CAL_DIR"
echo ""

mkdir -p "$CAL_DIR"

# 兼容旧点号命名：存量 .platform-state.json 自动改名（幂等）
if [[ -f "$CAL_DIR/.platform-state.json" && ! -f "$CAL_DIR/platform-state.json" ]]; then
  mv "$CAL_DIR/.platform-state.json" "$CAL_DIR/platform-state.json"
  echo "  迁移 .platform-state.json → platform-state.json"
fi

if [[ -f "$CAL_DIR/platform-state.json" ]]; then
  echo "✅ 平台 $PLATFORM 已初始化（platform-state.json 已存在）"
else
  cat > "$CAL_DIR/platform-state.json" <<PSSTATE
{
  "schema_version": 3,
  "scope": "platform",
  "platform": "$PLATFORM",
  "enabled": true,
  "content_form": "",
  "baseline_plays": null,
  "typical_word_count": null,
  "enabled_perf_adapters": ["$PLATFORM"]
}
PSSTATE
  echo "  创建 platform-state.json（baseline 兜底参考，账号无历史数据时使用）"
fi

if [[ ! -f "$CAL_DIR/audience.md" ]]; then
  cat > "$CAL_DIR/audience.md" <<'AUD'
# Audience — 受众画像

> 从互动数据与评论聚类派生，供 DNA 表现评估归因时参考。

## 基本画像

（数据积累后从评论关键词聚类填充。）

## 互动偏好

（哪些类型的内容获得更多互动？哪些评论模因反复出现？）
AUD
  echo "  创建 audience.md"
fi

echo "✅ 初始化完成 — 平台: $PLATFORM"
echo ""
echo "下一步:"
echo "  1. 内容生产绑定 DNA（生产环节写 dna-meta.json，record.sh 自动落 dna_id）"
echo "  2. 每日使用各平台专家包的 engagement 工具采集互动数据"
echo "  3. 每个（平台, DNA）累积 ≥5 条成熟记录后跑 dna-eval.sh 评估"
