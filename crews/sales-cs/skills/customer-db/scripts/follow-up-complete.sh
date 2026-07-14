#!/bin/bash
# Mark a follow_up task as completed (sent_once → completed).
# Records the final sent message text and completion timestamp.
set -euo pipefail

DB_FILE="./db/customer.db"

ID=""
SENT_TEXT=""

while [ $# -gt 0 ]; do
  case "$1" in
    --id)         ID="${2:-}";        shift 2 ;;
    --sent-text)  SENT_TEXT="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$ID" ]; then
  echo "❌ --id is required" >&2
  exit 1
fi

if [ -z "$SENT_TEXT" ]; then
  echo "❌ --sent-text is required" >&2
  exit 1
fi

if [ ! -f "$DB_FILE" ]; then
  echo "❌ Database not found: $DB_FILE" >&2
  exit 1
fi

sql_quote() {
  printf '%s' "$1" | sed "s/'/''/g"
}

sqlite3 "$DB_FILE" \
  "UPDATE follow_up
   SET status='completed',
       sent_text='$(sql_quote "$SENT_TEXT")',
       completed_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime'),
       retry_count=retry_count+1
   WHERE id=$(sql_quote "$ID")
     AND status='sent_once';"

echo "✅ follow_up #$ID marked as completed"
