#!/usr/bin/env bash
# record-contact.sh — Insert a contact record into contacts table
# Usage: record-contact.sh --investor-id <> --contact-type <> --direction <> --summary <> --contact-date <> [--result <>] [--next-step <>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

INVESTOR_ID=""
CONTACT_TYPE=""
DIRECTION=""
SUMMARY=""
RESULT=""
NEXT_STEP=""
CONTACT_DATE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --investor-id)   INVESTOR_ID="$2"; shift 2 ;;
    --contact-type)  CONTACT_TYPE="$2"; shift 2 ;;
    --direction)     DIRECTION="$2"; shift 2 ;;
    --summary)       SUMMARY="$2"; shift 2 ;;
    --result)        RESULT="$2"; shift 2 ;;
    --next-step)     NEXT_STEP="$2"; shift 2 ;;
    --contact-date)  CONTACT_DATE="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$INVESTOR_ID" || -z "$CONTACT_TYPE" || -z "$DIRECTION" || -z "$SUMMARY" || -z "$CONTACT_DATE" ]]; then
  echo '{"ok": false, "error": "--investor-id, --contact-type, --direction, --summary, and --contact-date are required"}'
  exit 1
fi

RESULT="${RESULT:-}"
NEXT_STEP="${NEXT_STEP:-}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

# Escape single quotes for SQL
CT_ESC="${CONTACT_TYPE//\'/\'\'}"
D_ESC="${DIRECTION//\'/\'\'}"
S_ESC="${SUMMARY//\'/\'\'}"
R_ESC="${RESULT//\'/\'\'}"
NS_ESC="${NEXT_STEP//\'/\'\'}"
CD_ESC="${CONTACT_DATE//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO contacts (investor_id, contact_type, direction, summary, result, next_step, contact_date)
VALUES ($INVESTOR_ID, '$CT_ESC', '$D_ESC', '$S_ESC', '$R_ESC', '$NS_ESC', '$CD_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
