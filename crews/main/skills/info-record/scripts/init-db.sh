#!/usr/bin/env bash
# init-db.sh — Initialize info_record.db with intel_items table

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_DIR="$WORKSPACE_DIR/db"
DB_FILE="$DB_DIR/info_record.db"

mkdir -p "$DB_DIR"

sqlite3 "$DB_FILE" <<'SQL'
CREATE TABLE IF NOT EXISTS intel_items (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source        TEXT NOT NULL,
  source_type   TEXT NOT NULL,
  title         TEXT,
  author        TEXT,
  publish_date  TEXT,
  content       TEXT NOT NULL,
  created_at    TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);
SQL

echo '{"ok": true, "message": "info_record.db initialized"}'
