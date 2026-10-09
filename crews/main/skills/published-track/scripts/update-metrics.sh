#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$ROOT/db/published_track.db"

# Self-heal stale schema: if a platform table is missing, run idempotent init-db.sh
# (CREATE TABLE IF NOT EXISTS) and re-check before treating the platform as unknown.
# Auto-adds tables for platforms introduced into init-db.sh after the DB was first created.
ensure_platform_table() {
  local table="pub_$1" found
  found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  if [ -z "$found" ]; then
    bash "$(dirname "$0")/init-db.sh" >/dev/null 2>&1 || true
    found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  fi
  [ -n "$found" ]
}

# --help/-h is a usage probe; honor it before the DB check so it works without a DB.
for arg in "$@"; do
  if [ "$arg" = "--help" ] || [ "$arg" = "-h" ]; then
    cat <<'EOF'
Usage: update-metrics.sh --platform <name> (--id <rowid> | --source-folder <folder>) [--<metric-col> <value>]...

Update metric columns of an existing published-track record in table pub_<platform>.

Required:
  --platform <name>        Platform table suffix (record lives in pub_<name>).
  --id <rowid>             Update ONE row by primary key id (preferred — avoids
                           same-source_folder duplicate-publish rows being written
                           together). Either --id or --source-folder is required.
  --source-folder <folder> Update ALL rows matching source_folder (legacy batch
                           write; use only when you intentionally want every row
                           with that folder to receive the same metrics).

Metrics (at least one of metrics / --deep-file required):
  --<column> <value>       A metric column to set (integer or text).
  --<column>=<value>       Equivalent inline form.
  Valid columns depend on the platform table schema; an unknown column is rejected
  with the list of valid metric columns.
  --deep-file <path>       Deep-metrics JSON file (single line) → deep_metrics column
                           (latest value only, no history). Written via sqlite readfile().
  --deep-source <str>      Data source tag stored in deep_source (e.g. douyin:creator_item_list).
  --fan-portrait-file <path>  Single-note XHS audience portrait JSON → pub_xhs.fan_portrait.

Examples:
  update-metrics.sh --platform xhs --id 10 --views 100 --likes 10
  update-metrics.sh --platform xhs --source-folder abc --views 100 --likes 10
  update-metrics.sh --platform wx --source-folder abc --reads=50

Output: JSON on stdout. {"ok":true,...} on success, {"ok":false,"error":...} on error.
EOF
    exit 0
  fi
done

if [ ! -f "$DB" ]; then
  echo '{"ok":false,"error":"database not initialized, run init-db.sh first"}'
  exit 1
fi

# Parse args
PLATFORM="" SOURCE_FOLDER="" ROW_ID=""
# deep 指标走 JSON 文件而非 --col=value（JSON 进 shell 参数是引号地狱，readfile 免疫）
DEEP_FILE=""
DEEP_SOURCE=""
FAN_PORTRAIT_FILE=""
# bash 3.2 兼容：不用关联数组，平行索引数组存 metric 键值；同名键后值覆盖
METRIC_KEYS=()
METRIC_VALS=()

set_metric() {
  local k="$1" v="$2" i
  for ((i=0; i<${#METRIC_KEYS[@]}; i++)); do
    if [ "${METRIC_KEYS[$i]}" = "$k" ]; then
      METRIC_VALS[$i]="$v"
      return 0
    fi
  done
  METRIC_KEYS+=("$k")
  METRIC_VALS+=("$v")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    --id)             ROW_ID="$2"; shift 2 ;;
    --deep-file)      DEEP_FILE="$2"; shift 2 ;;
    --deep-source)    DEEP_SOURCE="$2"; shift 2 ;;
    --fan-portrait-file) FAN_PORTRAIT_FILE="$2"; shift 2 ;;
    --*=*)
      KEY="${1#--}"
      KEY="${KEY%%=*}"
      VAL="${1#*=}"
      set_metric "$KEY" "$VAL"
      shift
      ;;
    --*)
      KEY="${1#--}"
      VAL="$2"
      set_metric "$KEY" "$VAL"
      shift 2
      ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  echo '{"ok":false,"error":"missing required arg: --platform"}'
  exit 1
fi

# --id 优先（按主键写单行，避免同 source_folder 多条重复发布被批量污染）；
# 否则回退到 --source-folder（批量写所有同 folder 行，旧行为）。
if [ -n "$ROW_ID" ]; then
  if ! [[ "$ROW_ID" =~ ^[0-9]+$ ]]; then
    echo "{\"ok\":false,\"error\":\"--id must be a positive integer, got: $ROW_ID\"}"
    exit 1
  fi
  WHERE_CLAUSE="id=${ROW_ID}"
  LOCATE_KEY="id=${ROW_ID}"
elif [ -n "$SOURCE_FOLDER" ]; then
  WHERE_CLAUSE="source_folder='${SOURCE_FOLDER//\'/\'\'}'"
  LOCATE_KEY="source_folder=$SOURCE_FOLDER"
else
  echo '{"ok":false,"error":"missing required arg: --id or --source-folder"}'
  exit 1
fi

TABLE="pub_${PLATFORM}"
if ! ensure_platform_table "$PLATFORM"; then
  echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM\"}"
  exit 1
fi

# Check record exists
EXISTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $TABLE WHERE $WHERE_CLAUSE;")
if [ "$EXISTS" -eq 0 ]; then
  echo "{\"ok\":false,\"error\":\"no record found in $TABLE for ${LOCATE_KEY}\"}"
  exit 1
fi

# Get valid columns for this table (exclude id, created_at)
COLS=$(sqlite3 "$DB" "PRAGMA table_info($TABLE);" | awk -F'|' '{print $2}' | grep -v -E '^(id|created_at|source_folder|content_type|title|publish_date)$' | tr '\n' ' ')

# Build SET clause（deep-only 写入也算有效——无标量指标但有 --deep-file 时继续）
if [ ${#METRIC_KEYS[@]} -eq 0 ] && [ -z "$DEEP_FILE" ] && [ -z "$FAN_PORTRAIT_FILE" ]; then
  echo '{"ok":false,"error":"no metrics provided to update"}'
  exit 1
fi

SET_PARTS=()
for ((i=0; i<${#METRIC_KEYS[@]}; i++)); do
  KEY="${METRIC_KEYS[$i]}"
  # Validate column exists
  if ! echo " $COLS " | grep -q " $KEY "; then
    echo "{\"ok\":false,\"error\":\"column '$KEY' not found in $TABLE. Valid metric columns: $COLS\"}"
    exit 1
  fi
  VAL="${METRIC_VALS[$i]}"
  # Only allow integer or text values
  ESC_VAL="${VAL//\'/\'\'}"
  SET_PARTS+=("$KEY='$ESC_VAL'")
done

DEEP_UPDATED=false
if [ -n "$DEEP_FILE" ]; then
  if [ ! -f "$DEEP_FILE" ]; then
    echo "{\"ok\":false,\"error\":\"deep file not found: $DEEP_FILE\"}"
    exit 1
  fi
  # 路径拼进 SQL（readfile 参数），只放行安全字符
  if ! [[ "$DEEP_FILE" =~ ^[A-Za-z0-9_./-]+$ ]]; then
    echo '{"ok":false,"error":"deep file path contains invalid characters"}'
    exit 1
  fi
  # 自愈补列（同 ensure_platform_table 模式：init-db 幂等，ALTER 有 has_col 守卫）
  if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$TABLE') WHERE name='deep_metrics';")" = "0" ]; then
    bash "$(dirname "$0")/init-db.sh" >/dev/null 2>&1 || true
  fi
  if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$TABLE') WHERE name='deep_metrics';")" = "0" ]; then
    echo "{\"ok\":false,\"error\":\"deep columns not available in $TABLE (init-db self-heal failed)\",\"hint\":\"手动跑 init-db.sh 补列后重试\"}"
    exit 1
  fi
  ESC_DEEP_SOURCE="${DEEP_SOURCE:-unknown}"
  ESC_DEEP_SOURCE="${ESC_DEEP_SOURCE//\'/\'\'}"
  SET_PARTS+=("deep_metrics=CAST(readfile('$DEEP_FILE') AS TEXT)")
  SET_PARTS+=("deep_captured_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')")
  SET_PARTS+=("deep_source='$ESC_DEEP_SOURCE'")
  DEEP_UPDATED=true
fi

FAN_PORTRAIT_UPDATED=false
if [ -n "$FAN_PORTRAIT_FILE" ]; then
  if [ "$PLATFORM" != "xhs" ]; then
    echo '{"ok":false,"error":"fan portrait is only supported for xhs"}'
    exit 1
  fi
  if [ ! -f "$FAN_PORTRAIT_FILE" ]; then
    echo "{\"ok\":false,\"error\":\"fan portrait file not found: $FAN_PORTRAIT_FILE\"}"
    exit 1
  fi
  if ! [[ "$FAN_PORTRAIT_FILE" =~ ^[A-Za-z0-9_./-]+$ ]]; then
    echo '{"ok":false,"error":"fan portrait file path contains invalid characters"}'
    exit 1
  fi
  if [ "$(sqlite3 "$DB" "SELECT json_valid(CAST(readfile('$FAN_PORTRAIT_FILE') AS TEXT));")" != "1" ]; then
    echo '{"ok":false,"error":"fan portrait file is not valid JSON"}'
    exit 1
  fi
  if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('pub_xhs') WHERE name='fan_portrait';")" = "0" ]; then
    bash "$(dirname "$0")/init-db.sh" >/dev/null 2>&1 || true
  fi
  if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('pub_xhs') WHERE name='fan_portrait';")" = "0" ]; then
    echo '{"ok":false,"error":"fan_portrait column not available in pub_xhs"}'
    exit 1
  fi
  SET_PARTS+=("fan_portrait=CAST(readfile('$FAN_PORTRAIT_FILE') AS TEXT)")
  FAN_PORTRAIT_UPDATED=true
fi

# 验证完成后一次 UPDATE，基础指标、深度指标和画像要么同时写入，要么都不写入。
SET_PARTS+=("updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')")
SET_CLAUSE=$(IFS=','; echo "${SET_PARTS[*]}")
sqlite3 "$DB" "UPDATE $TABLE SET $SET_CLAUSE WHERE $WHERE_CLAUSE;"

echo "{\"ok\":true,\"table\":\"$TABLE\",\"located_by\":\"${LOCATE_KEY}\",\"updated_columns\":${#METRIC_KEYS[@]},\"deep_updated\":$DEEP_UPDATED,\"fan_portrait_updated\":$FAN_PORTRAIT_UPDATED}"
