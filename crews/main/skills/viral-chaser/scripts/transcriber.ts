#!/usr/bin/env -S node --experimental-strip-types
/**
 * transcriber.ts — ASR transcription via 火山引擎豆包语音（录音文件极速版）
 *
 * 接口：POST https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash
 * 资源 ID：volc.bigasr.auc_turbo（需在火山控制台「开通管理 → 语音模型」开通）
 *
 * 选型说明：viral-chaser 的输入是本地 audio.wav（16kHz mono，≤10min），
 * 极速版支持 audio.data（base64）直传本地文件，一次请求即返回，无需对象
 * 存储/公网 URL，且原生返回 utterances 带 start_time/end_time（毫秒）和
 * word 级时间戳——正好替代原先 SiliconFlow SenseVoiceSmall 无时间戳、
 * 靠字数比例估算的方案。标准版 2.0（volc.seedasr.auc）单价更低但只接受
 * audio.url，需自备 TOS 托管，未采用。
 *
 * 鉴权：兼容新旧控制台（二选一，优先旧控制台双头）。
 *   - 旧控制台双头：VOLC_ASR_APP_ID（数字 APP ID）+ VOLC_ASR_ACCESS_KEY（Access Token）
 *     → X-Api-App-Key=APP_ID, X-Api-Access-Key=Token, user.uid=APP_ID
 *   - 新控制台单头：VOLC_ASR_APP_KEY（APP Key）→ X-Api-Key=APP_KEY, user.uid=APP_KEY
 *   注意：旧控制台 X-Api-App-Key 要的是数字 APP ID，不是 Secret Key/APP Key
 *   （把 Secret Key 塞进 X-Api-App-Key 会得到 45000010 request and grant appid mismatch）。
 *
 * 实现说明：沿用 xhs.ts 同一模式（python3 -c 内联脚本调 requests），避免
 * Node fetch/FormData 在部分环境的兼容异常。
 *
 * 注意：保留 synthesizeSegments 作为兜底——正常情况下火山会返回真实
 * utterances，estimated=false；仅当接口异常未返回 utterances 时才按音频
 * 时长估算，estimated=true。
 */

import { existsSync, statSync } from "fs"
import { execFile } from "child_process"
import { promisify } from "util"

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

const PYTHON_SCRIPT = `
import json, os, sys, uuid, base64
try:
    import requests
except ImportError as e:
    print(json.dumps({"ok": False, "error": f"requests 不可用: {e}"}))
    sys.exit(1)

audio_path = sys.argv[1]
# 鉴权（二选一，优先旧控制台双头）：
#   旧控制台双头：VOLC_ASR_APP_ID（数字 APP ID）+ VOLC_ASR_ACCESS_KEY（Access Token）
#   新控制台单头：VOLC_ASR_APP_KEY（APP Key / X-Api-Key）
app_id = os.environ.get("VOLC_ASR_APP_ID", "")
access_key = os.environ.get("VOLC_ASR_ACCESS_KEY", "")
app_key = os.environ.get("VOLC_ASR_APP_KEY", "")

resource_id = os.environ.get("VOLC_ASR_RESOURCE_ID", "volc.bigasr.auc_turbo")
url = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"

headers = {
    "X-Api-Resource-Id": resource_id,
    "X-Api-Request-Id": str(uuid.uuid4()),
    "X-Api-Sequence": "-1",
}
if app_id and access_key:
    headers["X-Api-App-Key"] = app_id
    headers["X-Api-Access-Key"] = access_key
    uid = app_id
elif app_key:
    headers["X-Api-Key"] = app_key
    uid = app_key
else:
    print(json.dumps({"ok": False, "error": "火山 ASR 凭证未配置：需 VOLC_ASR_APP_ID+VOLC_ASR_ACCESS_KEY（旧控制台双头）或 VOLC_ASR_APP_KEY（新控制台单头）"}))
    sys.exit(1)

try:
    with open(audio_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
except Exception as e:
    print(json.dumps({"ok": False, "error": f"读取音频失败: {e}"}))
    sys.exit(1)

# 根据扩展名推断 format（火山支持 wav/mp3/ogg；默认 wav）
ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
fmt = ext if ext in ("wav", "mp3", "ogg") else "wav"

body = {
    "user": {"uid": uid},
    "audio": {"data": b64, "format": fmt},
    "request": {
        "model_name": "bigmodel",
        "show_utterances": True,
        "enable_itn": True,
        "enable_punc": True,
    },
}

try:
    r = requests.post(url, json=body, headers=headers, timeout=300)
except Exception as e:
    print(json.dumps({"ok": False, "error": f"请求失败: {e}"}))
    sys.exit(1)

status = r.headers.get("X-Api-Status-Code", "")
msg = r.headers.get("X-Api-Message", "")
logid = r.headers.get("X-Tt-Logid", "")

if status != "20000000":
    snippet = r.text[:500] if r.text else ""
    print(json.dumps({"ok": False, "error": f"火山 ASR 失败 (status={status}, msg={msg}, logid={logid}): {snippet}"}))
    sys.exit(1)

try:
    resp = r.json()
except Exception as e:
    print(json.dumps({"ok": False, "error": f"响应解析失败: {e}; raw={r.text[:500]}"}))
    sys.exit(1)

result = resp.get("result") or {}
text = result.get("text", "") or ""
segs = []
for u in (result.get("utterances") or []):
    try:
        start_ms = float(u.get("start_time", 0))
        end_ms = float(u.get("end_time", 0))
        segs.append({
            "start": round(start_ms / 1000.0, 3),
            "end": round(end_ms / 1000.0, 3),
            "text": u.get("text", "") or "",
        })
    except Exception:
        continue

print(json.dumps({"ok": True, "text": text, "segments": segs}, ensure_ascii=False))
`

export async function transcribeAudio(audioPath: string, durationSeconds = 0): Promise<TranscriptResult> {
  if (!existsSync(audioPath)) {
    throw new Error(`音频文件不存在: ${audioPath}`)
  }

  // 极速版硬限 100MB；本地 audio.wav（16kHz mono ≤10min）约 19MB，远低于上限。
  const sizeMb = statSync(audioPath).size / (1024 * 1024)
  if (sizeMb > 100) {
    throw new Error(`音频文件过大 (${sizeMb.toFixed(1)}MB)，火山极速版上限 100MB`)
  }

  const { stdout } = await execFileAsync(
    "python3",
    ["-c", PYTHON_SCRIPT, audioPath],
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
