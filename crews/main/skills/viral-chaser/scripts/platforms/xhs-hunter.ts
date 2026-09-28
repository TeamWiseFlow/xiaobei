import { execFile } from "node:child_process"
import { stat } from "node:fs/promises"
import { basename, join, resolve } from "node:path"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

export class XhsHunterFailure extends Error {
  readonly code: "SESSION_EXPIRED" | "SIGN_UNAVAILABLE" | "SECURITY_BLOCK" | "FAILED"

  constructor(
    message: string,
    code: "SESSION_EXPIRED" | "SIGN_UNAVAILABLE" | "SECURITY_BLOCK" | "FAILED",
  ) {
    super(message)
    this.name = "XhsHunterFailure"
    this.code = code
  }
}

function failure(data: Record<string, unknown>): XhsHunterFailure {
  const error = String(data.error ?? "")
  const message = String(data.message || error || "小红书笔记读取失败")
  if (error === "SESSION_MISSING") return new XhsHunterFailure(message, "SESSION_EXPIRED")
  if (error === "XhsRelayError" || message.includes("SIGN_UNAVAILABLE")) {
    return new XhsHunterFailure(message, "SIGN_UNAVAILABLE")
  }
  if (/300017|300031|访问频繁|安全限制|SECURITY_BLOCK/.test(message)) {
    return new XhsHunterFailure(message, "SECURITY_BLOCK")
  }
  return new XhsHunterFailure(message, "FAILED")
}

function count(metrics: Record<string, unknown>, key: string): number {
  const value = metrics[`${key}_num`]
  return typeof value === "number" && Number.isFinite(value) ? value : 0
}

async function probeVideo(path: string): Promise<{ durationMs: number; width: number; height: number }> {
  try {
    const { stdout } = await execFileAsync("ffprobe", [
      "-v", "error", "-show_entries", "format=duration:stream=width,height",
      "-of", "json", path,
    ], { timeout: 15_000 })
    const info = JSON.parse(stdout) as {
      format?: { duration?: string }
      streams?: Array<{ width?: number; height?: number }>
    }
    const video = info.streams?.find(stream => stream.width && stream.height)
    const seconds = Number(info.format?.duration)
    return {
      durationMs: Number.isFinite(seconds) ? Math.round(seconds * 1000) : 0,
      width: video?.width ?? 0,
      height: video?.height ?? 0,
    }
  } catch {
    return { durationMs: 0, width: 0, height: 0 }
  }
}

export async function getXhsVideoViaHunter(url: string, contentId: string, outputDir: string) {
  let stdout = ""
  try {
    ({ stdout } = await execFileAsync("xhs-hunter", [
      "fetch", url, "--output-dir", outputDir, "--download-media",
    ], { timeout: 180_000, maxBuffer: 8 * 1024 * 1024 }))
  } catch (error) {
    const result = error as Error & { stdout?: string }
    stdout = result.stdout ?? ""
    if (!stdout) throw new XhsHunterFailure(`xhs-hunter 调用失败: ${result.message}`, "FAILED")
  }

  let data: Record<string, unknown>
  try {
    data = JSON.parse(stdout) as Record<string, unknown>
  } catch {
    throw new XhsHunterFailure("xhs-hunter 未返回有效 JSON", "FAILED")
  }
  if (!data.ok) throw failure(data)

  const note = data.note as Record<string, unknown> | undefined
  if (!note || typeof note !== "object") throw new XhsHunterFailure("xhs-hunter 未返回笔记", "FAILED")
  if (note.type && note.type !== "video") {
    throw new XhsHunterFailure("该小红书笔记是图文，不含视频", "FAILED")
  }
  const paths = Array.isArray(data.media_paths) ? data.media_paths : []
  const videoPath = paths.find(path => typeof path === "string" && basename(path) === "video.mp4")
  if (typeof videoPath !== "string" || resolve(videoPath) !== join(resolve(outputDir), "video.mp4")) {
    throw new XhsHunterFailure("xhs-hunter 未下载到视频文件", "FAILED")
  }
  const file = await stat(videoPath).catch(() => null)
  if (!file?.isFile() || file.size === 0) throw new XhsHunterFailure("xhs-hunter 视频文件为空", "FAILED")

  const author = note.author && typeof note.author === "object"
    ? note.author as Record<string, unknown> : {}
  const metrics = note.metrics && typeof note.metrics === "object"
    ? note.metrics as Record<string, unknown> : {}
  const images = Array.isArray(note.images) ? note.images : []
  const technical = await probeVideo(videoPath)
  return {
    contentId,
    title: String(note.title ?? ""),
    desc: String(note.content ?? ""),
    videoUrl: String(note.video_url ?? ""),
    localVideoPath: videoPath,
    coverUrl: String(images[0] ?? ""),
    author: String(author.nickname ?? ""),
    authorUid: String(author.user_id ?? ""),
    createTime: typeof note.publish_time_ms === "number"
      ? Math.floor(note.publish_time_ms / 1000) : 0,
    hashtags: Array.isArray(note.tags) ? note.tags.map(String) : [],
    stats: {
      playCount: 0,
      likeCount: count(metrics, "liked_count"),
      commentCount: count(metrics, "comment_count"),
      collectCount: count(metrics, "collected_count"),
      shareCount: count(metrics, "share_count"),
    },
    ...technical,
  }
}
