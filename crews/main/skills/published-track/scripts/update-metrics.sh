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

Metrics (at least one required):
  --<column> <value>       A metric column to set (integer or text).
  --<column>=<value>       Equivalent inline form.
  Valid columns depend on the platform table schema; an unknown column is rejected
  with the list of valid metric columns.

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
declare -A METRICS

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    --id)             ROW_ID="$2"; shift 2 ;;
    --*=*)
      KEY="${1#--}"
      KEY="${KEY%%=*}"
      VAL="${1#*=}"
      METRICS["$KEY"]="$VAL"
      shift
      ;;
    --*)
      KEY="${1#--}"
      VAL="$2"
      METRICS["$KEY"]="$VAL"
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

# Build SET clause
SET_PARTS=()
for KEY in "${!METRICS[@]}"; do
  # Validate column exists
  if ! echo " $COLS " | grep -q " $KEY "; then
    echo "{\"ok\":false,\"error\":\"column '$KEY' not found in $TABLE. Valid metric columns: $COLS\"}"
    exit 1
  fi
  VAL="${METRICS[$KEY]}"
  # Only allow integer or text values
  ESC_VAL="${VAL//\'/\'\'}"
  SET_PARTS+=("$KEY='$ESC_VAL'")
done

if [ ${#SET_PARTS[@]} -eq 0 ]; then
  echo '{"ok":false,"error":"no metrics provided to update"}'
  exit 1
fi

# Always update updated_at
SET_PARTS+=("updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')")

SET_CLAUSE=$(IFS=','; echo "${SET_PARTS[*]}")

sqlite3 "$DB" "UPDATE $TABLE SET $SET_CLAUSE WHERE $WHERE_CLAUSE;"

echo "{\"ok\":true,\"table\":\"$TABLE\",\"located_by\":\"${LOCATE_KEY}\",\"updated_columns\":${#METRICS[@]}}"
