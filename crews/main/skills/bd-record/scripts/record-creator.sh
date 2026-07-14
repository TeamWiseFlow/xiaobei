#!/usr/bin/env bash
# record-creator.sh — Insert a creator record into lead_creators
# Usage: record-creator.sh --platform <> --creator-id <> --nickname <> --homepage-url <> --qualified <0|1> --notes <>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/bd_record.db"

PLATFORM=""
CREATOR_ID=""
NICKNAME=""
HOMEPAGE_URL=""
QUALIFIED=""
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)      PLATFORM="$2"; shift 2 ;;
    --creator-id)    CREATOR_ID="$2"; shift 2 ;;
    --nickname)      NICKNAME="$2"; shift 2 ;;
    --homepage-url)  HOMEPAGE_URL="$2"; shift 2 ;;
    --qualified)     QUALIFIED="$2"; shift 2 ;;
    --notes)         NOTES="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$CREATOR_ID" || -z "$HOMEPAGE_URL" ]]; then
  echo '{"ok": false, "error": "--platform, --creator-id, and --homepage-url are required"}'
  exit 1
fi

QUALIFIED="${QUALIFIED:-0}"
NOTES="${NOTES:-}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

# Escape single quotes for SQL
NICKNAME_ESC="${NICKNAME//\'/\'\'}"
NOTES_ESC="${NOTES//\'/\'\'}"
HOMEPAGE_URL_ESC="${HOMEPAGE_URL//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO lead_creators (platform, creator_id, nickname, homepage_url, qualified, notes) VALUES ('$PLATFORM', '$CREATOR_ID', '$NICKNAME_ESC', '$HOMEPAGE_URL_ESC', $QUALIFIED, '$NOTES_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
