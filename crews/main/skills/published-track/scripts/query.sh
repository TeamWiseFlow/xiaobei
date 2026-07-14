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

if [ ! -f "$DB" ]; then
  echo '[]'
  exit 0
fi

PLATFORM="" LIMIT="" UNPUBLISHED=false STALE_DAYS="" BELOW=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)      PLATFORM="$2"; shift 2 ;;
    --limit)         LIMIT="$2"; shift 2 ;;
    --unpublished)   UNPUBLISHED=true; shift ;;
    --stale-days)    STALE_DAYS="$2"; shift 2 ;;
    --below)         BELOW="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ "$UNPUBLISHED" = true ]; then
  # Find source_folders in output_articles/ and output_videos/ that have no record in any platform table
  TABLES=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pub_%';")
  FOLDERS=$(find "$ROOT/output_articles" "$ROOT/output_videos" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sed "s|$ROOT/||" | sort)

  UNPUB_LIST="["
  FIRST=true
  for F in $FOLDERS; do
    FOUND=false
    for T in $TABLES; do
      CNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $T WHERE source_folder='${F//\'/\'\'}';")
      if [ "$CNT" -gt 0 ]; then
        FOUND=true
        break
      fi
    done
    if [ "$FOUND" = false ]; then
      [ "$FIRST" = true ] && FIRST=false || UNPUB_LIST+=","
      UNPUB_LIST+="\"$F\""
    fi
  done
  UNPUB_LIST+="]"
  echo "$UNPUB_LIST"
  exit 0
fi

if [ -z "$PLATFORM" ]; then
  echo '{"ok":false,"error":"--platform is required (unless --unpublished)"}'
  exit 1
fi

TABLE="pub_${PLATFORM}"
if ! ensure_platform_table "$PLATFORM"; then
  echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM\"}"
  exit 1
fi

# Build query
WHERE=""
if [ -n "$STALE_DAYS" ]; then
  WHERE="WHERE publish_date <= date('now','-$STALE_DAYS days')"
fi

LIMIT_CLAUSE=""
if [ -n "$LIMIT" ]; then
  LIMIT_CLAUSE="LIMIT $LIMIT"
fi

# Query all records
ROWS=$(sqlite3 -json "$DB" "SELECT * FROM $TABLE $WHERE ORDER BY publish_date DESC $LIMIT_CLAUSE;" 2>/dev/null)

if [ -n "$BELOW" ] && [ -n "$STALE_DAYS" ]; then
  # Filter for records where all main metric columns are below threshold
  # Get integer columns
  INT_COLS=$(sqlite3 "$DB" "PRAGMA table_info($TABLE);" | awk -F'|' '$2 != "id" && $2 != "title" && $2 != "content_type" && $2 != "source_folder" && $2 != "publish_url" && $2 != "publish_date" && $2 != "notes" && $2 != "top_comment" && $2 != "created_at" && $2 != "updated_at" {print $2}')

  CONDS=""
  for C in $INT_COLS; do
    [ -n "$CONDS" ] && CONDS+=" AND "
    CONDS+="$C < $BELOW"
  done

  ROWS=$(sqlite3 -json "$DB" "SELECT * FROM $TABLE WHERE publish_date <= date('now','-$STALE_DAYS days') AND ($CONDS) ORDER BY publish_date DESC $LIMIT_CLAUSE;" 2>/dev/null)
fi

echo "${ROWS:-[]}"
