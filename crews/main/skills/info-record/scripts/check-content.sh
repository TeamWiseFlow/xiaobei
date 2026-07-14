#!/usr/bin/env bash
# check-content.sh — Check if content is already recorded in intel_items
# Usage: check-content.sh --source <信源URL或标识>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/info_record.db"

SOURCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    *) echo '{"exists": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$SOURCE" ]]; then
  echo '{"exists": false, "error": "--source is required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"exists": false}'
  exit 0
fi

SOURCE_ESC="${SOURCE//\'/\'\'}"
COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM intel_items WHERE source='$SOURCE_ESC';" 2>/dev/null || echo "0")

if [[ "$COUNT" -gt 0 ]]; then
  echo '{"exists": true}'
else
  echo '{"exists": false}'
fi
