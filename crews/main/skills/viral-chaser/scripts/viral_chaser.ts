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
import { requireSession, readUserAgent } from "./session.ts"
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

  // 2. Load session (exit 2 if missing)
  // XHS uses xhs-browse cookie (consumer domain www.xiaohongshu.com)
  const sessionPlatform = platform === "xhs" ? "xhs-browse" as Platform : platform
  // requireSession：只做 cheap 字段门（cookie 文件存在 + 非空 + 关键字段）。
  // 抓取前探活（pong）不在此自动跑——批量场景 Agent 先跑一次 check-login 探活即可，
  // 不必每条机械探活。见 SKILL.md「抓取前探活」。
  const session = requireSession(sessionPlatform)

  // 3. Fetch video metadata from platform API
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
      videoInfo = await getXhsVideo(contentId, session, xsecToken, xsecSource)
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

  // 4. Download video
  const tmpDir = getTmpDir(contentId)
  mkdirSync(tmpDir, { recursive: true })

  process.stderr.write(`[viral-chaser] 开始下载视频...\n`)
  // UA 走独立 .ua.json 文件（原则 4：cookie + UA 同指纹同源）
  const userAgent = readUserAgent(sessionPlatform)
  let downloadResult: Awaited<ReturnType<typeof downloadVideo>>
  try {
    downloadResult = await downloadVideo(
      videoInfo!.videoUrl, tmpDir, "video.mp4", userAgent
    )
  } catch (e) {
    errExit(`视频下载失败: ${(e as Error).message}`)
  }

  // 5. Extract audio
  process.stderr.write(`[viral-chaser] 提取音频...\n`)
  let audioResult: Awaited<ReturnType<typeof extractAudio>>
  try {
    audioResult = await extractAudio(downloadResult!.filePath, tmpDir)
  } catch (e) {
    errExit(`音频提取失败: ${(e as Error).message}`)
  }

  // 6. ASR transcription
  process.stderr.write(`[viral-chaser] 音频转录中...\n`)
  let transcript: Awaited<ReturnType<typeof transcribeAudio>>
  try {
    transcript = await transcribeAudio(audioResult!.audioPath, audioResult!.durationSeconds)
  } catch (e) {
    errExit(`ASR 转录失败: ${(e as Error).message}`)
  }

  // 7. Extract key frames
  process.stderr.write(`[viral-chaser] 提取关键帧...\n`)
  const framePaths = await extractKeyFrames(
    downloadResult!.filePath,
    tmpDir,
    transcript!.segments,
    noFrames,
  )

  // 8. Output result JSON to stdout
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
