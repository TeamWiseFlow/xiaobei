#!/usr/bin/env bash
# import-viral-chaser.sh — 将 viral-chaser 追爆报告导入为指定平台的对标信号
# 用法: import-viral-chaser.sh --platform <platform_id> <report-path>
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"
CAL_ROOT="$WORKSPACE/calibration"

PLATFORM=""
REPORT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM="$2"; shift 2 ;;
    *) REPORT_PATH="$1"; shift ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$REPORT_PATH" ]]; then
  echo "用法: import-viral-chaser.sh --platform <platform_id> <report-path>"
  echo "  platform_id: wx_mp | xhs | zhihu | bilibili | douyin | kuaishou | toutiao | youtube"
  echo "  report-path: viral-chaser 追爆报告.md 的路径"
  echo ""
  echo "示例:"
  echo "  import-viral-chaser.sh --platform douyin output_videos/douyin-7389abc/追爆报告.md"
  exit 1
fi

CAL_DIR="$CAL_ROOT/$PLATFORM"
if [[ ! -d "$CAL_DIR" ]]; then
  echo "❌ 平台 $PLATFORM 的校准目录不存在: $CAL_DIR"
  echo "   先运行 init.sh --platform $PLATFORM"
  exit 1
fi

if [[ ! -f "$REPORT_PATH" ]]; then
  echo "❌ 报告文件不存在: $REPORT_PATH"
  exit 1
fi

BENCHMARK_FILE="$CAL_DIR/benchmark.md"
if [[ ! -f "$BENCHMARK_FILE" ]]; then
  echo "❌ benchmark.md 不存在，先运行 init.sh --platform $PLATFORM"
  exit 1
fi

echo "🎯 导入追爆报告为对标信号 — 平台: $PLATFORM"
echo "   报告: $REPORT_PATH"

# 提取报告关键信息
REPORT_CONTENT=$(cat "$REPORT_PATH")

# 提取平台
REPORT_PLATFORM=$(echo "$REPORT_CONTENT" | grep -oP '(?<=平台[：:]\s*)\S+' | head -1 || echo "unknown")
# 提取标题
TITLE=$(echo "$REPORT_CONTENT" | grep -oP '(?<=标题[：:]\s*).*' | head -1 || echo "unknown")
# 提取播放量
PLAYS=$(echo "$REPORT_CONTENT" | grep -oP '(?<=播放[：:]\s*)[\d.]+[wW万]?' | head -1 || echo "N/A")

TIMESTAMP=$(date -Iseconds)

# 追加到该平台的 benchmark.md
cat >> "$BENCHMARK_FILE" << EOF

---

### 追爆对标 — $TITLE ($REPORT_PLATFORM)

- **来源**: viral-chaser 追爆报告
- **导入平台**: $PLATFORM
- **导入时间**: $TIMESTAMP
- **播放量**: $PLAYS
- **报告路径**: $REPORT_PATH

**Pattern 提炼**（由 agent 从报告中分析）:
- 结构 pattern: （待 agent 分析填充）
- 开头方式: （待分析）
- 转折技巧: （待分析）
- 金句模式: （待分析）
- 互动钩子: （待分析）

**Rubric 信号**（对当前 rubric 维度的启示）:
- （待 agent 从报告数据中提炼，如"高 ER + 高 HP → 高流量"）

EOF

echo ""
echo "✅ 已追加到 calibration/$PLATFORM/benchmark.md"
echo ""
echo "下一步: 让 agent 分析追爆报告，填充 pattern 和 rubric 信号"
