#!/usr/bin/env bash
# check-contact.sh — Check recent contacts for an investor
# Usage: check-contact.sh --investor-id <ID> --days <天数>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

INVESTOR_ID=""
DAYS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --investor-id)  INVESTOR_ID="$2"; shift 2 ;;
    --days)         DAYS="$2"; shift 2 ;;
    *) echo '{"has_recent": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$INVESTOR_ID" || -z "$DAYS" ]]; then
  echo '{"has_recent": false, "error": "--investor-id and --days are required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"has_recent": false, "last_contact_date": null}'
  exit 0
fi

RESULT=$(sqlite3 "$DB_FILE" <<EOF
SELECT contact_date FROM contacts
WHERE investor_id=$INVESTOR_ID
  AND contact_date >= date('now','localtime','-$DAYS days')
ORDER BY contact_date DESC LIMIT 1;
EOF
)

if [[ -n "$RESULT" ]]; then
  echo "{\"has_recent\": true, \"last_contact_date\": \"$RESULT\"}"
else
  echo '{"has_recent": false, "last_contact_date": null}'
fi
