#!/usr/bin/env bash
# query-stale.sh — Find investors with no recent contact (over N days)
# Usage: query-stale.sh --days <天数>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

DAYS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)  DAYS="$2"; shift 2 ;;
    *) echo '{"error": "Unknown argument: '"$1"'"}' ; exit 1 ;;
  esac
done

if [[ -z "$DAYS" ]]; then
  echo '{"error": "--days is required"}'
  exit 1
fi

if [[ ! -f "$DB_FILE" ]]; then
  echo '[]'
  exit 0
fi

sqlite3 -json "$DB_FILE" <<EOF
SELECT
  i.id,
  i.name,
  i.firm,
  i.status,
  i.match_score,
  i.updated_at,
  (SELECT contact_date FROM contacts c WHERE c.investor_id=i.id ORDER BY c.contact_date DESC LIMIT 1) AS last_contact_date,
  (SELECT next_step FROM contacts c WHERE c.investor_id=i.id ORDER BY c.contact_date DESC LIMIT 1) AS next_step,
  CAST(julianday('now','localtime') - julianday(COALESCE((SELECT contact_date FROM contacts c WHERE c.investor_id=i.id ORDER BY c.contact_date DESC LIMIT 1), i.created_at)) AS INTEGER) AS days_since_last
FROM investors i
WHERE i.status IN ('new','contacted','bp_sent','meeting','dd','ts')
  AND i.status != 'passed'
  AND i.status != 'invested'
  AND days_since_last >= $DAYS
ORDER BY days_since_last DESC;
EOF
