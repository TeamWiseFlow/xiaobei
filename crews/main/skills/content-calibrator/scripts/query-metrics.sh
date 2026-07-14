#!/usr/bin/env bash
# query-metrics.sh — 从 published-track DB 查询某篇内容的互动指标
# 用法: query-metrics.sh --platform <platform> --source-folder <folder>
# platform 对应 published-track 的平台 ID（wx_mp/xhs/zhihu/bilibili/douyin/kuaishou/toutiao/juejin/twitter/facebook/instagram/tiktok/youtube/pinterest/threads/wxwork_moments）
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"
DB="$WORKSPACE/db/published_track.db"

PLATFORM=""
SOURCE_FOLDER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)      PLATFORM="$2"; shift 2 ;;
    --source-folder) SOURCE_FOLDER="$2"; shift 2 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

if [[ -z "$PLATFORM" || -z "$SOURCE_FOLDER" ]]; then
  echo "用法: query-metrics.sh --platform <platform> --source-folder <folder>"
  echo "  platform: wx_mp | wx_channel | xhs | zhihu | bilibili | douyin | kuaishou | toutiao | juejin | twitter | facebook | instagram | tiktok | youtube | pinterest | threads | wxwork_moments"
  exit 1
fi

if [[ ! -f "$DB" ]]; then
  echo "❌ published-track DB 不存在: $DB"
  echo "   先运行 published-track 的 init-db.sh"
  exit 1
fi

TABLE="pub_${PLATFORM}"

# 检查表是否存在
table_exists=$(sqlite3 "$DB" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$TABLE';")
if [[ "$table_exists" -eq 0 ]]; then
  echo "❌ 平台表不存在: $TABLE"
  exit 1
fi

# 查询
result=$(sqlite3 -header -column "$DB" "SELECT * FROM $TABLE WHERE source_folder='$SOURCE_FOLDER';")

if [[ -z "$result" ]]; then
  echo "⚠️  未找到记录: platform=$PLATFORM, source_folder=$SOURCE_FOLDER"
  exit 0
fi

echo "$result"
