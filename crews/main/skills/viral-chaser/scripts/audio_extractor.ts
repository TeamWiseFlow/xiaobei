#!/usr/bin/env -S node --experimental-strip-types
/**
 * audio_extractor.ts — Extract audio from video using ffmpeg
 */

import { execFile } from "child_process"
import { promisify } from "util"
import { existsSync } from "fs"
import { join } from "path"

const execFileAsync = promisify(execFile)

export interface AudioExtractResult {
  audioPath: string
  durationSeconds: number
}

// Max audio duration for ASR: 10 minutes (focus on opening structure)
const MAX_DURATION_SECONDS = 600

export async function extractAudio(
  videoPath: string,
  outputDir: string,
): Promise<AudioExtractResult> {
  if (!existsSync(videoPath)) {
    throw new Error(`视频文件不存在: ${videoPath}`)
  }

  const audioPath = join(outputDir, "audio.wav")

  // First probe duration
  let durationSeconds = 0
  try {
    const { stdout } = await execFileAsync("ffprobe", [
      "-v", "quiet",
      "-print_format", "json",
      "-show_format",
      videoPath,
    ], { maxBuffer: 10 * 1024 * 1024 })
    const info = JSON.parse(stdout)
    durationSeconds = parseFloat(info.format?.duration ?? "0")
  } catch {
    // ffprobe failed, proceed without duration limit
  }

  const args = [
    "-y",                        // overwrite output
    "-i", videoPath,
    "-vn",                       // no video
    "-ar", "16000",              // 16kHz sample rate (ASR requirement)
    "-ac", "1",                  // mono
    "-f", "wav",
  ]

  // Cap at MAX_DURATION_SECONDS
  if (durationSeconds === 0 || durationSeconds > MAX_DURATION_SECONDS) {
    args.push("-t", String(MAX_DURATION_SECONDS))
  }

  args.push(audioPath)

  await execFileAsync("ffmpeg", args, { maxBuffer: 10 * 1024 * 1024 })

  return {
    audioPath,
    durationSeconds: Math.min(durationSeconds, MAX_DURATION_SECONDS) || MAX_DURATION_SECONDS,
  }
}
