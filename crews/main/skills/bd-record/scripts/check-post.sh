#!/usr/bin/env bash
# check-post.sh — Check if a post is already recorded in comment_posts
# Usage: check-post.sh --platform <平台> --post-url <帖子URL>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/bd_record.db"

PLATFORM=""
POST_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)  PLATFORM="$2"; shift 2 ;;
    --post-url)  POST_URL="$2"; shift 2 ;;
    *) echo '{"exists": false, "replied": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$POST_URL" ]]; then
  echo '{"exists": false, "replied": false, "error": "--platform and --post-url are required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"exists": false, "replied": false}'
  exit 0
fi

POST_URL_ESC="${POST_URL//\'/\'\'}"
RESULT=$(sqlite3 "$DB_FILE" "SELECT replied FROM comment_posts WHERE platform='$PLATFORM' AND post_url='$POST_URL_ESC' LIMIT 1;" 2>/dev/null || echo "")

if [[ -z "$RESULT" ]]; then
  echo '{"exists": false, "replied": false}'
elif [[ "$RESULT" == "1" ]]; then
  echo '{"exists": true, "replied": true}'
else
  echo '{"exists": true, "replied": false}'
fi
