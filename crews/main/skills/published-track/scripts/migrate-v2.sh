#!/usr/bin/env bash
# migrate-v2.sh — 迁移到 v2 schema
#   1. 为所有表添加 distribute_status 字段 (INTEGER NOT NULL DEFAULT 0)
#   2. 去除 source_folder 的 UNIQUE 约束（重建表）
#   3. 设置已有记录的 distribute_status：
#      - wx_mp 最近一篇 = 0（待分发），其余 = 1（无需分发）
#      - 其他平台所有记录 = 1（无需分发）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$ROOT/db/published_track.db"

if [ ! -f "$DB" ]; then
  echo '{"ok":false,"error":"database not found, run init-db.sh first"}'
  exit 1
fi

echo "🔄 迁移 published_track.db → v2 schema..."

# 获取所有 pub_ 表
TABLES=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pub_%';")

for TABLE in $TABLES; do
  PLATFORM="${TABLE#pub_}"
  echo "  处理 $TABLE ..."

  # 检查 distribute_status 列是否已存在
  HAS_COL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM pragma_table_info('$TABLE') WHERE name='distribute_status';")
  if [ "$HAS_COL" -eq 0 ]; then
    # 添加 distribute_status 列
    sqlite3 "$DB" "ALTER TABLE $TABLE ADD COLUMN distribute_status INTEGER NOT NULL DEFAULT 0;"
    echo "    ✓ 添加 distribute_status 列"
  else
    echo "    - distribute_status 列已存在，跳过"
  fi

  # 检查 source_folder 是否有 UNIQUE 约束
  # SQLite 不支持 ALTER TABLE DROP CONSTRAINT，需要重建表
  HAS_UNIQUE=$(sqlite3 "$DB" "SELECT sql FROM sqlite_master WHERE type='table' AND name='$TABLE';" | grep -c "source_folder.*UNIQUE" || true)
  if [ "$HAS_UNIQUE" -gt 0 ]; then
    echo "    ⚠️  $TABLE 的 source_folder 有 UNIQUE 约束，需要重建表..."

    # 获取建表 SQL，去掉 UNIQUE
    OLD_SQL=$(sqlite3 "$DB" "SELECT sql FROM sqlite_master WHERE type='table' AND name='$TABLE';")
    NEW_SQL=$(echo "$OLD_SQL" | sed 's/source_folder TEXT NOT NULL UNIQUE/source_folder TEXT NOT NULL/')

    # 重建表（SQLite 标准 procedure）
    TEMP_TABLE="${TABLE}_migrate_temp"
    sqlite3 "$DB" <<EOF
CREATE TABLE $TEMP_TABLE AS SELECT * FROM $TABLE;
DROP TABLE $TABLE;
$NEW_SQL;
INSERT INTO $TABLE SELECT * FROM $TEMP_TABLE;
DROP TABLE $TEMP_TABLE;
EOF
    echo "    ✓ 重建表完成，UNIQUE 约束已移除"
  else
    echo "    - source_folder 无 UNIQUE 约束，跳过"
  fi
done

# 设置已有记录的 distribute_status
# wx_mp: 最近一篇 = 0（待分发测试），其余 = 1
echo ""
echo "  设置已有记录的 distribute_status..."

# wx_mp 最近一篇设为 0
WX_LATEST_ID=$(sqlite3 "$DB" "SELECT id FROM pub_wx_mp ORDER BY created_at DESC LIMIT 1;" 2>/dev/null || echo "")
if [ -n "$WX_LATEST_ID" ]; then
  sqlite3 "$DB" "UPDATE pub_wx_mp SET distribute_status = 1 WHERE id != $WX_LATEST_ID;"
  sqlite3 "$DB" "UPDATE pub_wx_mp SET distribute_status = 0 WHERE id = $WX_LATEST_ID;"
  echo "    ✓ pub_wx_mp: id=$WX_LATEST_ID → 0(待分发), 其余 → 1(无需分发)"
else
  echo "    - pub_wx_mp 无记录，跳过"
fi

# 其他平台所有记录设为 1
for TABLE in $TABLES; do
  PLATFORM="${TABLE#pub_}"
  [ "$PLATFORM" = "wx_mp" ] && continue
  CNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM $TABLE;" 2>/dev/null || echo "0")
  if [ "$CNT" -gt 0 ]; then
    sqlite3 "$DB" "UPDATE $TABLE SET distribute_status = 1;"
    echo "    ✓ $TABLE: $CNT 条记录 → 1(无需分发)"
  fi
done

echo ""
echo '{"ok":true,"message":"migrated to v2: distribute_status added, source_folder UNIQUE removed, existing records updated"}'
