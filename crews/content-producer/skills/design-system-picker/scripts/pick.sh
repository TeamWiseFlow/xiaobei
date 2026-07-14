#!/usr/bin/env bash
# design-system-picker — 根据风格描述从设计系统库中匹配最合适的设计系统
# 用法: ./skills/design-system-picker/scripts/pick.sh "<风格描述>"
# 示例: ./skills/design-system-picker/scripts/pick.sh "科技感暗色主题"

set -euo pipefail

QUERY="${1:?用法: pick.sh <风格描述>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEMS_DIR="${SCRIPT_DIR}/../design-systems"
INDEX_FILE="${SYSTEMS_DIR}/index.json"

if [ ! -f "$INDEX_FILE" ]; then
  echo "❌ 设计系统索引文件不存在: ${INDEX_FILE}"
  exit 1
fi

echo "🔍 搜索风格: ${QUERY}"
echo ""
echo "=== 可用设计系统 ==="

# 输出索引中的所有设计系统概要
python3 -c "
import json, sys

with open('${INDEX_FILE}') as f:
    systems = json.load(f)

query = '${QUERY}'.lower()
query_chars = set(query)

results = []
for s in systems:
    # 计算匹配分数
    score = 0
    searchable = ' '.join(s['keywords'] + [s['name'], s['category'], s['description']]).lower()
    for kw in s['keywords']:
        if kw.lower() in query:
            score += 3
    if s['category'] in query:
        score += 2
    if s['name'].lower() in query:
        score += 5
    # 通用匹配
    for word in query.split():
        if word in searchable:
            score += 1
    results.append((score, s))

# 按分数排序
results.sort(key=lambda x: -x[0])

print(f'共 {len(results)} 个设计系统可用\n')
for i, (score, s) in enumerate(results):
    marker = '⭐' if score > 0 else '  '
    print(f\"{marker} [{i+1}] {s['name']} ({s['category']})\")
    print(f\"    风格: {'、'.join(s['keywords'])}\")
    print(f\"    主色: {s['colorPrimary']} | 暗色模式: {'✓' if s['darkMode'] else '✗'}\")
    print(f\"    最适合: {s['bestFor']}\")
    print(f\"    文件: design-systems/{s['file']}\")
    if score > 0:
        print(f\"    匹配度: {'★' * min(score, 5)}{'☆' * (5 - min(score, 5))}\")
    print()

# 推荐最佳匹配
if results[0][0] > 0:
    best = results[0][1]
    print(f'💡 推荐首选: {best[\"name\"]} (匹配度最高)')
    print(f'   使用方式: 读取 design-systems/{best[\"file\"]} 获取完整设计规范')
else:
    print('💡 未找到高匹配结果，请根据上方列表选择或描述更具体的风格偏好')
" 2>/dev/null || {
  # fallback: 如果 python3 不可用，直接输出列表
  cat "$INDEX_FILE"
}
