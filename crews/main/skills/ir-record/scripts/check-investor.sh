#!/usr/bin/env bash
# check-investor.sh — Check if an investor is already recorded (by name + firm)
# Usage: check-investor.sh --name <姓名> --firm <机构名>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

NAME=""
FIRM=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)  NAME="$2"; shift 2 ;;
    --firm)  FIRM="$2"; shift 2 ;;
    *) echo '{"exists": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$NAME" || -z "$FIRM" ]]; then
  echo '{"exists": false, "error": "--name and --firm are required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"exists": false, "id": null}'
  exit 0
fi

NAME_ESC="${NAME//\'/\'\'}"
FIRM_ESC="${FIRM//\'/\'\'}"

RESULT=$(sqlite3 "$DB_FILE" "SELECT id FROM investors WHERE name='$NAME_ESC' AND firm='$FIRM_ESC' LIMIT 1;" 2>/dev/null || echo "")

if [[ -n "$RESULT" ]]; then
  echo "{\"exists\": true, \"id\": $RESULT}"
else
  echo '{"exists": false, "id": null}'
fi
