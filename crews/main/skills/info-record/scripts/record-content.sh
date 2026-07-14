#!/usr/bin/env bash
# record-content.sh — Insert an intel item into intel_items
# Usage: record-content.sh --source <> --source-type <> --title <> --author <> --publish-date <> --content <>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/info_record.db"

SOURCE=""
SOURCE_TYPE=""
TITLE=""
AUTHOR=""
PUBLISH_DATE=""
CONTENT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)       SOURCE="$2"; shift 2 ;;
    --source-type)  SOURCE_TYPE="$2"; shift 2 ;;
    --title)        TITLE="$2"; shift 2 ;;
    --author)       AUTHOR="$2"; shift 2 ;;
    --publish-date) PUBLISH_DATE="$2"; shift 2 ;;
    --content)      CONTENT="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$SOURCE" || -z "$SOURCE_TYPE" || -z "$CONTENT" ]]; then
  echo '{"ok": false, "error": "--source, --source-type, and --content are required"}'
  exit 1
fi

TITLE="${TITLE:-}"
AUTHOR="${AUTHOR:-}"
PUBLISH_DATE="${PUBLISH_DATE:-}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

# Escape single quotes for SQL
SOURCE_ESC="${SOURCE//\'/\'\'}"
TITLE_ESC="${TITLE//\'/\'\'}"
AUTHOR_ESC="${AUTHOR//\'/\'\'}"
CONTENT_ESC="${CONTENT//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO intel_items (source, source_type, title, author, publish_date, content) VALUES ('$SOURCE_ESC', '$SOURCE_TYPE', '$TITLE_ESC', '$AUTHOR_ESC', '$PUBLISH_DATE', '$CONTENT_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
