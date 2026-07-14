#!/usr/bin/env bash
# record-investor.sh — Insert a new investor into investors table
# Usage: record-investor.sh --name <> --type <> --firm <> [--title <>] [--email <>] ...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

NAME=""
TYPE=""
FIRM=""
TITLE=""
EMAIL=""
PHONE=""
WECHAT=""
LINKEDIN=""
SOURCE=""
FOCUS_AREAS=""
MATCH_SCORE=""
STATUS="new"
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)         NAME="$2"; shift 2 ;;
    --type)         TYPE="$2"; shift 2 ;;
    --firm)         FIRM="$2"; shift 2 ;;
    --title)        TITLE="$2"; shift 2 ;;
    --email)        EMAIL="$2"; shift 2 ;;
    --phone)        PHONE="$2"; shift 2 ;;
    --wechat)       WECHAT="$2"; shift 2 ;;
    --linkedin)     LINKEDIN="$2"; shift 2 ;;
    --source)       SOURCE="$2"; shift 2 ;;
    --focus-areas)  FOCUS_AREAS="$2"; shift 2 ;;
    --match-score)  MATCH_SCORE="$2"; shift 2 ;;
    --status)       STATUS="$2"; shift 2 ;;
    --notes)        NOTES="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$NAME" || -z "$TYPE" || -z "$FIRM" ]]; then
  echo '{"ok": false, "error": "--name, --type, and --firm are required"}'
  exit 1
fi

STATUS="${STATUS:-new}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

# Escape single quotes for SQL
N_ESC="${NAME//\'/\'\'}"
T_ESC="${TYPE//\'/\'\'}"
F_ESC="${FIRM//\'/\'\'}"
TI_ESC="${TITLE//\'/\'\'}"
E_ESC="${EMAIL//\'/\'\'}"
P_ESC="${PHONE//\'/\'\'}"
W_ESC="${WECHAT//\'/\'\'}"
L_ESC="${LINKEDIN//\'/\'\'}"
S_ESC="${SOURCE//\'/\'\'}"
FA_ESC="${FOCUS_AREAS//\'/\'\'}"
MS_ESC="${MATCH_SCORE//\'/\'\'}"
ST_ESC="${STATUS//\'/\'\'}"
NT_ESC="${NOTES//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO investors (name, type, firm, title, email, phone, wechat, linkedin, source, focus_areas, match_score, status, notes)
VALUES ('$N_ESC', '$T_ESC', '$F_ESC', '$TI_ESC', '$E_ESC', '$P_ESC', '$W_ESC', '$L_ESC', '$S_ESC', '$FA_ESC', '$MS_ESC', '$ST_ESC', '$NT_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
