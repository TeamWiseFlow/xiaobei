#!/usr/bin/env bash
# content-calibrator init — 为指定平台创建校准目录与平台数据文件
# 首次调用时同时创建根级统一 rubric（rubric_notes.md / rubric-memo.md / .cheat-state.json）
# 用法: init.sh --platform <platform_id>
#   platform_id: wx_mp | wx_channel | xhs | zhihu | bilibili | douyin | kuaishou | toutiao | youtube
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"
CAL_ROOT="$WORKSPACE/calibration"

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

echo "🔧 初始化 Content Calibrator — $PLATFORM"
echo "   工作区: $WORKSPACE"
echo ""

# ── 1. 根级统一 rubric（若不存在）──
mkdir -p "$CAL_ROOT"
if [[ ! -f "$CAL_ROOT/rubric_notes.md" ]]; then
  echo "  创建根级统一 rubric（v0）"
  cat > "$CAL_ROOT/rubric_notes.md" <<'RUBRIC'
# Rubric Notes — 评分公式（统一）

> **当前版本**: v0
> **适用范围**: 全平台统一（一个作品一个打分 ⇒ 一个评分标准）
> **blind sub-agent 可读此文件**；rubric-memo / .cheat-state / audience / benchmark / 各 work 的 retro 不可读。

## 当前评分维度

| 维度 | 代号 | 0 分 | 5 分 | 权重 |
|------|------|------|------|------|
| 情感共鸣 | ER | 纯信息罗列，无情感触点 | 读者强烈代入"说的就是我" | ×1.5 |
| 钩子强度 | HP | 标题平庸，开头无悬念 | 标题/开头一句话锁定注意力 | ×1.5 |
| 社会议题共振 | SR | 纯个人/产品向 | 触及当下社会讨论，有立场可议 | ×1.5 |
| 金句密度 | QL | 全文无独立可传播表达 | ≥3 句可脱离上下文独立传播的金句 | ×1.0 |
| 叙事性 | NA | 纯观点堆砌 | 清晰起承转合 | ×1.0 |
| 受众广度 | AB | 极窄垂直 | 跨人群普适 | ×1.0 |
| 实用价值 | PV | 纯情绪/观点 | 可获得具体方法/工具/步骤 | ×1.0 |

## 综合分公式

composite = (ER×1.5 + HP×1.5 + SR×1.5 + QL + NA + AB + PV) / 8.5 × 2.0

## 版本速查

| 版本 | 公式签名 | 日期 |
|------|---------|------|
| v0 | ER1.5+HP1.5+SR1.5+QL+NA+AB+PV / 8.5×2 | 初始 |
RUBRIC
else
  echo "  根级 rubric 已存在，跳过"
fi

if [[ ! -f "$CAL_ROOT/rubric-memo.md" ]]; then
  cat > "$CAL_ROOT/rubric-memo.md" <<'MEMO'
# Rubric Memo — 观察记录（统一）

> **blind sub-agent 硬禁读此文件**。被推翻/吸收的观察删除，git history 是档案。

## 观察记录

（复盘后观察追加于此。每条观察必须可追溯到具体作品 + 平台数据点。）

## Bump 升级 Memo

（每次 rubric 升级后，append 升级详情含证据+诊断。）
MEMO
fi

if [[ ! -f "$CAL_ROOT/.cheat-state.json" ]]; then
  cat > "$CAL_ROOT/.cheat-state.json" <<'STATE'
{
  "schema_version": 3,
  "scope": "global",
  "rubric_version": "v0",
  "mode": "cold-start",
  "calibration_samples": 0,
  "retro_window_days": 3,
  "consecutive_directional_errors": [],
  "last_bump_at": null,
  "last_bump_self_audited": null,
  "calibration_samples_at_last_bump": 0,
  "score_threshold": 0
}
STATE
fi

# ── 2. 平台数据目录 ──
CAL_DIR="$CAL_ROOT/$PLATFORM"
mkdir -p "$CAL_DIR"

# 平台目录建 rubric_notes.md 软链 → 根级统一 rubric（blind subagent 可能按平台目录找 rubric，
# 软链保证它无论从根级还是平台路径都读到同一份；单一事实源仍是根级文件）。幂等。
if [[ -f "$CAL_ROOT/rubric_notes.md" && ! -e "$CAL_DIR/rubric_notes.md" ]]; then
  ln -s ../rubric_notes.md "$CAL_DIR/rubric_notes.md"
elif [[ -L "$CAL_DIR/rubric_notes.md" && "$(readlink "$CAL_DIR/rubric_notes.md")" != "../rubric_notes.md" ]]; then
  rm -f "$CAL_DIR/rubric_notes.md"
  ln -s ../rubric_notes.md "$CAL_DIR/rubric_notes.md"
fi

if [[ -f "$CAL_DIR/.platform-state.json" ]]; then
  echo "✅ 平台 $PLATFORM 的校准已启用（.platform-state.json 已存在）"
  exit 0
fi

cat > "$CAL_DIR/.platform-state.json" <<PSSTATE
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

cat > "$CAL_DIR/audience.md" <<'AUD'
# Audience — 受众画像

> 从复盘评论聚类派生。blind sub-agent **不可读**此文件。

## 基本画像

（复盘后从评论关键词聚类填充。）

## 互动偏好

（哪些类型的内容获得更多互动？哪些评论模因反复出现？）
AUD

cat > "$CAL_DIR/benchmark.md" <<'BM'
# Benchmark — 对标账号

> 导入对标账号后，记录对标信号和 pattern。由 LearnFrom 操作维护。

## 对标账号列表

（暂无。运行"导入对标"添加。）

## Pattern 提炼

（从对标内容中提取的结构 pattern。）
BM

echo "✅ 初始化完成 — 平台: $PLATFORM"
echo ""
echo "下一步:"
echo "  1. 对已有发布内容做首次复盘 → 积累校准样本"
echo "  2. 导入对标账号 → 获取初始 rubric 信号"
echo "  3. 对新稿子打分+预测 → 开始校准循环"
