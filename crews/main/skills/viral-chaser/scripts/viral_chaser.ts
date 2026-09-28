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
 *   3  XHS SECURITY_BLOCK after one cooldown retry; stop, do not re-login
 */

import { mkdirSync, existsSync, statSync } from "fs"
import { execFile } from "child_process"
import { promisify } from "util"
import { join } from "path"

import { parseLink } from "./link_parser.ts"
import { requireSession, readUserAgent } from "./session.ts"
import type { SessionData } from "./session.ts"
import { checkSession } from "../../_shared/check-session.ts"
import { getDouyinVideo } from "./platforms/douyin.ts"
import { getBilibiliVideo } from "./platforms/bilibili.ts"
import { getXhsVideoViaHunter, XhsHunterFailure } from "./platforms/xhs-hunter.ts"
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

function unixToIso(seconds?: number): string {
  if (!seconds || seconds <= 0) return ""
  return new Date(seconds * 1000).toISOString()
}

function getTmpDir(contentId: string): string {
  // Honor OUTPUT_DIR env var (SKILL.md sets it to <platform>/ref/<slug>/references).
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
  durationSeconds = 0,
): Promise<string[]> {
  if (noFrames) return []

  const framesDir = join(outputDir, "frames")
  mkdirSync(framesDir, { recursive: true })

  // 采样点：开场（0s / 3s，看钩子与首帧包装）+ 各口播段中点（看画面与口播的对应）
  // + 全片比例点 25% / 50% / 63% / 75% / 90%（看结构转折——反转植入类作品的反转点
  // 通常落在 55%-76%，只采前几秒会完全错过）。去重后按时间排序，最多 12 张。
  const timestamps: number[] = [0, 3]
  for (const seg of segments) {
    const mid = Math.floor((seg.start + seg.end) / 2)
    if (!timestamps.includes(mid)) timestamps.push(mid)
  }
  if (durationSeconds > 0) {
    for (const ratio of [0.25, 0.5, 0.63, 0.75, 0.9]) {
      const ts = Math.min(Math.floor(durationSeconds * ratio), Math.max(durationSeconds - 1, 0))
      if (!timestamps.includes(ts)) timestamps.push(ts)
    }
  }
  timestamps.sort((a, b) => a - b)

  const framePaths: string[] = []
  let frameIdx = 0

  for (const ts of timestamps.slice(0, 12)) {  // max 12 frames, 覆盖全片
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
  //    xhs 的会话检查、取数和下载统一由 xhs-hunter 处理。
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
  // 抖音、B 站使用本技能的会话；小红书会话由 xhs-hunter 管理。
  const session: SessionData | null = platform === "xhs" ? null : requireSession(platform)
  const tmpDir = getTmpDir(contentId)
  mkdirSync(tmpDir, { recursive: true })

  // 4. Fetch video metadata from platform API
  let videoInfo: {
    title: string; desc: string; videoUrl: string; audioUrl?: string
    coverUrl: string; durationMs?: number; durationSeconds?: number
    author: string; stats: Record<string, number>
    contentId: string; mediaFormat?: string; localVideoPath?: string
    // DNA 采样补充字段（平台能给则给，缺失为 0 / 空）
    width?: number; height?: number; ratio?: string
    createTime?: number; authorSignature?: string; authorUid?: string
    hashtags?: string[]; imageUrls?: string[]
  }

  try {
    if (platform === "douyin") {
      videoInfo = await getDouyinVideo(contentId, session)
    } else if (platform === "bilibili") {
      videoInfo = await getBilibiliVideo(contentId, session)
    } else if (platform === "xhs") {
      videoInfo = await getXhsVideoViaHunter(parsed.resolvedUrl, contentId, tmpDir)
    } else {
      errExit(`不支持的平台: ${platform}`)
    }
  } catch (e) {
    if (e instanceof XhsHunterFailure) {
      printJson({ ok: false, error: e.code, platform: "xhs", reason: e.message })
      process.exit(e.code === "SESSION_EXPIRED" ? 2 : e.code === "SECURITY_BLOCK" ? 3 : 1)
    }
    const msg = (e as Error).message
    if (msg.includes("cookie") || msg.includes("失效") || msg.includes("auth")) {
      process.stderr.write(JSON.stringify({ ok: false, error: "SESSION_EXPIRED" }) + "\n")
      process.exit(2)
    }
    errExit(`获取视频信息失败: ${msg}`)
  }

  // 4b. 图文作品分支（抖音图集笔记）：无播放地址但有图片列表时，只下载图片 +
  //     输出文本与 meta，不做音频提取 / ASR / 抽帧。这类样本喂图文 DNA（note 框架），
  //     视觉证据就是下载到的图片。
  const imageUrls = videoInfo!.imageUrls ?? []
  if (!videoInfo!.videoUrl && imageUrls.length) {
    process.stderr.write(`[viral-chaser] 图文作品：下载 ${imageUrls.length} 张图片...\n`)
    const imagePaths: string[] = []
    for (let i = 0; i < imageUrls.length && i < 20; i++) {
      const outName = `image_${String(i).padStart(2, "0")}.jpg`
      try {
        const r = await downloadVideo(imageUrls[i], tmpDir, outName, session ? readUserAgent(session.platform) : "")
        if (r?.filePath) imagePaths.push(r.filePath)
      } catch {
        // 单张失败不致命：跳过继续
      }
    }
    printJson({
      ok: true,
      platform,
      kind: "note",
      metadata: {
        contentId,
        title: videoInfo!.title,
        desc: videoInfo!.desc,
        author: videoInfo!.author,
        authorSignature: videoInfo!.authorSignature ?? "",
        publishTime: unixToIso(videoInfo!.createTime),
        hashtags: videoInfo!.hashtags ?? [],
        coverUrl: videoInfo!.coverUrl,
        stats: videoInfo!.stats,
        imageCount: imagePaths.length,
      },
      transcript: null,
      frames: [],
      images: imagePaths,
      localPaths: { tmpDir },
    })
    process.stderr.write(`[viral-chaser] 完成（图文）。图片: ${imagePaths.length} 张\n`)
    return
  }

  if (!videoInfo!.videoUrl) {
    errExit("未能获取视频下载地址（可能需要登录或视频已删除）")
  }

  // 5. Download video

  process.stderr.write(`[viral-chaser] 开始下载视频...\n`)
  let downloadResult: Awaited<ReturnType<typeof downloadVideo>>
  if (platform === "xhs") {
    if (!videoInfo!.localVideoPath) {
      errExit("xhs-hunter 未返回已下载的视频文件")
    }
    downloadResult = {
      filePath: videoInfo!.localVideoPath,
      fileSize: statSync(videoInfo!.localVideoPath).size,
    }
  } else {
    const userAgent = (session && readUserAgent(session.platform)) ||
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    try {
      downloadResult = await downloadVideo(videoInfo!.videoUrl, tmpDir, "video.mp4", userAgent)
    } catch (e) {
      errExit(`视频下载失败: ${(e as Error).message}`)
    }
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
  const durationForFrames =
    videoInfo!.durationSeconds ??
    (videoInfo!.durationMs ? Math.round(videoInfo!.durationMs / 1000) : audioResult!.durationSeconds)
  const framePaths = await extractKeyFrames(
    downloadResult!.filePath,
    tmpDir,
    transcript!.segments,
    noFrames,
    durationForFrames,
  )

  // 9. Output result JSON to stdout
  const durationSeconds =
    videoInfo!.durationSeconds ??
    (videoInfo!.durationMs ? Math.round(videoInfo!.durationMs / 1000) : audioResult!.durationSeconds)

  const width = videoInfo!.width ?? 0
  const height = videoInfo!.height ?? 0
  const orientation =
    width && height ? (height > width ? "vertical" : height < width ? "horizontal" : "square") : ""

  const result = {
    ok: true,
    platform,
    kind: "video",
    metadata: {
      contentId,
      title: videoInfo!.title,
      desc: videoInfo!.desc,
      author: videoInfo!.author,
      authorSignature: videoInfo!.authorSignature ?? "",
      authorUid: videoInfo!.authorUid ?? "",
      durationSeconds,
      width,
      height,
      orientation,          // vertical / horizontal / square —— DNA 制作规格维度用
      ratio: videoInfo!.ratio ?? "",
      publishTime: unixToIso(videoInfo!.createTime),
      hashtags: videoInfo!.hashtags ?? [],
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
