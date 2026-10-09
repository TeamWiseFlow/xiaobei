"""bailian_asr.py — 公共 skills/_shared 的百炼同步 Flash ASR 后端。

业务空间候选链 qwen-audio-3.1-asr-flash → qwen-audio-3.0-asr-flash；
Agent Plan 保留 qwen-audio-3.0-asr-flash。BAILIAN_ASR_MODEL 显式指定时只调用该模型。

与 volc_asr.py 返回同构：
  {ok: True, text, utterances:[{start,end,text}], words:[{start,end,text}]}
  {ok: False, error}
时间戳统一为秒（百炼返毫秒）。

协议（input-audio family，参考百炼录音文件识别 HTTP API 文档
与 modelstudioai/cli packages/core/src/client/asr-routes.ts）：
  POST {base}/services/aigc/multimodal-generation/generation
  headers: Authorization Bearer <key> + Content-Type application/json + X-DashScope-SSE: disable
  body: {model, input:{messages:[{role:"user",
           content:[{type:"input_audio", input_audio:{data:"data:audio/<fmt>;base64,..."}}]}]},
         parameters:{format}}
  响应: output.text 全文 + output.sentence.words[]（整段合并为单 sentence，
        每 word 带 begin_time/end_time 毫秒与 punctuation）。

端点/key 双模式（resolve_bailian_endpoint）：
  - WORKSPACE_ID 在 → 业务空间 https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1，
    key = MODELSTUDIO_API_KEY / DASHSCOPE_API_KEY
  - 否则 → agent plan https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1，
    key = AWK_API_KEY

音频以 base64 data URI 直传，编码后限 10MB；超限自动 ffmpeg 压成
16kHz 单声道 32kbps mp3 再传（10 分钟音频约 2.4MB，稳过）。

utterances 合成：百炼把整段音频并成一个 sentence，本模块按 words[].punctuation
中的句末标点把词流切回多个 utterance，保持与火山返回同粒度（viral-chaser /
talking-head-cut 按 utterance 切段）。
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

DEFAULT_ASR_MODEL = "qwen-audio-3.1-asr-flash"
WS_ASR_MODELS = [DEFAULT_ASR_MODEL, "qwen-audio-3.0-asr-flash"]
PLAN_ASR_MODELS = ["qwen-audio-3.0-asr-flash"]

WS_BASE_TEMPLATE = "https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1"
AGENT_PLAN_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
ASR_PATH = "/services/aigc/multimodal-generation/generation"

# 编码后 base64 体积上限（百炼文档：编码后 ≤10MB，留安全余量）
MAX_B64_BYTES = 9 * 1024 * 1024

# 句末标点：出现即收束一个 utterance
SENTENCE_END_PUNCT = set("。！？；!?;\n")

MIME_BY_EXT = {
    "mp3": "audio/mpeg",
    "wav": "audio/x-wav",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "amr": "audio/amr",
}


BailianEndpoint = tuple[str, str, str]  # (base, api_key, mode)


def list_bailian_endpoints() -> list[BailianEndpoint]:
    """列出所有已配置凭据的百炼端点，按优先级排序。

    业务空间（WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY）在前，
    agent plan（AWK_API_KEY，token-plan 端点）在后。未配置的不出现。
    mode: "workspace" 或 "agent-plan"。
    """
    endpoints: list[BailianEndpoint] = []
    wsid = (os.environ.get("WORKSPACE_ID") or "").strip()
    if wsid:
        key = (
            os.environ.get("MODELSTUDIO_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        ).strip()
        if key:
            endpoints.append((WS_BASE_TEMPLATE.format(wsid=wsid), key, "workspace"))
    awk_key = (os.environ.get("AWK_API_KEY") or "").strip()
    if awk_key:
        endpoints.append((AGENT_PLAN_BASE, awk_key, "agent-plan"))
    return endpoints


def resolve_bailian_endpoint() -> BailianEndpoint | None:
    """取最高优先级的已配置端点；无凭据返回 None。"""
    endpoints = list_bailian_endpoints()
    return endpoints[0] if endpoints else None


def asr_models(mode: str) -> list[str]:
    """显式模型关闭回退；默认候选链按业务空间 / Agent Plan 区分。"""
    model = os.environ.get("BAILIAN_ASR_MODEL", "").strip()
    if model:
        return [model]
    return list(PLAN_ASR_MODELS if mode == "agent-plan" else WS_ASR_MODELS)


def _transcode_to_mp3(audio_path: str) -> str | None:
    """ffmpeg 压成 16kHz 单声道 32kbps mp3，返回临时文件路径；失败返回 None。"""
    fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="bailian-asr-")
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", audio_path,
             "-codec:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "16000",
             tmp_path],
            check=True, capture_output=True, timeout=300,
        )
        return tmp_path
    except (OSError, subprocess.SubprocessError):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return None


def _build_data_uri(audio_path: str) -> tuple[str, str, list[str]]:
    """读音频构造 base64 data URI。超限自动转码。

    返回 (data_uri, format_hint, 待清理临时文件列表)。
    """
    cleanups: list[str] = []
    path = audio_path
    raw = Path(path).read_bytes()
    if len(raw) * 4 / 3 > MAX_B64_BYTES:
        transcoded = _transcode_to_mp3(path)
        if transcoded is None:
            raise RuntimeError(
                f"音频 {len(raw)} 字节超百炼 base64 上限且 ffmpeg 转码失败"
            )
        cleanups.append(transcoded)
        path = transcoded
        raw = Path(path).read_bytes()

    ext = Path(path).suffix.lower().lstrip(".")
    fmt = ext if ext in MIME_BY_EXT else "wav"
    mime = MIME_BY_EXT.get(fmt, "audio/x-wav")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}", fmt, cleanups


def _split_utterances(sentence: dict, words: list[dict]) -> list[dict]:
    """按 words[].punctuation 的句末标点把单 sentence 切回多个 utterance。

    words 为原始百炼 word 条目（含 begin_time/end_time 毫秒、punctuation）。
    无法切分（无词/无标点）时整段作一个 utterance。
    """
    utterances: list[dict] = []
    buf: list[dict] = []
    for w in words:
        buf.append(w)
        punct = w.get("punctuation") or ""
        if any(ch in SENTENCE_END_PUNCT for ch in punct):
            utterances.append({
                "start": float(buf[0].get("begin_time", 0)) / 1000.0,
                "end": float(buf[-1].get("end_time", 0)) / 1000.0,
                "text": "".join((x.get("text") or "") + (x.get("punctuation") or "") for x in buf),
            })
            buf = []
    if buf:
        utterances.append({
            "start": float(buf[0].get("begin_time", 0)) / 1000.0,
            "end": float(buf[-1].get("end_time", 0)) / 1000.0,
            "text": "".join((x.get("text") or "") + (x.get("punctuation") or "") for x in buf),
        })
    if not utterances:
        # 无词级信息时退化为整句一个 utterance
        utterances.append({
            "start": float(sentence.get("begin_time", 0)) / 1000.0,
            "end": float(sentence.get("end_time", 0)) / 1000.0,
            "text": sentence.get("text", "") or "",
        })
    return [u for u in utterances if u["text"].strip()]


def bailian_asr(audio_path: str, endpoint: BailianEndpoint | None = None) -> dict:
    """调百炼同步 Flash ASR，返回 {ok, text, utterances, words}（与 volc_asr 同构）。

    endpoint 显式传入 (base, api_key, mode)；缺省按 resolve_bailian_endpoint() 取最高优先级。
    """
    if endpoint is None:
        endpoint = resolve_bailian_endpoint()
    if endpoint is None:
        return {
            "ok": False,
            "error": "百炼 ASR 凭据未配置：需 WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY"
                     "（业务空间）或 AWK_API_KEY（agent plan）",
        }
    models = asr_models(endpoint[2])

    try:
        data_uri, fmt, cleanups = _build_data_uri(audio_path)
    except Exception as e:
        return {"ok": False, "error": f"读取/转码音频失败: {e}"}

    errors: list[str] = []
    try:
        for model in models:
            result = _recognize(endpoint, model, data_uri, fmt)
            if result.get("ok"):
                return result
            errors.append(f"{model}: {result.get('error', '未知错误')}")
        return {"ok": False, "error": " | ".join(errors)}
    finally:
        for tmp in cleanups:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _recognize(endpoint: BailianEndpoint, model: str, data_uri: str, fmt: str) -> dict:
    """调用一个固定端点与模型，保持公共 ASR 的文本及秒级时间戳结构。"""
    try:
        import requests
    except ImportError as e:
        return {"ok": False, "error": f"requests 不可用: {e}"}
    base, api_key, mode = endpoint
    body = {
        "model": model,
        "input": {"messages": [{
            "role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": data_uri}}],
        }]},
        "parameters": {"format": fmt},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "disable",
    }

    try:
        r = requests.post(f"{base}{ASR_PATH}", json=body, headers=headers, timeout=300)
    except Exception as e:
        return {"ok": False, "error": f"百炼 ASR 请求失败 ({mode}): {e}"}

    if r.status_code != 200:
        return {
            "ok": False,
            "error": f"百炼 ASR 失败 ({mode}, HTTP {r.status_code}): {r.text[:500]}",
        }

    try:
        resp = r.json()
    except Exception as e:
        return {"ok": False, "error": f"响应解析失败: {e}; raw={r.text[:500]}"}

    output = resp.get("output") or {}
    text = output.get("text") or ""
    sentence = output.get("sentence") or {}
    if isinstance(sentence, list):
        sentence = sentence[-1] if sentence else {}

    raw_words = sentence.get("words") or []
    words = []
    for w in raw_words:
        try:
            words.append({
                "start": float(w.get("begin_time", 0)) / 1000.0,
                "end": float(w.get("end_time", 0)) / 1000.0,
                "text": (w.get("text") or "").strip(),
            })
        except (TypeError, ValueError):
            continue
    words = [w for w in words if w["text"]]

    if not text:
        text = sentence.get("text") or ""
    if not text:
        return {
            "ok": False,
            "error": f"百炼 ASR 返回空文本 ({mode}): request_id={resp.get('request_id', '')}",
        }

    utterances = _split_utterances(sentence, raw_words)
    return {"ok": True, "text": text, "utterances": utterances, "words": words}
