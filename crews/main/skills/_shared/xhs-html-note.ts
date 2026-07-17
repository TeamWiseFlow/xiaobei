/**
 * xhs-html-note.ts — 小红书笔记详情走 SSR HTML 路线（get_note_by_id_from_html）
 *
 * 直接 GET https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...&xsec_source=pc_feed，
 * 解析页面拿 title / desc / author / coverUrl / videoUrl / durationMs / 互动计数。
 *
 * 数据来源（合并，互为兜底）：
 *   - og: meta 标签（<meta property="og:*">）— 公开 SSR，无 cookie 也有，给 title/desc/cover/video。
 *   - window.__INITIAL_STATE__.note.noteDetailMap[note_id].note — 给 author/duration/互动计数/video 流。
 *
 * 为何不走 feed API（/api/sns/web/v1/feed）：feed 需 xRap 签名 + 极易 406/500/滑块
 * （MediaCrawlerPro get_note_by_id 原注释印证「开启xsec_token详情接口特别容易出现滑块验证」）。
 * HTML 路线是真实页面导航，风控远低于签名 API；带 xsec_token 的公开笔记无 cookie 也能 SSR。
 *
 * headers 形态参考 MediaCrawlerPro xhs/client.py 的 headers 属性。因是真实页面导航（非 XHR），
 * sec-fetch 用 document/navigate，accept 用 text/html。cookie 可为空（公开笔记无 cookie SSR）。
 * camoufox 造的 cookie 来自 Firefox，故按 UA 家族区分 sec-ch-ua：Firefox 不发 brand 列表，
 * 仅发 platform/mobile；Chrome 发完整 sec-ch-ua——避免 UA 与 sec-ch-ua 不一致的指纹破绽。
 *
 * 导出（供 viral-chaser / published-track / xhs-content-ops 复用）：
 *   parseXhsCount(v) — 计数串 "1.2万"/"3.5亿" → number
 *   xhsBrowserHeaders(ua, cookieStr) — 笔记详情页导航请求头
 *   extractInitialState(html) — 解 window.__INITIAL_STATE__（JSON.parse + vm 兜底）
 *   parseXhsNoteFromHtml(html, noteId) — 合并 og:meta + __INITIAL_STATE__ → XhsHtmlNote | null
 *   fetchXhsNoteFromHtml(noteId, opts) — 抓取 + 解析，带重试 + captcha 检测
 */

import vm from "node:vm"

export interface XhsHtmlNote {
  noteId: string
  type: string // "video" | "normal"
  title: string
  desc: string
  author: string
  coverUrl: string
  videoUrl: string
  durationMs: number
  stats: {
    likeCount: number
    collectCount: number
    commentCount: number
    shareCount: number
  }
  /** 话题标签（图文笔记）。视频笔记也可能有。 */
  tags: string[]
  /** 图文笔记的图片地址列表（urlDefault 优先）。视频笔记为空。 */
  imageUrls: string[]
}

export class XhsCaptchaError extends Error {
  constructor() {
    super("NEED_VERIFY: 小红书出现安全验证滑块，请扫码验证后重试")
    this.name = "XhsCaptchaError"
  }
}

export class XhsNoteInaccessibleError extends Error {
  constructor(msg = "多次重试仍未拿到笔记数据（可能笔记已删除/私密或触发风控）") {
    super(`NOTE_INACCESSIBLE: ${msg}`)
    this.name = "XhsNoteInaccessibleError"
  }
}

// ── 计数解析 ─────────────────────────────────────────────────────────────────

/** 解析 xhs 计数串：支持 "12345" / "1.2万" / "3.5亿" / 12345（Number）。 */
export function parseXhsCount(v: unknown): number {
  if (v == null || v === "") return 0
  const s = String(v).trim()
  const m = /^(-?[\d.]+)\s*(万|亿)?$/.exec(s)
  if (!m) return Number(s) || 0
  let n = parseFloat(m[1])
  if (m[2] === "万") n *= 1e4
  else if (m[2] === "亿") n *= 1e8
  return Math.round(n)
}

// ── 请求头 ───────────────────────────────────────────────────────────────────

const DEFAULT_CHROME_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

/** 构造 xhs 笔记详情页导航请求头。cookieStr 可为空（公开笔记无 cookie SSR）。 */
export function xhsBrowserHeaders(ua: string, cookieStr: string): Record<string, string> {
  const ua0 = ua || DEFAULT_CHROME_UA
  const isFirefox = /Firefox\//.test(ua0)
  const chromeVer = (/Chrome\/(\d+)/.exec(ua0)?.[1]) ?? "146"
  let platform = '"macOS"'
  if (/Windows/.test(ua0)) platform = '"Windows"'
  else if (/Linux/.test(ua0)) platform = '"Linux"'
  const h: Record<string, string> = {
    accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    pragma: "no-cache",
    priority: "u=1, i",
    referer: "https://www.xiaohongshu.com/",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": platform,
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": ua0,
  }
  if (cookieStr) h.cookie = cookieStr
  if (!isFirefox) {
    h["sec-ch-ua"] = `"Chromium";v="${chromeVer}", "Not-A.Brand";v="24", "Google Chrome";v="${chromeVer}"`
  }
  return h
}

// ── __INITIAL_STATE__ 解析 ───────────────────────────────────────────────────

/** 从 HTML 抽 window.__INITIAL_STATE__ 对象。JSON.parse 快路径 + vm 慢路径兜底。返回 null 表示未抽到。 */
export function extractInitialState(html: string): any | null {
  const m = html.match(/window\.__INITIAL_STATE__\s*=\s*([\s\S]*?)<\/script>/)
  if (!m) return null
  const literal = m[1].trim().replace(/;$/, "")
  try {
    return JSON.parse(literal.replace(/\bundefined\b/g, "null"))
  } catch {
    try {
      return vm.runInNewContext("(" + literal + ")", {})
    } catch {
      return null
    }
  }
}

// ── og: meta 解析 ────────────────────────────────────────────────────────────

function parseOgMeta(html: string): Record<string, string> {
  const og: Record<string, string> = {}
  const re = /<meta\s+property="og:([a-zA-Z_:]+)"\s+content="([^"]*)"/g
  let m: RegExpExecArray | null
  while ((m = re.exec(html))) og[m[1]] = m[2]
  return og
}

// ── 合并解析 ─────────────────────────────────────────────────────────────────

/**
 * 从笔记详情页 HTML 解析出完整笔记信息（og:meta + __INITIAL_STATE__ 合并）。
 * 返回 null 表示未解析到（验证码/笔记不存在/页面未就绪）。
 * 新发笔记四项计数全 0 属正常态，解析成功即返回，调用方勿据此重试。
 */
export function parseXhsNoteFromHtml(html: string, noteId: string): XhsHtmlNote | null {
  // 验证码重定向页直接判失败
  if (/website-login\/captcha/.test(html)) return null

  const og = parseOgMeta(html)
  const state = extractInitialState(html)
  const noteMap = state?.note?.noteDetailMap ?? state?.note?.note_detail_map
  const note = noteMap?.[noteId]?.note

  // type / author / duration / stats 只能从 __INITIAL_STATE__ 拿
  const type: string = note?.type ?? note?.noteType ?? ""
  const author: string = note?.user?.nickName ?? note?.user?.nickname ?? ""

  // 封面：og:image 优先（公开 SSR 稳），兜底 state note.cover
  const coverUrl: string =
    og.image ||
    note?.cover?.urlDefault ||
    note?.cover?.url_default ||
    note?.cover?.url ||
    ""

  // 视频地址：state video stream 优先（masterUrl 直链），兜底 og:video
  let videoUrl = ""
  const video = note?.video
  if (video) {
    const h264 = video?.media?.stream?.h264 ?? video?.media?.stream?.h265 ?? []
    videoUrl = h264[0]?.masterUrl ?? h264[0]?.master_url ?? ""
    if (!videoUrl) {
      // consumer.originVideoKey 是个 key，需拼域名——仅当无直链时作最后线索，此处不拼，留空走 og:video
      const originKey = video?.consumer?.originVideoKey ?? video?.consumer?.origin_video_key
      if (originKey) videoUrl = "" // 不直接用 key，交给 og:video
    }
  }
  if (!videoUrl && og.video) videoUrl = og.video

  // 时长（ms）：HTML state 里 video.capa.duration 单位是**秒**（实测 129 = 2 分 09 秒），
  // 需 ×1000。feed API 的 video.duration 才是 ms，但 HTML state 无该字段——
  // 若将来出现 video.duration 则按 ms 直用，否则 capa.duration（秒）×1000。
  let durationMs = 0
  if (video) {
    if (video.duration != null) {
      const d = video.duration
      durationMs = typeof d === "number" ? d : parseInt(String(d), 10) || 0
    } else if (video.capa?.duration != null) {
      const d = video.capa.duration
      const sec = typeof d === "number" ? d : parseInt(String(d), 10) || 0
      durationMs = sec * 1000
    }
  }

  // 互动计数：interactInfo（camelCase 优先，snake_case 兜底）
  const ii = note?.interactInfo ?? note?.interact_info ?? {}
  const pick = (o: any, ...keys: string[]): number => {
    for (const k of keys) if (o?.[k] != null && o?.[k] !== "") return parseXhsCount(o[k])
    return 0
  }
  const stats = {
    likeCount: pick(ii, "likedCount", "liked_count"),
    collectCount: pick(ii, "collectedCount", "collected_count"),
    commentCount: pick(ii, "commentCount", "comment_count"),
    shareCount: pick(ii, "shareCount", "share_count"),
  }

  const title: string = note?.title ?? og.title ?? ""
  const desc: string = note?.desc ?? og.description ?? ""

  // 话题标签：tagList（camelCase）优先，tag_list 兜底
  const tagArr = note?.tagList ?? note?.tag_list ?? []
  const tags: string[] = Array.isArray(tagArr)
    ? tagArr.map((t: any) => t?.name ?? "").filter(Boolean)
    : []

  // 图文图片列表：imageList（camelCase）优先，image_list 兜底；urlDefault 优先
  const imgArr = note?.imageList ?? note?.image_list ?? []
  const imageUrls: string[] = Array.isArray(imgArr)
    ? imgArr.map((img: any) => img?.urlDefault || img?.url_default || img?.url || "")
        .filter(Boolean)
        .map((u: string) => (u.startsWith("//") ? "https:" + u : u))
    : []

  // 至少要有 title 或 videoUrl 才算解析成功（避免空页误判成功）
  if (!title && !videoUrl && !coverUrl) return null

  // 协议相对 //host 补 https:；http CDN 升 https（XHS CDN 支持 https，避免明文链接）
  const norm = (u: string): string => {
    if (!u) return u
    if (u.startsWith("//")) return "https:" + u
    if (u.startsWith("http://")) return "https://" + u.slice(7)
    return u
  }

  return {
    noteId,
    type,
    title,
    desc,
    author,
    coverUrl: norm(coverUrl),
    videoUrl: norm(videoUrl),
    durationMs,
    stats,
    tags,
    imageUrls,
  }
}

// ── 抓取 ─────────────────────────────────────────────────────────────────────

const XHS_BROWSE_BASE = "https://www.xiaohongshu.com"
const CAPTCHA_RE = /www\.xiaohongshu\.com\/website-login\/captcha\?redirectPath=/
const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

export interface FetchXhsNoteOpts {
  xsecToken: string
  xsecSource?: string
  /** cookie 字符串（可选）。公开笔记带 xsec_token 时无 cookie 也能 SSR；cookie 提高风控阈值。 */
  cookieStr?: string
  /** UA（可选，空走默认 Chrome UA）。带 cookie 时应传造 cookie 的同指纹 UA。 */
  ua?: string
  retries?: number
}

/**
 * GET 笔记详情页 HTML 并解析。带重试 + captcha 检测。
 * - 命中滑块 → 抛 XhsCaptchaError
 * - 重试耗尽未拿到 → 抛 XhsNoteInaccessibleError
 */
export async function fetchXhsNoteFromHtml(
  noteId: string,
  opts: FetchXhsNoteOpts,
): Promise<XhsHtmlNote> {
  const retries = opts.retries ?? 5
  // token 入参可能已 percent-encoded（从 publish_url 抽出）或 raw（CLI 直传/profile 映射）；
  // 先 decode 再让 URLSearchParams 编码一次，避免双重编码（%3D → %253D）。
  let tok = opts.xsecToken
  try {
    tok = decodeURIComponent(opts.xsecToken)
  } catch {
    /* 已是 raw 或非法编码，保持原值 */
  }
  const qs = new URLSearchParams()
  qs.set("xsec_token", tok)
  qs.set("xsec_source", opts.xsecSource || "pc_feed")
  const url = `${XHS_BROWSE_BASE}/explore/${noteId}?${qs.toString()}`
  const headers = xhsBrowserHeaders(opts.ua ?? "", opts.cookieStr ?? "")

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(url, {
        headers,
        signal: AbortSignal.timeout(20_000),
      })
      if (!resp.ok) {
        process.stderr.write(`[xhs-html] HTML 请求返回 ${resp.status}（第 ${attempt}/${retries} 次）\n`)
        await sleep(800 + Math.random() * 1200)
        continue
      }
      const html = await resp.text()
      if (CAPTCHA_RE.test(html)) throw new XhsCaptchaError()
      const note = parseXhsNoteFromHtml(html, noteId)
      if (note) return note
      process.stderr.write(`[xhs-html] 第 ${attempt}/${retries} 次未解析到笔记数据，重试...\n`)
      await sleep(800 + Math.random() * 1200)
    } catch (e) {
      if (e instanceof XhsCaptchaError) throw e
      process.stderr.write(`[xhs-html] 抓取异常（第 ${attempt}/${retries} 次): ${e}\n`)
      await sleep(800 + Math.random() * 1200)
    }
  }
  throw new XhsNoteInaccessibleError()
}
