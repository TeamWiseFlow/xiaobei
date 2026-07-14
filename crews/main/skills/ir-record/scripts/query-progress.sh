#!/usr/bin/env bash
# query-progress.sh — Query all investors with status and last contact date
# Usage: query-progress.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_FILE="$WORKSPACE_DIR/db/ir_record.db"

if [[ ! -f "$DB_FILE" ]]; then
  echo '[]'
  exit 0
fi

sqlite3 -json "$DB_FILE" <<'EOF'
SELECT
  i.id,
  i.name,
  i.type,
  i.firm,
  i.title,
  i.email,
  i.status,
  i.match_score,
  i.focus_areas,
  i.updated_at,
  (SELECT contact_date FROM contacts c WHERE c.investor_id=i.id ORDER BY c.contact_date DESC LIMIT 1) AS last_contact_date,
  (SELECT next_step FROM contacts c WHERE c.investor_id=i.id ORDER BY c.contact_date DESC LIMIT 1) AS next_step
FROM investors i
WHERE i.status != 'passed'
ORDER BY
  CASE i.status
    WHEN 'ts' THEN 1
    WHEN 'dd' THEN 2
    WHEN 'meeting' THEN 3
    WHEN 'bp_sent' THEN 4
    WHEN 'contacted' THEN 5
    WHEN 'invested' THEN 6
    WHEN 'new' THEN 7
    ELSE 8
  END,
  i.updated_at DESC;
EOF
