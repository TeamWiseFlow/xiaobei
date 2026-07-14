#!/usr/bin/env bash
set -euo pipefail

# fetch-and-update-metrics.sh — 一键数据获取+更新封装
#
# 封装 login-manager 探活 → fetch-retro-data.ts 抓取 → update-metrics.sh 写入
# 三步流程，返回统一 JSON 结果。
#
# Usage:
#   ./skills/published-track/scripts/fetch-and-update-metrics.sh \
#     --platform <platform> --id <rowid>           # 推荐：按主键抓该行自己的帖子并写该行
#   ./skills/published-track/scripts/fetch-and-update-metrics.sh \
#     --platform <platform> --source-folder <folder>   # 旧：按 folder（重复发布会互相污染）
#   ./skills/published-track/scripts/fetch-and-update-metrics.sh \
#     --platform <platform> --content-id <id> [--id <rowid> | --source-folder <folder>]
#
# Exit codes:
#   0  成功或返回了需要浏览器/手动处理的 JSON
#   1  一般错误
#   2  Cookie 失效（SESSION_EXPIRED）

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DB="$ROOT/db/published_track.db"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# camoufox-cli 路径（全局可用）
CAMOUFOX_CLI="${CAMOUFOX_CLI:-camoufox-cli}"

# published-track 平台名 → 持久化 session 名映射
# 小红书按域拆为 xhs-publish / xhs-browse，取数走消费者端 xhs-browse
LM_PLATFORM="$PLATFORM"
if [ "$PLATFORM" = "xhs" ]; then
  LM_PLATFORM="xhs-browse"
fi

# 平台首页 URL（探活时 open 用）
case "$LM_PLATFORM" in
  douyin)     PLATFORM_HOME="https://www.douyin.com/" ;;
  bilibili)   PLATFORM_HOME="https://www.bilibili.com/" ;;
  kuaishou)   PLATFORM_HOME="https://www.kuaishou.com/" ;;
  xhs-browse) PLATFORM_HOME="https://www.xiaohongshu.com/" ;;
  *)          PLATFORM_HOME="" ;;
esac

# ─── 辅助函数 ──────────────────────────────────────────────────────────────

extract_content_id() {
  local platform="$1"
  local url="$2"

  case "$platform" in
    bilibili)
      # https://www.bilibili.com/video/BVxxxxx → BVxxxxx
      echo "$url" | sed -n 's|.*/video/\(BV[^/?]*\).*|\1|p'
      ;;
    douyin)
      # https://www.douyin.com/video/1234567890 → 1234567890
      echo "$url" | sed -n 's|.*/video/\([0-9]*\).*|\1|p'
      ;;
    kuaishou)
      # https://www.kuaishou.com/short-video/xxx 或 /video/xxx
      echo "$url" | sed -n 's|.*/short-video/\([^/?]*\).*|\1|p; s|.*/video/\([^/?]*\).*|\1|p'
      ;;
    xhs)
      # https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy → xxx
      echo "$url" | sed -n 's|.*/explore/\([^/?]*\).*|\1|p'
      ;;
    *)
      echo ""
      ;;
  esac
}

# ─── 平台配置 ──────────────────────────────────────────────────────────────

# 脚本支持的平台（fetch-retro-data.ts 能处理的）
SCRIPT_PLATFORMS="xhs bilibili douyin kuaishou"

# 需要 cookie 的平台
COOKIE_PLATFORMS="xhs douyin kuaishou"

# 只能手动提供数据的平台
# Phase 4.6：wx_mp 已接入 wx-mp-engagement skill 自动抓取，移出手动列表
# wx_channel（视频号）暂未接入，保留 manual
MANUAL_PLATFORMS="wx_channel"

# ─── 参数解析 ──────────────────────────────────────────────────────────────

PLATFORM=""
SOURCE_FOLDER=""
ROW_ID=""
CONTENT_ID=""
XSEC_TOKEN=""
XSEC_SOURCE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    --id)             ROW_ID="$2"; shift 2 ;;
    --content-id)     CONTENT_ID="$2"; shift 2 ;;
    --xsec-token)     XSEC_TOKEN="$2"; shift 2 ;;
    --xsec-source)    XSEC_SOURCE="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  echo '{"ok":false,"error":"missing required arg: --platform"}'
  exit 1
fi

# ─── 平台路由 ──────────────────────────────────────────────────────────────

# wx_mp（微信公众号）**不走本脚本**——它走 camoufox 抓创作者中心的方案，
# 与 xhs/bilibili/douyin/kuaishou 的纯 HTTP+cookie 链路完全不同，
# 由 wx-mp-engagement 技能独立承担（agent 直调 wx-mp-engagement wrapper）。
# 见 crews/main/HEARTBEAT.md Step 2 与 wx-mp-engagement/SKILL.md。
if [ "$PLATFORM" = "wx_mp" ]; then
  echo "{\"ok\":false,\"error\":\"WX_MP_NOT_SUPPORTED_HERE\",\"platform\":\"wx_mp\",\"hint\":\"微信公众号不走 fetch-and-update-metrics.sh。请直调 wx-mp-engagement 技能：wx-mp-engagement fetch --row-id <rowid>（camoufox 抓创作者中心方案，与纯 HTTP+cookie 平台不同）\"}"
  exit 1
fi

# 手动平台：直接返回
for mp in $MANUAL_PLATFORMS; do
  if [ "$PLATFORM" = "$mp" ]; then
    echo "{\"ok\":false,\"method\":\"manual\",\"platform\":\"$PLATFORM\",\"hint\":\"该平台互动数据无法自动获取，需用户手动提供\"}"
    exit 0
  fi
done

# 检查是否为脚本支持的平台
IS_SCRIPT_PLATFORM=false
for sp in $SCRIPT_PLATFORMS; do
  if [ "$PLATFORM" = "$sp" ]; then
    IS_SCRIPT_PLATFORM=true
    break
  fi
done

if [ "$IS_SCRIPT_PLATFORM" = false ]; then
  # 浏览器平台
  BROWSER_HINT="通过浏览器导航到发布页面，snapshot 读取互动指标，然后调 update-metrics.sh 写入"

  # 特殊平台提示
  case "$PLATFORM" in
    twitter)  BROWSER_HINT="使用 twitter-interact 技能浏览推文详情获取互动数据（views/likes/retweets/replies/bookmarks），然后调 update-metrics.sh 写入" ;;
    zhihu)    BROWSER_HINT="浏览器导航到知乎文章/回答页面，snapshot 读取赞同数/评论数/收藏数，然后调 update-metrics.sh 写入" ;;
    toutiao)  BROWSER_HINT="浏览器导航到今日头条文章页面，snapshot 读取阅读数/评论数/点赞数，然后调 update-metrics.sh 写入" ;;
    juejin)   BROWSER_HINT="浏览器导航到掘金文章页面，snapshot 读取阅读数/点赞数/评论数，然后调 update-metrics.sh 写入" ;;
    youtube)  BROWSER_HINT="浏览器导航到 YouTube 视频页面，snapshot 读取观看数/点赞数/评论数，然后调 update-metrics.sh 写入" ;;
  esac

  echo "{\"ok\":false,\"method\":\"browser\",\"platform\":\"$PLATFORM\",\"hint\":\"$BROWSER_HINT\"}"
  exit 0
fi

# ─── 脚本平台流程 ──────────────────────────────────────────────────────────

# Step 1: login-manager 探活（需要 cookie 的平台）
NEEDS_COOKIE=false
for cp in $COOKIE_PLATFORMS; do
  if [ "$PLATFORM" = "$cp" ]; then
    NEEDS_COOKIE=true
    break
  fi
done

if [ "$NEEDS_COOKIE" = true ]; then
  if ! command -v "$CAMOUFOX_CLI" >/dev/null 2>&1; then
    echo "{\"ok\":false,\"error\":\"CAMOUFOX_CLI_NOT_FOUND\",\"platform\":\"$PLATFORM\",\"hint\":\"camoufox-cli 未找到，请确认已全局可用\"}"
    exit 1
  fi

  # 探活：开持久化 session open 平台首页 + snapshot 看是否跳登录页（spec §11-6，对齐 login-manager 步骤 0）
  "$CAMOUFOX_CLI" --session "$LM_PLATFORM" --persistent --headless --json open "$PLATFORM_HOME" >/dev/null 2>&1 || true
  sleep 3
  SNAP=$("$CAMOUFOX_CLI" --session "$LM_PLATFORM" --json snapshot 2>/dev/null || echo "")
  "$CAMOUFOX_CLI" --session "$LM_PLATFORM" --json close >/dev/null 2>&1 || true

  # snapshot 输出含登录标志 = 失效（跳登录页 / 出登录按钮 / 「请登录」文案）
  if echo "$SNAP" | grep -qE "login|登录|扫码|请登录|sign ?in"; then
    echo "{\"ok\":false,\"error\":\"SESSION_EXPIRED\",\"platform\":\"$PLATFORM\",\"login_platform\":\"$LM_PLATFORM\",\"method\":\"script\",\"hint\":\"Cookie 已失效，请使用 login-manager 技能引导用户重新登录 $LM_PLATFORM（camoufox-cli --session $LM_PLATFORM --persistent --headed open $PLATFORM_HOME → 用户手动登录 → cookies export + identity export 落中央存储）\"}"
    exit 2
  fi
fi

# Step 2: 获取 content_id
if [ -z "$CONTENT_ID" ]; then
  # --id 优先（按主键取该行自己的 publish_url，避免同 source_folder 多条重复发布
  # 被当作同一条抓取）；否则回退到 --source-folder（旧行为，LIMIT 1 取一行）。
  if [ -z "$ROW_ID" ] && [ -z "$SOURCE_FOLDER" ]; then
    echo '{"ok":false,"error":"missing required arg: --id / --source-folder / --content-id"}'
    exit 1
  fi

  if [ ! -f "$DB" ]; then
    echo '{"ok":false,"error":"database not initialized, run init-db.sh first"}'
    exit 1
  fi

  TABLE="pub_${PLATFORM}"
  VALID=$(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='$TABLE';" 2>/dev/null)
  if [ -z "$VALID" ]; then
    echo "{\"ok\":false,\"error\":\"unknown platform: $PLATFORM (table $TABLE not found)\"}"
    exit 1
  fi

  if [ -n "$ROW_ID" ]; then
    if ! [[ "$ROW_ID" =~ ^[0-9]+$ ]]; then
      echo "{\"ok\":false,\"error\":\"--id must be a positive integer, got: $ROW_ID\"}"
      exit 1
    fi
    # 按主键取该行自己的 publish_url（重复发布各自独立）
    PUBLISH_URL=$(sqlite3 "$DB" "SELECT publish_url FROM $TABLE WHERE id=${ROW_ID};" 2>/dev/null)
    if [ -z "$PUBLISH_URL" ]; then
      echo "{\"ok\":false,\"error\":\"no record found in $TABLE for id=${ROW_ID}\",\"hint\":\"请确认 id 正确且已记录到 published-track DB\"}"
      exit 1
    fi
  else
    # 同一 source_folder 可能对应多条记录（同目录重发不同版本），
    # 优先取 cal_enabled=1 的，其次取 publish_date 最新的，避免抓到旧版 note_id。
    PUBLISH_URL=$(sqlite3 "$DB" "SELECT publish_url FROM $TABLE WHERE source_folder='${SOURCE_FOLDER//\'/\'\'}' ORDER BY cal_enabled DESC, publish_date DESC, id DESC LIMIT 1;" 2>/dev/null)

    if [ -z "$PUBLISH_URL" ]; then
      echo "{\"ok\":false,\"error\":\"no record found in $TABLE for source_folder=$SOURCE_FOLDER\",\"hint\":\"请确认该内容已记录到 published-track DB\"}"
      exit 1
    fi
  fi

  # 从 publish_url 提取 content_id
  CONTENT_ID=$(extract_content_id "$PLATFORM" "$PUBLISH_URL")

  if [ -z "$CONTENT_ID" ]; then
    echo "{\"ok\":false,\"error\":\"CANNOT_EXTRACT_CONTENT_ID\",\"platform\":\"$PLATFORM\",\"publish_url\":\"$PUBLISH_URL\",\"hint\":\"无法从 publish_url 提取 content_id，请用 --content-id 参数直接提供\"}"
    exit 1
  fi
fi

# Step 3: 调 fetch-retro-data.ts
FETCH_SCRIPT="$SCRIPT_DIR/fetch-retro-data.ts"
if [ ! -f "$FETCH_SCRIPT" ]; then
  echo "{\"ok\":false,\"error\":\"FETCH_SCRIPT_NOT_FOUND\",\"hint\":\"fetch-retro-data.ts 不存在于 $SCRIPT_DIR/\"}"
  exit 1
fi

echo "[fetch-and-update] 调 fetch-retro-data.ts --platform $PLATFORM --content-id $CONTENT_ID ..." >&2
# stdout = JSON 结果，stderr = 进度日志（透传）
FETCH_ARGS=(--platform "$PLATFORM" --content-id "$CONTENT_ID")
# xhs 需要 xsec_token（feed API 强制）；其他脚本平台忽略这两个参数
if [ -n "$XSEC_TOKEN" ]; then
  FETCH_ARGS+=(--xsec-token "$XSEC_TOKEN")
  [ -n "$XSEC_SOURCE" ] && FETCH_ARGS+=(--xsec-source "$XSEC_SOURCE")
fi
FETCH_OUTPUT=$(node --experimental-strip-types "$FETCH_SCRIPT" "${FETCH_ARGS[@]}" 2>/dev/null) || FETCH_EXIT=$?
FETCH_EXIT=${FETCH_EXIT:-0}

if [ "$FETCH_EXIT" -eq 2 ]; then
  echo "{\"ok\":false,\"error\":\"SESSION_EXPIRED\",\"platform\":\"$PLATFORM\",\"method\":\"script\",\"hint\":\"Cookie 已失效，请使用 login-manager 技能引导用户重新登录 $PLATFORM\"}"
  exit 2
fi

if [ "$FETCH_EXIT" -ne 0 ] || [ -z "$FETCH_OUTPUT" ]; then
  echo "{\"ok\":false,\"error\":\"FETCH_FAILED\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"fetch_exit\":$FETCH_EXIT,\"hint\":\"fetch-retro-data.ts 执行失败，请检查脚本输出\"}"
  exit 1
fi

# Step 4: 解析结果 → 调 update-metrics.sh
# 将 fetch-retro-data.ts 的 JSON 输出转换为 update-metrics.sh 参数
# 用临时文件传递 JSON（避免多行 JSON 在 bash heredoc 中出问题）
FETCH_TMP=$(mktemp)
echo "$FETCH_OUTPUT" > "$FETCH_TMP"

METRICS_PARAMS=$(node -e "
const data = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));
if (!data.ok) { console.log('__fetch_failed__:' + (data.error || 'UNKNOWN') + ':' + ((data.msg || '').substring(0,80).replace(/[:\n]/g,' '))); process.exit(0); }
const stats = data.stats || {};
const args = [];
const mapping = {
  // viewCount → 'plays'：pub_bilibili / pub_kuaishou 的播放列叫 plays（非 views）。
  // 此 mapping 仅对 SCRIPT_PLATFORMS=xhs/bilibili/douyin/kuaishou 生效，其中
  // bili/kuaishou 返回 viewCount 且 DB 列为 plays；xhs 不返回 viewCount、douyin 返回 playCount，均不受影响。
  viewCount: 'plays', plays: 'plays', playCount: 'plays',
  likeCount: 'likes', likes: 'likes',
  commentCount: 'comments', comments: 'comments',
  shareCount: 'shares', shares: 'shares',
  favoriteCount: 'favorites', favorites: 'favorites',
  collectCount: 'favorites',
  danmakuCount: 'danmaku',
  coinCount: 'coins',
  replyCount: 'comments',
  upvotes: 'upvotes', reads: 'reads',
  impressions: 'impressions', reach: 'reach', saves: 'saves',
  retweets: 'retweets', replies: 'replies',
  bookmarks: 'bookmarks', reposts: 'reposts',
};
for (const [k, v] of Object.entries(stats)) {
  const mapped = mapping[k];
  if (mapped && v > 0) {
    args.push('--' + mapped + '=' + v);
  }
}
const comments = data.comments || [];
if (comments.length > 0) {
  const top = comments[0];
  const text = (top.text || '').substring(0, 200).replace(/[\"']/g, '');
  args.push('--top_comment=' + text);
}
// 即使无 stats 也输出 __empty__ 标记，避免被 bash 判为空
if (args.length === 0) {
  console.log('__no_metrics__');
} else {
  console.log(args.join(' '));
}
" "$FETCH_TMP" 2>/dev/null) || METRICS_EXIT=$?
METRICS_EXIT=${METRICS_EXIT:-0}
rm -f "$FETCH_TMP"

if [ "$METRICS_EXIT" -ne 0 ]; then
  echo "{\"ok\":false,\"error\":\"METRICS_PARSE_FAILED\",\"platform\":\"$PLATFORM\",\"hint\":\"fetch-retro-data.ts 返回了数据但解析为 update-metrics.sh 参数时失败\"}"
  exit 1
fi

# fetch-retro-data.ts 返回 ok:false（如 xhs NOTE_INACCESSIBLE：缺/失效 xsec_token）
if [[ "$METRICS_PARAMS" == __fetch_failed__:* ]]; then
  FAIL_ERR="${METRICS_PARAMS#__fetch_failed__:}"
  FAIL_CODE="${FAIL_ERR%%:*}"
  FAIL_MSG="${FAIL_ERR#*:}"
  echo "{\"ok\":false,\"error\":\"${FAIL_CODE}\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"msg\":\"${FAIL_MSG}\",\"hint\":\"fetch-retro-data.ts 返回 ok:false\"}"
  exit 1
fi

# 无指标数据但 API 调用成功——直接返回成功
if [ "$METRICS_PARAMS" = "__no_metrics__" ]; then
  echo "{\"ok\":true,\"method\":\"script\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"note\":\"API 返回成功但无互动指标数据（内容可能不存在或数据尚未产生）\"}"
  exit 0
fi

# Step 5: 调 update-metrics.sh
UPDATE_SCRIPT="$SCRIPT_DIR/update-metrics.sh"
# --id 优先（按主键写单行，重复发布各自独立）；否则回退到 --source-folder（批量写）。
if [ -n "$ROW_ID" ]; then
  UPDATE_LOCATE=(--id "$ROW_ID")
elif [ -n "$SOURCE_FOLDER" ]; then
  UPDATE_LOCATE=(--source-folder "$SOURCE_FOLDER")
else
  echo "{\"ok\":false,\"error\":\"NO_LOCATE_KEY\",\"platform\":\"$PLATFORM\",\"hint\":\"写库需要 --id 或 --source-folder 定位记录，仅传 --content-id 无法更新\"}"
  exit 1
fi
eval "\"$UPDATE_SCRIPT\" --platform \"$PLATFORM\" ${UPDATE_LOCATE[*]} $METRICS_PARAMS" 2>/dev/null || UPDATE_EXIT=$?
UPDATE_EXIT=${UPDATE_EXIT:-0}

if [ "$UPDATE_EXIT" -ne 0 ]; then
  echo "{\"ok\":false,\"error\":\"UPDATE_FAILED\",\"platform\":\"$PLATFORM\",\"hint\":\"update-metrics.sh 执行失败 (exit $UPDATE_EXIT)\"}"
  exit 1
fi

# 成功
echo "{\"ok\":true,\"method\":\"script\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"metrics_params\":\"$METRICS_PARAMS\"}"
