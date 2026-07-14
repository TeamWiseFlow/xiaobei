#!/usr/bin/env python3
"""SiliconFlow text-to-speech — stdlib only (no httpx/requests)."""

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_API_BASE = "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = "fnlp/MOSS-TTSD-v0.5"
DEFAULT_VOICE = "fnlp/MOSS-TTSD-v0.5:benjamin"
DEFAULT_ASR_MODEL = "TeleAI/TeleSpeechASR"
VALID_FORMATS = {"mp3", "opus", "wav", "pcm"}
VALID_VOICES = {
    "fnlp/MOSS-TTSD-v0.5:benjamin",
    "fnlp/MOSS-TTSD-v0.5:charles",
    "fnlp/MOSS-TTSD-v0.5:claire",
    "fnlp/MOSS-TTSD-v0.5:david",
    "fnlp/MOSS-TTSD-v0.5:diana",
}
SAMPLE_RATES_BY_FORMAT = {
    "mp3": {32000, 44100},
    "opus": {48000},
    "wav": {8000, 16000, 24000, 32000, 44100},
    "pcm": {8000, 16000, 24000, 32000, 44100},
}
SAFE_INPUT_DIRS = (Path("scripts"), Path("assets"), Path("tmp"), Path("output_videos"), Path("fragments"))
SAFE_OUTPUT_DIRS = (Path("assets/audio"), Path("tmp"), Path("output_videos"), Path("fragments"))
TEXT_EXTENSIONS = {".txt", ".md", ".srt", ".vtt"}
MAX_TEXT_FILE_BYTES = 512 * 1024


def die(message: str) -> None:
    print(f"[error] {message}", file=sys.stderr)
    sys.exit(1)


def workspace_root(root: Path | None = None) -> Path:
    return (root or Path.cwd()).resolve()


def ensure_safe_path(raw_path: str, allowed_dirs: tuple[Path, ...], purpose: str, root: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        die(f"{purpose} path must be relative to the workspace")
    if ".." in path.parts:
        die(f"{purpose} path must not contain '..'")

    resolved_root = workspace_root(root)
    resolved = (resolved_root / path).resolve()
    if not any(resolved == (resolved_root / base).resolve() or resolved.is_relative_to((resolved_root / base).resolve()) for base in allowed_dirs):
        allowed = ", ".join(str(base) for base in allowed_dirs)
        die(f"{purpose} path must be under one of: {allowed}")
    return resolved


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
        if stripped.startswith("## "):
            if collecting:
                break
            collecting = any(marker in lower for marker in heading_markers)
            continue
        if not collecting:
            continue
        if not stripped or stripped.startswith("<!--"):
            continue
        extracted.append(stripped)

    return "\n".join(extracted).strip()


def extract_tts_requirement_settings(content: str) -> dict:
    settings: dict = {}
    for line in content.splitlines():
        stripped = line.strip().strip("-").strip()
        voice_match = re.search(r"(?:音色|语音|voice)\s*[:：]\s*`?([^\s`，,]+)", stripped, re.IGNORECASE)
        if voice_match:
            settings["voice"] = voice_match.group(1)
        speed_match = re.search(r"(?:语速|speed)\s*[:：]\s*(\d+(?:\.\d+)?)", stripped, re.IGNORECASE)
        if speed_match:
            settings["speed"] = float(speed_match.group(1))
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
    fragment_dir = ensure_safe_path(raw_path, (Path("fragments"), Path("output_videos")), "fragment directory", root=root)
    if fragment_dir.name == "artifacts":
        fragment_dir = fragment_dir.parent
    if not fragment_dir.is_dir():
        die(f"fragment directory does not exist: {raw_path}")
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


def apply_tts_settings(args: argparse.Namespace, settings: dict) -> None:
    if args.voice is None:
        args.voice = settings.get("voice") or DEFAULT_VOICE
    if args.speed is None and settings.get("speed") is not None:
        args.speed = settings["speed"]


def build_payload(args: argparse.Namespace, text: str) -> dict:
    payload = {
        "model": args.model,
        "input": text,
        "voice": args.voice,
        "response_format": args.format,
        "stream": args.stream,
    }
    if args.max_tokens is not None:
        payload["max_tokens"] = args.max_tokens
    if args.sample_rate is not None:
        payload["sample_rate"] = args.sample_rate
    if args.speed is not None:
        payload["speed"] = args.speed
    if args.gain is not None:
        payload["gain"] = args.gain
    return payload


def validate_args(args: argparse.Namespace, text: str) -> None:
    if args.model != DEFAULT_MODEL:
        die(f"Unsupported model: {args.model}. Use {DEFAULT_MODEL}")
    if args.voice and args.voice not in VALID_VOICES:
        die(f"Unsupported voice: {args.voice}. Valid voices: {', '.join(sorted(VALID_VOICES))}")
    if len(text) > 128000:
        die("Input text exceeds 128000 characters")
    if args.max_tokens is not None and args.max_tokens < 1:
        die("--max-tokens must be greater than 0")
    if args.sample_rate is not None and args.sample_rate not in SAMPLE_RATES_BY_FORMAT[args.format]:
        valid_rates = ", ".join(str(rate) for rate in sorted(SAMPLE_RATES_BY_FORMAT[args.format]))
        die(f"--sample-rate for {args.format} must be one of: {valid_rates}")
    if args.speed is not None and not 0.25 <= args.speed <= 4.0:
        die("--speed must be between 0.25 and 4.0")
    if args.gain is not None and not -10 <= args.gain <= 10:
        die("--gain must be between -10 and 10")


def create_speech(api_base: str, api_key: str, payload: dict, *, timeout: int = 120) -> bytes:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/audio/speech",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        die(f"HTTP {exc.code}: {body}")
    except urllib.error.URLError as exc:
        die(f"request failed: {exc.reason}")
    raise AssertionError("unreachable")

def resolve_output_path(args: argparse.Namespace, root: Path | None = None) -> Path:
    fragment_dir_arg = get_fragment_dir(args)
    if args.output:
        raw_path = args.output
    elif args.out_dir:
        raw_path = str(Path(args.out_dir) / f"speech.{args.format}")
    elif fragment_dir_arg:
        raw_path = str(Path(fragment_dir_arg) / "artifacts" / f"speech.{args.format}")
    else:
        raw_path = str(Path(f"tmp/sf-tts-{int(time.time())}") / f"speech.{args.format}")
    output_path = ensure_safe_path(raw_path, SAFE_OUTPUT_DIRS, "output", root=root)
    if output_path.exists() and not args.overwrite:
        die(f"output file already exists: {raw_path}. Use --overwrite to replace it")
    metadata_path = output_path.with_suffix(".json")
    if metadata_path.exists() and not args.overwrite:
        die(f"metadata file already exists: {metadata_path}. Use --overwrite to replace it")
    return output_path

def main() -> None:
    parser = argparse.ArgumentParser(description="SiliconFlow text-to-speech")
    parser.add_argument("fragment_dir", nargs="?", default=None, help="Fragment directory containing tts_requirement.md")
    parser.add_argument("--text", default=None, help="Text to synthesize")
    parser.add_argument("--text-file", default=None, dest="text_file", help="UTF-8 text file")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=[DEFAULT_MODEL], help="TTS model ID")
    parser.add_argument("--voice", default=None, choices=sorted(VALID_VOICES), help="Voice ID")
    parser.add_argument(
        "--format",
        default="mp3",
        choices=sorted(VALID_FORMATS),
        help="Audio response format",
    )
    parser.add_argument("--max-tokens", type=int, default=None, dest="max_tokens", help="Maximum tokens to generate")
    parser.add_argument("--sample-rate", type=int, default=None, dest="sample_rate", help="Output sample rate")
    parser.add_argument("--stream", action=argparse.BooleanOptionalAction, default=False, help="Enable streaming response")
    parser.add_argument("--speed", type=float, default=None, help="Speech speed, 0.25 to 4.0")
    parser.add_argument("--gain", type=float, default=None, help="Audio gain, -10 to 10")
    parser.add_argument("--output", default=None, help="Exact output file path under assets/audio, tmp, output_videos, or fragments")
    parser.add_argument("--out-dir", default=None, dest="out_dir", help="Output directory under assets/audio, tmp, output_videos, or fragments")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--no-asr-check", action="store_true", dest="no_asr_check", help="Skip ASR self-check after TTS generation")
    args = parser.parse_args()

    text, tts_settings = read_text_source(args)
    apply_tts_settings(args, tts_settings)
    validate_args(args, text)
    payload = build_payload(args, text)
    output_path = resolve_output_path(args)

    api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not api_key:
        die("SILICONFLOW_API_KEY not set")
    api_base = os.environ.get("SILICONFLOW_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Estimate TTS duration: ~4 Chinese chars/sec at normal speed
    estimated_duration = len(text) / 4
    timeout = max(120, int(estimated_duration * 1.5))

    print(
        f"[info] generating speech: model={args.model} voice={args.voice} "
        f"format={args.format} chars={len(text)} timeout={timeout}s"
    )
    audio = create_speech(api_base, api_key, payload, timeout=timeout)
    if not audio:
        die("empty audio response")

    output_path.write_bytes(audio)

    # Calculate audio duration via ffprobe
    audio_duration = get_audio_duration(output_path)

    metadata_path = output_path.with_suffix(".json")
    metadata = {
        "model": args.model,
        "voice": args.voice,
        "format": args.format,
        "stream": args.stream,
        "sample_rate": args.sample_rate,
        "speed": args.speed,
        "gain": args.gain,
        "text_chars": len(text),
        "audio_bytes": len(audio),
        "duration": round(audio_duration, 3),
        "file": str(output_path),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[done] Audio saved to: {output_path}")
    print(f"[done] Metadata: {metadata_path}")
    print(f"[done] Duration: {audio_duration:.3f}s")

    # ASR self-check (optional, requires SILICONFLOW_API_KEY)
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


def run_asr_check(audio_path: Path, script_text: str, threshold: float = 0.5) -> None:
    """Transcribe audio via SiliconFlow ASR and compare with script text.

    Uses Jaccard similarity with the given threshold (default 0.5).
    Only warns on failure; does not abort.
    """
    api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not api_key:
        print("[info] ASR check skipped: SILICONFLOW_API_KEY not set")
        return
    api_base = os.environ.get("SILICONFLOW_API_BASE", DEFAULT_API_BASE).strip() or DEFAULT_API_BASE
    asr_model = os.environ.get("SILICONFLOW_ASR_MODEL", DEFAULT_ASR_MODEL).strip() or DEFAULT_ASR_MODEL

    print(f"[info] Running ASR self-check: model={asr_model}")
    transcribed = transcribe_audio(audio_path, api_key, api_base=api_base, model=asr_model)
    if not transcribed:
        print("[warn] ASR check: transcription failed, skipping comparison")
        return

    sim = jaccard_similarity(transcribed, script_text)
    status = "PASS" if sim >= threshold else "WARN"
    print(f"[info] ASR self-check: {status} (similarity={sim:.3f}, threshold={threshold})")
    if sim < threshold:
        script_words = set(script_text.split())
        transcribed_words = set(transcribed.split())
        missing = script_words - transcribed_words
        if missing:
            sample = ", ".join(list(missing)[:5])
            print(f"[warn] Missing keywords: {sample}...")


def build_multipart_form_data(file_path: Path, fields: dict[str, str], boundary: str | None = None) -> tuple[bytes, str]:
    """Build multipart/form-data for SiliconFlow audio transcription."""
    boundary = boundary or f"----OpenClawBoundary{uuid.uuid4().hex}"
    filename = file_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body_parts: list[bytes] = []

    body_parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    body_parts.append(file_path.read_bytes())
    body_parts.append(b"\r\n")

    for name, value in fields.items():
        body_parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )

    body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body_parts), f"multipart/form-data; boundary={boundary}"


def build_transcription_request(api_base: str, api_key: str, audio_path: Path, model: str = DEFAULT_ASR_MODEL) -> urllib.request.Request:
    body, content_type = build_multipart_form_data(audio_path, {"model": model})
    req = urllib.request.Request(f"{api_base.rstrip('/')}/audio/transcriptions", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", content_type)
    return req


def transcribe_audio(audio_path: Path, api_key: str, api_base: str = DEFAULT_API_BASE, model: str = DEFAULT_ASR_MODEL) -> str:
    """Transcribe audio via SiliconFlow ASR API."""
    req = build_transcription_request(api_base, api_key, Path(audio_path), model=model)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result.get("text", "")
    except (urllib.error.HTTPError, urllib.error.URLError):
        return ""


def jaccard_similarity(text_a: str, text_b: str) -> float:
    a_set = set(text_a.strip().split())
    b_set = set(text_b.strip().split())
    if not a_set and not b_set:
        return 1.0
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / max(len(a_set | b_set), 1)


if __name__ == "__main__":
    main()
