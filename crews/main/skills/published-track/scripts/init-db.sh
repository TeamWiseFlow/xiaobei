#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$ROOT/db/published_track.db"

mkdir -p "$ROOT/db"

sqlite3 "$DB" <<'SQL'

-- 微信公众号
CREATE TABLE IF NOT EXISTS pub_wx_mp (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  reads INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 知乎
CREATE TABLE IF NOT EXISTS pub_zhihu (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  upvotes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- B站
CREATE TABLE IF NOT EXISTS pub_bilibili (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  plays INTEGER DEFAULT 0,
  danmaku INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  coins INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 抖音
CREATE TABLE IF NOT EXISTS pub_douyin (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  plays INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  deep_metrics TEXT,
  deep_captured_at TEXT,
  deep_source TEXT,
  favorites INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 快手
CREATE TABLE IF NOT EXISTS pub_kuaishou (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  plays INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 小红书
CREATE TABLE IF NOT EXISTS pub_xhs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  deep_metrics TEXT,
  deep_captured_at TEXT,
  deep_source TEXT,
  fan_portrait TEXT,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 今日头条
CREATE TABLE IF NOT EXISTS pub_toutiao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  impressions INTEGER DEFAULT 0,
  reads INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 掘金
CREATE TABLE IF NOT EXISTS pub_juejin (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- Twitter/X
CREATE TABLE IF NOT EXISTS pub_twitter (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  retweets INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  bookmarks INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- Facebook
CREATE TABLE IF NOT EXISTS pub_facebook (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  reach INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- Instagram
CREATE TABLE IF NOT EXISTS pub_instagram (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  reach INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  saves INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- TikTok
CREATE TABLE IF NOT EXISTS pub_tiktok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  plays INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- YouTube
CREATE TABLE IF NOT EXISTS pub_youtube (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- Pinterest
CREATE TABLE IF NOT EXISTS pub_pinterest (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  impressions INTEGER DEFAULT 0,
  saves INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- Threads
CREATE TABLE IF NOT EXISTS pub_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  replies INTEGER DEFAULT 0,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

-- 微信视频号
CREATE TABLE IF NOT EXISTS pub_wx_channel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK(content_type IN ('article','video','post')),
  source_folder TEXT NOT NULL,
  publish_url TEXT,
  publish_date TEXT NOT NULL,
  distribute_status INTEGER NOT NULL DEFAULT 0,
  plays INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  favorites INTEGER DEFAULT 0,
  top_comment TEXT,
  notes TEXT,
  dna_id TEXT,
  account TEXT,
  perf_evaluated INTEGER DEFAULT 0,
  cal_enabled INTEGER DEFAULT 0,
  cal_score_er INTEGER,
  cal_score_hp INTEGER,
  cal_score_sr INTEGER,
  cal_score_ql INTEGER,
  cal_score_na INTEGER,
  cal_score_ab INTEGER,
  cal_score_pv INTEGER,
  cal_composite REAL,
  cal_rubric_version TEXT,
  cal_scored_at TEXT,
  cal_bias_signals TEXT,
  cal_bump_evaluated INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')),
  updated_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime'))
);

SQL

# ── 迁移：为已有表补 cal_bias_signals / cal_bump_evaluated 列 ──────────────
# CREATE TABLE IF NOT EXISTS 不会给已存在的表加列，需显式 ALTER。
for table in $(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pub_%'"); do
  has_col=$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='cal_bias_signals'")
  if [ "$has_col" = "0" ]; then
    sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN cal_bias_signals TEXT;"
  fi
  has_col=$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='cal_bump_evaluated'")
  if [ "$has_col" = "0" ]; then
    sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN cal_bump_evaluated INTEGER DEFAULT 0;"
  fi
  # v3：数据直连 DNA（dna_id / account / perf_evaluated）
  has_col=$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='dna_id'")
  if [ "$has_col" = "0" ]; then
    sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN dna_id TEXT;"
  fi
  has_col=$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='account'")
  if [ "$has_col" = "0" ]; then
    sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN account TEXT;"
  fi
  has_col=$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='perf_evaluated'")
  if [ "$has_col" = "0" ]; then
    sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN perf_evaluated INTEGER DEFAULT 0;"
  fi
done

# ── 迁移：创作侧深指标列（deep_metrics / deep_captured_at / deep_source）──
# 只存最新值，不留历史快照（用户 2026-09-18 定调：不需要增长史）。
for table in pub_douyin pub_xhs; do
  if [ "$(sqlite3 "$DB" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$table';")" = "1" ]; then
    for column in deep_metrics deep_captured_at deep_source; do
      if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('$table') WHERE name='$column';")" = "0" ]; then
        sqlite3 "$DB" "ALTER TABLE $table ADD COLUMN $column TEXT;"
      fi
    done
  fi
done

# 单篇作品受众画像：完整保留 Creator 响应 data 的 JSON，只在有数据时更新。
if [ "$(sqlite3 "$DB" "SELECT count(*) FROM pragma_table_info('pub_xhs') WHERE name='fan_portrait';")" = "0" ]; then
  sqlite3 "$DB" "ALTER TABLE pub_xhs ADD COLUMN fan_portrait TEXT;"
fi

echo '{"ok":true,"message":"published_track.db initialized (v6: xhs fan_portrait)"}'
