#!/usr/bin/env python3
"""阿里云百炼：业务空间 Wan3.0 视频 / Fun-Music；Agent Plan / legacy HappyHorse / Wan2.7。

直连百炼异步任务端点：
  - POST /services/aigc/video-generation/video-synthesis  → 创建任务，返回 task_id
  - GET  /tasks/{task_id}                                  → 轮询 task_status
  - 成功时 output.video_url 即成片下载地址。

模型候选链：
  - 业务空间：wan3.0-video-prime → wan3.0-video（统一模型，按媒体输入识别任务）
  - Agent Plan / legacy：happyhorse-1.1-{mode} → happyhorse-1.0-{mode} → wan2.7-{mode}

端点/key 双模式（2026-09 provider 收敛，ds_resolve）：
  - 业务空间（优先）：WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY
    → https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1
  - agent plan：否则 AWK_API_KEY → https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1
  - legacy 兼容：都没有但 MODELSTUDIO/DASHSCOPE 在 → 默认 dashscope.aliyuncs.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# aigc_common.py 与本脚本同目录（skills/aigc-video-gen/scripts/）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aigc_common import (  # noqa: E402
    HttpError,
    TaskFailed,
    die,
    download,
    ensure_safe_output,
    generate,
    get_json,
    log,
    post_json,
    resolve_image,
    resolve_media_url,
    resolve_prev_segment,
)

# ---- 百炼端点与常量 -----------------------------------------------------------

DS_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"  # legacy 兼容端点
DS_WS_BASE_TEMPLATE = "https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1"
DS_AGENT_PLAN_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
DS_CREATE_PATH = "/services/aigc/video-generation/video-synthesis"
DS_QUERY_PATH = "/tasks/{task_id}"
DS_MUSIC_PATH = "/services/audio/music/generation"
DS_MUSIC_MODEL = "fun-music-v1"

# 业务空间使用 Wan3.0 统一模型，不按 t2v/i2v/r2v 拼接模型 ID。
DS_WS_MODEL_CHAIN = ["wan3.0-video-prime", "wan3.0-video"]
# Agent Plan / legacy 保留原有每模式候选链。
# generate() 在 TaskFailed / HttpError 时自动沿链 fallback；--model 显式指定时只用该模型。
DS_MODEL_CHAIN = {
    "t2v": ["happyhorse-1.1-t2v", "happyhorse-1.0-t2v", "wan2.7-t2v"],
    "i2v": ["happyhorse-1.1-i2v", "happyhorse-1.0-i2v", "wan2.7-i2v"],
    "r2v": ["happyhorse-1.1-r2v", "happyhorse-1.0-r2v", "wan2.7-r2v"],
}

DS_POLL_INTERVAL = 15
DS_TIMEOUT = 900
WAN3_RATIOS = {"adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}


def ds_resolve() -> tuple[str, str, str]:
    """解析百炼端点模式。返回 (base, api_key, mode)。

    - 业务空间（优先）：WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY
    - agent plan：否则 AWK_API_KEY（token-plan 端点）
    - legacy 兼容：都没有但 MODELSTUDIO/DASHSCOPE 在 → 默认端点（老部署无 AWK_API_KEY 时）
    - 都不可用 → die
    """
    wsid = (os.environ.get("WORKSPACE_ID") or "").strip()
    ws_key = (
        (os.environ.get("MODELSTUDIO_API_KEY") or "").strip()
        or (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    )
    if wsid and ws_key:
        return DS_WS_BASE_TEMPLATE.format(wsid=wsid), ws_key, "workspace"
    if wsid:
        log("WORKSPACE_ID 已配置但 MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY 缺失，尝试 agent plan")
    awk_key = (os.environ.get("AWK_API_KEY") or "").strip()
    if awk_key:
        return DS_AGENT_PLAN_BASE, awk_key, "agent-plan"
    if ws_key:
        return DS_DEFAULT_BASE, ws_key, "legacy"
    die("百炼视频生成凭据未配置：需 WORKSPACE_ID+MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（业务空间）或 AWK_API_KEY（agent plan）")

# ---- 百炼业务空间音乐生成 -----------------------------------------------------

def ds_music_resolve() -> tuple[str, str]:
    """音乐仅使用完整业务空间凭据，不采用视频的 Plan / legacy 端点。"""
    wsid = os.environ.get("WORKSPACE_ID", "").strip()
    key = (os.environ.get("MODELSTUDIO_API_KEY", "").strip()
           or os.environ.get("DASHSCOPE_API_KEY", "").strip())
    if not wsid or not key:
        die("百炼音乐生成需要 WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY（业务空间）")
    return DS_WS_BASE_TEMPLATE.format(wsid=wsid), key


def ds_music_build_payload(args: argparse.Namespace) -> dict:
    """构造 Fun-Music 非流式请求；音频参数属于 input，无时长参数。"""
    prompt = (args.prompt or "").strip()
    lyrics = (args.lyrics or "").strip()
    if not prompt and not lyrics:
        die("音乐生成至少提供 --prompt 或 --lyrics 其中之一")
    if args.prompt is not None and not 1 <= len(prompt) <= 2000:
        die("--prompt 必须为1–2000字符")
    if lyrics:
        has_chinese = any("\u3400" <= char <= "\u9fff" for char in lyrics)
        max_chars = 350 if has_chinese else 2000
        if not 5 <= len(lyrics) <= max_chars:
            die(f"--lyrics 必须为5–{max_chars}字符（中文最多350，英文最多2000）")
    elif args.lyrics is not None:
        die("--lyrics 不能为空")
    if args.instrumental and not prompt:
        die("纯音乐模式需要 --prompt；--lyrics 在纯音乐模式下不生效")
    inp = {"is_instrumental": args.instrumental, "format": args.format}
    if prompt:
        inp["prompt"] = prompt
    if args.instrumental:
        if lyrics or args.gender:
            log("纯音乐模式忽略 --lyrics / --gender")
    else:
        if lyrics:
            inp["lyrics"] = lyrics
        if args.gender:
            inp["gender"] = args.gender
    return {"model": args.model, "input": inp}


def cmd_music(args: argparse.Namespace) -> None:
    """同步生成完整音乐 → 下载音频 → 保存实际响应与模型 metadata。"""
    base, key = ds_music_resolve()
    output_path = ensure_safe_output(args.output)
    extension = output_path.suffix.lower().lstrip(".")
    if extension not in ("mp3", "wav"):
        die("百炼音乐 --output 必须使用 .mp3 或 .wav 后缀")
    args.format = args.format or extension
    if args.format != extension:
        die("--format 必须与 --output 文件后缀一致")
    payload = ds_music_build_payload(args)
    log(f"platform=dashscope provider=workspace capability=music model={args.model} format={args.format}")
    try:
        data = post_json(base + DS_MUSIC_PATH, payload, {
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "X-DashScope-SSE": "disable",
        }, timeout=300)
    except HttpError as exc:
        die(f"百炼音乐生成失败：{exc}")
    if data.get("code") not in (None, "", 0, "0", "Success"):
        die(f"百炼音乐生成失败：code={data.get('code')} message={data.get('message', '')}")
    output = data.get("output") or {}
    audio = output.get("audio") or {}
    audio_url = audio.get("url") or ""
    if not audio_url.startswith(("https://", "http://")):
        die("百炼音乐响应缺少有效的 output.audio.url")
    if output.get("finish_reason") not in (None, "stop"):
        die(f"百炼音乐未完成：finish_reason={output.get('finish_reason')}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download(audio_url, output_path)
    if not output_path.is_file() or not output_path.stat().st_size:
        die("百炼音乐下载返回空音频")
    meta = output_path.with_suffix(".json")
    meta.write_text(json.dumps({
        "platform": "dashscope", "provider_mode": "workspace", "capability": "music",
        "model": args.model, "prompt": payload["input"].get("prompt"),
        "lyrics": payload["input"].get("lyrics"), "is_instrumental": args.instrumental,
        "gender": payload["input"].get("gender"), "format": args.format,
        "audio_url": audio_url, "audio_id": audio.get("id"), "expires_at": audio.get("expires_at"),
        "request_id": data.get("request_id"), "extra_info": output.get("extra_info") or {},
        "duration": (data.get("usage") or {}).get("duration"),
        "file": str(output_path), "bytes": output_path.stat().st_size,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] music saved: {output_path}")
    print(f"[done] metadata:    {meta}")


# ---- 百炼视频生成 -------------------------------------------------------------

def references(value) -> list[str]:
    """兼容单个引用和 CLI 的可重复参数。"""
    return [value] if isinstance(value, str) else (value or [])


def ds_mode(args: argparse.Namespace) -> str:
    if any(references(getattr(args, name, None)) for name in ("ref_image", "ref_video", "ref_audio")):
        return "r2v"
    return "i2v" if args.image or args.last_frame or args.prev_segment else "t2v"


def ds_image(value: str, wan3: bool) -> str:
    if wan3:
        if value.startswith(("data:image/", "oss://")):
            return value
        if not value.startswith(("http://", "https://")):
            path = Path(value)
            if path.is_file() and path.stat().st_size > 20 * 1024 * 1024:
                die(f"Wan3.0 图片超过20MB：{value}")
    return resolve_image(value)


def ds_media_url(value: str, kind: str, wan3: bool) -> str:
    if wan3 and value.startswith("oss://"):
        return value
    return resolve_media_url(value, kind)


def ds_build_input(args: argparse.Namespace, model: str) -> dict:
    wan3 = model in DS_WS_MODEL_CHAIN
    inp: dict = {"prompt": args.prompt} if args.prompt else {}

    media: list[dict] = []
    if args.image:
        media.append({"type": "first_frame", "url": ds_image(args.image, wan3)})
    if args.last_frame:
        media.append({"type": "last_frame", "url": ds_image(args.last_frame, wan3)})
    for ref in references(args.ref_image):
        media.append({"type": "reference_image", "url": ds_image(ref, wan3)})
    for kind in ("video", "audio"):
        for ref in references(getattr(args, f"ref_{kind}", None)):
            media.append({"type": f"reference_{kind}", "url": ds_media_url(ref, f"ref-{kind}", wan3)})
    if media:
        inp["media"] = media
    return inp


def ds_submit(model: str, args: argparse.Namespace, api_key: str, base: str) -> str:
    wan3 = model in DS_WS_MODEL_CHAIN
    parameters = {
        "resolution": args.resolution.upper(),
        "ratio": "adaptive" if wan3 and args.image else args.ratio,
        "duration": args.duration,
        "watermark": False,
    }
    if wan3:
        parameters["audio"] = args.audio
    payload: dict = {
        "model": model,
        "input": ds_build_input(args, model),
        "parameters": parameters,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    resp = post_json(f"{base}{DS_CREATE_PATH}", payload, headers, timeout=60)
    task_id = (resp.get("output") or {}).get("task_id")
    if not task_id:
        die(f"dashscope submit: no task id in response: {json.dumps(resp, ensure_ascii=False)}")
    return task_id


def ds_poll(task_id: str, api_key: str, base: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base}{DS_QUERY_PATH.format(task_id=task_id)}"
    deadline = time.time() + DS_TIMEOUT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        resp = get_json(url, headers, timeout=30)
        out = resp.get("output") or {}
        status = out.get("task_status", "")
        log(f"dashscope poll #{attempt}: status={status}")
        if status == "SUCCEEDED":
            video_url = out.get("video_url")
            if not video_url:
                die(f"dashscope succeeded but no video_url: {json.dumps(resp, ensure_ascii=False)}")
            return video_url
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise TaskFailed(
                f"dashscope task {status}: {out.get('code', '')} {out.get('message', '')}"
            )
        time.sleep(DS_POLL_INTERVAL)
    die(f"dashscope timed out after {DS_TIMEOUT}s (task {task_id})")


def ds_validate(args: argparse.Namespace, model: str, provider_mode: str) -> None:
    """校验所选模型的能力；显式 --model 也必须遵守输入约束。"""
    has_frames = bool(args.image or args.last_frame or args.prev_segment)
    refs = {kind: references(getattr(args, f"ref_{kind}", None)) for kind in ("image", "video", "audio")}
    has_ref = any(refs.values())
    if args.image and args.prev_segment:
        die("--prev-segment 与 --image 互斥")
    if args.last_frame and not (args.image or args.prev_segment):
        die("--last-frame 需要 --image 或 --prev-segment")
    if has_frames and has_ref:
        die("首帧/首尾帧与参考素材不可混用")

    if model in DS_WS_MODEL_CHAIN:
        if provider_mode != "workspace":
            die("Wan3.0 视频生成需要百炼业务空间：WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY")
        if not args.prompt and not (has_frames or has_ref):
            die("Wan3.0 需要提示词或媒体素材")
        if args.duration != -1 and not 2 <= args.duration <= 30:
            die("Wan3.0 --duration 必须为2–30秒或 -1（智能时长）")
        if args.resolution.upper() not in {"480P", "720P", "1080P"}:
            die("Wan3.0 --resolution 仅支持480P/720P/1080P")
        if args.ratio not in WAN3_RATIOS:
            die("Wan3.0 --ratio 仅支持 adaptive/21:9/16:9/4:3/1:1/3:4/9:16")
        for kind, limit in (("image", 10), ("video", 5), ("audio", 5)):
            if len(refs[kind]) > limit:
                die(f"Wan3.0 参考{kind}数量上限为{limit}")
        return

    if model.startswith("wan3."):
        die("Wan3.0 模型ID应为 wan3.0-video 或 wan3.0-video-prime")
    if not args.prompt:
        die("HappyHorse/Wan2.7 需要 --prompt")
    if not 3 <= args.duration <= 15:
        die("HappyHorse/Wan2.7 --duration 必须在3–15秒之间")
    if args.resolution.upper() not in {"720P", "1080P"}:
        die("HappyHorse/Wan2.7 --resolution 仅支持720P/1080P")
    if args.last_frame:
        die("HappyHorse/Wan2.7 i2v 仅支持首帧，不支持 --last-frame")
    if refs["video"] or refs["audio"] or len(refs["image"]) > 1:
        die("HappyHorse/Wan2.7 参考模式仅支持一张 --ref-image")
    if not args.audio:
        die("--no-audio 当前仅支持百炼业务空间 Wan3.0")


def ds_candidates(args: argparse.Namespace, mode: str, provider_mode: str) -> list[str]:
    candidates = [args.model] if args.model else (
        list(DS_WS_MODEL_CHAIN) if provider_mode == "workspace" else list(DS_MODEL_CHAIN[mode])
    )
    for model in candidates:
        ds_validate(args, model, provider_mode)
    return candidates


# ---- 调度 --------------------------------------------------------------------

def run_one(platform: str, model: str, args: argparse.Namespace, api_key: str) -> str:
    """Submit + poll for a single DashScope model. Returns video URL or raises."""
    base = args.provider_base
    task_id = ds_submit(model, args, api_key, base)
    log(f"dashscope task submitted: {task_id} (model={model} base={base})")
    video_url = ds_poll(task_id, api_key, base)
    args.used_model = model
    args.effective_ratio = "adaptive" if model in DS_WS_MODEL_CHAIN and args.image else args.ratio
    return video_url


def cmd_video(args: argparse.Namespace) -> None:
    base, api_key, provider_mode = ds_resolve()
    args.provider_base = base
    mode = ds_mode(args)
    candidates = ds_candidates(args, mode, provider_mode)

    # --prev-segment: 抽取上一段末帧作为本段首帧（人物故事首尾帧对齐）
    resolve_prev_segment(args)

    output_path = ensure_safe_output(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(
        f"platform=dashscope provider={provider_mode} mode={mode} candidates={candidates} "
        f"duration={args.duration}s ratio={args.ratio} resolution={args.resolution}"
    )
    video_url = generate("dashscope", candidates, args, api_key, run_one)
    download(video_url, output_path)

    meta = output_path.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "platform": "dashscope",
                "provider_mode": provider_mode,
                "mode": mode,
                "model_candidates": candidates,
                "model": args.used_model,
                "duration": args.duration,
                "ratio": args.effective_ratio,
                "requested_ratio": args.ratio,
                "resolution": args.resolution,
                "audio": args.audio,
                "video_url": video_url,
                "file": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[done] video saved: {output_path}")
    print(f"[done] metadata:    {meta}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aliyun workspace Wan3.0 video / Fun-Music; Agent Plan HappyHorse video."
    )
    sub = parser.add_subparsers(dest="command")

    # ── 默认子命令：video ──
    p_video = sub.add_parser("video", help="视频生成(默认,可省略 video 子命令)")
    p_video.add_argument("--prompt", default=None, help="画面+音频描述；Wan3.0 传媒体时可省略，其他模型必需")
    p_video.add_argument("--image", default=None, help="首帧图片：URL 或本地路径（→ i2v）")
    p_video.add_argument("--prev-segment", default=None, dest="prev_segment",
                         help="上一段视频本地路径：脚本自动抽取其末帧作为本段首帧（人物故事首尾帧对齐）。与 --image 互斥")
    p_video.add_argument("--last-frame", default=None, dest="last_frame", help="尾帧图片：URL 或本地路径（i2v 首尾帧）")
    p_video.add_argument("--ref-image", action="append", default=None, dest="ref_image", help="参考图；Wan3.0 可重复传入最多10张，URL / 本地路径")
    p_video.add_argument("--ref-video", action="append", default=None, dest="ref_video", help="Wan3.0 参考视频，可重复传入最多5段；公网 URL / OSS 临时 URL")
    p_video.add_argument("--ref-audio", action="append", default=None, dest="ref_audio", help="Wan3.0 参考音频，可重复传入最多5段；公网 URL / OSS 临时 URL")
    p_video.add_argument("--no-audio", action="store_false", dest="audio", help="Wan3.0 输出无声视频；默认包含声音")
    p_video.add_argument("--duration", type=int, default=8, help="时长（秒），默认8；Wan3.0 为2–30或 -1，其他模型3–15")
    p_video.add_argument("--ratio", default="9:16", help="宽高比，默认 9:16")
    p_video.add_argument("--resolution", default="720P", type=str.upper, choices=["480P", "720P", "1080P"], help="分辨率，默认720P；480P 仅 Wan3.0 支持")
    p_video.add_argument("--model", default=None, help="指定模型 id（关闭候选链 fallback）")
    p_video.add_argument("--output", required=True, help="输出 MP4 路径（相对工作区，须在 output_videos/tmp/fragments/artifacts 或 <platform>/outputs/ 下）")

    p_music = sub.add_parser("music", help="百炼业务空间 Fun-Music 音乐生成")
    p_music.add_argument("--prompt", default=None, help="音乐风格/场景描述，1–2000字符；与歌词至少提供一项")
    p_music.add_argument("--lyrics", default=None, help="歌词：中文5–350字符，英文5–2000字符；提供时优先于 prompt")
    p_music.add_argument("--instrumental", action="store_true", help="生成纯音乐（无人声），需要 prompt")
    p_music.add_argument("--gender", choices=["male", "female"], default=None, help="演唱性别，API 默认女声；纯音乐时忽略")
    p_music.add_argument("--format", choices=["mp3", "wav"], default=None, help="音频格式，默认按输出文件后缀选择")
    p_music.add_argument("--model", choices=[DS_MUSIC_MODEL], default=DS_MUSIC_MODEL, help="音乐模型，默认 fun-music-v1")
    p_music.add_argument("--output", required=True, help="输出 MP3/WAV 路径（相对工作区，沿用视频输出目录约束）")

    return parser


def main() -> None:
    parser = build_parser()

    # 向后兼容：无子命令时，把全部 argv 当成 video 子命令的参数
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["video"] + argv

    # video 子命令可省略：如果第一个 token 不是已知子命令，默认走 video
    known_subcommands = {"video", "music"}
    if argv and argv[0] not in known_subcommands:
        argv = ["video"] + argv

    args = parser.parse_args(argv)
    if args.command == "music":
        cmd_music(args)
    else:
        cmd_video(args)


if __name__ == "__main__":
    main()
