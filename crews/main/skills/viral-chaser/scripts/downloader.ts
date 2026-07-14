#!/usr/bin/env -S node --experimental-strip-types
/**
 * downloader.ts — HTTP streaming video download
 *
 * Ported from ContentRemixAgent/backend/services/video_downloader.py
 * Downloads the video URL returned by platform API clients.
 */

import { createWriteStream, mkdirSync } from "fs"
import { join } from "path"
import { pipeline } from "stream/promises"
import { Readable } from "stream"

export interface DownloadResult {
  filePath: string
  fileSize: number
}

const CHUNK_SIZE = 65536 // 64 KB
const MAX_RETRIES = 3
const RETRY_DELAY_MS = 2000

// Platform-specific headers for CDN anti-hotlinking
function getPlatformHeaders(videoUrl: string, userAgent: string): Record<string, string> {
  const headers: Record<string, string> = {
    "User-Agent": userAgent,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Range": "bytes=0-",
  }

  if (videoUrl.includes("douyinvod") || videoUrl.includes("bytedance") || videoUrl.includes("toutiao")) {
    headers["Referer"] = "https://www.douyin.com/"
    headers["Origin"] = "https://www.douyin.com"
  } else if (videoUrl.includes("bilivideo") || videoUrl.includes("bili") || videoUrl.includes("hdslb")) {
    headers["Referer"] = "https://www.bilibili.com/"
    headers["Origin"] = "https://www.bilibili.com"
  } else if (videoUrl.includes("xhscdn.com") || videoUrl.includes("xiaohongshu")) {
    headers["Referer"] = "https://www.xiaohongshu.com/"
    headers["Origin"] = "https://www.xiaohongshu.com"
  }

  return headers
}

async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export async function downloadVideo(
  videoUrl: string,
  outputDir: string,
  filename: string,
  userAgent: string,
): Promise<DownloadResult> {
  mkdirSync(outputDir, { recursive: true })
  const filePath = join(outputDir, filename)
  const headers = getPlatformHeaders(videoUrl, userAgent)

  let lastError: Error | null = null

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const resp = await fetch(videoUrl, {
        headers,
        signal: AbortSignal.timeout(120_000),
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`)
      }

      if (!resp.body) {
        throw new Error("响应体为空")
      }

      const fileStream = createWriteStream(filePath)
      const nodeReadable = Readable.fromWeb(resp.body as any)
      await pipeline(nodeReadable, fileStream)

      const { size } = await import("fs").then(m => m.promises.stat(filePath))
      return { filePath, fileSize: size }

    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err))
      process.stderr.write(
        `[downloader] 下载失败 (attempt ${attempt}/${MAX_RETRIES}): ${lastError.message}\n`
      )
      if (attempt < MAX_RETRIES) {
        await sleep(RETRY_DELAY_MS)
      }
    }
  }

  // Final fallback: try curl (some CDNs trigger Node fetch quirks like "location is not defined")
  process.stderr.write(`[downloader] 改用 curl 重试...\n`)
  try {
    const { execFile } = await import("child_process")
    const { promisify } = await import("util")
    const execFileAsync = promisify(execFile)
    const curlArgs = ["-sS", "-L", "--max-time", "180",
      "-A", userAgent,
      "-H", "Range: bytes=0-",
      "-o", filePath, videoUrl]
    if (headers.Referer) curlArgs.push("-H", `Referer: ${headers.Referer}`)
    if (headers.Origin) curlArgs.push("-H", `Origin: ${headers.Origin}`)
    await execFileAsync("curl", curlArgs, { maxBuffer: 1024 * 1024 })
    const { size } = await import("fs").then(m => m.promises.stat(filePath))
    if (size > 0) return { filePath, fileSize: size }
    lastError = new Error("curl 下载结果为空")
  } catch (e) {
    lastError = e instanceof Error ? e : new Error(String(e))
  }

  throw new Error(`视频下载失败（重试 ${MAX_RETRIES} 次 + curl 兜底）: ${lastError?.message}`)
}
