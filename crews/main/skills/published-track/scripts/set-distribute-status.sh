#!/usr/bin/env bash
# set-distribute-status.sh — 设置条目的分发状态
#   distribute_status: 0=待分发, 1=无需分发, 2=已分发
#
# 用法:
#   set-distribute-status.sh --platform <platform> --source-folder <folder> --status <0|1|2>
#   set-distribute-status.sh --platform <platform> --id <id> --status <0|1|2>
#   set-distribute-status.sh --mark-all-distributed --platform <platform>  # 将某平台所有待分发标记为已分发
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
  echo '{"ok":false,"error":"database not initialized"}'
  exit 1
fi

PLATFORM="" SOURCE_FOLDER="" ID="" STATUS="" MARK_ALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    --id)             ID="$2"; shift 2 ;;
    --status)         STATUS="$2"; shift 2 ;;
    --mark-all-distributed) MARK_ALL=true; shift ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  echo '{"ok":false,"error":"--platform is required"}'
  exit 1
fi

TABLE="pub_${PLATFORM}"
if ! ensure_platform_table "$PLATFORM"; then
  echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM\"}"
  exit 1
fi

if [ "$MARK_ALL" = true ]; then
  # 将该平台所有 distribute_status=0 的条目标记为 2
  CNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $TABLE WHERE distribute_status = 0;")
  sqlite3 "$DB" "UPDATE $TABLE SET distribute_status = 2, updated_at = strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE distribute_status = 0;"
  echo "{\"ok\":true,\"action\":\"mark_all_distributed\",\"platform\":\"$PLATFORM\",\"count\":$CNT}"
  exit 0
fi

# 验证 status 值
case "${STATUS:-}" in
  0|1|2) ;;
  *) echo '{"ok":false,"error":"--status must be 0(pending), 1(no_distribution), or 2(distributed)"}'; exit 1 ;;
esac

if [ -n "$ID" ]; then
  sqlite3 "$DB" "UPDATE $TABLE SET distribute_status = $STATUS, updated_at = strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE id = $ID;"
  echo "{\"ok\":true,\"action\":\"updated\",\"platform\":\"$PLATFORM\",\"id\":$ID,\"distribute_status\":$STATUS}"
elif [ -n "$SOURCE_FOLDER" ]; then
  sqlite3 "$DB" "UPDATE $TABLE SET distribute_status = $STATUS, updated_at = strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE source_folder = '${SOURCE_FOLDER//\'/\'\'}';"
  echo "{\"ok\":true,\"action\":\"updated\",\"platform\":\"$PLATFORM\",\"source_folder\":\"$SOURCE_FOLDER\",\"distribute_status\":$STATUS}"
else
  echo '{"ok":false,"error":"need --id or --source-folder to identify the record"}'
  exit 1
fi
