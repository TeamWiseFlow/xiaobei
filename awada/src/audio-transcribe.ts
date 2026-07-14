/**
 * Audio transcription via SiliconFlow API.
 *
 * Env vars:
 *   SILICONFLOW_API_KEY — API key (required)
 *   ASR_MODEL           — model name (required, e.g. "FunAudioLLM/SenseVoiceSmall")
 *
 * API: POST https://api.siliconflow.cn/v1/audio/transcriptions
 *   multipart/form-data { file, model }
 *   Response: { text: string }
 */

const SILICONFLOW_ENDPOINT = "https://api.siliconflow.cn/v1/audio/transcriptions";

export type TranscribeResult =
  | { ok: true; text: string }
  | { ok: false; error: string };

/**
 * Transcribe an audio buffer using SiliconFlow's ASR API.
 */
export async function transcribeAudio(
  audioBuffer: Buffer,
  fileName: string,
): Promise<TranscribeResult> {
  const apiKey = process.env.SILICONFLOW_API_KEY?.trim();
  if (!apiKey) {
    return { ok: false, error: "SILICONFLOW_API_KEY not set" };
  }

  const model = process.env.ASR_MODEL?.trim();
  if (!model) {
    return { ok: false, error: "ASR_MODEL not set" };
  }

  const form = new FormData();
  form.append("file", new Blob([audioBuffer]), fileName);
  form.append("model", model);

  try {
    const res = await fetch(SILICONFLOW_ENDPOINT, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
      body: form,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      return { ok: false, error: `SiliconFlow API ${res.status}: ${body.slice(0, 200)}` };
    }

    const json = (await res.json()) as { text?: string };
    const text = json.text?.trim();
    if (!text) {
      return { ok: false, error: "SiliconFlow returned empty transcript" };
    }

    return { ok: true, text };
  } catch (err) {
    return { ok: false, error: `SiliconFlow request failed: ${String(err)}` };
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
