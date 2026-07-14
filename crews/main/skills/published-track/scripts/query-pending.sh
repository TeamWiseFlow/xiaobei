#!/usr/bin/env bash
# query-pending.sh — 查询所有待分发（distribute_status=0）的条目
# 返回 JSON 数组，每项包含 platform、source_folder、title、publish_url
#
# 用法:
#   query-pending.sh              # 查询所有平台待分发条目
#   query-pending.sh --platform wx_mp  # 只查某平台
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$ROOT/db/published_track.db"

# Self-heal stale schema: if a platform table is missing, run idempotent init-db.sh
# (CREATE TABLE IF NOT EXISTS) and re-check before treating the platform as unknown.
# Auto-adds tables for platforms introduced into init-db.sh after the DB was first created.
ensure_platform_table() {
  local table="pub_$1" found
  found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  if [ -z "$found" ]; then
    bash "$(dirname "$0")/init-db.sh" >/dev/null 2>&1 || true
    found=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$table';")
  fi
  [ -n "$found" ]
}

if [ ! -f "$DB" ]; then
  echo '[]'
  exit 0
fi

PLATFORM_FILTER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform) PLATFORM_FILTER="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

# 获取所有 pub_ 表
TABLES=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pub_%';")

if [ -n "$PLATFORM_FILTER" ]; then
  TABLES="pub_${PLATFORM_FILTER}"
  if ! ensure_platform_table "$PLATFORM_FILTER"; then
    echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM_FILTER\"}"
    exit 1
  fi
fi

# 输出 JSON 数组
echo "["
FIRST=true

for TABLE in $TABLES; do
  PLATFORM="${TABLE#pub_}"

  # 检查 distribute_status 列是否存在
  HAS_COL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM pragma_table_info('$TABLE') WHERE name='distribute_status';" 2>/dev/null || echo "0")
  if [ "$HAS_COL" -eq 0 ]; then
    continue
  fi

  # 查询 distribute_status = 0 的条目
  sqlite3 -separator "|" "$DB" "SELECT source_folder, title, publish_url FROM $TABLE WHERE distribute_status = 0;" 2>/dev/null | while IFS='|' read -r folder title url; do
    [ -z "$folder" ] && continue
    if [ "$FIRST" = true ]; then
      FIRST=false
    else
      echo ","
    fi
    # JSON 转义
    esc_folder="${folder//\"/\\\"}"
    esc_title="${title//\"/\\\"}"
    esc_url="${url//\"/\\\"}"
    printf '  {"platform":"%s","source_folder":"%s","title":"%s","publish_url":"%s"}' "$PLATFORM" "$esc_folder" "$esc_title" "$esc_url"
  done
done

echo ""
echo "]"
