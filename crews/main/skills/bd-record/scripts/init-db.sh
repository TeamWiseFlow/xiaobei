#!/usr/bin/env bash
# init-db.sh — Initialize bd_record.db with lead_creators and comment_posts tables

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DB_DIR="$WORKSPACE_DIR/db"
DB_FILE="$DB_DIR/bd_record.db"

mkdir -p "$DB_DIR"

sqlite3 "$DB_FILE" <<'SQL'
CREATE TABLE IF NOT EXISTS lead_creators (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  platform      TEXT NOT NULL,
  creator_id    TEXT NOT NULL,
  nickname      TEXT,
  homepage_url  TEXT NOT NULL,
  qualified     INTEGER DEFAULT 0,
  notes         TEXT,
  created_at    TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

CREATE TABLE IF NOT EXISTS comment_posts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  platform         TEXT NOT NULL,
  post_title       TEXT,
  post_url         TEXT NOT NULL,
  strategy         TEXT NOT NULL,
  replied          INTEGER DEFAULT 0,
  reply_content    TEXT,
  reply_target_id  TEXT,
  created_at       TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);
SQL

echo '{"ok": true, "message": "bd_record.db initialized"}'
