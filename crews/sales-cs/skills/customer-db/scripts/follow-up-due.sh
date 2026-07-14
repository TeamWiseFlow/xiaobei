#!/bin/bash
# Query follow_up tasks that are due now (status pending or sent_once,
# and follow_up_at <= current local time).
# Output: tab-separated rows with header.
set -euo pipefail

DB_FILE="./db/customer.db"

if [ ! -f "$DB_FILE" ]; then
  echo "❌ Database not found: $DB_FILE" >&2
  exit 1
fi

sqlite3 -header -separator $'\t' "$DB_FILE" \
  "SELECT id, peer, user_id_external, follow_up_at, reason, context_summary, status
   FROM follow_up
   WHERE status IN ('pending', 'sent_once')
     AND follow_up_at <= strftime('%Y-%m-%d %H:%M', 'now', 'localtime')
   ORDER BY follow_up_at ASC;"
