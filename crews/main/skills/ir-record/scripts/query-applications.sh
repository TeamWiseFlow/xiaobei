#!/usr/bin/env bash
# query-applications.sh — Query application records
# Usage: query-applications.sh [--status <状态>] [--upcoming <天数>]
#   --upcoming: 查询未来 N 天内截止的申报

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

STATUS_FILTER=""
UPCOMING_DAYS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status)    STATUS_FILTER="$2"; shift 2 ;;
    --upcoming)  UPCOMING_DAYS="$2"; shift 2 ;;
    *) echo '[]' ; exit 1 ;;
  esac
done

if [[ ! -f "$DB_FILE" ]]; then
  echo '[]'
  exit 0
fi

if [[ -n "$UPCOMING_DAYS" ]]; then
  UPCOMING_ESC="${UPCOMING_DAYS//\'/\'\'}"
  sqlite3 -json "$DB_FILE" <<EOF
SELECT id, name, type, organizer, platform_url, deadline, status, submitted_date, result, notes, created_at, updated_at
FROM applications
WHERE deadline IS NOT NULL
  AND deadline >= date('now','localtime')
  AND deadline <= date('now','localtime','+${UPCOMING_ESC} days')
  AND status NOT IN ('passed','rejected')
ORDER BY deadline ASC;
EOF
elif [[ -n "$STATUS_FILTER" ]]; then
  SF_ESC="${STATUS_FILTER//\'/\'\'}"
  sqlite3 -json "$DB_FILE" <<EOF
SELECT id, name, type, organizer, platform_url, deadline, status, submitted_date, result, notes, created_at, updated_at
FROM applications
WHERE status = '$SF_ESC'
ORDER BY updated_at DESC;
EOF
else
  sqlite3 -json "$DB_FILE" <<'EOF'
SELECT id, name, type, organizer, platform_url, deadline, status, submitted_date, result, notes, created_at, updated_at
FROM applications
ORDER BY
  CASE status
    WHEN 'planning' THEN 1
    WHEN 'drafting' THEN 2
    WHEN 'submitted' THEN 3
    WHEN 'shortlisted' THEN 4
    WHEN 'awarded' THEN 5
    WHEN 'rejected' THEN 6
    WHEN 'passed' THEN 7
    ELSE 8
  END,
  deadline ASC;
EOF
fi
