#!/bin/bash
# Insert a new follow_up task for a customer.
set -euo pipefail

DB_FILE="./db/customer.db"

PEER=""
USER_ID_EXTERNAL=""
FOLLOW_UP_AT=""
REASON=""
CONTEXT_SUMMARY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --peer)              PEER="${2:-}";             shift 2 ;;
    --user-id-external)  USER_ID_EXTERNAL="${2:-}"; shift 2 ;;
    --follow-up-at)      FOLLOW_UP_AT="${2:-}";     shift 2 ;;
    --reason)            REASON="${2:-}";            shift 2 ;;
    --context-summary)   CONTEXT_SUMMARY="${2:-}";  shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

for REQUIRED_VAR in PEER USER_ID_EXTERNAL FOLLOW_UP_AT REASON; do
  eval VAL=\$$REQUIRED_VAR
  if [ -z "$VAL" ]; then
    echo "❌ --$(echo "$REQUIRED_VAR" | tr '[:upper:]' '[:lower:]' | tr '_' '-') is required" >&2
    exit 1
  fi
done

if [ ! -f "$DB_FILE" ]; then
  echo "❌ Database not found: $DB_FILE" >&2
  exit 1
fi

sql_quote() {
  printf '%s' "$1" | sed "s/'/''/g"
}

sqlite3 "$DB_FILE" \
  "INSERT INTO follow_up (peer, user_id_external, follow_up_at, reason, context_summary)
   VALUES (
     '$(sql_quote "$PEER")',
     '$(sql_quote "$USER_ID_EXTERNAL")',
     '$(sql_quote "$FOLLOW_UP_AT")',
     '$(sql_quote "$REASON")',
     '$(sql_quote "$CONTEXT_SUMMARY")'
   );"

echo "✅ follow_up created for peer: $PEER (follow_up_at: $FOLLOW_UP_AT)"
