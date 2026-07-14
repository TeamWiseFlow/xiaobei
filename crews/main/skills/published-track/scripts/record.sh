#!/usr/bin/env bash
# record.sh — 发布记录统一入口（已合并 score-and-record.sh）
#
# 分数来源：直接从 <source-folder>/calibration/score.json 读取（per-work 权威落盘）。
#   - 默认（不传 --no-cal）：必须存在 <source-folder>/calibration/score.json + prediction.md，
#     缺失则报错退出——上一步 1A（打分+预测）未执行或落盘失败，主 agent 须先补跑
#     content-calibrator 的 blind subagent + commit-prediction.sh，再调本脚本。
#   - --no-cal：显式跳过读分（补发/补登记历史作品/不打分场景），cal_enabled=0，不校验文件。
#
# composite / rubric_version 均从 score.json 读（commit-prediction.sh 已算好落盘）。
#
# ── 落库语义：upsert（同一篇文章 + 同一平台 + 同一发布日 → 更新，不重复插行）──
# 去重键：(source_folder, publish_date)。同 work 同平台同天重跑（重打分/重发/record 重调）
# 覆盖旧行，避免僵尸行；不同 publish_date（真正的再发布/补发历史）仍新建行。
# 这只管 DB 层去重——公众号后台是否堆积草稿由 wx-mp-publisher 自身幂等性决定，本脚本管不到。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CAL_ROOT="$ROOT/calibration"
DB="$ROOT/db/published_track.db"

# Self-heal stale schema: if a platform table is missing, run idempotent init-db.sh
ensure_platform_table() {
  local table="pub_$1" found
  found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  if [ -z "$found" ]; then
    bash "$(dirname "$0")/init-db.sh" >/dev/null 2>&1 || true
    found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  fi
  [ -n "$found" ]
}

if [ ! -f "$DB" ]; then
  bash "$(dirname "$0")/init-db.sh"
fi

# Parse args
PLATFORM="" TITLE="" CONTENT_TYPE="" SOURCE_FOLDER="" PUBLISH_URL="" PUBLISH_DATE="" NOTES=""
DISTRIBUTE_STATUS=""
NO_CAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)            PLATFORM="$2"; shift 2 ;;
    --title)               TITLE="$2"; shift 2 ;;
    --content-type)        CONTENT_TYPE="$2"; shift 2 ;;
    --source-folder)       SOURCE_FOLDER="$2"; shift 2 ;;
    --publish-url)         PUBLISH_URL="$2"; shift 2 ;;
    # ⚠️ 发布日期就是当天时不要传此参数，让脚本默认今天。
    # ❌ 不要用 --publish-date "$(date +%Y-%m-%d)" —— exec 沙箱不展开 $()。
    --publish-date)        PUBLISH_DATE="$2"; shift 2 ;;
    --notes)               NOTES="$2"; shift 2 ;;
    --distribute-status)   DISTRIBUTE_STATUS="$2"; shift 2 ;;
    --no-cal)              NO_CAL=1; shift ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

# Default publish_date to today（防御 exec 沙箱不展开 $() 的脏数据）
if [ -z "$PUBLISH_DATE" ]; then
  PUBLISH_DATE="$(date +%Y-%m-%d)"
elif [[ "$PUBLISH_DATE" =~ ^\$\(*date* || "$PUBLISH_DATE" =~ ^\`*date* ]]; then
  echo "{\"ok\":false,\"error\":\"--publish-date looks unexpanded: '$PUBLISH_DATE'. omit --publish-date for today, or pass literal like 2026-06-14.\"}" >&2
  PUBLISH_DATE="$(date +%Y-%m-%d)"
fi

if [ -z "$PLATFORM" ] || [ -z "$TITLE" ] || [ -z "$CONTENT_TYPE" ] || [ -z "$SOURCE_FOLDER" ]; then
  echo '{"ok":false,"error":"missing required args: --platform, --title, --content-type, --source-folder"}'
  exit 1
fi

TABLE="pub_${PLATFORM}"
if ! ensure_platform_table "$PLATFORM"; then
  echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM (table $TABLE not found)\"}"
  exit 1
fi

case "$CONTENT_TYPE" in
  article|video|post) ;;
  *) echo "{\"ok\":false,\"error\":\"invalid content_type: $CONTENT_TYPE (must be article/video/post)\"}"; exit 1 ;;
esac

# ── 解析 work 绝对路径（--source-folder = 直接包含 calibration/ 的目录）──
if [[ "$SOURCE_FOLDER" = /* ]]; then WORK_ABS="$SOURCE_FOLDER"; else WORK_ABS="$ROOT/$SOURCE_FOLDER"; fi

# ── 读分 ──
CAL_ENABLED=0
CAL_ER="" CAL_HP="" CAL_SR="" CAL_QL="" CAL_NA="" CAL_AB="" CAL_PV=""
CAL_COMPOSITE="" CAL_RUBRIC_VERSION=""

if [[ "$NO_CAL" -eq 1 ]]; then
  CAL_ENABLED=0
else
  SCORE_JSON="$WORK_ABS/calibration/score.json"
  PRED_MD="$WORK_ABS/calibration/prediction.md"
  missing=""
  [[ -f "$SCORE_JSON" ]] || missing="$missing score.json"
  [[ -f "$PRED_MD" ]]    || missing="$missing prediction.md"
  if [[ -n "$missing" ]]; then
    echo "{\"ok\":false,\"error\":\"calibration files missing at $SOURCE_FOLDER/calibration:$missing. 上一步 1A（打分+预测）未执行或落盘失败——先跑 content-calibrator 的 blind subagent + commit-prediction.sh 落盘，再 record。若本次为补发/不打分，显式传 --no-cal 跳过。\"}"
    exit 1
  fi
  # 从 score.json 读 7 维 + composite + rubric_version
  read -r CAL_ER CAL_HP CAL_SR CAL_QL CAL_NA CAL_AB CAL_PV CAL_COMPOSITE CAL_RUBRIC_VERSION < <(python3 -c "
import json
d=json.load(open('$SCORE_JSON'))
s=d['scores']
print(s['ER'], s['HP'], s['SR'], s['QL'], s['NA'], s['AB'], s['PV'], d.get('composite',''), d.get('rubric_version','v0'))
")
  CAL_ENABLED=1
  echo "📊 打分 — $PLATFORM  ER=$CAL_ER HP=$CAL_HP SR=$CAL_SR QL=$CAL_QL NA=$CAL_NA AB=$CAL_AB PV=$CAL_PV  composite=$CAL_COMPOSITE (rubric $CAL_RUBRIC_VERSION)" >&2
fi

# ── 构建 cal_ 列 ──
cal_cols=""; cal_vals=""

if [[ -n "$CAL_ENABLED" ]]; then
  cal_cols="cal_enabled"; cal_vals="$CAL_ENABLED"
fi

for dim in er hp sr ql na ab pv; do
  var_name="CAL_$(echo $dim | tr '[:lower:]' '[:upper:]')"; val="${!var_name}"
  if [[ -n "$val" ]]; then
    if [[ -n "$cal_cols" ]]; then cal_cols="$cal_cols,cal_score_$dim"; cal_vals="$cal_vals,$val"
    else cal_cols="cal_score_$dim"; cal_vals="$val"; fi
  fi
done

if [[ -n "$CAL_COMPOSITE" ]]; then
  if [[ -n "$cal_cols" ]]; then cal_cols="$cal_cols,cal_composite"; cal_vals="$cal_vals,$CAL_COMPOSITE"
  else cal_cols="cal_composite"; cal_vals="$CAL_COMPOSITE"; fi
fi

if [[ -n "$CAL_RUBRIC_VERSION" ]]; then
  esc_rv="${CAL_RUBRIC_VERSION//\'/\'\'}"
  if [[ -n "$cal_cols" ]]; then cal_cols="$cal_cols,cal_rubric_version"; cal_vals="$cal_vals,'$esc_rv'"
  else cal_cols="cal_rubric_version"; cal_vals="'$esc_rv'"; fi
fi

if [[ -n "$cal_cols" ]]; then
  cal_cols="$cal_cols,cal_scored_at"
  scored_at="$(strftime '%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')"
  cal_vals="$cal_vals,'$scored_at'"
fi

# ── distribute_status ──
DS_VAL=0
if [[ -n "$DISTRIBUTE_STATUS" ]]; then
  case "$DISTRIBUTE_STATUS" in
    0|1|2) DS_VAL="$DISTRIBUTE_STATUS" ;;
    *) echo '{"ok":false,"error":"--distribute-status must be 0(pending), 1(no_distribution), or 2(distributed)"}'; exit 1 ;;
  esac
fi

ESC_TITLE="${TITLE//\'/\'\'}"
ESC_FOLDER="${SOURCE_FOLDER//\'/\'\'}"
ESC_URL="${PUBLISH_URL//\'/\'\'}"
ESC_NOTES="${NOTES//\'/\'\'}"

BASE_COLS="title,content_type,source_folder,publish_url,publish_date,distribute_status,notes"
BASE_VALS="'$ESC_TITLE','$CONTENT_TYPE','$ESC_FOLDER','$ESC_URL','$PUBLISH_DATE',$DS_VAL,'$ESC_NOTES'"

if [[ -n "$cal_cols" ]]; then
  ALL_COLS="$BASE_COLS,$cal_cols"; ALL_VALS="$BASE_VALS,$cal_vals"
else
  ALL_COLS="$BASE_COLS"; ALL_VALS="$BASE_VALS"
fi

# ── upsert：同 (source_folder, publish_date) 存在则 UPDATE，否则 INSERT ──
EXISTING_ID=$(sqlite3 "$DB" "SELECT id FROM $TABLE WHERE source_folder='$ESC_FOLDER' AND publish_date='$PUBLISH_DATE' LIMIT 1;")

if [[ -n "$EXISTING_ID" ]]; then
  SET_CLAUSE="title='$ESC_TITLE',content_type='$CONTENT_TYPE',source_folder='$ESC_FOLDER',publish_url='$ESC_URL',publish_date='$PUBLISH_DATE',distribute_status=$DS_VAL,notes='$ESC_NOTES'"
  if [[ -n "$cal_cols" ]]; then
    IFS=',' read -ra _COL_ARR <<< "$cal_cols"
    IFS=',' read -ra _VAL_ARR <<< "$cal_vals"
    for _i in "${!_COL_ARR[@]}"; do
      SET_CLAUSE="$SET_CLAUSE,${_COL_ARR[$_i]}=${_VAL_ARR[$_i]}"
    done
  fi
  SET_CLAUSE="$SET_CLAUSE,updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')"
  sqlite3 "$DB" "UPDATE $TABLE SET $SET_CLAUSE WHERE id=$EXISTING_ID;"
  echo "{\"ok\":true,\"action\":\"updated\",\"id\":$EXISTING_ID,\"table\":\"$TABLE\",\"distribute_status\":$DS_VAL,\"cal_enabled\":${CAL_ENABLED:-0}}"
else
  ID=$(sqlite3 "$DB" "INSERT INTO $TABLE ($ALL_COLS) VALUES ($ALL_VALS); SELECT last_insert_rowid();")
  echo "{\"ok\":true,\"action\":\"inserted\",\"id\":$ID,\"table\":\"$TABLE\",\"distribute_status\":$DS_VAL,\"cal_enabled\":${CAL_ENABLED:-0}}"
fi
