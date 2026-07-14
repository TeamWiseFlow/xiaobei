#!/usr/bin/env bash
# record-post.sh — Insert a post engagement record into comment_posts
# Usage: record-post.sh --platform <> --post-title <> --post-url <> --strategy <> --reply-content <> --reply-target-id <>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/bd_record.db"

PLATFORM=""
POST_TITLE=""
POST_URL=""
STRATEGY=""
REPLY_CONTENT=""
REPLY_TARGET_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)         PLATFORM="$2"; shift 2 ;;
    --post-title)       POST_TITLE="$2"; shift 2 ;;
    --post-url)         POST_URL="$2"; shift 2 ;;
    --strategy)         STRATEGY="$2"; shift 2 ;;
    --reply-content)    REPLY_CONTENT="$2"; shift 2 ;;
    --reply-target-id)  REPLY_TARGET_ID="$2"; shift 2 ;;
    *) echo '{"ok": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$POST_URL" || -z "$STRATEGY" ]]; then
  echo '{"ok": false, "error": "--platform, --post-url, and --strategy are required"}'
  exit 1
fi

POST_TITLE="${POST_TITLE:-}"
REPLY_CONTENT="${REPLY_CONTENT:-}"
REPLY_TARGET_ID="${REPLY_TARGET_ID:-}"

# Ensure DB and tables exist
bash "$SCRIPT_DIR/init-db.sh" > /dev/null

# Escape single quotes for SQL
POST_TITLE_ESC="${POST_TITLE//\'/\'\'}"
POST_URL_ESC="${POST_URL//\'/\'\'}"
REPLY_CONTENT_ESC="${REPLY_CONTENT//\'/\'\'}"
REPLY_TARGET_ID_ESC="${REPLY_TARGET_ID//\'/\'\'}"

NEW_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO comment_posts (platform, post_title, post_url, strategy, replied, reply_content, reply_target_id) VALUES ('$PLATFORM', '$POST_TITLE_ESC', '$POST_URL_ESC', '$STRATEGY', 1, '$REPLY_CONTENT_ESC', '$REPLY_TARGET_ID_ESC');
SELECT last_insert_rowid();
EOF
)
echo "{\"ok\": true, \"id\": $NEW_ID}"
