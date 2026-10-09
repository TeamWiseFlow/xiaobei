/** Audio messages reuse the public skills/_shared/asr.py route. */
import { execFile } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const sourceScript = resolve(dirname(realpathSync(fileURLToPath(import.meta.url))), "../../skills/_shared/asr.py");
const ASR_SCRIPT = existsSync(sourceScript) ? sourceScript : join(
  process.env.OPENCLAW_STATE_DIR || join(homedir(), ".openclaw"), "skills", "_shared", "asr.py",
);

export type TranscribeResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

/** Buffer adapter only: provider selection, model fallback, and requests live in public ASR. */
export async function transcribeAudio(
  audioBuffer: Buffer,
  fileName: string,
): Promise<TranscribeResult> {
  let workDir: string | undefined;
  try {
    workDir = await mkdtemp(join(tmpdir(), "xiaobei-asr-"));
    const format = fileName.match(/\.(mp3|wav|ogg|opus|m4a|aac|flac|amr)$/i)?.[1].toLowerCase() ?? "wav";
    const audioPath = join(workDir, `audio.${format}`);
    await writeFile(audioPath, audioBuffer, { mode: 0o600 });
    const { stdout } = await execFileAsync("python3", [ASR_SCRIPT, audioPath], {
      timeout: 320_000,
      maxBuffer: 50 * 1024 * 1024,
    });
    const result = JSON.parse(stdout.trim()) as { ok?: boolean; text?: string; error?: string };
    if (!result.ok) {
      return { ok: false, error: result.error || "ASR 转写失败" };
    }
    const text = result.text?.trim() ?? "";
    return text ? { ok: true, text } : { ok: false, error: "ASR 返回空文本" };
  } catch {
    // Child-process errors may contain stdout/stderr; do not echo audio or credentials.
    return { ok: false, error: "公共 ASR 转写失败：请检查 Python、公共脚本及语音服务配置" };
  } finally {
    if (workDir) {
      await rm(workDir, { recursive: true, force: true }).catch(() => {});
    }
  }
}

/**
 * Fetch audio content from a URL and return as Buffer.
 */
export async function fetchAudioBuffer(url: string): Promise<Buffer> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch audio: ${res.status} ${res.statusText}`);
  }
  return Buffer.from(await res.arrayBuffer());
}
