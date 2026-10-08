#!/usr/bin/env python3
"""火山引擎方舟（Volcengine Ark）Seedance 视频生成。

直连火山异步任务端点：
  - POST /api/v3/contents/generations/tasks   → 创建任务，返回 task_id
  - GET  /api/v3/contents/generations/tasks/{task_id} → 轮询 status
  - 成功时 content.video_url 即成片下载地址。

模型：仅 Seedance 2.5 → Seedance 2.0 fast；按参数能力筛选候选链。
鉴权：HTTP header `Authorization: Bearer ${VOLC_SEEDANCE_API_KEY}`。

⚠️ 火山视频生成只认 VOLC_SEEDANCE_API_KEY，不回退 ARK_API_KEY：ARK_API_KEY 是火山主模型
（doubao 对话）的 key，用户可能只想用火山主模型而不用火山生成视频；若回退会
误触发火山视频生成。想用火山生成视频必须单独配 VOLC_SEEDANCE_API_KEY。
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

# ---- 火山端点与常量 -----------------------------------------------------------

VOLC_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLC_CREATE = f"{VOLC_BASE}/contents/generations/tasks"
VOLC_QUERY = f"{VOLC_BASE}/contents/generations/tasks/{{task_id}}"

# 只支持这两个模型；不能通过 --model 绕过范围限制。
VOLC_MODELS = {
    "2.5": "doubao-seedance-2-5-260628",
    "fast": "doubao-seedance-2-0-fast-260128",
}

VOLC_POLL_INTERVAL = 15
VOLC_TIMEOUT = 900


# ---- 火山视频生成 -------------------------------------------------------------

def references(value) -> list[str]:
    return [value] if isinstance(value, str) else (value or [])


def volc_image(value: str) -> str:
    if value.startswith(("data:image/", "asset://")):
        return value
    return resolve_image(value)


def volc_build_content(args: argparse.Namespace) -> list[dict]:
    items = [{"type": "text", "text": args.prompt}] if args.prompt else []
    for value, role in ((args.image, "first_frame"), (args.last_frame, "last_frame")):
        if value:
            items.append({"type": "image_url", "image_url": {"url": volc_image(value)}, "role": role})
    for value in references(args.ref_image):
        items.append({"type": "image_url", "image_url": {"url": volc_image(value)}, "role": "reference_image"})
    for kind in ("video", "audio"):
        for value in references(getattr(args, f"ref_{kind}")):
            url = value if value.startswith("asset://") else resolve_media_url(value, f"ref-{kind}")
            items.append({"type": f"{kind}_url", f"{kind}_url": {"url": url}, "role": f"reference_{kind}"})
    return items


def model_constraint(model: str, args: argparse.Namespace) -> str | None:
    if model not in VOLC_MODELS.values():
        return "仅支持 Seedance 2.5 和 Seedance 2.0 fast"
    is_25 = model == VOLC_MODELS["2.5"]
    maximum = 30 if is_25 else 15
    if args.duration != -1 and not 4 <= args.duration <= maximum:
        return f"时长须为 4–{maximum} 秒或 -1（自动）"
    if args.resolution.upper() not in ("480P", "720P"):
        return "当前火山线路支持 480P / 720P"
    limits = (30, 10, 10) if is_25 else (9, 3, 3)
    for kind, limit in zip(("image", "video", "audio"), limits):
        if len(references(getattr(args, f"ref_{kind}"))) > limit:
            return f"参考 {kind} 数量上限为 {limit}"
    if not is_25 and args.ref_audio and not (args.ref_image or args.ref_video):
        return "2.0 fast 不支持仅音频参考"
    return None


def validate_inputs(args: argparse.Namespace) -> None:
    frames = args.image or args.last_frame or args.prev_segment
    refs = args.ref_image or args.ref_video or args.ref_audio
    if frames and refs:
        die("首帧/首尾帧与全模态参考不可混用")
    if args.last_frame and not (args.image or args.prev_segment):
        die("--last-frame 需要 --image 或 --prev-segment")
    if not (args.prompt or frames or refs):
        die("必须提供提示词或参考素材")
    if args.ref_audio and not args.audio:
        die("参考音频不能与 --no-audio 同时使用")


def volc_build_payload(model: str, args: argparse.Namespace) -> dict:
    validate_inputs(args)
    reason = model_constraint(model, args)
    if reason:
        die(f"{model}: {reason}")
    ratio = args.ratio
    if model == VOLC_MODELS["2.5"] and args.image:
        if ratio != "adaptive":
            log("Seedance 2.5 首帧/首尾帧锁定输入比例，ratio 使用 adaptive")
        ratio = "adaptive"
    return {
        "model": model, "content": volc_build_content(args), "ratio": ratio,
        "duration": args.duration, "resolution": args.resolution.lower(),
        "generate_audio": args.audio, "watermark": False,
    }


def volc_submit(model: str, args: argparse.Namespace, api_key: str) -> str:
    payload = volc_build_payload(model, args)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = post_json(VOLC_CREATE, payload, headers, timeout=60)
    task_id = resp.get("id") or resp.get("task_id")
    if not task_id:
        die(f"volcengine submit: no task id in response: {json.dumps(resp, ensure_ascii=False)}")
    return task_id


def volc_poll(task_id: str, api_key: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = VOLC_QUERY.format(task_id=task_id)
    deadline = time.time() + VOLC_TIMEOUT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        resp = get_json(url, headers, timeout=30)
        status = resp.get("status", "")
        log(f"volc poll #{attempt}: status={status}")
        if status == "succeeded":
            video_url = (resp.get("content") or {}).get("video_url")
            if not video_url:
                die(f"volcengine succeeded but no video_url: {json.dumps(resp, ensure_ascii=False)}")
            return video_url
        if status in {"failed", "cancelled", "expired"}:
            err = resp.get("error") or {}
            raise TaskFailed(f"volcengine task {status}: {err.get('code', '')} {err.get('message', '')}")
        time.sleep(VOLC_POLL_INTERVAL)
    die(f"volcengine timed out after {VOLC_TIMEOUT}s (task {task_id})")


def volc_candidates(args: argparse.Namespace) -> list[str]:
    chain = [args.model] if args.model else list(VOLC_MODELS.values())
    candidates = []
    for model in chain:
        reason = model_constraint(model, args)
        if reason:
            if args.model:
                die(f"{model}: {reason}")
            log(f"跳过 {model}: {reason}")
        else:
            candidates.append(model)
    if not candidates:
        die("Seedance 2.5 / 2.0 fast 均不支持当前参数")
    return candidates


# ---- 调度 --------------------------------------------------------------------

def run_one(platform: str, model: str, args: argparse.Namespace, api_key: str) -> str:
    """Submit + poll for a single Volcengine model. Returns video URL or raises."""
    task_id = volc_submit(model, args, api_key)
    log(f"volcengine task submitted: {task_id} (model={model})")
    video_url = volc_poll(task_id, api_key)
    args.used_model = model
    args.effective_ratio = "adaptive" if model == VOLC_MODELS["2.5"] and args.image else args.ratio
    return video_url


def cmd_video(args: argparse.Namespace) -> None:
    validate_inputs(args)
    candidates = volc_candidates(args)

    # --prev-segment: 抽取上一段末帧作为本段首帧（人物故事首尾帧对齐）
    resolve_prev_segment(args)

    api_key = (os.environ.get("VOLC_SEEDANCE_API_KEY") or "").strip()
    if not api_key:
        die("VOLC_SEEDANCE_API_KEY 未设置（火山 Seedance 视频生成专用的普通方舟 API key，非 Coding/Token Plan，不可与 ARK_API_KEY 混用）")

    output_path = ensure_safe_output(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    has_ref = bool(args.ref_image or args.ref_video or args.ref_audio)
    has_i2v = bool(args.image or args.last_frame)
    mode = "r2v" if has_ref else ("i2v" if has_i2v else "t2v")
    log(
        f"platform=volcengine mode={mode} candidates={candidates} "
        f"duration={args.duration}s ratio={args.ratio} resolution={args.resolution} audio={args.audio}"
    )
    video_url = generate("volcengine", candidates, args, api_key, run_one)
    download(video_url, output_path)

    meta = output_path.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "platform": "volcengine",
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
        description="Volcengine Seedance video generation."
    )
    sub = parser.add_subparsers(dest="command")

    # ── 默认子命令：video ──
    p_video = sub.add_parser("video", help="视频生成(默认,可省略 video 子命令)")
    p_video.add_argument("--prompt", default=None, help="画面+音频描述（声画同出）")
    p_video.add_argument("--image", default=None, help="首帧图片：URL 或本地路径（→ i2v）")
    p_video.add_argument("--prev-segment", default=None, dest="prev_segment",
                         help="上一段视频本地路径：脚本自动抽取其末帧作为本段首帧（人物故事首尾帧对齐）。与 --image 互斥")
    p_video.add_argument("--last-frame", default=None, dest="last_frame", help="尾帧图片：URL 或本地路径（i2v 首尾帧）")
    p_video.add_argument("--ref-image", action="append", default=None, dest="ref_image", help="参考图片：URL 或本地路径（→ r2v）")
    p_video.add_argument("--ref-video", action="append", default=None, dest="ref_video", help="参考视频 URL（→ r2v，需公网 URL）")
    p_video.add_argument("--ref-audio", action="append", default=None, help="参考音频公网 URL，可重复；仅音频输入只支持 2.5")
    p_video.add_argument("--duration", type=int, default=8, help="时长（秒），默认 8，2.5 为 4–30，fast 为 4–15；-1 自动")
    p_video.add_argument("--ratio", default="9:16", choices=["21:9", "16:9", "4:3", "1:1", "3:4", "9:16", "adaptive"], help="宽高比，默认 9:16；2.5 首帧自动 adaptive")
    p_video.add_argument("--resolution", default="720P", type=str.upper, choices=["480P", "720P"], help="分辨率，默认 720P")
    p_video.add_argument("--no-audio", action="store_false", dest="audio", help="关闭声画同出（默认开启）")
    p_video.add_argument("--model", default=None, choices=list(VOLC_MODELS.values()), help="指定 2.5 / 2.0 fast Model ID，关闭候选链 fallback")
    p_video.add_argument("--output", required=True, help="输出 MP4 路径（相对工作区，须在 output_videos/tmp/fragments/artifacts 或 <platform>/outputs/ 下）")

    return parser


def main() -> None:
    parser = build_parser()

    # 向后兼容：无子命令时，把全部 argv 当成 video 子命令的参数
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        argv = ["video"] + argv

    # video 子命令可省略：如果第一个 token 不是已知子命令，默认走 video
    known_subcommands = {"video"}
    if argv and argv[0] not in known_subcommands:
        argv = ["video"] + argv

    args = parser.parse_args(argv)
    cmd_video(args)


if __name__ == "__main__":
    main()
