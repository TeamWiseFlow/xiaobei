#!/bin/bash
# Update cs_record fields (purpose, prompt_source).
# Never overwrites an existing value with an empty string.
set -euo pipefail

DB_FILE="./db/customer.db"

PEER=""
PURPOSE=""
PROMPT_SOURCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --peer)           PEER="${2:-}";          shift 2 ;;
    --purpose)        PURPOSE="${2:-}";       shift 2 ;;
    --prompt-source)  PROMPT_SOURCE="${2:-}"; shift 2 ;;
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

# Build SET clause — only include non-empty values
SET_PARTS=""

if [ -n "$PURPOSE" ]; then
  SET_PARTS="${SET_PARTS}purpose='$(sql_quote "$PURPOSE")', "
fi

if [ -n "$PROMPT_SOURCE" ]; then
  SET_PARTS="${SET_PARTS}prompt_source='$(sql_quote "$PROMPT_SOURCE")', "
fi

if [ -z "$SET_PARTS" ]; then
  echo "⚠️  Nothing to update (all provided values are empty, skipping)"
  exit 0
fi

# Always bump updated_at
SET_PARTS="${SET_PARTS}updated_at=strftime('%Y-%m-%d %H:%M:%S','now','localtime')"

sqlite3 "$DB_FILE" \
  "UPDATE cs_record SET ${SET_PARTS} WHERE peer='$(sql_quote "$PEER")';"

echo "✅ cs_record updated for peer: $PEER"
