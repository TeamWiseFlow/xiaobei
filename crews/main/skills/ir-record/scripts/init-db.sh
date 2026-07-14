#!/usr/bin/env bash
# init-db.sh — Initialize ir_record.db with investors and contacts tables

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_DIR="$WORKSPACE_DIR/db"
DB_FILE="$DB_DIR/ir_record.db"

mkdir -p "$DB_DIR"

sqlite3 "$DB_FILE" <<'SQL'
CREATE TABLE IF NOT EXISTS investors (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  type        TEXT NOT NULL,
  firm        TEXT NOT NULL,
  title       TEXT,
  email       TEXT,
  phone       TEXT,
  wechat      TEXT,
  linkedin    TEXT,
  source      TEXT,
  focus_areas TEXT,
  match_score TEXT,
  status      TEXT NOT NULL DEFAULT 'new',
  notes       TEXT,
  created_at  TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at  TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

CREATE TABLE IF NOT EXISTS contacts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  investor_id  INTEGER NOT NULL,
  contact_type TEXT NOT NULL,
  direction    TEXT NOT NULL,
  summary      TEXT NOT NULL,
  result       TEXT,
  next_step    TEXT,
  contact_date TEXT NOT NULL,
  created_at   TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  FOREIGN KEY (investor_id) REFERENCES investors(id)
);

CREATE TABLE IF NOT EXISTS applications (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL,
  type           TEXT NOT NULL,
  organizer      TEXT,
  platform_url   TEXT,
  deadline       TEXT,
  status         TEXT NOT NULL DEFAULT 'planning',
  submitted_date TEXT,
  result         TEXT,
  notes          TEXT,
  created_at     TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at     TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);
SQL

echo '{"ok": true, "message": "ir_record.db initialized"}'
