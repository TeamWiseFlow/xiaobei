#!/bin/bash
# Expire stale follow_up tasks: pending tasks older than 48 hours
# are silently marked completed (customer has gone cold).
set -euo pipefail

DB_FILE="./db/customer.db"

if [ ! -f "$DB_FILE" ]; then
  echo "❌ Database not found: $DB_FILE" >&2
  exit 1
fi

sqlite3 "$DB_FILE" \
  "UPDATE follow_up
   SET status='completed',
       completed_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')
   WHERE status='pending'
     AND datetime(follow_up_at, '+48 hours') < datetime('now','localtime');"

echo "✅ Stale pending follow_up tasks expired"
