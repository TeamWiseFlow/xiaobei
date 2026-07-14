#!/bin/bash
# Mark all pending follow_up tasks for a peer as completed.
# Call this before creating a new follow_up for the same peer.
set -euo pipefail

DB_FILE="./db/customer.db"

PEER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --peer) PEER="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [ -z "$PEER" ]; then
  echo "❌ --peer is required" >&2
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
       completed_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')
   WHERE peer='$(sql_quote "$PEER")'
     AND status='pending';"

echo "✅ Pending follow_up tasks cancelled for peer: $PEER"
