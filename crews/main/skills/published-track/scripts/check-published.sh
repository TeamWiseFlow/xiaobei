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
  echo '{"exists":false}'
  exit 0
fi

PLATFORM="" SOURCE_FOLDER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ -z "$PLATFORM" ] || [ -z "$SOURCE_FOLDER" ]; then
  echo '{"ok":false,"error":"missing required args: --platform, --source-folder"}'
  exit 1
fi

TABLE="pub_${PLATFORM}"
if ! ensure_platform_table "$PLATFORM"; then
  echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM\"}"
  exit 1
fi

ROW=$(sqlite3 "$DB" "SELECT id,publish_url FROM $TABLE WHERE source_folder='${SOURCE_FOLDER//\'/\'\'}';")
if [ -z "$ROW" ]; then
  echo '{"exists":false}'
else
  ID=$(echo "$ROW" | cut -d'|' -f1)
  URL=$(echo "$ROW" | cut -d'|' -f2)
  echo "{\"exists\":true,\"id\":$ID,\"publish_url\":\"$URL\"}"
fi
