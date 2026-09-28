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

# ─── 辅助函数 ──────────────────────────────────────────────────────────────

extract_content_id() {
  local platform="$1"
  local url="$2"

  case "$platform" in
    douyin)
      # 视频 https://www.douyin.com/video/1234567890 → 1234567890
      # 图文 https://www.douyin.com/note/7686383022777634058   → 7686383022777634058
      # （2026-09-17 xiaobei 反馈：note 链接提取为空报 CANNOT_EXTRACT_CONTENT_ID。
      #  定界符用 #：用 | 的话 \| 被解析成字面管道而非 BRE alternation。）
      echo "$url" | sed -n 's#.*/\(video\|note\)/\([0-9]*\).*#\2#p'
      ;;
    *)
      echo ""
      ;;
  esac
}

# ─── 平台配置 ──────────────────────────────────────────────────────────────

# 脚本支持的平台（fetch-retro-data.ts 能处理的）
# xhs 走 xhs-engagement 的 Creator HTTP 接口，
# 与 wx_mp/wx_channel 同模式，见下方平台路由
# 2026-09-16：bilibili / kuaishou 移出——自动取数范围收窄为完全支持 Expert 架构的
# 4 个平台（douyin 走本脚本；xhs/wx_mp/wx_channel 走各自专家包的 engagement 工具），
# bilibili/kuaishou 只保留发布记录/查询，不抓互动数据，见下方平台路由
SCRIPT_PLATFORMS="douyin"

# 需要 cookie 的平台
COOKIE_PLATFORMS="douyin"

# 只能手动提供数据的平台
# Phase 4.6：wx_mp 已接入 wx-mp-engagement skill 自动抓取，移出手动列表
# Phase 4.7：wx_channel 已接入 wx-channel-engagement 自动抓取（现 expert-wx-channel 专家包内工具），移出手动列表
# 当前无 manual 平台，保留变量供未来扩展
MANUAL_PLATFORMS=""

# ─── 参数解析 ──────────────────────────────────────────────────────────────

PLATFORM=""
SOURCE_FOLDER=""
ROW_ID=""
CONTENT_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)       PLATFORM="$2"; shift 2 ;;
    --source-folder)  SOURCE_FOLDER="$2"; shift 2 ;;
    --id)             ROW_ID="$2"; shift 2 ;;
    --content-id)     CONTENT_ID="$2"; shift 2 ;;
    *) echo "{\"ok\":false,\"error\":\"unknown arg: $1\"}"; exit 1 ;;
  esac
done

if [ -z "$PLATFORM" ]; then
  echo '{"ok":false,"error":"missing required arg: --platform"}'
  exit 1
fi

# 平台首页 URL（探活提示用；login-manager session 名与平台名一致）
LM_PLATFORM="$PLATFORM"
case "$LM_PLATFORM" in
  douyin)     PLATFORM_HOME="https://www.douyin.com/" ;;
  *)          PLATFORM_HOME="" ;;
esac

# ─── 平台路由 ──────────────────────────────────────────────────────────────

# bilibili / kuaishou **不走本脚本**——2026-09-16 起自动取数范围收窄为完全支持
# Expert 架构的 4 个平台（douyin 走本脚本；xhs/wx_mp/wx_channel 走各自专家包的
# engagement 工具）。bilibili/kuaishou 只保留发布记录/查询，不自动抓互动数据。
case "$PLATFORM" in
  bilibili|kuaishou)
    echo "{\"ok\":false,\"error\":\"PLATFORM_OUT_OF_FETCH_SCOPE\",\"platform\":\"$PLATFORM\",\"hint\":\"自动取数仅覆盖完全支持 Expert 架构的 4 个平台（douyin/xhs/wx_mp/wx_channel）。bilibili/kuaishou 不做自动取数，发布记录与查询照常支持\"}"
    exit 1
    ;;
esac

# wx_mp（微信公众号）**不走本脚本**——它走 camoufox 抓创作者中心的方案，
# 与 douyin 的纯 HTTP+cookie 链路完全不同，
# 由 expert-wx-mp 专家包内的 wx-mp-engagement 工具独立承担（agent 直调 wx-mp-engagement wrapper）。
# 见 crews/main/HEARTBEAT.md Step 2 与 crews/main/skills/expert-wx-mp/tools/wx-mp-engagement/SKILL.md。
if [ "$PLATFORM" = "wx_mp" ]; then
  echo "{\"ok\":false,\"error\":\"WX_MP_NOT_SUPPORTED_HERE\",\"platform\":\"wx_mp\",\"hint\":\"微信公众号不走 fetch-and-update-metrics.sh。请直调 wx-mp-engagement 技能：wx-mp-engagement fetch --row-id <rowid>（camoufox 抓创作者中心方案，与纯 HTTP+cookie 平台不同）\"}"
  exit 1
fi

# xhs（小红书）**不走本脚本**——它走 xhs-engagement 技能（camoufox 打开 creator 后台
# 笔记管理页方案），与 wx_mp/wx_channel 同模式，由 agent 直调 xhs-engagement wrapper。
# 见 crews/main/HEARTBEAT.md Step 2 与 crews/main/skills/expert-xhs/tools/xhs-engagement/SKILL.md。
if [ "$PLATFORM" = "xhs" ]; then
  echo "{\"ok\":false,\"error\":\"XHS_NOT_SUPPORTED_HERE\",\"platform\":\"xhs\",\"hint\":\"小红书不走 fetch-and-update-metrics.sh。请直调 xhs-engagement 技能：xhs-engagement fetch --row-id <rowid>（camoufox 抓 creator 后台方案，与纯 HTTP+cookie 平台不同）\"}"
  exit 1
fi

# wx_channel（微信视频号）**不走本脚本**——它走 camoufox 抓视频号助手后台的方案，
# 与 douyin 的纯 HTTP+cookie 链路完全不同，
# 由 expert-wx-channel 专家包内的 wx-channel-engagement 工具独立承担（agent 直调同名 wrapper）。
# 见 crews/main/HEARTBEAT.md Step 2 与 crews/main/skills/expert-wx-channel/tools/wx-channel-engagement/SKILL.md。
if [ "$PLATFORM" = "wx_channel" ]; then
  echo "{\"ok\":false,\"error\":\"WX_CHANNEL_NOT_SUPPORTED_HERE\",\"platform\":\"wx_channel\",\"hint\":\"微信视频号不走 fetch-and-update-metrics.sh。请直调 wx-channel-engagement 工具（expert-wx-channel 专家包内）：wx-channel-engagement fetch --row-id <rowid>（camoufox 抓视频号助手后台方案，与纯 HTTP+cookie 平台不同）\"}"
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
  # 探活：按平台 cookie 关键字段判（借鉴 docs/nodriver_helper_reference._check_login_status），
  # 读 ~/.openclaw/logins/<session>.json，不再开 camoufox + snapshot grep——已登录页面里
  # 「登录」文案会假阳性误报 SESSION_EXPIRED。cookie 关键字段缺失必失效；真伪交
  # fetch-retro-data 实请求验证，本步只做 cheap gate。探活与取数读同一份 cookie，状态对齐。
  CHECK_LOGIN="$SCRIPT_DIR/check-login.ts"
  if [ ! -f "$CHECK_LOGIN" ]; then
    echo "{\"ok\":false,\"error\":\"CHECK_LOGIN_SCRIPT_NOT_FOUND\",\"platform\":\"$PLATFORM\",\"hint\":\"check-login.ts 不存在于 $SCRIPT_DIR/\"}"
    exit 1
  fi
  CHECK_OUT=$(node --experimental-strip-types "$CHECK_LOGIN" --platform "$PLATFORM") || CHECK_EXIT=$?
  CHECK_EXIT=${CHECK_EXIT:-0}
  if [ "$CHECK_EXIT" -eq 2 ]; then
    CHECK_REASON=$(printf '%s' "$CHECK_OUT" | node -e 'let d="";process.stdin.on("data",c=>d+=c);process.stdin.on("end",()=>{try{console.log(JSON.parse(d).reason||"")}catch{}})' 2>/dev/null)
    echo "{\"ok\":false,\"error\":\"SESSION_EXPIRED\",\"platform\":\"$PLATFORM\",\"login_platform\":\"$LM_PLATFORM\",\"method\":\"script\",\"reason\":\"$CHECK_REASON\",\"hint\":\"登录态探活未通过（具体原因见 reason）：cookie 关键字段缺失/过期，或 pong 明确返回未登录。请使用 login-manager 技能引导用户重新登录 $LM_PLATFORM（camoufox-cli --session $LM_PLATFORM --persistent --headed open $PLATFORM_HOME → 用户手动登录 → cookies export + identity export 落中央存储）\"}"
    exit 2
  fi
  if [ "$CHECK_EXIT" -ne 0 ]; then
    # exit 1 区分 SIGN_UNAVAILABLE（签名基础设施缺凭证，非 cookie 问题，不触发重登）
    # 与真·CHECK_LOGIN_FAILED（脚本异常）
    CHECK_ERROR=$(printf '%s' "$CHECK_OUT" | node -e 'let d="";process.stdin.on("data",c=>d+=c);process.stdin.on("end",()=>{try{console.log(JSON.parse(d).error||"")}catch{}})' 2>/dev/null)
    if [ "$CHECK_ERROR" = "SIGN_UNAVAILABLE" ]; then
      CHECK_REASON=$(printf '%s' "$CHECK_OUT" | node -e 'let d="";process.stdin.on("data",c=>d+=c);process.stdin.on("end",()=>{try{console.log(JSON.parse(d).reason||"")}catch{}})' 2>/dev/null)
      echo "{\"ok\":false,\"error\":\"SIGN_UNAVAILABLE\",\"platform\":\"$PLATFORM\",\"login_platform\":\"$LM_PLATFORM\",\"reason\":\"$CHECK_REASON\",\"hint\":\"签名基础设施不可用（如 OFB_KEY 未配置），非 cookie 失效——重登无益，请 IT engineer 修 relay 凭证后重跑\"}"
      exit 1
    fi
    echo "{\"ok\":false,\"error\":\"CHECK_LOGIN_FAILED\",\"platform\":\"$PLATFORM\",\"hint\":\"check-login.ts 执行异常 (exit $CHECK_EXIT): $CHECK_OUT\"}"
    exit 1
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
FETCH_OUTPUT=$(node --experimental-strip-types "$FETCH_SCRIPT" --platform "$PLATFORM" --content-id "$CONTENT_ID") || FETCH_EXIT=$?
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
DEEP_TMP=$(mktemp)
trap 'rm -f "$DEEP_TMP"' EXIT
echo "$FETCH_OUTPUT" > "$FETCH_TMP"

METRICS_PARAMS=$(node -e "
const data = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));
if (!data.ok) { console.log('__fetch_failed__:' + (data.error || 'UNKNOWN') + ':' + ((data.msg || '').substring(0,80).replace(/[:\n]/g,' '))); process.exit(0); }
const stats = data.stats || {};
const args = [];
const mapping = {
  // viewCount → 'plays' 等通用映射保留（fetch-retro-data.ts 可能返回多种键名）；
  // 当前 SCRIPT_PLATFORMS 仅 douyin，返回 playCount → plays。
  viewCount: 'plays', plays: 'plays', playCount: 'plays', views: 'views',
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
  if (mapped && typeof v === 'number' && Number.isFinite(v) && v >= 0) {
    args.push('--' + mapped + '=' + v);
  }
}
// deep 指标 → 单行 JSON 文件（update-metrics --deep-file readfile 读入，
// 免引号地狱），stdout 标记只表达标量指标有无
if (data.deep && typeof data.deep === 'object' && !Array.isArray(data.deep)) {
  require('fs').writeFileSync(process.argv[2], JSON.stringify(data.deep));
}
if (args.length === 0) {
  console.log('__no_metrics__');
} else {
  console.log(args.join(' '));
}
" "$FETCH_TMP" "$DEEP_TMP" 2>/dev/null) || METRICS_EXIT=$?
METRICS_EXIT=${METRICS_EXIT:-0}
rm -f "$FETCH_TMP"

if [ "$METRICS_EXIT" -ne 0 ]; then
  echo "{\"ok\":false,\"error\":\"METRICS_PARSE_FAILED\",\"platform\":\"$PLATFORM\",\"hint\":\"fetch-retro-data.ts 返回了数据但解析为 update-metrics.sh 参数时失败\"}"
  exit 1
fi

# fetch-retro-data.ts 返回 ok:false
if [[ "$METRICS_PARAMS" == __fetch_failed__:* ]]; then
  FAIL_ERR="${METRICS_PARAMS#__fetch_failed__:}"
  FAIL_CODE="${FAIL_ERR%%:*}"
  FAIL_MSG="${FAIL_ERR#*:}"
  echo "{\"ok\":false,\"error\":\"${FAIL_CODE}\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"msg\":\"${FAIL_MSG}\",\"hint\":\"fetch-retro-data.ts 返回 ok:false\"}"
  exit 1
fi

# 无标量指标但 API 调用成功：有 deep → 继续 deep-only 写入；无 deep → 直接返回成功
if [ "$METRICS_PARAMS" = "__no_metrics__" ]; then
  if [ -s "$DEEP_TMP" ]; then
    METRICS_PARAMS=""
  else
    echo "{\"ok\":true,\"method\":\"script\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"note\":\"API 返回成功但无互动指标数据（内容可能不存在或数据尚未产生）\"}"
    exit 0
  fi
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
# deep 指标参数（mktemp 路径无空格，eval 安全）
DEEP_ARGS=()
if [ -s "$DEEP_TMP" ]; then
  DEEP_ARGS=(--deep-file "$DEEP_TMP" --deep-source "${PLATFORM}:creator_item_list")
fi
eval "\"$UPDATE_SCRIPT\" --platform \"$PLATFORM\" ${UPDATE_LOCATE[*]} $METRICS_PARAMS ${DEEP_ARGS[*]}" >&2 || UPDATE_EXIT=$?
UPDATE_EXIT=${UPDATE_EXIT:-0}
rm -f "$DEEP_TMP"

if [ "$UPDATE_EXIT" -ne 0 ]; then
  echo "{\"ok\":false,\"error\":\"UPDATE_FAILED\",\"platform\":\"$PLATFORM\",\"hint\":\"update-metrics.sh 执行失败 (exit $UPDATE_EXIT)\"}"
  exit 1
fi

# 成功
echo "{\"ok\":true,\"method\":\"script\",\"platform\":\"$PLATFORM\",\"content_id\":\"$CONTENT_ID\",\"metrics_params\":\"$METRICS_PARAMS\",\"deep_stored\":$([ -z "${DEEP_ARGS[*]}" ] && echo false || echo true)}"
