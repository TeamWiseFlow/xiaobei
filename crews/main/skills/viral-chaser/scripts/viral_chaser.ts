#!/usr/bin/env -S node --experimental-strip-types
/**
 * viral_chaser.ts — Viral video analyzer CLI
 *
 * Usage:
 *   viral-chaser <url> [--no-frames]
 *
 * Exit codes:
 *   0  Success — prints JSON result to stdout
 *   1  General error (URL invalid, download failed, etc.)
 *   2  Cookie invalid / not logged in → caller should run login-manager
 */

import { mkdirSync, existsSync, rmSync } from "fs"
import { execFile } from "child_process"
import { promisify } from "util"
import { join } from "path"

import { parseLink } from "./link_parser.ts"
import { requireSession, readSession, readUserAgent } from "./session.ts"
import type { SessionData } from "./session.ts"
import { checkSession } from "../../_shared/check-session.ts"
import { getDouyinVideo } from "./platforms/douyin.ts"
import { getBilibiliVideo } from "./platforms/bilibili.ts"
import { getXhsVideo } from "./platforms/xhs.ts"
import { downloadVideo } from "./downloader.ts"
import { extractAudio } from "./audio_extractor.ts"
import { transcribeAudio } from "./transcriber.ts"

const execFileAsync = promisify(execFile)

// ── Helpers ────────────────────────────────────────────────────────────────

function printJson(data: unknown): void {
  process.stdout.write(JSON.stringify(data, null, 2) + "\n")
}

function errExit(msg: string, code = 1): never {
  process.stderr.write(JSON.stringify({ ok: false, error: msg }) + "\n")
  process.exit(code)
}

function getTmpDir(contentId: string): string {
  // Honor OUTPUT_DIR env var (SKILL.md sets it to output_videos/<slug>/references).
  // Fall back to a per-id tmp dir when unset.
  if (process.env.OUTPUT_DIR && process.env.OUTPUT_DIR.trim()) {
    return process.env.OUTPUT_DIR.trim()
  }
  return join("/tmp", "viral_chaser", contentId)
}

// ── Key frame extraction (ffmpeg seek, one frame per timestamp) ────────────

async function extractKeyFrames(
  videoPath: string,
  outputDir: string,
  segments: Array<{ start: number; end: number; text: string }>,
  noFrames: boolean,
): Promise<string[]> {
  if (noFrames) return []

  const framesDir = join(outputDir, "frames")
  mkdirSync(framesDir, { recursive: true })

  // Build list of timestamps: 0s, 3s, segment midpoints.
  // Intentionally front-loaded (slice(0, 8) keeps the earliest 8): for short
  // videos the opening is what matters most — the goal is to not let viewers
  // scroll past the first few seconds.
  const timestamps: number[] = [0, 3]
  for (const seg of segments) {
    const mid = Math.floor((seg.start + seg.end) / 2)
    if (!timestamps.includes(mid)) timestamps.push(mid)
  }

  const framePaths: string[] = []
  let frameIdx = 0

  for (const ts of timestamps.slice(0, 8)) {  // max 8 frames, front-loaded
    const timeStr = new Date(ts * 1000).toISOString().substring(11, 19)
    const outPath = join(framesDir, `frame_${String(frameIdx).padStart(2, "0")}_${ts}s.jpg`)
    try {
      await execFileAsync("ffmpeg", [
        "-hide_banner", "-loglevel", "error", "-y",
        "-ss", timeStr, "-i", videoPath, "-frames:v", "1", outPath,
      ])
      if (existsSync(outPath)) {
        framePaths.push(outPath)
        frameIdx++
      }
    } catch {
      // Non-fatal: skip this frame
    }
  }

  return framePaths
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  if (!args.length || args[0] === "--help") {
    process.stderr.write("Usage: viral-chaser <url> [--no-frames]\n")
    process.exit(1)
  }

  const url = args.find(a => !a.startsWith("--")) ?? ""
  const noFrames = args.includes("--no-frames")

  if (!url) errExit("请提供视频 URL")

  // 1. Parse URL → platform + contentId
  let parsed: Awaited<ReturnType<typeof parseLink>>
  try {
    parsed = await parseLink(url)
  } catch (e) {
    errExit(`URL 解析失败: ${(e as Error).message}`)
  }

  const { platform, contentId } = parsed
  process.stderr.write(`[viral-chaser] 平台: ${platform}, 内容 ID: ${contentId}\n`)

  // 2. 抓取前探活（pong）合并进下载脚本——单条下载无法批量，每条自带探活最稳，
  //    且 pong 带 TTL 缓存，重复调用成本低。bilibili 公开视频免登录，跳过。
  //    douyin 走 _shared checkSession（Tier1 字段 + Tier2 平台 pong）。
  //    xhs 走无 cookie HTML 路线（见 platforms/xhs.ts），不依赖签名/cookie，跳过探活——
  //    探活 user/me 通过也不代表 feed 签名路径被接受，HTML 路线根本不走签名，无需探活。
  if (platform === "douyin") {
    const probe = await checkSession(platform)
    if (!probe.ok) {
      const err = probe.error === "SIGN_UNAVAILABLE" ? "SIGN_UNAVAILABLE" : "SESSION_EXPIRED"
      process.stderr.write(
        JSON.stringify({ ok: false, error: err, reason: probe.reason, platform }) + "\n",
      )
      process.exit(err === "SIGN_UNAVAILABLE" ? 1 : 2)
    }
  }

  // 3. Load session
  // - douyin / bilibili：必需，缺失 exit 2（交 login-manager 重登）
  // - xhs：可选读。xhs 走无 cookie HTML 路线，session 仅作滑块/空页时的 cookie 回退，
  //   缺失不致命；有则用同指纹 UA + cookie 重试一次。
  const sessionPlatform = platform === "xhs" ? "xhs-browse" as Platform : platform
  let session: SessionData | null
  if (platform === "xhs") {
    session = readSession(sessionPlatform)
  } else {
    session = requireSession(sessionPlatform)
  }

  // 4. Fetch video metadata from platform API
  let videoInfo: {
    title: string; desc: string; videoUrl: string; audioUrl?: string
    coverUrl: string; durationMs?: number; durationSeconds?: number
    author: string; stats: Record<string, number>
    contentId: string; mediaFormat?: string
  }

  try {
    if (platform === "douyin") {
      videoInfo = await getDouyinVideo(contentId, session)
    } else if (platform === "bilibili") {
      videoInfo = await getBilibiliVideo(contentId, session)
    } else if (platform === "xhs") {
      // Extract xsec_token from the resolved URL (after short-link expansion),
      // not the original input — short links carry no token until expanded.
      const tokenMatch = parsed.resolvedUrl.match(/[?&]xsec_token=([^&]+)/)
      const xsecToken = tokenMatch ? decodeURIComponent(tokenMatch[1]) : ""
      const sourceMatch = parsed.resolvedUrl.match(/[?&]xsec_source=([^&]+)/)
      const xsecSource = sourceMatch ? decodeURIComponent(sourceMatch[1]) : ""
      videoInfo = await getXhsVideo(contentId, xsecToken, xsecSource, session)
    } else {
      errExit(`不支持的平台: ${platform}`)
    }
  } catch (e) {
    const msg = (e as Error).message
    if (msg.includes("cookie") || msg.includes("失效") || msg.includes("auth")) {
      process.stderr.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED" }) + "\n")
      process.exit(2)
    }
    errExit(`获取视频信息失败: ${msg}`)
  }

  if (!videoInfo!.videoUrl) {
    errExit("未能获取视频下载地址（可能需要登录或视频已删除）")
  }

  // 5. Download video
  const tmpDir = getTmpDir(contentId)
  mkdirSync(tmpDir, { recursive: true })

  process.stderr.write(`[viral-chaser] 开始下载视频...\n`)
  // UA 走独立 .ua.json 文件（原则 4：cookie + UA 同指纹同源）。
  // xhs 无 cookie 路线可能没有 UA 文件，给默认 Chrome UA 兜底。
  const userAgent = readUserAgent(sessionPlatform) ||
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
  let downloadResult: Awaited<ReturnType<typeof downloadVideo>>
  try {
    downloadResult = await downloadVideo(
      videoInfo!.videoUrl, tmpDir, "video.mp4", userAgent
    )
  } catch (e) {
    errExit(`视频下载失败: ${(e as Error).message}`)
  }

  // 6. Extract audio
  process.stderr.write(`[viral-chaser] 提取音频...\n`)
  let audioResult: Awaited<ReturnType<typeof extractAudio>>
  try {
    audioResult = await extractAudio(downloadResult!.filePath, tmpDir)
  } catch (e) {
    errExit(`音频提取失败: ${(e as Error).message}`)
  }

  // 7. ASR transcription
  process.stderr.write(`[viral-chaser] 音频转录中...\n`)
  let transcript: Awaited<ReturnType<typeof transcribeAudio>>
  try {
    transcript = await transcribeAudio(audioResult!.audioPath, audioResult!.durationSeconds)
  } catch (e) {
    errExit(`ASR 转录失败: ${(e as Error).message}`)
  }

  // 8. Extract key frames
  process.stderr.write(`[viral-chaser] 提取关键帧...\n`)
  const framePaths = await extractKeyFrames(
    downloadResult!.filePath,
    tmpDir,
    transcript!.segments,
    noFrames,
  )

  // 9. Output result JSON to stdout
  const durationSeconds =
    videoInfo!.durationSeconds ??
    (videoInfo!.durationMs ? Math.round(videoInfo!.durationMs / 1000) : audioResult!.durationSeconds)

  const result = {
    ok: true,
    platform,
    metadata: {
      contentId,
      title: videoInfo!.title,
      desc: videoInfo!.desc,
      author: videoInfo!.author,
      durationSeconds,
      coverUrl: videoInfo!.coverUrl,
      stats: videoInfo!.stats,
    },
    transcript: transcript!,
    frames: framePaths,
    localPaths: {
      video: downloadResult!.filePath,
      audio: audioResult!.audioPath,
      tmpDir,
    },
  }

  printJson(result)
  process.stderr.write(`[viral-chaser] 完成。关键帧: ${framePaths.length} 张\n`)
}

main().catch(e => errExit(String(e)))
