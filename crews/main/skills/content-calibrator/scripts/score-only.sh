#!/usr/bin/env bash
# score-only.sh — 仅打分不记录到 DB，用于 Agent 自查
# 输出打分结果到 stdout（JSON），不写入 published-track DB
#
# 用法:
#   score-only.sh --content-path <file_path> [--platform <platform>] \
#     --cal-er ? --cal-hp ? --cal-sr ? --cal-ql ? --cal-na ? --cal-ab ? --cal-pv ?
#
# --platform 可选：per-work 下阈值是全局的；--platform 仅用于校验该平台是否启用 calibration。
#
# Agent 调用此脚本时，应同时传入打分参数（由 Agent LLM 打分后传入）:
#   score-only.sh --content-path output_articles/xxx/article.md \
#     --cal-er 3 --cal-hp 4 --cal-sr 3 --cal-ql 3 --cal-na 2 --cal-ab 4 --cal-pv 3
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CAL_ROOT="$ROOT/calibration"

PLATFORM="" CONTENT_PATH=""
CAL_ER="" CAL_HP="" CAL_SR="" CAL_QL="" CAL_NA="" CAL_AB="" CAL_PV=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)      PLATFORM="$2"; shift 2 ;;
    --content-path)  CONTENT_PATH="$2"; shift 2 ;;
    --cal-er)        CAL_ER="$2"; shift 2 ;;
    --cal-hp)        CAL_HP="$2"; shift 2 ;;
    --cal-sr)        CAL_SR="$2"; shift 2 ;;
    --cal-ql)        CAL_QL="$2"; shift 2 ;;
    --cal-na)        CAL_NA="$2"; shift 2 ;;
    --cal-ab)        CAL_AB="$2"; shift 2 ;;
    --cal-pv)        CAL_PV="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

# --platform 可选：per-work 下阈值是全局的，--platform 仅用于校验该平台是否启用 calibration
if [ -n "$PLATFORM" ]; then
  CAL_DIR="$CAL_ROOT/$PLATFORM"
  if [ ! -f "$CAL_DIR/.platform-state.json" ]; then
    echo "{\"ok\":false,\"error\":\"platform $PLATFORM has content-calibrator disabled. Enable with cal-toggle.sh --platform $PLATFORM --enable\"}"
    exit 1
  fi
fi

# rubric_version + score_threshold 均取自根级统一 .cheat-state.json（per-work 全局阈值）
RUBRIC_VERSION=$(python3 -c "import json; print(json.load(open('$CAL_ROOT/.cheat-state.json')).get('rubric_version','v0'))" 2>/dev/null || echo "v0")
SCORE_THRESHOLD=$(python3 -c "import json; print(json.load(open('$CAL_ROOT/.cheat-state.json')).get('score_threshold',0))" 2>/dev/null || echo 0)

# 验证打分参数
HAS_SCORES=0
for dim in ER HP SR QL NA AB PV; do
  var_name="CAL_$dim"
  if [[ -n "${!var_name}" ]]; then
    HAS_SCORES=1
    val="${!var_name}"
    if [[ "$val" -lt 0 || "$val" -gt 5 ]] 2>/dev/null; then
      echo "{\"ok\":false,\"error\":\"cal_score_$dim=$val out of range (must be 0-5 integer)\"}"
      exit 1
    fi
  fi
done

if [ "$HAS_SCORES" -eq 0 ]; then
  echo '{"ok":false,"error":"no scores provided. Agent must score the content (ER/HP/SR/QL/NA/AB/PV, each 0-5) and pass via --cal-er etc."}'
  exit 1
fi

# 算 composite
er="${CAL_ER:-0}" hp="${CAL_HP:-0}" sr="${CAL_SR:-0}"
ql="${CAL_QL:-0}" na="${CAL_NA:-0}" ab="${CAL_AB:-0}" pv="${CAL_PV:-0}"

COMPOSITE=$(python3 -c "
er=$er; hp=$hp; sr=$sr; ql=$ql; na=$na; ab=$ab; pv=$pv
composite = (er*1.5 + hp*1.5 + sr*1.5 + ql + na + ab + pv) / 8.5 * 2.0
print(f'{composite:.2f}')
")

# 找最弱维度
declare -A WEIGHTS=([ER]=1.5 [HP]=1.5 [SR]=1.5 [QL]=1.0 [NA]=1.0 [AB]=1.0 [PV]=1.0)
declare -A SCORES=([ER]="$er" [HP]="$hp" [SR]="$sr" [QL]="$ql" [NA]="$na" [AB]="$ab" [PV]="$pv")

worst_dim=""
worst_contrib=999
for dim in ER HP SR QL NA AB PV; do
  contrib=$(python3 -c "print(${SCORES[$dim]} * ${WEIGHTS[$dim]})")
  if python3 -c "exit(0 if $contrib < $worst_contrib else 1)"; then
    worst_contrib=$contrib
    worst_dim=$dim
  fi
done

# 输出 JSON（不写 DB）+ 阈值门判定
python3 -c "
import json
scores = {'ER': $er, 'HP': $hp, 'SR': $sr, 'QL': $ql, 'NA': $na, 'AB': $ab, 'PV': $pv}
threshold = $SCORE_THRESHOLD
failing = [d for d, v in scores.items() if v <= threshold]
result = {
  'ok': True,
  'action': 'score_only',
  'platform': '$PLATFORM',
  'rubric_version': '$RUBRIC_VERSION',
  'scores': scores,
  'composite': $COMPOSITE,
  'worst_dim': '$worst_dim',
  'worst_contrib': $worst_contrib,
  'score_threshold': threshold,
  'passed': len(failing) == 0,
  'failing_dims': failing,
  'recorded': False
}
print(json.dumps(result, ensure_ascii=False))
"
