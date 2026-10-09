#!/usr/bin/env python3
"""多供应商 TTS（火山豆包 2.0 + 阿里云百炼），ASR 自检复用公共路由。

供应商优先级（2026-09 拍板，凭据在哪家走哪家）：
  1. 火山方舟豆包语音合成 2.0（seed-tts-2.0 字符版）
     POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
     鉴权 X-Api-App-Id + X-Api-Access-Key（旧控制台双头）或 X-Api-Key（新控制台单头）
     X-Api-Resource-Id 路由模型版本（seed-tts-2.0 / seed-icl-2.0 等）
     响应 NDJSON（换行分隔 JSON），每行含 base64 音频分片，拼装成完整音频
  2. 百炼业务空间：WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY
  3. 百炼 agent plan：AWK_API_KEY（token-plan 端点）
     百炼走同步 HTTP POST {base}/services/audio/tts/SpeechSynthesizer，
     非流式返回 output.audio.url（24h）下载；--enable-subtitle 时改 SSE 流式
     （X-DashScope-SSE: enable + word_timestamp_enabled）拿字级时间戳

火山凭据：VOLC_TTS_APP_ID + VOLC_TTS_ACCESS_KEY（旧双头，优先）或 VOLC_TTS_APP_KEY（新单头）
Resource ID 默认 seed-tts-2.0，可由 VOLC_TTS_RESOURCE_ID 覆盖

ASR 自检复用 skills/_shared/asr.py，按 火山 → 百炼业务空间 → Agent Plan 回退。
清洗文本后做序敏感相似度比对，阈值 0.5；自检失败仅警告。
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from asr import asr  # noqa: E402

DEFAULT_API_BASE = "https://openspeech.bytedance.com/api/v3"
DEFAULT_TTS_PATH = "/tts/unidirectional"
DEFAULT_RESOURCE_ID = "seed-tts-2.0"
# 默认 speaker：爽快思思 2.0（通用，官方 2.0 音色）
DEFAULT_SPEAKER = "zh_female_shuangkuaisisi_uranus_bigtts"

# 火山官方 2.0 音色列表（_uranus_bigtts 后缀）
VALID_VOICES = {
    # 通用女声（对应原 claire 清澈女声）
    "zh_female_shuangkuaisisi_uranus_bigtts",   # 爽快思思 2.0，通用，推荐默认
    "zh_female_cancan_uranus_bigtts",           # 知性灿灿 2.0，角色扮演
    "zh_female_tianmeixiaoyuan_uranus_bigtts",  # 甜美小源 2.0，通用
    "zh_female_vv_uranus_bigtts",               # Vivi 2.0，多语种通用
    "zh_female_xiaohe_uranus_bigtts",           # 小何 2.0，通用
    "zh_female_kefunvsheng_uranus_bigtts",      # 暖阳女声 2.0，客服
    # 通用男声（对应原 benjamin 幽默男声 / david 清脆男声 / charles 激昂男声）
    "zh_male_m191_uranus_bigtts",               # 舟 2.0，通用
    "zh_male_taocheng_uranus_bigtts",           # 小天 2.0，通用
    # 多语种（对应原 diana 可爱女声的娃娃音色备选）
    "en_female_dacey_uranus_bigtts",            # Dacey，多语种（英）
    "en_male_tim_uranus_bigtts",                # Tim，多语种（英）
}

VALID_FORMATS = {"mp3", "pcm", "ogg_opus", "wav"}
SAMPLE_RATES = {8000, 16000, 22050, 24000, 32000, 44100, 48000}
# 语速 [-50, 100]：0 默认，100 = 2x，-50 = 0.5x；映射到 [0.5, 2.0]
SPEECH_RATE_MIN = -50
SPEECH_RATE_MAX = 100
LOUDNESS_RATE_MIN = -50
LOUDNESS_RATE_MAX = 100

# ── 百炼 TTS 常量 ─────────────────────────────────────────────────────────────

BAILIAN_WS_BASE_TEMPLATE = "https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1"
BAILIAN_AGENT_PLAN_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
BAILIAN_TTS_PATH = "/services/audio/tts/SpeechSynthesizer"
# 业务空间：plus 主力，3.1 flash 优先于 3.0 flash；Agent Plan 保留原候选链。
BAILIAN_TTS_MODELS = ["qwen-audio-3.0-tts-plus", "qwen-audio-3.1-tts-flash", "qwen-audio-3.0-tts-flash"]
BAILIAN_PLAN_TTS_MODELS = ["qwen-audio-3.0-tts-plus", "qwen-audio-3.0-tts-flash"]
BAILIAN_DEFAULT_VOICE = "longanhuan_v3.6"
BAILIAN_31_DEFAULT_VOICE = "longanhuan_v3.1"
BAILIAN_DEFAULT_SAMPLE_RATE = 24000
BAILIAN_FORMATS = {"mp3", "pcm", "wav", "opus"}
# 火山 ogg_opus 在百炼叫 opus
FORMAT_ALIAS = {"ogg_opus": "opus"}
BAILIAN_SAMPLE_RATES = {8000, 16000, 22050, 24000, 44100, 48000}
BAILIAN_MODEL_UNAVAILABLE_CODES = {403, 404}

SAFE_INPUT_DIRS = (Path("scripts"), Path("assets"), Path("tmp"), Path("output_videos"), Path("fragments"))
SAFE_OUTPUT_DIRS = (Path("assets/audio"), Path("tmp"), Path("output_videos"), Path("fragments"))
TEXT_EXTENSIONS = {".txt", ".md", ".srt", ".vtt"}
MAX_TEXT_FILE_BYTES = 512 * 1024
# seed-tts-2.0 单次合成文本上限（字符版，保守值）
MAX_TEXT_CHARS = 5000


def die(message: str) -> None:
    print(f"[error] {message}", file=sys.stderr)
    sys.exit(1)


def workspace_root(root: Path | None = None) -> Path:
    return (root or Path.cwd()).resolve()


def ensure_safe_path(raw_path: str, allowed_dirs: tuple[Path, ...], purpose: str, root: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    if ".." in path.parts:
        die(f"{purpose} path must not contain '..'")

    resolved_root = workspace_root(root)
    resolved = (resolved_root / path).resolve()
    under_allowed = any(resolved == (resolved_root / base).resolve() or resolved.is_relative_to((resolved_root / base).resolve()) for base in allowed_dirs)
    # 平台运营文件夹约定：允许 <platform>/outputs/...（平台内容项目目录）
    under_platform_outputs = "outputs" in path.parts[:-1]
    if not (under_allowed or under_platform_outputs):
        allowed = ", ".join(str(base) for base in allowed_dirs)
        die(f"{purpose} path must be under one of: {allowed}, or a platform ops folder <platform>/outputs/")
    return resolved


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting that shouldn't be read aloud."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^#{1,6}\s", stripped):
            continue
        if stripped.startswith("<!--") or stripped.endswith("-->"):
            continue
        cleaned = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", stripped)
        cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        lines.append(cleaned)
    return "\n".join(lines).strip()


def extract_tts_requirement_text(content: str) -> str:
    """Extract only the voiceover copy from a tts_requirement.md file."""
    heading_markers = (
        "配音文案",
        "voiceover text",
        "voiceover copy",
        "narration text",
        "script text",
    )
    lines = content.splitlines()
    collecting = False
    extracted: list[str] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if re.match(r"^#{1,6}\s", stripped):
            if collecting:
                break
            if stripped.startswith("## "):
                collecting = any(marker in lower for marker in heading_markers)
            continue
        if not collecting:
            continue
        if not stripped or stripped.startswith("<!--"):
            continue
        extracted.append(stripped)

    return _strip_markdown("\n".join(extracted).strip())


def extract_tts_requirement_settings(content: str) -> dict:
    settings: dict = {}
    for line in content.splitlines():
        stripped = line.strip().strip("-").strip()
        voice_match = re.search(r"(?:音色|语音|voice|speaker)\s*[:：]\s*`?([^\s`，,]+)", stripped, re.IGNORECASE)
        if voice_match:
            settings["voice"] = voice_match.group(1)
        speed_match = re.search(r"(?:语速|speed|speech_rate)\s*[:：]\s*(-?\d+(?:\.\d+)?)", stripped, re.IGNORECASE)
        if speed_match:
            settings["speech_rate"] = float(speed_match.group(1))
    return settings


def read_tts_requirement(path: Path) -> tuple[str, dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        die("tts_requirement.md must be UTF-8 encoded")
    except OSError as exc:
        die(f"failed to read tts_requirement.md: {exc}")

    return extract_tts_requirement_text(content) or content, extract_tts_requirement_settings(content)


def resolve_fragment_dir(raw_path: str, root: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        fragment_dir = path.resolve()
    else:
        if ".." in path.parts:
            die("fragment directory path must not contain '..'")
        resolved_root = workspace_root(root)
        fragment_dir = (resolved_root / path).resolve()
    if fragment_dir.name == "artifacts":
        fragment_dir = fragment_dir.parent
    if not fragment_dir.is_dir():
        die(f"fragment directory does not exist: {raw_path}")
    if not (fragment_dir / "tts_requirement.md").is_file() and not (fragment_dir / "requirement.md").is_file():
        die(f"fragment directory must contain tts_requirement.md or requirement.md: {raw_path}")
    return fragment_dir


def get_fragment_dir(args: argparse.Namespace) -> str | None:
    return getattr(args, "fragment_dir", None)


def read_text_file(raw_path: str, root: Path | None = None) -> str:
    path = ensure_safe_path(raw_path, SAFE_INPUT_DIRS, "--text-file", root=root)
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        die(f"--text-file must use one of these extensions: {', '.join(sorted(TEXT_EXTENSIONS))}")
    if not path.is_file():
        die(f"--text-file does not exist or is not a file: {raw_path}")
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        die(f"--text-file exceeds {MAX_TEXT_FILE_BYTES} bytes")
    try:
        content = path.read_text(encoding="utf-8")
        if path.name == "tts_requirement.md":
            extracted = extract_tts_requirement_text(content)
            return extracted or content
        return content
    except UnicodeDecodeError:
        die("--text-file must be UTF-8 encoded")
    except OSError as exc:
        die(f"failed to read --text-file: {exc}")
    raise AssertionError("unreachable")


def read_text_source(args: argparse.Namespace, root: Path | None = None) -> tuple[str, dict]:
    fragment_dir_arg = get_fragment_dir(args)
    source_count = sum(1 for value in (args.text, args.text_file, fragment_dir_arg) if value)
    if source_count > 1:
        die("Use only one of --text, --text-file, or fragment_dir")
    if args.text_file:
        path = ensure_safe_path(args.text_file, SAFE_INPUT_DIRS, "--text-file", root=root)
        if path.name == "tts_requirement.md":
            text, settings = read_tts_requirement(path)
        else:
            text = read_text_file(args.text_file, root=root)
            settings = {}
    elif args.text:
        text = args.text
        settings = {}
    elif fragment_dir_arg:
        fragment_dir = resolve_fragment_dir(fragment_dir_arg, root=root)
        tts_requirement = fragment_dir / "tts_requirement.md"
        if not tts_requirement.is_file():
            die(f"tts_requirement.md not found under fragment directory: {fragment_dir_arg}")
        text, settings = read_tts_requirement(tts_requirement)
    else:
        die("Either --text, --text-file, or fragment_dir is required")
    text = text.strip()
    if not text:
        die("Input text is empty")
    return text, settings


def read_text(args: argparse.Namespace, root: Path | None = None) -> str:
    text, _settings = read_text_source(args, root=root)
    return text


def apply_tts_settings(args: argparse.Namespace, settings: dict, provider: str = "volc") -> None:
    default_voice = BAILIAN_DEFAULT_VOICE if provider == "bailian" else DEFAULT_SPEAKER
    args.voice_is_default = args.voice is None and not settings.get("voice")
    if args.voice is None:
        args.voice = settings.get("voice") or default_voice
    if args.speech_rate is None and settings.get("speech_rate") is not None:
        args.speech_rate = settings["speech_rate"]


def resolve_resource_id(speaker: str) -> str:
    """按 speaker ID 特征路由 X-Api-Resource-Id。

    - S_xxx 克隆音色 → seed-icl-2.0
    - _uranus_bigtts / saturn_ 官方 2.0 → seed-tts-2.0
    - _mars_bigtts / _moon_bigtts / ICL_ 官方 1.0 → seed-tts-1.0
    """
    if speaker.startswith("S_"):
        return "seed-icl-2.0"
    if "_uranus_bigtts" in speaker or speaker.startswith("saturn_"):
        return "seed-tts-2.0"
    if "_mars_bigtts" in speaker or "_moon_bigtts" in speaker or speaker.startswith("ICL_"):
        return "seed-tts-1.0"
    return os.environ.get("VOLC_TTS_RESOURCE_ID", DEFAULT_RESOURCE_ID).strip() or DEFAULT_RESOURCE_ID


def build_payload(args: argparse.Namespace, text: str) -> dict:
    audio_params: dict = {"format": args.format}
    if args.sample_rate is not None:
        audio_params["sample_rate"] = args.sample_rate
    if args.speech_rate is not None:
        audio_params["speech_rate"] = int(args.speech_rate)
    if args.loudness_rate is not None:
        audio_params["loudness_rate"] = int(args.loudness_rate)
    # enable_subtitle=true 让火山单向流式 HTTP 原生返回字级时间戳
    # （sentence.words 带 startTime/endTime，秒）。默认 false 保持向后兼容。
    if getattr(args, "enable_subtitle", False):
        audio_params["enable_subtitle"] = True

    payload: dict = {
        "user": {"uid": f"wiseflow-awk-tts-{int(time.time())}"},
        "req_params": {
            "text": text,
            "speaker": args.voice,
            "audio_params": audio_params,
        },
    }

    additions: dict = {}
    if args.context_text:
        additions["context_texts"] = [args.context_text]
    # 克隆音色需 model_type=4
    if args.voice.startswith("S_"):
        model_type = getattr(args, "voice_model_type", 4)
        if model_type is not None:
            additions["model_type"] = model_type
    if additions:
        payload["req_params"]["additions"] = json.dumps(additions, ensure_ascii=False)

    return payload


def validate_args(args: argparse.Namespace, text: str, provider: str = "volc") -> None:
    if len(text) > MAX_TEXT_CHARS:
        die(f"Input text exceeds {MAX_TEXT_CHARS} characters (single-call limit)")
    if provider == "bailian":
        # 百炼格式集与火山不同：ogg_opus → opus 别名放行，其余白名单
        mapped = FORMAT_ALIAS.get(args.format, args.format)
        if mapped not in BAILIAN_FORMATS:
            die(f"--format must be one of: {', '.join(sorted(BAILIAN_FORMATS))} (volc ogg_opus → opus)")
        args.format = mapped
        if args.sample_rate is not None and args.sample_rate not in BAILIAN_SAMPLE_RATES:
            die(f"--sample-rate must be one of: {', '.join(str(r) for r in sorted(BAILIAN_SAMPLE_RATES))} (百炼)")
        # 百炼音色不硬拦：系统/克隆/设计音色名由百炼侧校验，火山系音色在 bailian_voice 里换默认
    else:
        if args.voice and args.voice not in VALID_VOICES:
            # 不硬拦——允许用户传克隆音色 S_xxx 或官方未列入的 speaker
            if not (args.voice.startswith("S_") or "_uranus_bigtts" in args.voice or "_mars_bigtts" in args.voice or "_moon_bigtts" in args.voice or args.voice.startswith("saturn_") or args.voice.startswith("ICL_")):
                die(f"Unsupported voice: {args.voice}. Valid voices: {', '.join(sorted(VALID_VOICES))}")
        if args.sample_rate is not None and args.sample_rate not in SAMPLE_RATES:
            die(f"--sample-rate must be one of: {', '.join(str(r) for r in sorted(SAMPLE_RATES))}")
    if args.speech_rate is not None and not SPEECH_RATE_MIN <= args.speech_rate <= SPEECH_RATE_MAX:
        die(f"--speech-rate must be between {SPEECH_RATE_MIN} and {SPEECH_RATE_MAX} (0=default, 100=2x, -50=0.5x)")
    if args.loudness_rate is not None and not LOUDNESS_RATE_MIN <= args.loudness_rate <= LOUDNESS_RATE_MAX:
        die(f"--loudness must be between {LOUDNESS_RATE_MIN} and {LOUDNESS_RATE_MAX}")


def build_headers(resource_id: str) -> dict[str, str]:
    """构造火山鉴权 header：优先旧控制台双头，否则新控制台单头。"""
    headers = {
        "Content-Type": "application/json",
        "X-Api-Resource-Id": resource_id,
        "Connection": "keep-alive",
    }
    app_id = os.environ.get("VOLC_TTS_APP_ID", "").strip()
    access_key = os.environ.get("VOLC_TTS_ACCESS_KEY", "").strip()
    app_key = os.environ.get("VOLC_TTS_APP_KEY", "").strip()

    if app_id and access_key:
        headers["X-Api-App-Id"] = app_id
        headers["X-Api-Access-Key"] = access_key
    elif app_key:
        headers["X-Api-Key"] = app_key
    else:
        die("火山 TTS 凭据未配置：需 VOLC_TTS_APP_ID + VOLC_TTS_ACCESS_KEY（旧控制台双头）或 VOLC_TTS_APP_KEY（新控制台单头）")
    return headers


def create_speech(api_base: str, payload: dict, headers: dict, *, timeout: int = 120) -> tuple[bytes, list[dict]]:
    """调火山 openspeech v3 单向流式 TTS。

    返回 (audio_bytes, sentences)：
    - audio_bytes: 拼装后的 base64 音频分片
    - sentences: 各 sentence 段（含 text/words/phonemes），enable_subtitle=true 时 words 带字级时间戳
    """
    url = f"{api_base.rstrip('/')}{DEFAULT_TTS_PATH}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        die(f"HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        die(f"request failed: {exc.reason}")

    # NDJSON：逐行解析 JSON，收集 data 字段（base64 音频分片）+ sentence 段
    chunks: list[bytes] = []
    sentences: list[dict] = []
    for line in raw.decode(errors="replace").splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        code = parsed.get("code")
        if code == 0 and parsed.get("data"):
            chunks.append(base64.b64decode(parsed["data"]))
        if code == 0 and parsed.get("sentence"):
            sentences.append(parsed["sentence"])
        elif code == 20000000:
            # 正常结束事件
            break
        elif code is not None and code != 0:
            die(f"火山 TTS 流错误: code={code} message={parsed.get('message', '')}")

    if not chunks:
        die("火山 TTS 返回空音频（无 data 分片）")
    return b"".join(chunks), sentences


# ── 百炼 TTS ──────────────────────────────────────────────────────────────────

def resolve_tts_provider():
    """解析 TTS 供应商。返回 "volc" 或 ("bailian", base, api_key, mode)。

    优先级：火山凭据 → 百炼业务空间 → 百炼 agent plan；都未配置 die。
    """
    app_id = os.environ.get("VOLC_TTS_APP_ID", "").strip()
    access_key = os.environ.get("VOLC_TTS_ACCESS_KEY", "").strip()
    app_key = os.environ.get("VOLC_TTS_APP_KEY", "").strip()
    if (app_id and access_key) or app_key:
        return "volc"
    wsid = (os.environ.get("WORKSPACE_ID") or "").strip()
    if wsid:
        key = (
            os.environ.get("MODELSTUDIO_API_KEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or ""
        ).strip()
        if key:
            return ("bailian", BAILIAN_WS_BASE_TEMPLATE.format(wsid=wsid), key, "workspace")
    key = (os.environ.get("AWK_API_KEY") or "").strip()
    if key:
        return ("bailian", BAILIAN_AGENT_PLAN_BASE, key, "agent-plan")
    die(
        "TTS 凭据未配置：需 VOLC_TTS_APP_ID+VOLC_TTS_ACCESS_KEY 或 VOLC_TTS_APP_KEY（火山），"
        "或 WORKSPACE_ID+MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（百炼业务空间），"
        "或 AWK_API_KEY（百炼 agent plan）"
    )


def bailian_voice(voice: str | None, model: str = "") -> str:
    """百炼模式音色选择：用户传了火山系 speaker 时警告并换百炼默认音色。"""
    default_voice = BAILIAN_31_DEFAULT_VOICE if model == "qwen-audio-3.1-tts-flash" else BAILIAN_DEFAULT_VOICE
    if voice and (
        voice in VALID_VOICES
        or "_bigtts" in voice
        or voice.startswith(("S_", "saturn_", "ICL_"))
    ):
        print(
            f"[warn] 音色 {voice} 是火山系音色，百炼不识别；改用百炼默认音色 {default_voice}",
            file=sys.stderr,
        )
        return default_voice
    return voice or default_voice


def build_bailian_payload(args: argparse.Namespace, text: str, model: str) -> dict:
    """构造百炼 SpeechSynthesizer 请求体（model 由调用方传入，便于候选链 fallback）。"""
    inp: dict = {
        "text": text,
        "voice": bailian_voice(None if getattr(args, "voice_is_default", False) is True else args.voice, model),
        "format": FORMAT_ALIAS.get(args.format, args.format),
        "sample_rate": args.sample_rate if args.sample_rate is not None else BAILIAN_DEFAULT_SAMPLE_RATE,
    }
    # 语速 [-50,100] → rate [0.5,2.0] 线性映射（0 → 1.0）
    if args.speech_rate is not None:
        inp["rate"] = round(min(2.0, max(0.5, 1 + args.speech_rate / 100)), 2)
    # 响度 [-50,100] → volume [0,100]（0 → 50，与百炼默认一致）
    if args.loudness_rate is not None:
        inp["volume"] = int(min(100, max(0, 50 + args.loudness_rate / 2)))
    if args.context_text:
        # 火山情感上下文 → 百炼 instruction（风格控制）
        inp["instruction"] = args.context_text
    return {"model": model, "input": inp}


def _bailian_stream_sentences(raw_sentence: dict) -> dict:
    """把百炼 sentence-end 事件的 sentence 转成火山 subtitle schema。

    火山 schema：{text, words:[{word, startTime, endTime}], phonemes:[]}（秒）
    """
    words = []
    for w in raw_sentence.get("words") or []:
        words.append({
            "word": w.get("text") or "",
            "startTime": float(w.get("begin_time", 0)) / 1000.0,
            "endTime": float(w.get("end_time", 0)) / 1000.0,
        })
    # 部分百炼 sentence-end 事件只返回 words，需为下游句级对齐补全文本。
    text = raw_sentence.get("text") or "".join(w["word"] for w in words)
    return {"text": text, "words": words, "phonemes": []}


def create_speech_bailian(
    base: str, api_key: str, payload: dict, *, streaming: bool, timeout: int = 120,
) -> tuple[bytes, list[dict]]:
    """调百炼 SpeechSynthesizer。返回 (audio_bytes, sentences)。

    streaming=False：非流式，响应 JSON 的 output.audio.url 再下载（24h 有效）。
    streaming=True：SSE 流式 + word_timestamp_enabled，audio.data base64 分片按序拼接，
    sentence-end 事件带字级时间戳（转成火山 subtitle schema 落 .subtitle.json）。
    """
    url = f"{base.rstrip('/')}{BAILIAN_TTS_PATH}"
    body = dict(payload)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if streaming:
        headers["X-DashScope-SSE"] = "enable"
        headers["Accept"] = "text/event-stream"
        body["input"] = dict(body["input"], word_timestamp_enabled=True)

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        raise BailianTtsHTTPError(exc.code, err_body)
    except urllib.error.URLError as exc:
        die(f"百炼 TTS 请求失败: {exc.reason}")

    with resp:
        if not streaming:
            try:
                parsed = json.loads(resp.read())
            except json.JSONDecodeError:
                die("百炼 TTS 非流式响应不是 JSON")
            audio_url = ((parsed.get("output") or {}).get("audio") or {}).get("url")
            if not audio_url:
                die(f"百炼 TTS 响应无 output.audio.url: {json.dumps(parsed, ensure_ascii=False)[:500]}")
            try:
                with urllib.request.urlopen(audio_url, timeout=60) as dl:
                    return dl.read(), []
            except urllib.error.URLError as exc:
                die(f"百炼 TTS 音频下载失败: {exc.reason}")

        # SSE：逐行解析，audio.data 分片按序拼接；sentence-end 收字级时间戳
        chunks: list[bytes] = []
        sentences: list[dict] = []
        for raw_line in resp:
            line = raw_line.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk_raw = line[len("data:"):].strip()
            if not chunk_raw or chunk_raw == "[DONE]":
                continue
            try:
                chunk = json.loads(chunk_raw)
            except json.JSONDecodeError:
                continue
            output = chunk.get("output") or {}
            audio = output.get("audio") or {}
            if audio.get("data"):
                chunks.append(base64.b64decode(audio["data"]))
            if output.get("type") == "sentence-end" and output.get("sentence"):
                sentences.append(_bailian_stream_sentences(output["sentence"]))
            code = chunk.get("code")
            if code and code not in ("0", 0, "Success"):
                die(f"百炼 TTS 流错误: code={code} message={chunk.get('message', '')}")
        if not chunks:
            die("百炼 TTS 流式返回空音频（无 audio.data 分片）")
        return b"".join(chunks), sentences


class BailianTtsHTTPError(Exception):
    """百炼 TTS HTTP 错误（携带状态码，供候选链 fallback 决策）。"""

    def __init__(self, code: int, body: str) -> None:
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def create_speech_bailian_with_fallback(
    base: str, api_key: str, args: argparse.Namespace, text: str, *, timeout: int,
    mode: str = "workspace",
) -> tuple[bytes, list[dict], str]:
    """沿选定端点的候选链合成。返回 (audio, sentences, used_model)。"""
    candidates = BAILIAN_PLAN_TTS_MODELS if mode == "agent-plan" else BAILIAN_TTS_MODELS
    models = [args.model] if getattr(args, "model", None) else list(candidates)
    for idx, model in enumerate(models):
        payload = build_bailian_payload(args, text, model)
        try:
            audio, sentences = create_speech_bailian(
                base, api_key, payload, streaming=bool(args.enable_subtitle), timeout=timeout,
            )
            args.voice = payload["input"]["voice"]
            return audio, sentences, model
        except BailianTtsHTTPError as exc:
            print(f"[error] 百炼 TTS HTTP {exc.code}: {exc.body[:500]}", file=sys.stderr)
            is_last = idx == len(models) - 1
            if exc.code in BAILIAN_MODEL_UNAVAILABLE_CODES and not is_last:
                print(f"[warn] model {model} 不可用 (HTTP {exc.code})，切换候选链下一个...", file=sys.stderr)
                continue
            die(f"百炼 TTS 合成失败 (HTTP {exc.code}): {exc.body[:500]}")
    die("百炼 TTS 候选链全部失败")


def resolve_output_path(args: argparse.Namespace, root: Path | None = None) -> Path:
    fragment_dir_arg = get_fragment_dir(args)
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ensure_safe_path(args.output, SAFE_OUTPUT_DIRS, "output", root=root)
        else:
            output_path = output_path.resolve()
    elif args.out_dir:
        out_dir = Path(args.out_dir)
        if out_dir.is_absolute():
            output_path = (out_dir / f"speech.{args.format}").resolve()
        else:
            output_path = ensure_safe_path(str(out_dir / f"speech.{args.format}"), SAFE_OUTPUT_DIRS, "output", root=root)
    elif fragment_dir_arg:
        frag_path = Path(fragment_dir_arg)
        if frag_path.is_absolute():
            output_path = (frag_path / "artifacts" / f"speech.{args.format}").resolve()
            if frag_path.name == "artifacts":
                output_path = (frag_path / f"speech.{args.format}").resolve()
        else:
            output_path = ensure_safe_path(str(frag_path / "artifacts" / f"speech.{args.format}"), SAFE_OUTPUT_DIRS, "output", root=root)
    else:
        output_path = ensure_safe_path(str(Path(f"tmp/awk-tts-{int(time.time())}") / f"speech.{args.format}"), SAFE_OUTPUT_DIRS, "output", root=root)
    if output_path.exists() and not args.overwrite:
        die(f"output file already exists: {output_path}. Use --overwrite to replace it")
    metadata_path = output_path.with_suffix(".json")
    if metadata_path.exists() and not args.overwrite:
        die(f"metadata file already exists: {metadata_path}. Use --overwrite to replace it")
    return output_path


def _audio_input_args(path: Path, fmt: str, sample_rate: int | None) -> list[str]:
    if fmt == "pcm":
        return ["-f", "s16le", "-ar", str(sample_rate or 24000), "-ac", "1", "-i", str(path)]
    return ["-i", str(path)]


def _true_peak(path: Path, fmt: str, sample_rate: int | None) -> float:
    """Measure decoded true peak; use the same source for the avatar and final mix."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", *_audio_input_args(path, fmt, sample_rate),
           "-af", "loudnorm=I=-16:TP=-2.5:LRA=11:print_format=json", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise ValueError(f"TTS 真峰值测量失败：{result.stderr[-500:]}")
    match = re.search(r'\{\s*"input_i"\s*:[\s\S]*?\}', result.stderr)
    if not match:
        raise ValueError("TTS 真峰值测量没有返回 loudnorm JSON")
    return float(json.loads(match.group())["input_tp"])


def protect_audio_peak(path: Path, fmt: str, sample_rate: int | None) -> dict:
    """Add headroom to hot TTS output without changing its timing or dynamics."""
    before = _true_peak(path, fmt, sample_rate)
    if before <= -2.5:
        return {"input_true_peak_db": before, "output_true_peak_db": before, "gain_db": 0}
    # A clipped source cannot be restored; gain prevents another overload in
    # avatar driving, AAC conversion and final delivery.
    gain = -(before + 3.0)
    encoding = {
        "wav": ["-c:a", "pcm_s16le", "-f", "wav"],
        "pcm": ["-c:a", "pcm_s16le", "-f", "s16le"],
        "mp3": ["-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3"],
        "ogg_opus": ["-c:a", "libopus", "-b:a", "96k", "-f", "ogg"],
        "opus": ["-c:a", "libopus", "-b:a", "96k", "-f", "ogg"],
    }[fmt]
    with tempfile.TemporaryDirectory(prefix=".tts-peak-", dir=path.parent) as tmp:
        candidate = Path(tmp) / ("protected." + fmt)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               *_audio_input_args(path, fmt, sample_rate), "-af", f"volume={gain:.3f}dB",
               *encoding, str(candidate)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ValueError(f"TTS 峰值保护失败：{result.stderr[-500:]}")
        after = _true_peak(candidate, fmt, sample_rate)
        if after > -1.5:
            raise ValueError(f"TTS 峰值保护后仍过高：{after:.2f} dBTP")
        candidate.replace(path)
    return {"input_true_peak_db": before, "output_true_peak_db": after, "gain_db": round(gain, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description="火山方舟豆包语音合成 2.0 (seed-tts-2.0)")
    parser.add_argument("fragment_dir", nargs="?", default=None, help="Fragment directory containing tts_requirement.md")
    parser.add_argument("--text", default=None, help="Text to synthesize")
    parser.add_argument("--text-file", default=None, dest="text_file", help="UTF-8 text file")
    parser.add_argument("--voice-profile", type=Path, help="声音复刻/设计保存的 voice.json；锁定供应商、音色与模型")
    parser.add_argument("--platform", choices=["auto", "volc", "workspace", "agent-plan"], default="auto", help="显式选择 volc / workspace / agent-plan；默认自动选路")
    parser.add_argument("--voice", default=None, help="音色 ID（火山系如 zh_female_shuangkuaisisi_uranus_bigtts；百炼系如 longanhuan_v3.6）")
    parser.add_argument(
        "--model", default=None,
        help="百炼模型 ID（显式指定关闭候选链 fallback；火山模式忽略。缺省 qwen-audio-3.0-tts-plus）",
    )
    parser.add_argument(
        "--format",
        default="mp3",
        choices=sorted(VALID_FORMATS),
        help="Audio response format (mp3/pcm/ogg_opus/wav)",
    )
    parser.add_argument("--sample-rate", type=int, default=None, dest="sample_rate", help="Output sample rate")
    parser.add_argument("--speech-rate", type=float, default=None, help="Speech rate [-50, 100], 0=default, 100=2x, -50=0.5x")
    parser.add_argument("--loudness", type=float, default=None, dest="loudness_rate", help="Loudness [-50, 100], 0=default")
    parser.add_argument("--context-text", default=None, dest="context_text", help="情感控制上下文文本（如 '用撒娇甜蜜的语气'）")
    parser.add_argument("--output", default=None, help="Exact output file path under assets/audio, tmp, output_videos, fragments, or <platform>/outputs/")
    parser.add_argument("--out-dir", default=None, dest="out_dir", help="Output directory under assets/audio, tmp, output_videos, fragments, or <platform>/outputs/")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--no-asr-check", action="store_true", dest="no_asr_check", help="Skip ASR self-check after TTS generation")
    parser.add_argument("--enable-subtitle", action="store_true", dest="enable_subtitle", help="产出字级时间戳 .subtitle.json（火山：单向流式原生返回；百炼：SSE 流式 + word_timestamp_enabled）")
    args = parser.parse_args()

    if args.voice_profile or args.platform != "auto":
        import voice_customization
        try:
            if args.voice_profile:
                provider, profile = voice_customization.load_profile(args.voice_profile)
                expected_platform = 'volc' if provider == 'volc' else provider[3]
                if args.platform not in ('auto', expected_platform):
                    die("--platform 与音色档案供应商冲突")
                if (args.voice and args.voice != profile['voice_id']) or (args.model and args.model != profile['target_model']):
                    die("--voice / --model 与音色档案冲突")
                args.voice, args.model = profile['voice_id'], profile['target_model']
                if provider == 'volc':
                    args.voice_model_type = profile.get('model_type')
            else:
                provider = voice_customization.route(args.platform)
        except (ValueError, OSError) as exc:
            die(str(exc))
    else:
        provider = resolve_tts_provider()
    provider_name = provider if provider == "volc" else "bailian"

    text, tts_settings = read_text_source(args)
    apply_tts_settings(args, tts_settings, provider_name)
    validate_args(args, text, provider_name)

    output_path = resolve_output_path(args)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 估算超时：中文约 4 字/秒（正常语速）
    estimated_duration = len(text) / 4
    timeout = max(120, int(estimated_duration * 1.5))

    if provider == "volc":
        resource_id = resolve_resource_id(args.voice)
        payload = build_payload(args, text)
        api_base = os.environ.get("VOLC_TTS_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE
        headers = build_headers(resource_id)
        print(
            f"[info] generating speech: provider=volc speaker={args.voice} resource={resource_id} "
            f"format={args.format} chars={len(text)} timeout={timeout}s"
        )
        audio, sentences = create_speech(api_base, payload, headers, timeout=timeout)
        meta_extra = {"provider": "volcengine-openspeech-v3", "resource_id": resource_id}
    else:
        _tag, base, api_key, mode = provider
        print(
            f"[info] generating speech: provider=bailian({mode}) voice={args.voice} "
            f"format={args.format} subtitle={args.enable_subtitle} chars={len(text)} timeout={timeout}s"
        )
        audio, sentences, used_model = create_speech_bailian_with_fallback(
            base, api_key, args, text, timeout=timeout, mode=mode,
        )
        meta_extra = {"provider": f"bailian-{mode}", "model": used_model}
    if not audio:
        die("empty audio response")

    output_path.write_bytes(audio)

    try:
        peak_guard = protect_audio_peak(output_path, args.format, args.sample_rate)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        die(str(exc))

    audio_duration = get_audio_duration(output_path)

    metadata_path = output_path.with_suffix(".json")
    metadata = {
        **meta_extra,
        "speaker": args.voice,
        "format": args.format,
        "sample_rate": args.sample_rate,
        "speech_rate": args.speech_rate,
        "loudness_rate": args.loudness_rate,
        "text_chars": len(text),
        "audio_bytes": output_path.stat().st_size,
        "peak_guard": peak_guard,
        "duration": round(audio_duration, 3),
        "file": str(output_path),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    # enable_subtitle=true 时 sentences 带 words[startTime/endTime]，落盘供下游对齐
    subtitle_path: Path | None = None
    if sentences:
        subtitle_path = output_path.with_suffix(".subtitle.json")
        subtitle_path.write_text(
            json.dumps({"sentences": sentences}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"[done] Audio saved to: {output_path}")
    print(f"[done] Metadata: {metadata_path}")
    print(f"[done] Duration: {audio_duration:.3f}s")
    if subtitle_path:
        total_words = sum(len(s.get("words", [])) for s in sentences)
        print(f"[done] Subtitle (字级时间戳): {subtitle_path} ({len(sentences)} sentences, {total_words} words)")

    if not args.no_asr_check:
        run_asr_check(output_path, text)


def get_audio_duration(filepath: Path) -> float:
    """Get audio duration via ffprobe. Returns 0.0 if unavailable."""
    import subprocess
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(filepath)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return 0.0


# ── ASR 自检（复用公共路由，与视频转写、剪辑、旁白对齐共用后端）──────────────

def run_asr_check(audio_path: Path, script_text: str, threshold: float = 0.5) -> None:
    """共用公共 ASR 路由转写并比对文本；自检失败仅警告，不中断 TTS。"""
    print("[info] Running ASR self-check (公共 ASR 路由)")
    try:
        result = asr(str(audio_path))
    except Exception:
        print("[warn] ASR check: transcription failed, skipping comparison")
        return
    if not result.get("ok"):
        if "凭证未配置" in result.get("error", ""):
            print("[info] ASR check skipped: 无 ASR 凭据（VOLC_ASR_* 或百炼）")
        else:
            print("[warn] ASR check: transcription failed, skipping comparison")
        return
    transcribed = result.get("text") or ""
    if not transcribed:
        print("[warn] ASR check: empty transcription, skipping comparison")
        return

    sim = similarity_ratio(transcribed, script_text)
    status = "PASS" if sim >= threshold else "WARN"
    print(f"[info] ASR self-check: {status} (similarity={sim:.3f}, threshold={threshold})")
    if sim < threshold:
        print(f"[warn] 转写: {transcribed[:120]}")
        print(f"[warn] 脚本: {script_text[:120]}")


def _clean_for_similarity(text: str) -> str:
    """去掉标点/空白/符号，只留中日韩文字与字母数字。

    中文无空格，按空白分词会把整句压成单 token——一个标点差异相似度即归零；
    清洗后做序列比对，中英文统一可用。
    """
    return re.sub(r"[^0-9A-Za-z一-鿿]", "", text)


def similarity_ratio(text_a: str, text_b: str) -> float:
    """转写文本与脚本文本的相似度（清洗后 SequenceMatcher ratio，序敏感）。"""
    import difflib
    a = _clean_for_similarity(text_a)
    b = _clean_for_similarity(text_b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


if __name__ == "__main__":
    main()
