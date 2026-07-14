#!/usr/bin/env bash
# record-application.sh — Insert a new application into applications table
# Usage: record-application.sh --name <> --type <> [--organizer <>] [--platform-url <>] ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

NAME=""
TYPE=""
ORGANIZER=""
PLATFORM_URL=""
DEADLINE=""
STATUS="planning"
SUBMITTED_DATE=""
RESULT=""
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)            NAME="$2"; shift 2 ;;
    --type)            TYPE="$2"; shift 2 ;;
    --organizer)       ORGANIZER="$2"; shift 2 ;;
    --platform-url)    PLATFORM_URL="$2"; shift 2 ;;
    --deadline)        DEADLINE="$2"; shift 2 ;;
    --status)          STATUS="$2"; shift 2 ;;
    --submitted-date)  SUBMITTED_DATE="$2"; shift 2 ;;
    --result)          RESULT="$2"; shift 2 ;;
    --notes)           NOTES="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$NAME" || -z "$TYPE" ]]; then
  echo '{"ok": false, "error": "--name and --type are required"}'
  exit 1
fi

STATUS="${STATUS:-planning}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

N_ESC="${NAME//\'/\'\'}"
T_ESC="${TYPE//\'/\'\'}"
O_ESC="${ORGANIZER//\'/\'\'}"
PU_ESC="${PLATFORM_URL//\'/\'\'}"
DL_ESC="${DEADLINE//\'/\'\'}"
ST_ESC="${STATUS//\'/\'\'}"
SD_ESC="${SUBMITTED_DATE//\'/\'\'}"
R_ESC="${RESULT//\'/\'\'}"
NT_ESC="${NOTES//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO applications (name, type, organizer, platform_url, deadline, status, submitted_date, result, notes)
VALUES ('$N_ESC', '$T_ESC', '$O_ESC', '$PU_ESC', '$DL_ESC', '$ST_ESC', '$SD_ESC', '$R_ESC', '$NT_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
