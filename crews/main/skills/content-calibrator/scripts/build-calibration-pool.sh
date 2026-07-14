#!/usr/bin/env bash
# build-calibration-pool.sh — 构建全局校准池（per-work 归集）
# 递归扫描 output_articles/**/calibration/score.json 与 output_videos/**/calibration/score.json，
# 关联 published-track DB 各平台表的互动指标，输出供复盘和 bump 使用的校准池。
# 用法: build-calibration-pool.sh
set -euo pipefail

WORKSPACE="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )/../../.." &> /dev/null && pwd )"
DB="$WORKSPACE/db/published_track.db"

if [[ ! -f "$DB" ]]; then
  echo "❌ published-track DB 不存在: $DB"
  echo "   先运行 ./skills/published-track/scripts/init-db.sh"
  exit 1
fi

echo "📊 构建全局校准池（per-work）..."
echo ""

# 平台 → 主指标字段映射
declare -A METRIC_FIELD
METRIC_FIELD[wx_mp]="reads"
METRIC_FIELD[wx_channel]="plays"
METRIC_FIELD[xhs]="views"
METRIC_FIELD[zhihu]="views"
METRIC_FIELD[bilibili]="plays"
METRIC_FIELD[douyin]="plays"
METRIC_FIELD[kuaishou]="plays"
METRIC_FIELD[toutiao]="reads"
METRIC_FIELD[youtube]="views"

count=0
for kind in output_articles output_videos; do
  while IFS= read -r score_json; do
    [[ -f "$score_json" ]] || continue
    # work_rel = score.json 所在 calibration/ 的父目录，相对 WORKSPACE（即 --source-folder / DB source_folder）
    work_abs="$(cd "$(dirname "$score_json")/.." && pwd)"
    work_rel="${work_abs#$WORKSPACE/}"
    composite=$(python3 -c "import json; print(json.load(open('$score_json')).get('composite','?'))" 2>/dev/null || echo "?")
    rubric=$(python3 -c "import json; print(json.load(open('$score_json')).get('rubric_version','?'))" 2>/dev/null || echo "?")

    echo "── $work_rel (composite=$composite, rubric=$rubric) ──"
    for p in "${!METRIC_FIELD[@]}"; do
      table="pub_$p"
      metric="${METRIC_FIELD[$p]}"
      texists=$(sqlite3 "$DB" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='$table';" 2>/dev/null || echo 0)
      [[ "$texists" -eq 1 ]] || continue
      sqlite3 -separator "|" "$DB" \
        "SELECT publish_date, COALESCE($metric,0) FROM $table WHERE source_folder='$work_rel' AND COALESCE($metric,0)>0 ORDER BY publish_date DESC LIMIT 1;" 2>/dev/null | while IFS='|' read -r d m; do
        echo "    $p: $m ($d)"
      done
    done
    count=$((count + 1))
  done < <(find "$WORKSPACE/$kind" -type f -name score.json -path '*/calibration/score.json' 2>/dev/null)
done

echo ""
echo "---"
echo "校准池总计: $count 个作品（有 score.json）"
