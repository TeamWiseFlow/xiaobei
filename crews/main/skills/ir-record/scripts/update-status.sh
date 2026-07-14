#!/usr/bin/env bash
# update-status.sh — Update an investor's status and optionally notes
# Usage: update-status.sh --id <投资人ID> --status <新状态> [--notes <备注>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

ID=""
STATUS=""
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id)      ID="$2"; shift 2 ;;
    --status)  STATUS="$2"; shift 2 ;;
    --notes)   NOTES="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$ID" || -z "$STATUS" ]]; then
  echo '{"ok": false, "error": "--id and --status are required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"ok": false, "error": "Database not initialized. Run init-db.sh first."}'
  exit 1
fi

ST_ESC="${STATUS//\'/\'\'}"
NT_ESC="${NOTES//\'/\'\'}"

if [[ -n "$NOTES" ]]; then
  sqlite3 "$DB_FILE" "UPDATE investors SET status='$ST_ESC', notes='$NT_ESC', updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE id=$ID;"
else
  sqlite3 "$DB_FILE" "UPDATE investors SET status='$ST_ESC', updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime') WHERE id=$ID;"
fi

echo '{"ok": true}'
