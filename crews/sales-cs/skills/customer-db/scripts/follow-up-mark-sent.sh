#!/bin/bash
# Mark a follow_up task as sent_once (pending → sent_once).
# Records the sent message text and increments retry_count.
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
   SET status='sent_once',
       sent_text='$(sql_quote "$SENT_TEXT")',
       retry_count=retry_count+1
   WHERE id=$(sql_quote "$ID")
     AND status='pending';"

echo "✅ follow_up #$ID marked as sent_once"
