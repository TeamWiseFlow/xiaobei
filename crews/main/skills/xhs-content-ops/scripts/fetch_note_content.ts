#!/usr/bin/env -S node --experimental-strip-types
/**
 * fetch_note_content.ts — Download XHS note images and text for analysis
 *
 * and outputs structured JSON with text + local image paths.
 *
 * Cookie source: xhs-browse (consumer domain www.xiaohongshu.com)
 *
 * 内置探活（仿 viral-chaser）：抓取前调 _shared/check-session.ts 的 checkSession，
 * Tier1 cookie 字段门 + Tier2 user/me pong，pong 带 TTL 缓存（600s），
 * 批量抓多条时 N 次 pong 压成 1 次，避免批量签名触风控。
 *
 * Usage:
 *   node fetch_note_content.ts --note-id <id> --output-dir <dir>
 *
 * Exit codes:
 *   0  Success
 *   1  General error / SIGN_UNAVAILABLE（relay 签名缺 OFB_KEY，重登无益）
 *   2  Cookie expired → trigger login-manager
 */

import { readFileSync, existsSync, mkdirSync, writeFileSync } from "fs"
import { join, dirname } from "path"
import { homedir } from "os"
import { execFile } from "child_process"
import { promisify } from "util"

const execFileAsync = promisify(execFile)

// ── CLI args ────────────────────────────────────────────────────────────────

const args = process.argv.slice(2)
let url = ""
let noteId = ""
let xsecToken = ""
let xsecSource = ""
let outputDir = ""

for (let i = 0; i < args.length; i++) {
  if (args[i] === "--url" && args[i + 1]) url = args[++i]
  else if (args[i] === "--note-id" && args[i + 1]) noteId = args[++i]
  else if (args[i] === "--xsec-token" && args[i + 1]) xsecToken = args[++i]
  else if (args[i] === "--xsec-source" && args[i + 1]) xsecSource = args[++i]
  else if (args[i] === "--output-dir" && args[i + 1]) outputDir = args[++i]
}

// ── URL / short-link resolution ─────────────────────────────────────────────
// Resolve xhslink.com short links (curl — Node 24 fetch breaks on some redirect
// chains with "location is not defined") and extract noteId + xsec_token from
// the final URL. Mirrors viral-chaser's link_parser behavior.

async function resolveXhsUrl(rawUrl: string): Promise<{ noteId: string; xsecToken: string; xsecSource: string }> {
  let resolved = rawUrl
  const hostname = (() => { try { return new URL(rawUrl).hostname } catch { return "" } })()
  if (hostname === "xhslink.com") {
    try {
      const { stdout } = await execFileAsync(
        "curl",
        ["-sS", "-L", "--max-time", "15", "-o", "/dev/null", "-w", "%{url_effective}", rawUrl],
        { timeout: 20_000, maxBuffer: 1024 * 1024 },
      )
      const effective = stdout.trim()
      if (effective && /^https?:\/\//.test(effective)) resolved = effective
    } catch (e) {
      process.stderr.write(`[xhs-content-ops] 短链解析失败: ${(e as Error).message}\n`)
    }
  }
  const idMatch = resolved.match(/\/(?:explore|discovery\/item|note)\/([a-zA-Z0-9]+)/)
  const tokenMatch = resolved.match(/[?&]xsec_token=([^&]+)/)
  const sourceMatch = resolved.match(/[?&]xsec_source=([^&]+)/)
  return {
    noteId: idMatch ? idMatch[1] : "",
    xsecToken: tokenMatch ? decodeURIComponent(tokenMatch[1]) : "",
    xsecSource: sourceMatch ? decodeURIComponent(sourceMatch[1]) : "",
  }
}

if (url) {
  const r = await resolveXhsUrl(url)
  if (r.noteId) noteId = r.noteId
  if (r.xsecToken) xsecToken = r.xsecToken
  if (r.xsecSource) xsecSource = r.xsecSource
}

if (!noteId || !outputDir) {
  process.stderr.write(
    "Usage: fetch_note_content.ts --url <url> | --note-id <id> [--xsec-token <t>] [--xsec-source <s>] --output-dir <dir>\n",
  )
  process.exit(1)
}

// ── Session（内置探活，仿 viral-chaser）──────────────────────────────────────
//
// 抓取前探活合并进脚本：checkSession 做 Tier1 cookie 字段门 + Tier2 user/me pong，
// pong 带 TTL 缓存（600s），批量抓多条时 N 次 pong 压成 1 次，避免批量签名触风控。
// 不再让 Agent 单独跑 check-login.ts 探活。
//
// 中央存储格式（forked camoufox-cli 原生输出，= Playwright add_cookies 期望格式）：
//   ~/.openclaw/logins/xhs-browse.json     → { platform, cookies: [{name, value, domain, ...}], updated_at }
//   ~/.openclaw/logins/xhs-browse.ua.json  → { userAgent, platform, language, ... }
// 本脚本同时导入 cookie + UA——同一指纹下的 cookie 才不会被风控错配。

import { checkSession, loadCookies, loadUa } from "../../_shared/check-session.ts"
import { xhsFetch, LoginWallError } from "../../_shared/relay-sign.ts"

// 探活 + cookie/UA 加载在 main() 里做（async）。这里只声明，main 里赋值。
let cookieDict: Record<string, string> = {}
let userAgent = ""

const XHS_BROWSE_PLATFORM = "xhs-browse"

const XHS_BROWSE_BASE = "https://www.xiaohongshu.com"

interface NoteCard {
  note_id?: string
  display_title?: string
  title?: string
  desc?: string
  type?: string
  user?: { nickname?: string }
  cover?: { url_default?: string; url?: string }
  interact_info?: Record<string, string | number>
  tag_list?: Array<{ name?: string }>
  image_list?: Array<{ url_default?: string; url?: string }>
}

interface FeedResponse {
  data?: { items?: Array<Record<string, unknown>> }
}

async function fetchNoteDetail(): Promise<{
  ok: boolean
  error?: string
  hint?: string
  title?: string
  desc?: string
  noteType?: string
  author?: string
  coverUrl?: string
  stats?: Record<string, number>
  tags?: string[]
  imageUrls?: string[]
}> {
  const uri = "/api/sns/web/v1/feed"
  const payload: Record<string, unknown> = {
    source_note_id: noteId,
    image_formats: ["jpg", "webp", "avif"],
    extra: { need_body_topic: "1" },
  }
  if (xsecToken) {
    payload.xsec_source = xsecSource || "pc_feed"
    payload.xsec_token = xsecToken
  }
  const resp = await xhsFetch<FeedResponse>({
    baseUrl: XHS_BROWSE_BASE,
    uri,
    method: "post",
    payload,
    cookies: cookieDict,
    xsecToken: xsecToken || undefined,
    xsecSource: xsecSource || undefined,
    xRap: true,
  })
  const items = resp.data?.items ?? []
  let noteCard: NoteCard | null = null
  for (const it of items) {
    const nc = (it.note_card ?? it.note ?? it) as NoteCard
    if (nc && typeof nc === "object" && nc.note_id) {
      noteCard = nc
      break
    }
  }
  if (!noteCard) return { ok: false, error: "note_card not found in feed response" }

  const ii = noteCard.interact_info ?? {}
  const tags = (noteCard.tag_list ?? []).map((t) => t.name ?? "").filter(Boolean)
  const imageUrls = (noteCard.image_list ?? [])
    .map((img) => img.url_default || img.url || "")
    .filter(Boolean)

  if (noteCard.type === "video") {
    return { ok: false, error: "VIDEO_NOTE", hint: "请使用 viral-chaser 技能下载和分析视频笔记" }
  }

  return {
    ok: true,
    title: noteCard.display_title || noteCard.title || "",
    desc: noteCard.desc ?? "",
    noteType: noteCard.type ?? "",
    author: noteCard.user?.nickname ?? "",
    coverUrl: noteCard.cover?.url_default || noteCard.cover?.url || "",
    stats: {
      likeCount: Number(ii.liked_count ?? 0),
      collectCount: Number(ii.collected_count ?? 0),
      commentCount: Number(ii.comment_count ?? 0),
      shareCount: Number(ii.share_count ?? 0),
    },
    tags,
    imageUrls,
  }
}

// ── Image download ──────────────────────────────────────────────────────────

async function downloadImage(url: string, filePath: string): Promise<boolean> {
  const headers: Record<string, string> = {
    "User-Agent": userAgent || "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://www.xiaohongshu.com/",
    "Origin": "https://www.xiaohongshu.com",
  }

  try {
    const resp = await fetch(url, { headers, signal: AbortSignal.timeout(30_000) })
    if (!resp.ok || !resp.body) return false

    const { pipeline } = await import("stream/promises")
    const { createWriteStream } = await import("fs")
    const { Readable } = await import("stream")

    const fileStream = createWriteStream(filePath)
    const nodeReadable = Readable.fromWeb(resp.body as any)
    await pipeline(nodeReadable, fileStream)
    return true
  } catch {
    // fall through to curl
  }

  // curl fallback — Node 24 fetch breaks on some CDN redirects ("location is not defined")
  try {
    const curlArgs = ["-sS", "-L", "--max-time", "30",
      "-A", headers["User-Agent"],
      "-H", `Referer: ${headers.Referer}`,
      "-H", `Origin: ${headers.Origin}`,
      "-o", filePath, url]
    await execFileAsync("curl", curlArgs, { timeout: 35_000, maxBuffer: 1024 * 1024 })
    const { statSync } = await import("fs")
    return statSync(filePath).size > 0
  } catch {
    return false
  }
}

// ── Main ────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  mkdirSync(outputDir, { recursive: true })

  // 抓取前探活（仿 viral-chaser）：checkSession 做 Tier1 字段门 + Tier2 user/me pong，
  // pong 带 TTL 缓存（600s），批量抓多条时 N 次 pong 压成 1 次，避免批量签名触风控。
  // 探活失败按 exit code 约定：SESSION_EXPIRED → exit 2（交 login-manager 重登）；
  // SIGN_UNAVAILABLE → exit 1（relay 签名缺 OFB_KEY，重登无益，交 IT engineer 配凭证）。
  const probe = await checkSession(XHS_BROWSE_PLATFORM)
  if (!probe.ok) {
    const err = probe.error === "SIGN_UNAVAILABLE" ? "SIGN_UNAVAILABLE" : "SESSION_EXPIRED"
    process.stderr.write(`[xhs-content-ops] 🔒 探活失败: ${err}${probe.reason ? ` (${probe.reason})` : ""}\n`)
    process.stdout.write(JSON.stringify({ ok: false, error: err, platform: XHS_BROWSE_PLATFORM, reason: probe.reason }) + "\n")
    process.exit(err === "SESSION_EXPIRED" ? 2 : 1)
  }
  process.stderr.write(`[xhs-content-ops] 探活通过 (detail=${probe.detail ?? "n/a"}, ping=${probe.ping ?? "n/a"})\n`)

  // 探活通过后加载 cookie + UA 供 fetch / 下载用
  const loaded = loadCookies(XHS_BROWSE_PLATFORM)
  if (!loaded) {
    process.stderr.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform: XHS_BROWSE_PLATFORM }) + "\n")
    process.exit(2)
  }
  for (const [k, c] of Object.entries(loaded.map)) {
    if (c?.value) cookieDict[k] = c.value
  }
  userAgent = loadUa(XHS_BROWSE_PLATFORM)

  process.stderr.write(`[xhs-content-ops] 获取笔记详情 (noteId=${noteId})...\n`)

  // 1. Fetch note detail via relay sign proxy
  const data = await fetchNoteDetail()

  if (!data.ok) {
    if (data.error === "VIDEO_NOTE") {
      // Video note — tell caller to use viral-chaser
      process.stdout.write(JSON.stringify({
        ok: false,
        error: "VIDEO_NOTE",
        noteId,
        noteType: "video",
        hint: "请使用 viral-chaser 技能下载和分析视频笔记",
      }, null, 2) + "\n")
      process.exit(0)  // Not an error per se, just not our domain
    }
    process.stderr.write(`[xhs-content-ops] ❌ ${data.error}\n`)
    process.stdout.write(JSON.stringify({ ok: false, error: data.error }, null, 2) + "\n")
    process.exit(1)
  }

  // 2. Download images
  const imageUrls: string[] = data.imageUrls || []
  const localImages: string[] = []

  process.stderr.write(`[xhs-content-ops] 下载 ${imageUrls.length} 张图片...\n`)

  for (let i = 0; i < imageUrls.length; i++) {
    const url = imageUrls[i]
    // Determine extension from URL or default to jpg
    let ext = "jpg"
    if (url.includes(".png")) ext = "png"
    else if (url.includes(".webp")) ext = "webp"
    else if (url.includes(".avif")) ext = "avif"

    const filename = `img_${String(i).padStart(2, "0")}.${ext}`
    const filePath = join(outputDir, filename)

    const ok = await downloadImage(url, filePath)
    if (ok) {
      localImages.push(filePath)
      process.stderr.write(`  ✓ [${i + 1}/${imageUrls.length}] ${filename}\n`)
    } else {
      process.stderr.write(`  ⚠️ [${i + 1}/${imageUrls.length}] 下载失败: ${url.slice(0, 60)}...\n`)
    }

    // Rate limit: 500ms between downloads
    if (i < imageUrls.length - 1) {
      await new Promise(r => setTimeout(r, 500))
    }
  }

  // 3. Save text content as markdown
  const mdContent = [
    `# ${data.title || "无标题"}`,
    "",
    data.desc || "",
    "",
    data.tags?.length ? `标签：${data.tags.map((t: string) => `#${t}`).join(" ")}` : "",
    "",
    `作者：${data.author || "未知"}`,
    `点赞：${data.stats?.likeCount ?? 0} | 收藏：${data.stats?.collectCount ?? 0} | 评论：${data.stats?.commentCount ?? 0}`,
  ].join("\n")

  const mdPath = join(outputDir, "content.md")
  writeFileSync(mdPath, mdContent, "utf-8")

  // 4. Output result JSON
  const result = {
    ok: true,
    noteId,
    noteType: data.noteType || "normal",
    title: data.title || "",
    desc: data.desc || "",
    author: data.author || "",
    stats: data.stats || {},
    images: localImages,
    coverUrl: data.coverUrl || "",
    tags: data.tags || [],
    contentMd: mdPath,
  }

  process.stdout.write(JSON.stringify(result, null, 2) + "\n")
  process.stderr.write(`[xhs-content-ops] ✓ 完成。${localImages.length} 张图片 + 正文已保存到 ${outputDir}\n`)
}

main().catch(e => {
  // 登录墙（HTML 代替 JSON）→ SESSION_EXPIRED + exit 2，交 login-manager 重登
  if (e instanceof LoginWallError || String(e).startsWith("SESSION_EXPIRED")) {
    process.stderr.write(`[xhs-content-ops] 🔒 cookie 失效（HTML 登录墙）: ${e}\n`)
    process.stdout.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform: "xhs-browse" }) + "\n")
    process.exit(2)
  }
  process.stderr.write(`[xhs-content-ops] ❌ ${e}\n`)
  process.stdout.write(JSON.stringify({ ok: false, error: String(e) }) + "\n")
  process.exit(1)
})
