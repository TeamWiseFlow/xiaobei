#!/usr/bin/env -S node --experimental-strip-types
/** Analyze local video only. Platform sessions and downloads belong to hunters. */
import { execFile } from "node:child_process"
import { existsSync, mkdirSync, rmSync, statSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { parseArgs, promisify } from "node:util"
import { extractAudio } from "./audio_extractor.ts"
import { transcribeAudio } from "./transcriber.ts"

const execFileAsync = promisify(execFile)
const HELP = "Usage: viral-chaser --video <local-video> [--audio <local-audio>] [--output-dir <directory>] [--no-frames]\n"

export class AnalysisError extends Error {
  code: string
  exitCode: number
  constructor(code: string, message: string, exitCode = 1) {
    super(message)
    this.code = code
    this.exitCode = exitCode
  }
}

function localFile(value: string, label: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) {
    throw new AnalysisError("LOCAL_FILE_REQUIRED", `${label}必须是本地文件；请先调用对应 hunter 下载`)
  }
  const path = resolve(value)
  if (!existsSync(path) || !statSync(path).isFile() || !statSync(path).size) {
    throw new AnalysisError("LOCAL_FILE_MISSING", `${label}不存在或为空: ${path}`)
  }
  return path
}

async function probeVideo(path: string) {
  let info: any
  try {
    const { stdout } = await execFileAsync("ffprobe", [
      "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams",
      "-show_format", "-of", "json", path,
    ], { timeout: 30_000, maxBuffer: 10 * 1024 * 1024 })
    info = JSON.parse(stdout)
  } catch {
    throw new AnalysisError("VIDEO_PROBE_FAILED", "无法读取本地视频信息")
  }
  const streams: any[] = Array.isArray(info.streams) ? info.streams : []
  const video = streams.find(stream => stream.codec_type === "video" && !stream.disposition?.attached_pic)
  const durationSeconds = Number(info.format?.duration || video?.duration)
  if (!video || /image2|_pipe/.test(info.format?.format_name || "") ||
      !Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    throw new AnalysisError("VIDEO_REQUIRED", "仅分析视频；图文请转对应平台专家 workflow")
  }
  const width = Number(video.width) || 0
  const height = Number(video.height) || 0
  return {
    durationSeconds, width, height,
    orientation: width && height ? (height > width ? "vertical" : height < width ? "horizontal" : "square") : "",
    hasAudio: streams.some(stream => stream.codec_type === "audio"),
  }
}

export function keyFrameTimestamps(duration: number, segments: Array<{ start: number; end: number }>): number[] {
  const clamp = (value: number) => Math.round(Math.max(0, Math.min(value, Math.max(0, duration - 0.05))) * 1000) / 1000
  // Keep the full-film anchors even when the transcript has many early segments.
  const anchors = [...new Set([0, 3, ...[0.25, 0.5, 0.63, 0.75, 0.9].map(r => duration * r)].map(clamp))]
  const middles = [...new Set(segments.filter(s => Number.isFinite(s.start) && Number.isFinite(s.end) &&
    s.start >= 0 && s.end >= s.start && s.start < duration).map(s => clamp((s.start + s.end) / 2)))]
    .filter(ts => !anchors.includes(ts)).sort((a, b) => a - b)
  const slots = 12 - anchors.length
  const selected = middles.length <= slots ? middles : Array.from({ length: slots }, (_, i) =>
    middles[Math.round(i * (middles.length - 1) / Math.max(1, slots - 1))])
  return [...new Set([...anchors, ...selected])].sort((a, b) => a - b)
}

async function extractKeyFrames(video: string, directory: string, duration: number,
                                segments: Array<{ start: number; end: number }>) {
  const framesDir = join(directory, "frames")
  mkdirSync(framesDir, { recursive: true })
  const paths: string[] = []
  for (const timestamp of keyFrameTimestamps(duration, segments)) {
    const output = join(framesDir, `frame_${String(paths.length).padStart(2, "0")}_${timestamp}s.jpg`)
    try {
      rmSync(output, { force: true })
      await execFileAsync("ffmpeg", [
        "-hide_banner", "-loglevel", "error", "-y", "-ss", String(timestamp),
        "-protocol_whitelist", "file,pipe", "-i", video, "-frames:v", "1", "-threads", "1", output,
      ], { timeout: 30_000 })
      if (existsSync(output) && statSync(output).size) paths.push(output)
    } catch {
      // Keep successful frames and report partial extraction in the result.
    }
  }
  return paths
}

export async function analyze(options: { video: string; audio?: string; outputDir?: string; noFrames?: boolean }) {
  const video = localFile(options.video, "视频")
  const audioInput = options.audio ? localFile(options.audio, "音轨") : video
  const metadata = await probeVideo(video)
  if (!options.audio && !metadata.hasAudio) {
    throw new AnalysisError("AUDIO_REQUIRED", "视频没有音轨；如 hunter 下载了独立音轨，请用 --audio 指定")
  }
  const directory = resolve(options.outputDir || process.env.OUTPUT_DIR || dirname(video))
  mkdirSync(directory, { recursive: true })
  process.stderr.write("[analyzer] 提取本地音频...\n")
  const audio = await extractAudio(audioInput, directory)
  process.stderr.write("[analyzer] 转写...\n")
  let transcript: Awaited<ReturnType<typeof transcribeAudio>>
  try {
    transcript = await transcribeAudio(audio.audioPath, audio.durationSeconds)
  } catch (error) {
    const message = (error as Error).message
    const missingCredentials = /凭[证据].*未配置/.test(message)
    throw new AnalysisError(missingCredentials ? "ASR_NOT_CONFIGURED" : "ASR_FAILED",
                            message, missingCredentials ? 2 : 1)
  }
  const timestamps = options.noFrames ? [] : keyFrameTimestamps(metadata.durationSeconds, transcript.segments)
  const frames = options.noFrames ? [] : await extractKeyFrames(video, directory, metadata.durationSeconds, transcript.segments)
  const warnings: string[] = []
  const truncated = metadata.durationSeconds > audio.durationSeconds + 0.1
  if (truncated) warnings.push("TRANSCRIPT_PARTIAL")
  if (frames.length < timestamps.length) warnings.push("KEY_FRAMES_PARTIAL")
  return {
    ok: true, kind: "video", metadata,
    transcript: { ...transcript, durationSeconds: audio.durationSeconds, truncated },
    frames, warnings,
    localPaths: { video, audio: audio.audioPath, tmpDir: directory },
  }
}

async function main() {
  const { values } = parseArgs({ options: {
    video: { type: "string" }, audio: { type: "string" }, "output-dir": { type: "string" },
    "no-frames": { type: "boolean" }, help: { type: "boolean", short: "h" },
  } })
  if (values.help) {
    process.stdout.write(HELP)
    return
  }
  if (!values.video) throw new AnalysisError("VIDEO_REQUIRED", HELP.trim())
  const result = await analyze({ video: values.video, audio: values.audio,
    outputDir: values["output-dir"], noFrames: values["no-frames"] })
  process.stdout.write(JSON.stringify(result, null, 2) + "\n")
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {
    process.stdout.write(JSON.stringify({ ok: false,
      error: error instanceof AnalysisError ? error.code : "ANALYSIS_FAILED",
      message: (error as Error).message }) + "\n")
    process.exitCode = error instanceof AnalysisError ? error.exitCode : 1
  })
}
