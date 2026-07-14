#!/usr/bin/env bash
# commit-prediction.sh — 把 blind subagent 产出的 score + 预测草稿落盘到 <work>/calibration/
#
# 写两个文件：
#   <work>/calibration/score.json     — 7 维 + composite + rubric_version + 时间戳（覆盖）
#   <work>/calibration/prediction.md  — 盲预测（覆盖；发布后由 agent 保证不再覆盖）
#
# 同 work 重复调用直接覆盖（用户有意见/未过阈值 → 改稿重打）。
#
# 用法:
#   commit-prediction.sh --work-dir <work相对路径> --platform <platform> \
#     --cal-er 3 --cal-hp 4 --cal-sr 3 --cal-ql 4 --cal-na 3 --cal-ab 4 --cal-pv 2 \
#     --prediction-file /tmp/prediction-draft.md
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"
CAL_ROOT="$WORKSPACE/calibration"

WORK_DIR="" PLATFORM="" PREDICTION_FILE=""
CAL_ER="" CAL_HP="" CAL_SR="" CAL_QL="" CAL_NA="" CAL_AB="" CAL_PV=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --work-dir)         WORK_DIR="$2"; shift 2 ;;
    --platform)         PLATFORM="$2"; shift 2 ;;
    --prediction-file)  PREDICTION_FILE="$2"; shift 2 ;;
    --cal-er) CAL_ER="$2"; shift 2 ;;
    --cal-hp) CAL_HP="$2"; shift 2 ;;
    --cal-sr) CAL_SR="$2"; shift 2 ;;
    --cal-ql) CAL_QL="$2"; shift 2 ;;
    --cal-na) CAL_NA="$2"; shift 2 ;;
    --cal-ab) CAL_AB="$2"; shift 2 ;;
    --cal-pv) CAL_PV="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [[ -z "$WORK_DIR" || -z "$PLATFORM" ]]; then
  echo '{"ok":false,"error":"--work-dir and --platform are required"}'
  exit 1
fi

# 校验分数
for dim in ER HP SR QL NA AB PV; do
  var_name="CAL_$dim"
  if [[ -z "${!var_name}" ]]; then
    echo "{\"ok\":false,\"error\":\"missing --cal-$(echo $dim | tr '[:upper:]' '[:lower:]')\"}"
    exit 1
  fi
  val="${!var_name}"
  if [[ "$val" -lt 0 || "$val" -gt 5 ]] 2>/dev/null; then
    echo "{\"ok\":false,\"error\":\"cal_$dim=$val out of range (must be 0-5 integer)\"}"
    exit 1
  fi
done

# 解析 work-dir：支持相对路径（output_articles/xxx）或绝对路径
if [[ "$WORK_DIR" = /* ]]; then
  WORK_ABS="$WORK_DIR"
else
  WORK_ABS="$WORKSPACE/$WORK_DIR"
fi
if [[ ! -d "$WORK_ABS" ]]; then
  echo "{\"ok\":false,\"error\":\"work dir not found: $WORK_ABS\"}"
  exit 1
fi

CAL_DIR="$WORK_ABS/calibration"
mkdir -p "$CAL_DIR"

# rubric_version 取自根级统一 state
RUBRIC_VERSION=$(python3 -c "import json; print(json.load(open('$CAL_ROOT/.cheat-state.json')).get('rubric_version','v0'))" 2>/dev/null || echo "v0")

er="$CAL_ER" hp="$CAL_HP" sr="$CAL_SR" ql="$CAL_QL" na="$CAL_NA" ab="$CAL_AB" pv="$CAL_PV"
COMPOSITE=$(python3 -c "
er=$er; hp=$hp; sr=$sr; ql=$ql; na=$na; ab=$ab; pv=$pv
print(f'{(er*1.5 + hp*1.5 + sr*1.5 + ql + na + ab + pv) / 8.5 * 2.0:.2f}')
")
NOW="$(date '+%Y-%m-%d %H:%M:%S')"

# 写 score.json（覆盖）
python3 -c "
import json
d = {
  'rubric_version': '$RUBRIC_VERSION',
  'platform': '$PLATFORM',
  'scores': {'ER': $er, 'HP': $hp, 'SR': $sr, 'QL': $ql, 'NA': $na, 'AB': $ab, 'PV': $pv},
  'composite': $COMPOSITE,
  'scored_at': '$NOW'
}
json.dump(d, open('$CAL_DIR/score.json','w'), ensure_ascii=False, indent=2)
"

# 写 prediction.md（覆盖）
{
  echo "# Prediction — $(basename "$WORK_ABS")"
  echo ""
  echo "> **盲预测**：发布前在看到实际数据之前写就。发布后 immutable。"
  echo "> platform: $PLATFORM · rubric: $RUBRIC_VERSION · composite: $COMPOSITE · scored_at: $NOW"
  echo ""
  if [[ -n "$PREDICTION_FILE" && -f "$PREDICTION_FILE" ]]; then
    cat "$PREDICTION_FILE"
  else
    echo "（未提供 --prediction-file，仅落盘分数。请补预测草稿。）"
  fi
} > "$CAL_DIR/prediction.md"

echo "{\"ok\":true,\"action\":\"committed\",\"work\":\"$WORK_DIR\",\"platform\":\"$PLATFORM\",\"composite\":$COMPOSITE,\"rubric_version\":\"$RUBRIC_VERSION\",\"score_json\":\"$CAL_DIR/score.json\",\"prediction_md\":\"$CAL_DIR/prediction.md\"}"
