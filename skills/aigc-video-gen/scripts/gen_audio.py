#!/usr/bin/env python3
"""百炼业务空间 Qwen Audio：一次生成台词、人声、背景音、音效与环境音。"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from aigc_common import HttpError, die, download, ensure_safe_output, log, post_json
from audio_media import apply_wav_repair, decoded_timing, sha256, wav_repair_plan

MODEL = "qwen-audio-3.1-tts-next"
API_PATH = "/services/audio/tts/SpeechSynthesizer"
SAMPLE_RATES = (8000, 16000, 24000, 44100, 48000)


def workspace() -> tuple[str, str]:
    wsid = os.environ.get("WORKSPACE_ID", "").strip()
    key = (os.environ.get("MODELSTUDIO_API_KEY", "").strip()
           or os.environ.get("DASHSCOPE_API_KEY", "").strip())
    if not wsid or not key:
        die("音频生成需要 WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（百炼业务空间）", 2)
    if not re.fullmatch(r"[A-Za-z0-9-]+", wsid):
        die("WORKSPACE_ID 格式无效", 2)
    return f"https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1", key


def audio_info(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise ValueError("文件没有音轨")
    return info


def reference(value: str) -> dict:
    if value.startswith(("https://", "http://")):
        # URL 由服务端读取并验证；本地文件由此脚本编码，无需另建上传步骤。
        return {"audio_url": value}
    path = Path(value).expanduser()
    if not path.is_file() or not 0 < path.stat().st_size <= 10 * 1024 * 1024:
        raise ValueError("参考音频必须存在、非空且不超过10MB")
    info = audio_info(path)
    if decoded_timing(path, info)["duration"] > 30:
        raise ValueError("参考音频最长30秒")
    container = info["format"].get("format_name", "")
    codecs = [s.get("codec_name") for s in info["streams"] if s.get("codec_type") == "audio"]
    if container == "wav":
        mime = "audio/wav"
    elif container == "mp3":
        mime = "audio/mpeg"
    elif container == "ogg" and codecs == ["opus"]:
        mime = "audio/ogg"
    else:
        raise ValueError("参考音频只支持 WAV / MP3 / OGG Opus，不支持裸 PCM")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"audio_data": f"data:{mime};base64,{data}"}


def build_payload(args: argparse.Namespace, audio_format: str) -> dict:
    prompt = (Path(args.prompt_file).read_text(encoding="utf-8") if args.prompt_file else args.prompt).strip()
    if not 1 <= len(prompt) <= 3000:
        raise ValueError("--prompt / --prompt-file 必须为1–3000字符")
    refs = args.ref_audio or []
    if len(refs) > 3:
        raise ValueError("参考音频最多3条")
    if any(not 1 <= int(slot) <= len(refs) for slot in re.findall(r"@voice(\d+)", prompt)):
        raise ValueError("提示词引用了不存在的 @voice 编号；按 --ref-audio 顺序从1编号")
    if not 0 <= args.volume <= 100 or not 0.5 <= args.rate <= 2:
        raise ValueError("--volume 须为0–100，--rate 须为0.5–2.0")
    inp = {"text_prompt": prompt, "format": audio_format, "sample_rate": args.sample_rate,
           "channels": args.channels, "volume": args.volume, "rate": args.rate}
    if args.seed is not None:
        inp["seed"] = args.seed
    if refs:
        inp["references"] = [reference(value) for value in refs]
    return {"model": args.model, "input": inp}


def save_metadata(path: Path, metadata: dict) -> None:
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def retain_original(source: Path, output: Path, metadata: dict) -> None:
    """Keep downloaded evidence separate from the validated deliverable."""
    digest = sha256(source)
    original = output.with_name(output.stem + ".original" + output.suffix)
    if original.exists() and sha256(original) != digest:
        original = output.with_name(output.stem + f".original-{digest[:12]}" + output.suffix)
    if source.resolve() != original.resolve():
        shutil.copyfile(source, original)
    metadata.update(original_file=str(original), original_sha256=digest)


def finish_audio(output_path: Path, meta_path: Path, metadata: dict, source: Path | None = None) -> None:
    """Download or reuse local bytes, validate, measure and publish; never generate."""
    audio_format = output_path.suffix.lower().lstrip(".")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=output_path.suffix, delete=False) as temp:
        temp_path = Path(temp.name)
    metadata["status"] = "generated"
    save_metadata(meta_path, metadata)
    raw_retained = False
    try:
        if source is not None:
            shutil.copyfile(source, temp_path)
        else:
            url = metadata.get("audio_url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                raise ValueError("缺少有效生成链接；可用 --source 指定已有原始下载")
            download(url, temp_path)
        repair = wav_repair_plan(temp_path, metadata.get("reported_duration")) if audio_format == "wav" else None
        if repair:
            retain_original(temp_path, output_path, metadata)
            raw_retained = True
            save_metadata(meta_path, metadata)
            apply_wav_repair(temp_path, repair)
            metadata["header_repair"] = repair
            log("已修正WAV占位长度字段；原始文件已保留，PCM数据未改变")
        info = audio_info(temp_path)
        if info["format"].get("format_name") != audio_format:
            raise ValueError("返回音频格式与请求不一致")
        timing = decoded_timing(temp_path, info)
        try:
            probe_duration = float(info["format"].get("duration"))
        except (ValueError, TypeError):
            probe_duration = None
        if probe_duration is not None and (not math.isfinite(probe_duration) or probe_duration <= 0):
            probe_duration = None
        if "duration" in metadata and metadata.get("duration_source") != "decoded-samples":
            metadata["previous_duration"] = metadata["duration"]
        metadata.update(timing, probe_duration=probe_duration,
                        bytes=temp_path.stat().st_size, sha256=sha256(temp_path), status="downloaded")
        metadata.pop("validation_error", None)
        temp_path.replace(output_path)
        save_metadata(meta_path, metadata)
    except (OSError, ValueError, http.client.HTTPException, subprocess.SubprocessError) as exc:
        # Never publish suspect audio or discard the bytes needed for local recovery.
        if temp_path.is_file() and temp_path.stat().st_size and not raw_retained:
            retain_original(temp_path, output_path, metadata)
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        if isinstance(exc, subprocess.CalledProcessError):
            stderr = exc.stderr or b""
            detail += ": " + (stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr)[-1000:]
        metadata.update(status="generated", validation_error=detail)
        save_metadata(meta_path, metadata)
        die(f"音频下载或验证失败：{detail}；原始文件和生成链接见 {meta_path}。"
            "使用 audio --resume 恢复，不要重新提交生成")
    finally:
        temp_path.unlink(missing_ok=True)
    print(f"[done] audio saved: {output_path}")
    print(f"[done] duration:    {metadata['duration']:.6f}s (decoded-samples)")
    print(f"[done] metadata:    {meta_path}")


def resume_audio(args: argparse.Namespace) -> None:
    if args.output:
        die("--resume 使用metadata中原有输出路径，不与 --output 同用", 2)
    if (args.ref_audio or args.format or args.rate != 1.0 or args.volume != 50 or args.seed is not None
            or args.channels != 2 or args.sample_rate != 48000):
        die("--resume 仅恢复原音频，不接受新的参考音频、格式或生成参数", 2)
    meta_path = Path(args.resume).expanduser()
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if (not isinstance(metadata, dict) or metadata.get("capability") != "audio" or metadata.get("platform") != "dashscope"
                or metadata.get("model") != MODEL):
            raise ValueError("metadata不属于此声音场景模型")
        saved_output = Path(metadata["file"])
        if saved_output.is_absolute():
            saved_output = saved_output.resolve().relative_to(Path.cwd().resolve())
        output_path = ensure_safe_output(str(saved_output))
        if output_path.suffix.lower() not in (".wav", ".mp3"):
            raise ValueError("metadata输出须为WAV/MP3")
        if meta_path.resolve() == output_path.resolve():
            raise ValueError("metadata不可覆盖音频")
        source = Path(args.source).expanduser() if args.source else None
        if source is None and metadata.get("status") == "downloaded" and output_path.is_file():
            source = output_path
        if source is None and metadata.get("original_file"):
            candidate = Path(metadata["original_file"])
            if candidate.is_file():
                source = candidate
        if source is not None and not source.is_file():
            raise ValueError("--source 指定的原始音频不存在")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        die(f"音频恢复参数无效：{exc}", 2)
    # Recovery needs neither model credentials nor a POST request. Prefer local
    # files, so an expired signed URL does not prevent measurement or repair.
    finish_audio(output_path, meta_path, metadata, source)


def cmd_audio(args: argparse.Namespace) -> None:
    if args.resume:
        resume_audio(args)
        return
    if args.source:
        die("--source 只能与 --resume 同用", 2)
    if not args.output:
        die("生成音频必须提供 --output（工作区相对路径）", 2)
    base, key = workspace()
    output_path = ensure_safe_output(args.output)
    audio_format = output_path.suffix.lower().lstrip(".")
    if audio_format not in ("wav", "mp3"):
        die("audio --output 必须使用 .wav 或 .mp3 后缀", 2)
    if args.format and args.format != audio_format:
        die("--format 必须与 --output 文件后缀一致", 2)
    try:
        payload = build_payload(args, audio_format)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        die(f"音频输入无效：{exc}", 2)
    log(f"platform=dashscope provider=workspace capability=audio model={args.model}")
    try:
        data = post_json(base + API_PATH, payload, {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "X-DashScope-SSE": "disable",
        }, timeout=300)
    except (HttpError, OSError, ValueError) as exc:
        die(f"音频生成请求失败：{exc}；未自动重试，提交结果不确定时先核查")
    if not isinstance(data, dict):
        die("音频生成响应不是 JSON 对象")
    if data.get("code") not in (None, "", 0, "0", "Success"):
        die(f"音频生成失败：code={data.get('code')} request_id={data.get('request_id', '')}")
    output = data.get("output")
    audio = output.get("audio") if isinstance(output, dict) else None
    audio_url = audio.get("url") if isinstance(audio, dict) else None
    if (not isinstance(audio_url, str) or not audio_url.startswith(("https://", "http://"))
            or output.get("finish_reason") != "stop"):
        die(f"音频生成响应不完整：request_id={data.get('request_id', '')}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = output_path.with_suffix(".json")
    # 先保存已生成音频的链接；下载/验证失败也不应重新提交付费生成。
    metadata = {
        "platform": "dashscope", "provider_mode": "workspace", "capability": "audio",
        "model": args.model, "status": "generated", "text_prompt": payload["input"]["text_prompt"],
        "references": args.ref_audio or [],
        "parameters": {k: v for k, v in payload["input"].items() if k not in ("text_prompt", "references")},
        "audio_url": audio_url, "audio_id": audio.get("id"), "expires_at": audio.get("expires_at"),
        "request_id": data.get("request_id"), "reported_duration": audio.get("duration"),
        "usage": data.get("usage") or {}, "file": str(output_path),
    }
    save_metadata(meta_path, metadata)
    finish_audio(output_path, meta_path, metadata)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="百炼业务空间声音场景生成：人声、背景音、音效、环境音")
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt", help="台词、人物声音、背景和环境描述，1–3000字符")
    prompt.add_argument("--prompt-file", help="UTF-8 提示词文件，1–3000字符")
    prompt.add_argument("--resume", help="已有metadata JSON；仅下载/校验/修复并更新实测时长，不重新生成")
    parser.add_argument("--source", help="与 --resume 同用，指定已有原始下载文件；优先离线恢复")
    parser.add_argument("--ref-audio", action="append", help="参考音频 URL 或本地文件；最多3条，按 @voice1–3 引用")
    parser.add_argument("--format", choices=["wav", "mp3"], help="默认按 --output 后缀选择")
    parser.add_argument("--sample-rate", type=int, choices=SAMPLE_RATES, default=48000)
    parser.add_argument("--channels", type=int, choices=[1, 2], default=2)
    parser.add_argument("--volume", type=int, default=50, help="输出音量0–100，默认50")
    parser.add_argument("--rate", type=float, default=1.0, help="语速0.5–2.0，默认1.0")
    parser.add_argument("--seed", type=int, help="请求随机种子；省略时由服务端使用默认值")
    parser.add_argument("--model", choices=[MODEL], default=MODEL)
    parser.add_argument("--output", help="生成时必填：工作区相对WAV/MP3路径，须在 output_videos/tmp/fragments/artifacts 或平台 outputs 下；不支持绝对路径")
    return parser


if __name__ == "__main__":
    cmd_audio(build_parser().parse_args())
