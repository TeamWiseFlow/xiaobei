import { execFile } from "node:child_process"
import { stat } from "node:fs/promises"
import { basename, join, resolve } from "node:path"
import { promisify } from "node:util"

const execFileAsync = promisify(execFile)

export class DouyinHunterFailure extends Error {
  readonly code: string
  constructor(message: string, code: string) { super(message); this.code = code }
}

function numeric(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0
}

export async function getDouyinViaHunter(contentId: string, outputDir: string) {
  let stdout = ""
  try {
    ({ stdout } = await execFileAsync("douyin-hunter", [
      "fetch", "--id", contentId, "--output-dir", outputDir, "--download-media",
    ], { timeout: 180_000, maxBuffer: 8 * 1024 * 1024 }))
  } catch (error) {
    stdout = (error as Error & { stdout?: string }).stdout ?? ""
    if (!stdout) throw new DouyinHunterFailure(String(error), "FAILED")
  }
  let data: any
  try { data = JSON.parse(stdout) } catch { throw new DouyinHunterFailure("douyin-hunter 未返回 JSON", "FAILED") }
  if (!data.ok) throw new DouyinHunterFailure(String(data.error ?? "FAILED"), String(data.error ?? "FAILED"))
  const note = data.note
  if (!note || typeof note !== "object") throw new DouyinHunterFailure("douyin-hunter 未返回作品", "FAILED")
  const paths: string[] = Array.isArray(data.media_paths) ? data.media_paths : []
  const videoPath = paths.find(path => typeof path === "string" && basename(path) === "video.mp4")
  const imagePaths = paths.filter(path => typeof path === "string" && /^image-\d+\.jpg$/.test(basename(path)))
  for (const path of [videoPath, ...imagePaths].filter(Boolean) as string[]) {
    if (resolve(path) !== join(resolve(outputDir), basename(path))) throw new DouyinHunterFailure("媒体路径异常", "FAILED")
    const file = await stat(path).catch(() => null)
    if (!file?.isFile() || !file.size) throw new DouyinHunterFailure("媒体文件为空", "FAILED")
  }
  if (note.kind === "video" && !videoPath) throw new DouyinHunterFailure("未下载到视频", "FAILED")
  if (note.kind === "note" && !imagePaths.length) throw new DouyinHunterFailure("未下载到图文图片", "FAILED")
  const stats: Record<string, number> = {}
  for (const [source, target] of [["likes", "likeCount"], ["comments", "commentCount"],
    ["shares", "shareCount"], ["favorites", "collectCount"]]) {
    const value = note.metrics?.[source]
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) stats[target] = value
  }
  return {
    contentId,
    title: String(note.title ?? ""), desc: String(note.desc ?? ""),
    videoUrl: String(note.video_url ?? ""), localVideoPath: videoPath,
    imageUrls: Array.isArray(note.images) ? note.images : [], localImagePaths: imagePaths,
    coverUrl: String(note.cover_url ?? note.images?.[0] ?? ""),
    durationMs: numeric(note.duration_ms), width: numeric(note.width), height: numeric(note.height),
    createTime: numeric(note.create_time), hashtags: Array.isArray(note.hashtags) ? note.hashtags.map(String) : [],
    author: String(note.author?.nickname ?? ""), authorUid: String(note.author?.uid ?? ""),
    authorSignature: String(note.author?.signature ?? ""),
    stats,
  }
}
