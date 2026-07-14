#!/usr/bin/env bash
# check-application.sh — Check if an application is already recorded (by name + organizer)
# Usage: check-application.sh --name <项目名> --organizer <主办方>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

NAME=""
ORGANIZER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)       NAME="$2"; shift 2 ;;
    --organizer)  ORGANIZER="$2"; shift 2 ;;
    *) echo '{"exists": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$NAME" ]]; then
  echo '{"exists": false, "error": "--name is required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"exists": false, "id": null}'
  exit 0
fi

NAME_ESC="${NAME//\'/\'\'}"
ORGANIZER_ESC="${ORGANIZER//\'/\'\'}"

if [[ -n "$ORGANIZER" ]]; then
  RESULT=$(sqlite3 "$DB_FILE" "SELECT id FROM applications WHERE name='$NAME_ESC' AND organizer='$ORGANIZER_ESC' LIMIT 1;" 2>/dev/null || echo "")
else
  RESULT=$(sqlite3 "$DB_FILE" "SELECT id FROM applications WHERE name='$NAME_ESC' LIMIT 1;" 2>/dev/null || echo "")
fi

if [[ -n "$RESULT" ]]; then
  echo "{\"exists\": true, \"id\": $RESULT}"
else
  echo '{"exists": false, "id": null}'
fi
