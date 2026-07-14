#!/usr/bin/env bash
# query-today.sh — Query all intel items collected today
# Usage: query-today.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/info_record.db"

if [[ ! -f "$DB_FILE" ]]; then
  echo '[]'
  exit 0
fi

sqlite3 -json "$DB_FILE" "SELECT id, source, source_type, title, author, publish_date, content, created_at FROM intel_items WHERE date(created_at)=date('now','localtime') ORDER BY created_at DESC;"
