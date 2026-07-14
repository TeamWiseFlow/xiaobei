#!/usr/bin/env -S node --experimental-strip-types
/**
 * fetch-retro-data.ts — 复盘数据抓取（第一层：纯 HTTP + cookie + 签名）
 *
 * 这是复盘数据抓取的第一层，只拿基础互动指标（播放/点赞/评论数）。
 * 第二层（完播率/转粉率/评论内容等深度数据）通过 browser tool + evaluate
 * CDP 拦截实现，不在此脚本中。
 *
 * 签名方案复用：
 *   - 抖音: a_bogus（复用 viral-chaser 的 vendor/douyin.js）
 *   - B站:  WBI 签名（复用 viral-chaser 逻辑）
 *   - 快手:  GraphQL（无需签名）
 *
 * Cookie 来源: login-manager（~/.openclaw/logins/{platform}.json）
 *   小红书使用 xhs-browse cookie（消费者端域 www.xiaohongshu.com）
 *
 * Usage:
 *   node fetch-retro-data.ts --platform douyin --content-id <aweme_id>
 *   node fetch-retro-data.ts --platform bilibili --content-id <bvid>
 *   node fetch-retro-data.ts --platform kuaishou --content-id <photo_id>
 *   node fetch-retro-data.ts --platform xhs --content-id <note_id>
 *
 * Exit codes:
 *   0  成功 — JSON 输出到 stdout
 *   1  一般错误
 *   2  Cookie 无效/未登录 → 调用方应触发 login-manager
 */

const XHS_BROWSE_BASE = "https://www.xiaohongshu.com"

import { readFileSync, existsSync } from "fs"
import { join } from "path"
import { homedir } from "os"
import { execFile } from "child_process"
import { promisify } from "util"

const execFileAsync = promisify(execFile)

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
    return JSON.parse(readFileSync(path, "utf-8")) as SessionData
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

  // a_bogus 签名走 relay（D1 签名收敛到 server，vendor/douyin.js 已移至 relay）
  const { douyinSign } = await import("../../_shared/relay-sign.ts")

  const DOUYIN_API = "https://www.douyin.com"

  function douyinHeaders(cookieStr: string): Record<string, string> {
    return {
      "User-Agent": ua,
      "Cookie": cookieStr,
      "Referer": "https://www.douyin.com/",
      "Accept": "application/json",
    }
  }

  const result: RetroResult = {
    ok: true,
    platform: "douyin",
    contentId: awemeId,
    stats: {},
    comments: [],
  }

  // 1. 获取视频详情（aweme/detail 接口）
  console.error("  → 调抖音 API 获取视频详情...")
  try {
    const detailParams: Record<string, string> = {
      aweme_id: awemeId,
      ...Object.fromEntries([
        ["msToken", genFakeMsToken()],
      ]),
    }
    const paramStr = new URLSearchParams(detailParams).toString()
    const aBogus = await douyinSign({ queryString: paramStr, postData: "", ua })
    const url = `${DOUYIN_API}/aweme/v1/web/aweme/detail/?${paramStr}&a_bogus=${aBogus}`

    const resp = await fetch(url, {
      headers: douyinHeaders(cookieHeader(cookieDict)),
      signal: AbortSignal.timeout(15_000),
    })
    if (resp.ok) {
      const data = await resp.json() as any
      const aweme = data?.aweme_detail
      if (aweme) {
        const stats = aweme.statistics || {}
        result.stats = {
          playCount: stats.play_count || 0,
          likeCount: stats.digg_count || 0,
          commentCount: stats.comment_count || 0,
          shareCount: stats.share_count || 0,
          collectCount: stats.collect_count || 0,
        }
        console.error(`  ✓ 播放 ${result.stats.playCount} / 点赞 ${result.stats.likeCount} / 评论 ${result.stats.commentCount}`)
      }
    } else {
      console.error(`  ⚠️ 视频详情接口返回 ${resp.status}`)
    }
  } catch (e) {
    console.error(`  ⚠️ 视频详情获取失败: ${e}`)
  }

  // 2. 获取评论（comment/list 接口）
  console.error("  → 调抖音 API 获取评论...")
  try {
    const comments: Array<{ cid: string; text: string; likeCount: number; userName: string }> = []
    let cursor = 0

    for (let page = 0; page < 5; page++) {  // 最多 5 页
      const commentParams: Record<string, string> = {
        aweme_id: awemeId,
        cursor: String(cursor),
        count: "20",
        item_type: "0",
        insert_ids: "",
        msToken: genFakeMsToken(),
      }
      const paramStr = new URLSearchParams(commentParams).toString()
      const aBogus = await douyinSign({ queryString: paramStr, postData: "", ua })
      const url = `${DOUYIN_API}/aweme/v1/web/comment/list/?${paramStr}&a_bogus=${aBogus}`

      const resp = await fetch(url, {
        headers: douyinHeaders(cookieHeader(cookieDict)),
        signal: AbortSignal.timeout(15_000),
      })
      if (!resp.ok) break

      const data = await resp.json() as any
      const cmts = data?.comments || []
      if (cmts.length === 0) break

      for (const c of cmts) {
        comments.push({
          cid: c.cid || "",
          text: c.text || "",
          likeCount: c.digg_count || 0,
          userName: c.user?.nickname || "",
        })
      }

      cursor = data.cursor || 0
      if (!data.has_more) break
    }

    comments.sort((a, b) => b.likeCount - a.likeCount)
    result.comments = comments.slice(0, 50)
    console.error(`  ✓ 抓到 ${comments.length} 条评论`)
  } catch (e) {
    console.error(`  ⚠️ 评论获取失败: ${e}`)
  }

  return result
}

function genFakeMsToken(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
  let token = ""
  for (let i = 0; i < 126; i++) token += chars[Math.floor(Math.random() * chars.length)]
  return token + "=="
}

// ─── B站 ───────────────────────────────────────────────────────────────────

const BILI_API = "https://api.bilibili.com"
const BILI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

// WBI 签名走 relay（/api/v1/sign/bilibili/wbi，仅算 {wts, w_rid}）。
// imgKey/subKey 拉取与缓存归 client（契约 docs/API-CONTRACT.md §sign/bilibili/wbi）。
let wbiKeyCache: { imgKey: string; subKey: string; ts: number } | null = null

async function getWbiKeys(): Promise<{ imgKey: string; subKey: string }> {
  if (wbiKeyCache && Date.now() - wbiKeyCache.ts < 10 * 60 * 1000) {
    return { imgKey: wbiKeyCache.imgKey, subKey: wbiKeyCache.subKey }
  }

  const resp = await fetch(`${BILI_API}/x/web-interface/nav`, {
    headers: { "User-Agent": BILI_UA },
    signal: AbortSignal.timeout(10_000),
  })
  if (!resp.ok) throw new Error(`获取 WBI 密钥失败: ${resp.status}`)
  const data = await resp.json() as any
  const wbiImg = data?.data?.wbi_img
  if (!wbiImg) throw new Error("WBI 密钥字段不存在")

  wbiKeyCache = {
    imgKey: wbiImg.img_url.split("/").pop()!.split(".")[0],
    subKey: wbiImg.sub_url.split("/").pop()!.split(".")[0],
    ts: Date.now(),
  }
  return { imgKey: wbiKeyCache.imgKey, subKey: wbiKeyCache.subKey }
}

async function fetchBilibili(bvid: string): Promise<RetroResult> {
  const result: RetroResult = {
    ok: true,
    platform: "bilibili",
    contentId: bvid,
    stats: {},
    comments: [],
  }

  // 1. 视频详情（公开 API，无需 cookie）
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
    const aid = data.data.aid
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

    // 2. 评论（公开 API，WBI 签名走 relay）
    console.error("  → 调 B站 API 获取评论（relay 签名）...")
    const { bilibiliWbiSign } = await import("../../_shared/relay-sign.ts")
    const wbiKeys = await getWbiKeys()
    const comments: Array<{ cid: string; text: string; likeCount: number; userName: string }> = []

    for (let page = 1; page <= 5; page++) {
      const baseParams = { type: 1, oid: aid, pn: page, ps: 20, sort: 1 }
      const { wts, w_rid } = await bilibiliWbiSign({
        params: baseParams,
        imgKey: wbiKeys.imgKey,
        subKey: wbiKeys.subKey,
      })
      const qs = new URLSearchParams({ ...baseParams, wts, w_rid }).toString()
      const resp = await fetch(`${BILI_API}/x/v2/reply?${qs}`, {
        headers: { "User-Agent": BILI_UA },
        signal: AbortSignal.timeout(15_000),
      })
      if (!resp.ok) break
      const cmtData = await resp.json() as any
      if (cmtData.code !== 0) break
      const replies = cmtData?.data?.replies || []
      if (replies.length === 0) break

      for (const r of replies) {
        comments.push({
          cid: String(r.rpid || ""),
          text: r.content?.message || "",
          likeCount: r.like || 0,
          userName: r.member?.uname || "",
        })
      }
    }

    comments.sort((a, b) => b.likeCount - a.likeCount)
    result.comments = comments.slice(0, 50)
    console.error(`  ✓ 抓到 ${comments.length} 条评论`)
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

  // 1. 视频详情（GraphQL）
  console.error("  → 调快手 GraphQL 获取视频详情...")
  try {
    const query = `query visionVideoDetail($photoId: String) { visionVideoDetail(photoId: $photoId) { photo { id viewCount likeCount commentCount } } }`
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
          likeCount: photo.likeCount || 0,
          commentCount: photo.commentCount || 0,
        }
        console.error(`  ✓ 播放 ${result.stats.viewCount} / 点赞 ${result.stats.likeCount}`)
      }
    }
  } catch (e) {
    console.error(`  ⚠️ 快手详情获取失败: ${e}`)
  }

  // 2. 评论（GraphQL）
  console.error("  → 调快手 GraphQL 获取评论...")
  try {
    const comments: Array<{ cid: string; text: string; likeCount: number; userName: string }> = []
    let cursor = ""

    for (let page = 0; page < 5; page++) {
      const query = `query commentList($photoId: String, $cursor: String) { commentList(photoId: $photoId, cursor: $cursor) { comments { id content likeCount user { name } } cursor } }`
      const resp = await fetch(KUAISHOU_GQL, {
        method: "POST",
        headers: {
          "User-Agent": ua,
          "Cookie": cookieHeader(cookieDict),
          "Content-Type": "application/json",
          "Referer": "https://www.kuaishou.com/",
          "Origin": "https://www.kuaishou.com",
        },
        body: JSON.stringify({ query, variables: { photoId, cursor } }),
        signal: AbortSignal.timeout(15_000),
      })
      if (!resp.ok) break
      const data = await resp.json() as any
      const cmts = data?.data?.commentList?.comments || []
      if (cmts.length === 0) break

      for (const c of cmts) {
        comments.push({
          cid: String(c.id || ""),
          text: c.content || "",
          likeCount: c.likeCount || 0,
          userName: c.user?.name || "",
        })
      }
      cursor = data?.data?.commentList?.cursor || ""
      if (!cursor) break
    }

    comments.sort((a, b) => b.likeCount - a.likeCount)
    result.comments = comments.slice(0, 50)
    console.error(`  ✓ 抓到 ${comments.length} 条评论`)
  } catch (e) {
    console.error(`  ⚠️ 快手评论获取失败: ${e}`)
  }

  return result
}

// ─── 小红书 ────────────────────────────────────────────────────────────────

async function fetchXhs(noteId: string, xsecToken: string = "", xsecSource: string = ""): Promise<RetroResult> {
  const session = requireSession("xhs-browse")
  const cookieDict = parseCookies(session.cookies)
  const ua = sessionUA("xhs-browse", session)

  if (!cookieDict.a1 || !cookieDict.web_session) {
    process.stderr.write("[fetch-retro-data] 小红书 cookie 缺少 a1 或 web_session\n")
    process.exit(2)
  }

  const result: RetroResult = {
    ok: true,
    platform: "xhs",
    contentId: noteId,
    stats: {},
    comments: [],
  }

  // 签名走 relay
  const { xhsFetch } = await import("../../_shared/relay-sign.ts")

  console.error("  → 调小红书 API（relay 签名）...")
  try {
    // 1. 获取笔记详情 (feed 接口, POST)
    const feedUri = "/api/sns/web/v1/feed"
    const feedPayload: Record<string, unknown> = {
      source_note_id: noteId,
      image_formats: ["jpg", "webp", "avif"],
      extra: { need_body_topic: "1" },
    }
    if (xsecToken) {
      feedPayload.xsec_source = xsecSource || "pc_feed"
      feedPayload.xsec_token = xsecToken
    }
    const feedResp = await xhsFetch<{ data?: { items?: any[] }; msg?: string }>({
      baseUrl: XHS_BROWSE_BASE,
      uri: feedUri,
      method: "post",
      payload: feedPayload,
      cookies: cookieDict,
      xsecToken: xsecToken || undefined,
      xsecSource: xsecSource || undefined,
      xRap: true,
    })
    const items = feedResp.data?.items ?? []
    if (!items.length) {
      console.error(`  ❌ 小红书 feed 返回空 items（可能缺 xsec_token 或笔记已删除）`)
      return { ...result, ok: false, error: "NOTE_INACCESSIBLE", msg: feedResp.msg || "feed 返回空 items" }
    }
    for (const it of items) {
      const node = it.note_card ?? it.note ?? it
      const ii = node?.interact_info
      if (ii && typeof ii === "object") {
        result.stats = {
          likeCount: Number(ii.liked_count ?? 0),
          collectCount: Number(ii.collected_count ?? 0),
          commentCount: Number(ii.comment_count ?? 0),
          shareCount: Number(ii.share_count ?? 0),
        }
        break
      }
    }

    // 2. 获取评论 (comment/page 接口, GET, 分页)
    const comments: Array<{ cid: string; text: string; likeCount: number; userName: string }> = []
    let cursor = ""
    for (let page = 0; page < 5; page++) {
      const commentUri = "/api/sns/web/v2/comment/page"
      const commentParams: Record<string, string> = {
        note_id: noteId,
        cursor,
        top_comment_size: "0",
        image_formats: "jpg,webp,avif",
      }
      const cResp = await xhsFetch<{ data?: { comments?: any[]; cursor?: string; has_more?: boolean } }>({
        baseUrl: XHS_BROWSE_BASE,
        uri: commentUri,
        method: "get",
        params: commentParams,
        cookies: cookieDict,
      })
      const cmts = cResp.data?.comments ?? []
      if (!cmts.length) break
      for (const c of cmts) {
        const user = c.user_info ?? {}
        comments.push({
          cid: String(c.id ?? ""),
          text: c.content ?? "",
          likeCount: Number(c.like_count ?? 0),
          userName: user.nickname ?? "",
        })
      }
      cursor = cResp.data?.cursor ?? ""
      if (!cursor || !cResp.data?.has_more) break
    }
    comments.sort((a, b) => b.likeCount - a.likeCount)
    result.comments = comments.slice(0, 50)
    console.error(`  ✓ 点赞 ${result.stats.likeCount || 0} / 收藏 ${result.stats.collectCount || 0} / 评论 ${result.comments.length} 条`)
  } catch (e) {
    console.error(`  ⚠️ 小红书数据获取失败: ${e}`)
    return { ...result, ok: false, error: "XHS_FETCH_EXCEPTION", msg: String(e) }
  }

  return result
}

// ─── Main ─────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  let platform = ""
  let contentId = ""
  let xsecToken = ""
  let xsecSource = ""

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i]
    else if (args[i] === "--content-id" && args[i + 1]) contentId = args[++i]
    else if (args[i] === "--xsec-token" && args[i + 1]) xsecToken = args[++i]
    else if (args[i] === "--xsec-source" && args[i + 1]) xsecSource = args[++i]
  }

  if (!platform || !contentId) {
    process.stderr.write("用法: node fetch-retro-data.ts --platform <douyin|bilibili|kuaishou|xhs> --content-id <id> [--xsec-token <t> --xsec-source <s>]\n")
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
      result = await fetchXhs(contentId, xsecToken, xsecSource)
      break
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
