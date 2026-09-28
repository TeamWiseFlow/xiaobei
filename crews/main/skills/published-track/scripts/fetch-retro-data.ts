#!/usr/bin/env -S node --experimental-strip-types
/**
 * fetch-retro-data.ts — 复盘数据抓取（第一层：纯 HTTP + cookie + 签名）
 *
 * 这是复盘数据抓取的第一层，拿基础互动指标（播放/点赞/评论数）+ 抖音创作侧深指标
 * （2026-09 起 douyin 走 creator item/list：view_count 播放量公开侧恒 0 仅创作侧可见，
 * 另有完播率/封面 CTR 等 26 字段，视频+图文(note)作品通用；见 _shared/douyin-web.ts
 * douyinCreatorItem）。其余深度数据（评论内容等）通过 browser tool + evaluate
 * CDP 拦截实现，不在此脚本中。
 *
 * 签名方案复用：
 *   - 抖音: a_bogus（复用 viral-chaser 的 vendor/douyin.js）
 *   - B站:  WBI 签名（复用 viral-chaser 逻辑）
 *   - 快手:  GraphQL（无需签名）
 *
 * Cookie 来源: login-manager（~/.openclaw/logins/{platform}.json）
 *   小红书（xhs）走 xhs-engagement 的 Creator HTTP 接口
 *
 * Usage:
 *   node fetch-retro-data.ts --platform douyin --content-id <aweme_id>
 *   node fetch-retro-data.ts --platform bilibili --content-id <bvid>
 *   node fetch-retro-data.ts --platform kuaishou --content-id <photo_id>
 *
 * Exit codes:
 *   0  成功 — JSON 输出到 stdout
 *   1  一般错误
 *   2  Cookie 无效/未登录 → 调用方应触发 login-manager
 */

import { readFileSync, existsSync } from "fs"
import { join } from "path"
import { homedir } from "os"

// ─── Types ────────────────────────────────────────────────────────────────

interface CookieRecord { name: string; value: string; domain?: string }

interface SessionData {
  platform: string
  /** camoufox-cli 原生格式：cookies 是对象数组；向后兼容旧字符串格式 */
  cookies?: CookieRecord[] | string
  /** 旧字段保留兼容；新格式下 UA 走独立 .ua.json 文件 */
  user_agent?: string
  updated_at?: string
}

interface RetroResult {
  ok: boolean
  platform: string
  contentId: string
  stats: Record<string, number>
  /** 创作侧深指标（douyin item/list：完播率/封面 CTR 等，键为平台原名）。经 fetch-and-update 落 pub_douyin.deep_metrics（只存最新值）。 */
  deep?: Record<string, number>
  comments: Array<{ cid: string; text: string; likeCount: number; userName: string }>
  error?: string
  msg?: string
}

// ─── Session ──────────────────────────────────────────────────────────────

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins")
const DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

function readSession(platform: string): SessionData | null {
  const path = join(SESSIONS_DIR, `${platform}.json`)
  if (!existsSync(path)) return null
  try {
    const raw = JSON.parse(readFileSync(path, "utf-8"))
    // camoufox-cli `cookies export` 写的是裸数组（见 patches/camoufox-cli/src/commands.ts
    // `writeFileSync(path, JSON.stringify(cookies))`），消费方统一归一化为 {cookies: [...]}，
    // 否则 requireSession 的 `!data.cookies` 判空会把有效 cookie 误报 SESSION_EXPIRED。
    if (Array.isArray(raw)) return { platform, cookies: raw } as SessionData
    return raw as SessionData
  } catch {
    return null
  }
}

function readUserAgent(platform: string): string {
  const path = join(SESSIONS_DIR, `${platform}.ua.json`)
  if (!existsSync(path)) return DEFAULT_UA
  try {
    const data = JSON.parse(readFileSync(path, "utf-8")) as { userAgent?: string }
    return data.userAgent || DEFAULT_UA
  } catch {
    return DEFAULT_UA
  }
}

function requireSession(platform: string): SessionData {
  const data = readSession(platform)
  const empty = !data || !data.cookies || (Array.isArray(data.cookies) && data.cookies.length === 0)
  if (empty) {
    process.stderr.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform }) + "\n")
    process.exit(2)
  }
  return data
}

function parseCookies(raw: CookieRecord[] | string | undefined): Record<string, string> {
  const dict: Record<string, string> = {}
  if (Array.isArray(raw)) {
    for (const c of raw) {
      if (c && typeof c.name === "string" && typeof c.value === "string") {
        dict[c.name] = c.value
      }
    }
  } else if (typeof raw === "string" && raw) {
    for (const item of raw.split(";")) {
      const trimmed = item.trim()
      if (!trimmed || !trimmed.includes("=")) continue
      const [k, ...rest] = trimmed.split("=")
      dict[k.trim()] = rest.join("=").trim()
    }
  }
  return dict
}

function cookieHeader(dict: Record<string, string>): string {
  return Object.entries(dict).map(([k, v]) => `${k}=${v}`).join("; ")
}

/** 从 session + 独立 UA 文件拿 UA（spec §4 原则 4，同时导入 cookie + UA） */
function sessionUA(platform: string, session: SessionData): string {
  return readUserAgent(platform) || session.user_agent || DEFAULT_UA
}

// ─── 抖音 ──────────────────────────────────────────────────────────────────

async function fetchDouyin(awemeId: string): Promise<RetroResult> {
  const session = requireSession("douyin")
  const cookieDict = parseCookies(session.cookies)
  const ua = sessionUA("douyin", session)
  const cookieStr = cookieHeader(cookieDict)

  // 签名 + COMMON_PARAMS + webid/msToken/verifyFp 走 _shared/douyin-web.ts。
  // 早期此处只发 aweme_id+msToken+a_bogus，缺 COMMON_PARAMS，抖音 Janus 网关回 200 空体，
  // 长期取不到数（静默 __no_metrics__）。复用 viral-chaser 同款请求形态后修复。
  const { douyinWebGet } = await import("../../_shared/douyin-web.ts")

  const result: RetroResult = {
    ok: true,
    platform: "douyin",
    contentId: awemeId,
    stats: {},
    comments: [],
  }

  // 视频详情（aweme/detail 接口）——只取数，不碰评论
  // （参考 wiseflow4-pro douyin aweme_processor.__call__ → get_video_by_id →
  //  update_douyin_aweme：读 statistics 的 digg_count/collect_count/comment_count/share_count。）
  // 图文(note)作品的 mid 同样走此端点。play_count 公开侧恒为 0（播放量仅创作者可见），
  // 下方创作侧 lane 是播放量的唯一来源。
  console.error("  → 调抖音 API 获取作品详情...")
  try {
    const { status, data } = await douyinWebGet<any>(
      "/aweme/v1/web/aweme/detail/",
      { aweme_id: awemeId },
      cookieStr,
      ua,
    )
    const aweme = data?.aweme_detail
    if (aweme) {
      const stats = aweme.statistics || {}
      // 公开侧播放量不可用；其余指标仅接受明确返回的数值，缺失不补零。
      const mapping = {
        digg_count: "likeCount",
        comment_count: "commentCount",
        share_count: "shareCount",
        collect_count: "collectCount",
      }
      for (const [key, target] of Object.entries(mapping)) {
        const value = stats[key]
        if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
          result.stats[target] = value
        }
      }
      console.error(`  ✓ 点赞 ${result.stats.likeCount} / 评论 ${result.stats.commentCount} / 分享 ${result.stats.shareCount}`)
    } else {
      console.error(`  ⚠️ 作品详情接口返回 ${status} 但无 aweme_detail（cookie 可能失效）`)
    }
  } catch (e) {
    console.error(`  ⚠️ 作品详情获取失败: ${e}`)
  }

  // 创作侧 item/list（借鉴 OpenCLI #2307）：26 字段深指标，视频+图文都在；
  // creator 域 cookie-only 无需 a_bogus。失败不影响公开侧数据（graceful 降级）。
  console.error("  → 调创作侧 item/list 获取深指标（含播放量）...")
  try {
    const { douyinCreatorItem } = await import("../../_shared/douyin-web.ts")
    const item = await douyinCreatorItem(awemeId, cookieStr, ua)
    if (item) {
      const m = item.metrics
      // 有常规列的指标全部写 stats，创作侧优先；其余指标才放 deep。
      // view_count 是播放量唯一来源；缺失字段保留公开侧结果，明确的 0 正常覆盖。
      const mapping: Record<string, string> = {
        view_count: "playCount",
        like_count: "likeCount",
        comment_count: "commentCount",
        share_count: "shareCount",
        favorite_count: "collectCount",
      }
      result.deep = {}
      for (const [key, value] of Object.entries(m)) {
        if (mapping[key]) {
          if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
            result.stats[mapping[key]] = value
          }
        } else {
          result.deep[key] = value
        }
      }
      console.error(
        `  ✓ 播放 ${m.view_count ?? "?"} / 5s完播率 ${m.completion_rate_5s ?? "?"} / 2s跳出率 ${m.bounce_rate_2s ?? "?"} / 封面点击率 ${m.cover_click_rate ?? "?"}（审核 ${item.review ?? "?"}）`,
      )
    } else {
      console.error("  ⚠️ 创作侧列表未找到该作品（cookie 非本账号，或作品超出列表深度）——播放量/深指标缺失，公开侧数据不受影响")
    }
  } catch (e) {
    console.error(`  ⚠️ 创作侧深指标获取失败（不影响公开侧数据）: ${e}`)
  }

  return result
}

// ─── B站 ───────────────────────────────────────────────────────────────────

const BILI_API = "https://api.bilibili.com"
const BILI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

async function fetchBilibili(bvid: string): Promise<RetroResult> {
  const result: RetroResult = {
    ok: true,
    platform: "bilibili",
    contentId: bvid,
    stats: {},
    comments: [],
  }

  // 视频详情（公开 API，无需 cookie）——只取数，不碰评论
  // （参考 wiseflow4-pro bilibili video_processor.get_video_detail：读 View.stat 的
  //  like/view/danmaku/reply/coin/favorite/share。此处用更轻的 /view 公开端点，字段同。）
  console.error("  → 调 B站 API 获取视频详情...")
  try {
    const resp = await fetch(`${BILI_API}/x/web-interface/view?bvid=${bvid}`, {
      headers: { "User-Agent": BILI_UA },
      signal: AbortSignal.timeout(15_000),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json() as any
    if (data.code !== 0) throw new Error(data.message)

    const stat = data.data.stat
    result.stats = {
      viewCount: stat.view || 0,
      likeCount: stat.like || 0,
      coinCount: stat.coin || 0,
      favoriteCount: stat.favorite || 0,
      shareCount: stat.share || 0,
      danmakuCount: stat.danmaku || 0,
      replyCount: stat.reply || 0,
    }
    console.error(`  ✓ 播放 ${result.stats.viewCount} / 点赞 ${result.stats.likeCount} / 评论 ${result.stats.replyCount}`)
  } catch (e) {
    console.error(`  ⚠️ B站数据获取失败: ${e}`)
  }

  return result
}

// ─── 快手 ──────────────────────────────────────────────────────────────────

const KUAISHOU_GQL = "https://www.kuaishou.com/graphql"

async function fetchKuaishou(photoId: string): Promise<RetroResult> {
  const session = requireSession("kuaishou")
  const cookieDict = parseCookies(session.cookies)
  const ua = sessionUA("kuaishou", session)

  const result: RetroResult = {
    ok: true,
    platform: "kuaishou",
    contentId: photoId,
    stats: {},
    comments: [],
  }

  // 视频详情（GraphQL）——只取数，不碰评论（参考 wiseflow4-pro kuaishou video_processor.get_video_detail）
  // likeCount 是展示数，realLikeCount 才是真实点赞数（参考 update_kuaishou_video 读 realLikeCount）。
  console.error("  → 调快手 GraphQL 获取视频详情...")
  try {
    const query = `query visionVideoDetail($photoId: String) { visionVideoDetail(photoId: $photoId) { photo { id viewCount realLikeCount commentCount } } }`
    const resp = await fetch(KUAISHOU_GQL, {
      method: "POST",
      headers: {
        "User-Agent": ua,
        "Cookie": cookieHeader(cookieDict),
        "Content-Type": "application/json",
        "Referer": "https://www.kuaishou.com/",
        "Origin": "https://www.kuaishou.com",
      },
      body: JSON.stringify({ query, variables: { photoId } }),
      signal: AbortSignal.timeout(15_000),
    })
    if (resp.ok) {
      const data = await resp.json() as any
      const photo = data?.data?.visionVideoDetail?.photo
      if (photo) {
        result.stats = {
          viewCount: photo.viewCount || 0,
          likeCount: photo.realLikeCount || 0,
          commentCount: photo.commentCount || 0,
        }
        console.error(`  ✓ 播放 ${result.stats.viewCount} / 点赞 ${result.stats.likeCount}`)
      }
    }
  } catch (e) {
    console.error(`  ⚠️ 快手详情获取失败: ${e}`)
  }

  return result
}

// ─── 小红书 ────────────────────────────────────────────────────────────────
//
// xhs 取数由 xhs-engagement 使用独立 Creator HTTP 会话完成。
// agent 直调 `xhs-engagement fetch --row-id <rowid>`。

// ─── Main ─────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  let platform = ""
  let contentId = ""

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i]
    else if (args[i] === "--content-id" && args[i + 1]) contentId = args[++i]
  }

  if (!platform || !contentId) {
    process.stderr.write("用法: node fetch-retro-data.ts --platform <douyin|bilibili|kuaishou> --content-id <id>\n")
    process.exit(1)
  }

  let result: RetroResult

  switch (platform) {
    case "douyin":
      result = await fetchDouyin(contentId)
      break
    case "bilibili":
      result = await fetchBilibili(contentId)
      break
    case "kuaishou":
      result = await fetchKuaishou(contentId)
      break
    case "xhs":
      process.stderr.write("❌ xhs 不走 fetch-retro-data.ts。请直调 xhs-engagement fetch --row-id <rowid>（Creator HTTP 接口）\n")
      process.exit(1)
    default:
      process.stderr.write(`❌ 不支持的平台: ${platform}\n`)
      process.exit(1)
  }

  process.stdout.write(JSON.stringify(result, null, 2) + "\n")
}

main().catch(e => {
  process.stderr.write(`❌ ${e}\n`)
  process.exit(1)
})
