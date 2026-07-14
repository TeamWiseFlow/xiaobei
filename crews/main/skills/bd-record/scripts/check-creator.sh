#!/usr/bin/env bash
# check-creator.sh — Check if a creator is already recorded in lead_creators
# Usage: check-creator.sh --platform <平台> --creator-id <创作者ID>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/bd_record.db"

PLATFORM=""
CREATOR_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)    PLATFORM="$2"; shift 2 ;;
    --creator-id)  CREATOR_ID="$2"; shift 2 ;;
    *) echo '{"exists": false, "error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$CREATOR_ID" ]]; then
  echo '{"exists": false, "error": "--platform and --creator-id are required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '{"exists": false}'
  exit 0
fi

COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM lead_creators WHERE platform='$PLATFORM' AND creator_id='$CREATOR_ID';" 2>/dev/null || echo "0")

if [[ "$COUNT" -gt 0 ]]; then
  echo '{"exists": true}'
else
  echo '{"exists": false}'
fi
