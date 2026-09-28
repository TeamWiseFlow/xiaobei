#!/usr/bin/env -S node --experimental-strip-types
/**
 * transcriber.ts — ASR transcription via 公共 ASR 路由（_shared/asr.py）
 *
 * 供应商优先级（2026-09 拍板）：
 *   1. 火山录音文件极速版（volc.bigasr.auc_turbo，VOLC_ASR_* 凭据）
 *   2. 百炼业务空间（qwen-audio-3.0-asr-flash，WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY）
 *   3. 百炼 agent plan（qwen-audio-3.0-asr-flash，AWK_API_KEY，token-plan 端点）
 * 某家失败自动落下一家；协议细节见 _shared/volc_asr.py 与 _shared/bailian_asr.py。
 *
 * 选型说明：viral-chaser 的输入是本地 audio.wav（16kHz mono，≤10min）。
 * 两家都支持 base64 直传本地文件并返回 word 级时间戳（百炼超 10MB 自动
 * ffmpeg 压成 32kbps mp3 再传），无需对象存储/公网 URL。百炼把整段并成
 * 单 sentence，_shared/bailian_asr.py 按词级标点切回 utterances，与火山同构。
 *
 * 实现说明：调用 _shared/asr.py，由公共路由处理供应商请求，避免
 * Node fetch/FormData 在部分环境的兼容异常。
 *
 * 注意：保留 synthesizeSegments 作为兜底——正常情况下路由会返回真实
 * utterances，estimated=false；仅当接口异常未返回 utterances 时才按音频
 * 时长估算，estimated=true。
 */

import { existsSync, statSync } from "fs"
import { execFile } from "child_process"
import { promisify } from "util"
import { fileURLToPath } from "url"

const execFileAsync = promisify(execFile)

export interface TranscriptSegment {
  start: number
  end: number
  text: string
}

export interface TranscriptResult {
  text: string
  segments: TranscriptSegment[]
  /** true 表示 segments 是按音频时长估算的，非 ASR 真实时间戳。 */
  estimated?: boolean
}

// ── 估算分段（当 ASR 未返回 utterances 时的兜底）──────────────────────────────

function splitSentences(text: string): string[] {
  if (!text) return []
  const parts = text.split(/[。！？!?\n\r]+/).map(s => s.trim()).filter(Boolean)
  const out: string[] = []
  for (const p of parts) {
    if (p.length <= 40) {
      out.push(p)
      continue
    }
    // 过长段落再按逗号/分号切，并合并过短碎片避免帧时间戳过密
    const subs = p.split(/[，,；;]+/).map(s => s.trim()).filter(Boolean)
    let buf = ""
    for (const s of subs) {
      if (buf && buf.length + s.length > 40) {
        out.push(buf)
        buf = s
      } else {
        buf = buf ? buf + s : s
      }
    }
    if (buf) out.push(buf)
  }
  return out
}

function synthesizeSegments(text: string, durationSeconds: number): TranscriptSegment[] {
  const sentences = splitSentences(text)
  if (!sentences.length || durationSeconds <= 0) return []
  const totalChars = sentences.reduce((a, s) => a + s.length, 0) || 1
  const segs: TranscriptSegment[] = []
  let accChars = 0
  for (const s of sentences) {
    const start = (accChars / totalChars) * durationSeconds
    accChars += s.length
    const end = (accChars / totalChars) * durationSeconds
    segs.push({
      start: Math.round(start * 10) / 10,
      end: Math.round(end * 10) / 10,
      text: s,
    })
  }
  if (segs.length) segs[segs.length - 1].end = durationSeconds
  return segs
}

// 调公共 _shared/asr.py 路由（与 talking-head-cut / video-producer narration-align 共一份逻辑）。
// 范式：python3 -c 加载 _shared 到 sys.path，import asr，调它拿 {ok, text, utterances, words}，
// 输出 JSON 到 stdout 供 Node 解析。_shared 路径按本剧本位置算（crews/main/skills/_shared）。
const SHARED_DIR = fileURLToPath(new URL("../../_shared/", import.meta.url))
const PYTHON_CALL = `
import json, os, sys
sys.path.insert(0, ${JSON.stringify(SHARED_DIR)})
from asr import asr, load_env_file
load_env_file()
result = asr(sys.argv[1])
# 降级到 utterance 级供旧 TranscriptResult 结构兼容（viral-chaser 只用 utterance 级）
segs = []
if result.get("ok"):
    for u in (result.get("utterances") or []):
        segs.append({"start": round(u["start"], 3), "end": round(u["end"], 3), "text": u["text"]})
print(json.dumps({"ok": result.get("ok", False), "text": result.get("text", ""), "segments": segs, "error": result.get("error")}, ensure_ascii=False))
`

export async function transcribeAudio(audioPath: string, durationSeconds = 0): Promise<TranscriptResult> {
  if (!existsSync(audioPath)) {
    throw new Error(`音频文件不存在: ${audioPath}`)
  }

  // 兜底上限 100MB（火山极速版硬限；百炼路径 >10MB 会在 _shared 内自动转码压缩）。
  // 本地 audio.wav（16kHz mono ≤10min）约 19MB，正常远低于上限。
  const sizeMb = statSync(audioPath).size / (1024 * 1024)
  if (sizeMb > 100) {
    throw new Error(`音频文件过大 (${sizeMb.toFixed(1)}MB)，超出 ASR 输入上限 100MB`)
  }

  const { stdout } = await execFileAsync(
    "python3",
    ["-c", PYTHON_CALL, audioPath],
    { timeout: 320_000, maxBuffer: 50 * 1024 * 1024 },
  )

  let data: { ok: boolean; text?: string; segments?: TranscriptSegment[]; error?: string }
  try {
    data = JSON.parse(stdout.trim())
  } catch (e) {
    throw new Error(`ASR 响应解析失败: ${(e as Error).message}; raw=${stdout.slice(0, 500)}`)
  }

  if (!data.ok) {
    throw new Error(data.error || "ASR 未知错误")
  }

  const apiSegments = (data.segments ?? []).map(s => ({
    start: s.start,
    end: s.end,
    text: s.text,
  }))

  // 火山返回了真实 utterances → 直接用
  if (apiSegments.length) {
    return { text: data.text ?? "", segments: apiSegments, estimated: false }
  }

  // 接口未返回 utterances（异常情况）→ 按音频时长估算分段兜底
  const estimatedSegments = synthesizeSegments(data.text ?? "", durationSeconds)
  if (estimatedSegments.length) {
    process.stderr.write(
      `[transcriber] 火山未返回 utterances，按音频时长估算 ${estimatedSegments.length} 个分段\n`,
    )
  }
  return {
    text: data.text ?? "",
    segments: estimatedSegments,
    estimated: estimatedSegments.length > 0,
  }
}
