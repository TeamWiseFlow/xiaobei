#!/usr/bin/env -S node --experimental-strip-types
/**
 * fetch_note_content.ts — Download XHS note images and text for analysis
 *
 * 走 SSR HTML 路线（get_note_by_id_from_html）：GET 笔记详情页 HTML，
 * 解析 og:meta + window.__INITIAL_STATE__ 拿 title/desc/author/cover/stats/tags/imageList。
 * 详见 _shared/xhs-html-note.ts。
 *
 * 为何不走 feed API（/api/sns/web/v1/feed）：feed 需 xRap relay 签名 + 极易 406/500/滑块，
 * 且探活 user/me 通过不代表 feed 签名路径被接受（不同端点/签名/方法），会出现「探活绿、feed 红」假绿。
 * HTML 路线是真实页面导航，风控远低；带 xsec_token 的公开笔记无 cookie 也能 SSR。
 *
 * Cookie：可选回退。无 cookie 抓不到（滑块/空页）时，若本机有 xhs-browse session，
 * 用同指纹 UA + cookie 重试一次。无 xsec_token 直接报错（需从搜索 snapshot 或分享链接带 token）。
 *
 * Usage:
 *   node fetch_note_content.ts --note-id <id> --xsec-token <t> --output-dir <dir>
 *   node fetch_note_content.ts --url <url> --output-dir <dir>
 *
 * Exit codes:
 *   0  Success（含 VIDEO_NOTE 提示——视频笔记交 viral-chaser，非错误）
 *   1  General error / 无 xsec_token / SIGN_UNAVAILABLE
 *   2  Cookie expired → trigger login-manager（cookie 回退仍失败时）
 */

import { mkdirSync, writeFileSync } from "fs"
import { join } from "path"
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
    "Usage: fetch_note_content.ts --url <url> | --note-id <id> --xsec-token <t> [--xsec-source <s>] --output-dir <dir>\n",
  )
  process.exit(1)
}

if (!xsecToken) {
  process.stderr.write(
    JSON.stringify({
      ok: false,
      error: "NO_XSEC_TOKEN",
      msg: "小红书需要 xsec_token。请传 --url（分享链接，脚本自动抽 token）或 --note-id + --xsec-token（从搜索 snapshot 拿）。",
    }) + "\n",
  )
  process.exit(1)
}

// ── Session（可选，仅作 cookie 回退）──────────────────────────────────────────
//
// xhs 走无 cookie HTML 路线，session 非必需。仅当无 cookie 抓不到（滑块/空页）时
// 用 xhs-browse 同指纹 UA + cookie 重试一次。同时导入 cookie + UA——同一指纹下的
// cookie 才不会被风控错配（spec §4 原则 4）。

import { loadCookies, loadUa } from "../../_shared/check-session.ts"
import {
  fetchXhsNoteFromHtml,
  XhsCaptchaError,
  XhsNoteInaccessibleError,
} from "../../_shared/xhs-html-note.ts"

const XHS_BROWSE_PLATFORM = "xhs-browse"

const cookieSession = loadCookies(XHS_BROWSE_PLATFORM)
const cookieStr = cookieSession
  ? Object.entries(cookieSession.map).filter(([, c]) => c?.value).map(([k, c]) => `${k}=${c.value}`).join("; ")
  : ""
const sessionUa = loadUa(XHS_BROWSE_PLATFORM)

// ── Image download ──────────────────────────────────────────────────────────

async function downloadImage(imgUrl: string, filePath: string): Promise<boolean> {
  const ua = sessionUa || "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
  const headers: Record<string, string> = {
    "User-Agent": ua,
    "Referer": "https://www.xiaohongshu.com/",
    "Origin": "https://www.xiaohongshu.com",
  }

  try {
    const resp = await fetch(imgUrl, { headers, signal: AbortSignal.timeout(30_000) })
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
      "-o", filePath, imgUrl]
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

  process.stderr.write(`[xhs-content-ops] GET 笔记详情页 HTML (noteId=${noteId})...\n`)

  // 1. 无 cookie 优先；滑块/空页且有 session 时用 cookie 回退一次
  let note
  try {
    note = await fetchXhsNoteFromHtml(noteId, { xsecToken, xsecSource })
  } catch (e) {
    if (e instanceof XhsCaptchaError || e instanceof XhsNoteInaccessibleError) {
      if (!cookieStr) {
        // 无 cookie 回退可用 → cookie 可能过期，交 login-manager
        const err = e instanceof XhsCaptchaError ? "NEED_VERIFY" : "NOTE_INACCESSIBLE"
        process.stderr.write(`[xhs-content-ops] 🔒 ${err}：无 cookie 抓取失败且本机无 xhs-browse cookie 可回退\n`)
        process.stdout.write(
          JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform: XHS_BROWSE_PLATFORM, reason: err }) + "\n",
        )
        process.exit(2)
      }
      process.stderr.write(`[xhs-content-ops] 无 cookie 抓取失败（${e instanceof XhsCaptchaError ? "滑块" : "空页"}），用 xhs-browse cookie 回退...\n`)
      try {
        note = await fetchXhsNoteFromHtml(noteId, { xsecToken, xsecSource, cookieStr, ua: sessionUa })
      } catch (e2) {
        if (e2 instanceof XhsCaptchaError) {
          process.stdout.write(JSON.stringify({ ok: false, error: "NEED_VERIFY", msg: "小红书出现安全验证滑块，请扫码验证后重试" }) + "\n")
          process.exit(1)
        }
        process.stderr.write(`[xhs-content-ops] ❌ cookie 回退仍失败: ${e2}\n`)
        process.stdout.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform: XHS_BROWSE_PLATFORM }) + "\n")
        process.exit(2)
      }
    } else {
      throw e
    }
  }

  // 2. 视频笔记 → 交 viral-chaser
  if (note.type === "video") {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: "VIDEO_NOTE",
      noteId,
      noteType: "video",
      hint: "请使用 viral-chaser 技能下载和分析视频笔记",
    }, null, 2) + "\n")
    process.exit(0)
  }

  // 3. 下载图片
  const imageUrls: string[] = note.imageUrls || []
  const localImages: string[] = []

  process.stderr.write(`[xhs-content-ops] 下载 ${imageUrls.length} 张图片...\n`)

  for (let i = 0; i < imageUrls.length; i++) {
    const imgUrl = imageUrls[i]
    let ext = "jpg"
    if (imgUrl.includes(".png")) ext = "png"
    else if (imgUrl.includes(".webp")) ext = "webp"
    else if (imgUrl.includes(".avif")) ext = "avif"

    const filename = `img_${String(i).padStart(2, "0")}.${ext}`
    const filePath = join(outputDir, filename)

    const ok = await downloadImage(imgUrl, filePath)
    if (ok) {
      localImages.push(filePath)
      process.stderr.write(`  ✓ [${i + 1}/${imageUrls.length}] ${filename}\n`)
    } else {
      process.stderr.write(`  ⚠️ [${i + 1}/${imageUrls.length}] 下载失败: ${imgUrl.slice(0, 60)}...\n`)
    }

    // Rate limit: 500ms between downloads
    if (i < imageUrls.length - 1) {
      await new Promise(r => setTimeout(r, 500))
    }
  }

  // 4. Save text content as markdown
  const mdContent = [
    `# ${note.title || "无标题"}`,
    "",
    note.desc || "",
    "",
    note.tags.length ? `标签：${note.tags.map((t: string) => `#${t}`).join(" ")}` : "",
    "",
    `作者：${note.author || "未知"}`,
    `点赞：${note.stats.likeCount} | 收藏：${note.stats.collectCount} | 评论：${note.stats.commentCount}`,
  ].join("\n")

  const mdPath = join(outputDir, "content.md")
  writeFileSync(mdPath, mdContent, "utf-8")

  // 5. Output result JSON
  const result = {
    ok: true,
    noteId,
    noteType: note.type || "normal",
    title: note.title,
    desc: note.desc,
    author: note.author,
    stats: note.stats,
    images: localImages,
    coverUrl: note.coverUrl,
    tags: note.tags,
    contentMd: mdPath,
  }

  process.stdout.write(JSON.stringify(result, null, 2) + "\n")
  process.stderr.write(`[xhs-content-ops] ✓ 完成。${localImages.length} 张图片 + 正文已保存到 ${outputDir}\n`)
}

main().catch(e => {
  process.stderr.write(`[xhs-content-ops] ❌ ${e}\n`)
  process.stdout.write(JSON.stringify({ ok: false, error: String(e) }) + "\n")
  process.exit(1)
})
