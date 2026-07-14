#!/usr/bin/env python3
"""Video AIGC generation — direct endpoint calls to Volcengine Seedance or Aliyun DashScope.

Stdlib only (no httpx/requests). The script auto-detects which platform to use
from environment variables (DashScope/百炼 preferred over Volcengine/火山), submits
an async video-generation task, polls until completion, and downloads the MP4.

Flow:
  1. Resolve platform (override via --platform, else env vars)
  2. Resolve mode: r2v (ref-image/ref-video) > i2v (image) > t2v
  3. Pick model: --model, else platform candidate chain (with fallback)
  4. POST create task → task_id
  5. Poll task status until terminal
  6. Download video_url → --output

If neither MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY nor AWK_GEN_KEY is set,
prints guidance to use pexels-footage / pixabay-footage and exits non-zero.

Note: 火山引擎视频生成只认 AWK_GEN_KEY，不回退 ARK_API_KEY。
原因：ARK_API_KEY 是火山主模型（doubao 对话）的 key，用户可能只想用火山主模型
而不用火山生成视频；若此处回退 ARK_API_KEY，会误触发火山视频生成。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---- Volcengine Ark (Seedance) -------------------------------------------------
VOLC_BASE = "https://ark.cn-beijing.volces.com/api/v3"
VOLC_CREATE = f"{VOLC_BASE}/contents/generations/tasks"
VOLC_QUERY = f"{VOLC_BASE}/contents/generations/tasks/{{task_id}}"

# Seedance 2.0 series. Fast preferred → normal → mini. All three are multimodal
# (t2v / i2v / r2v share the same model id).
VOLC_MODELS = {
    "fast": "doubao-seedance-2-0-fast-260128",
    "normal": "doubao-seedance-2-0-260128",
    "mini": "doubao-seedance-2-0-mini-260615",
}

# ---- Aliyun DashScope (百炼 Wan2.7 / HappyHorse) ------------------------------
# wan2.7 走默认 dashscope 端点；HappyHorse 是华北2模型，配了 WORKSPACE_ID 时走业务空间
# 专属端点 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com（见 SKILL.md 模型选型）。
DS_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"
DS_WS_BASE_TEMPLATE = "https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1"
DS_CREATE_PATH = "/services/aigc/video-generation/video-synthesis"
DS_QUERY_PATH = "/tasks/{task_id}"


def ds_base_for_model(model: str) -> str:
    """Resolve the DashScope base URL for a given model.

    happyhorse-1.1 / 1.0 在默认 dashscope.aliyuncs.com 端点可正常调用（WorkspaceId 端点
    只是华北2的性能优化，非必需）。WORKSPACE_ID 设置时走专属端点更快，否则走默认。
    wan2.7 始终走默认端点。
    """
    wsid = (os.environ.get("WORKSPACE_ID") or "").strip()
    if model.startswith("happyhorse") and wsid:
        return DS_WS_BASE_TEMPLATE.format(wsid=wsid)
    return DS_DEFAULT_BASE

# 百炼模型候选链（按价格/可用性优先，每模式一条）：
#   happyhorse-1.1 系列（当前折扣价低于 wan2.7，优先）→ happyhorse-1.0 系列 → wan2.7 系列托底
# generate() 在 TaskFailed / HttpError 时自动沿链 fallback；--model 显式指定时只用该模型。
DS_MODEL_CHAIN = {
    "t2v": ["happyhorse-1.1-t2v", "happyhorse-1.0-t2v", "wan2.7-t2v"],
    "i2v": ["happyhorse-1.1-i2v", "happyhorse-1.0-i2v", "wan2.7-i2v"],
    "r2v": ["happyhorse-1.1-r2v", "happyhorse-1.0-r2v", "wan2.7-r2v"],
}

VALID_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}
SAFE_OUTPUT_DIRS = (
    Path("output_videos"),
    Path("tmp"),
    Path("fragments"),
    Path("artifacts"),
)

# Transient HTTP statuses worth retrying on the same model before falling back.
RETRYABLE_HTTP = {408, 429, 500, 502, 503, 504}


def die(message: str, code: int = 1) -> None:
    print(f"[error] {message}", file=sys.stderr)
    sys.exit(code)


def log(message: str) -> None:
    print(f"[info] {message}")


# ---- asset resolution ---------------------------------------------------------

def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def image_to_data_url(path: Path) -> str:
    """Base64-encode a local image into a data: URL acceptable by both platforms."""
    if not path.is_file():
        die(f"image file not found: {path}")
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        die(f"unsupported image type: {path}")
    raw = path.read_bytes()
    if len(raw) > 30 * 1024 * 1024:
        die(f"image exceeds 30MB: {path}")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def resolve_image(value: str) -> str:
    """Images may be a public URL or a local file (base64 data URL)."""
    if is_url(value):
        return value
    return image_to_data_url(Path(value))


# ---- prev-segment last-frame extraction ---------------------------------------

def ffprobe_duration(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_entries", "format=duration", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        info = json.loads(result.stdout)
        return float(info.get("format", {}).get("duration", 0) or 0)
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        die(f"ffprobe failed on {path}: {exc}")


def extract_last_frame(video_path: Path) -> Path:
    """Extract the last frame of a video to a sibling hidden .jpg.

    Used by --prev-segment: the last frame of the previous segment becomes the
    first frame of the next segment, giving首尾帧对齐 between人物故事片段.
    Output is a .jpg sibling of the source (assemble.py only picks video
    extensions, so this never pollutes the concat order).

    Strategy: try multiple ffmpeg seek strategies in order. Some AI-generated
    videos (notably 百炼 wan2.7-r2v) produce MP4s where the container duration
    is slightly larger than the actual stream end — e.g. duration=10.030998s but
    the last frame is at 9.967s (300 frames @ 30fps). A naive output-side
    `-ss duration - 0.05` then lands past the last frame and ffmpeg reports
    "Output file is empty, nothing was encoded". We try three strategies in
    order and use the first one that produces a non-empty jpg:
      1) `-sseof -1` + `-update 1` (seek-from-end, gives the actual last frame
         for any video ≥1s; the image2 muxer keeps overwriting the single jpg
         with each decoded frame and ends on the final one)
      2) `-ss duration - 0.5` (more conservative from-start accurate seek;
         decodes from 0 but lands well before any "container padding")
      3) `-ss duration - 1.0` (last resort; near-end frame)
    """
    if not video_path.is_file():
        die(f"--prev-segment video not found: {video_path}")
    duration = ffprobe_duration(video_path)
    if duration <= 0:
        die(f"could not determine duration for --prev-segment video: {video_path}")
    dest = video_path.with_name(f".{video_path.stem}_lastframe.jpg")
    # Clean up any stale file from a previous failed attempt
    if dest.is_file():
        dest.unlink()

    strategies: list[tuple[str, list[str]]] = [
        (
            "-sseof -1 (seek-from-end)",
            [
                "ffmpeg", "-y", "-sseof", "-1", "-i", str(video_path),
                "-update", "1", "-frames:v", "1", "-q:v", "2", "-an", str(dest),
            ],
        ),
        (
            f"-ss {max(0.0, duration - 0.5):.3f} (duration - 0.5s)",
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-ss", f"{max(0.0, duration - 0.5):.3f}",
                "-frames:v", "1", "-q:v", "2", "-an", str(dest),
            ],
        ),
        (
            f"-ss {max(0.0, duration - 1.0):.3f} (duration - 1.0s)",
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-ss", f"{max(0.0, duration - 1.0):.3f}",
                "-frames:v", "1", "-q:v", "2", "-an", str(dest),
            ],
        ),
    ]

    attempts: list[str] = []
    for label, cmd in strategies:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            attempts.append(f"[{label}] ffmpeg timed out after 60s")
            continue
        if (
            result.returncode == 0
            and dest.is_file()
            and dest.stat().st_size > 0
        ):
            log(
                f"extracted last frame of {video_path.name} → {dest.name} "
                f"(strategy: {label})"
            )
            return dest
        tail = (result.stderr or "")[-300:]
        attempts.append(
            f"[{label}] rc={result.returncode} "
            f"dest_exists={dest.is_file()} tail={tail!r}"
        )
        # Clean up partial/empty output before next attempt
        if dest.is_file():
            dest.unlink()

    die(
        f"ffmpeg last-frame extraction failed on {video_path} "
        f"(tried {len(strategies)} strategies):\n"
        + "\n".join(attempts)
    )


def resolve_media_url(value: str, kind: str) -> str:
    """Video/audio references must be public URLs — neither platform accepts
    base64 for video/audio in a way we can reliably use, so require a URL."""
    if is_url(value):
        return value
    die(
        f"--{kind} must be a public http(s) URL; local {kind} files are not "
        f"supported (upload to OSS/TOS/a public host first). Got: {value}"
    )


def ensure_safe_output(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        die(f"--output must be relative to the workspace: {raw_path}")
    if ".." in path.parts:
        die(f"--output must not contain '..': {raw_path}")
    root = Path.cwd().resolve()
    resolved = (root / path).resolve()
    if not any(
        resolved.is_relative_to((root / base).resolve()) for base in SAFE_OUTPUT_DIRS
    ):
        die(
            f"--output must be under one of: {', '.join(str(d) for d in SAFE_OUTPUT_DIRS)}"
        )
    return resolved


# ---- HTTP helpers -------------------------------------------------------------

def post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise HttpError(exc.code, body) from None
    except urllib.error.URLError as exc:
        raise HttpError(0, str(exc.reason)) from None


def get_json(url: str, headers: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise HttpError(exc.code, body) from None
    except urllib.error.URLError as exc:
        raise HttpError(0, str(exc.reason)) from None


class HttpError(Exception):
    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def download(url: str, dest: Path, timeout: int = 300) -> None:
    log(f"downloading → {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "wiseflow-video-gen/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


# ---- platform: Volcengine -----------------------------------------------------

def volc_build_content(args: argparse.Namespace) -> list[dict]:
    items: list[dict] = [{"type": "text", "text": args.prompt}]
    if args.image:
        items.append(
            {"type": "image_url", "image_url": {"url": resolve_image(args.image)}, "role": "first_frame"}
        )
    if args.last_frame:
        items.append(
            {"type": "image_url", "image_url": {"url": resolve_image(args.last_frame)}, "role": "last_frame"}
        )
    if args.ref_image:
        items.append(
            {"type": "image_url", "image_url": {"url": resolve_image(args.ref_image)}, "role": "reference_image"}
        )
    if args.ref_video:
        items.append(
            {"type": "video_url", "video_url": {"url": resolve_media_url(args.ref_video, "ref-video")}}
        )
    if args.ref_audio:
        items.append(
            {"type": "audio_url", "audio_url": {"url": resolve_media_url(args.ref_audio, "ref-audio")}}
        )
    return items


def volc_submit(model: str, args: argparse.Namespace, api_key: str) -> str:
    payload: dict = {
        "model": model,
        "content": volc_build_content(args),
        "ratio": args.ratio,
        "duration": args.duration,
        "resolution": args.resolution.lower(),
        "generate_audio": args.audio,
    }
    if args.seed is not None:
        payload["seed"] = args.seed
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = post_json(VOLC_CREATE, payload, headers, timeout=60)
    task_id = resp.get("id") or resp.get("task_id")
    if not task_id:
        die(f"volcengine submit: no task id in response: {json.dumps(resp, ensure_ascii=False)}")
    return task_id


def volc_poll(task_id: str, api_key: str, interval: int, timeout: int) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = VOLC_QUERY.format(task_id=task_id)
    deadline = time.time() + timeout
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
        time.sleep(interval)
    die(f"volcengine timed out after {timeout}s (task {task_id})")


# ---- platform: DashScope ------------------------------------------------------

def ds_build_input(args: argparse.Namespace) -> dict:
    inp: dict = {"prompt": args.prompt}
    if args.negative_prompt:
        inp["negative_prompt"] = args.negative_prompt

    media: list[dict] = []
    if args.image:
        media.append({"type": "first_frame", "url": resolve_image(args.image)})
    if args.last_frame:
        media.append({"type": "last_frame", "url": resolve_image(args.last_frame)})
    if args.ref_image:
        m = {"type": "reference_image", "url": resolve_image(args.ref_image)}
        if args.ref_audio:
            m["reference_voice"] = resolve_media_url(args.ref_audio, "ref-audio")
        media.append(m)
    if args.ref_video:
        m = {"type": "reference_video", "url": resolve_media_url(args.ref_video, "ref-video")}
        if args.ref_audio:
            m["reference_voice"] = resolve_media_url(args.ref_audio, "ref-audio")
        media.append(m)
    if args.ref_audio:
        audio_url = resolve_media_url(args.ref_audio, "ref-audio")
        if media and (args.image or args.last_frame) and not args.ref_image and not args.ref_video:
            # i2v + driving audio: audio rides as a media item
            media.append({"type": "driving_audio", "url": audio_url})
        elif not media:
            # t2v + audio: audio_url lives at input level
            inp["audio_url"] = audio_url
    if media:
        inp["media"] = media
    return inp


def ds_submit(model: str, args: argparse.Namespace, api_key: str, base: str) -> str:
    payload: dict = {
        "model": model,
        "input": ds_build_input(args),
        "parameters": {
            "resolution": args.resolution.upper(),
            "ratio": args.ratio,
            "duration": args.duration,
            "prompt_extend": args.prompt_extend,
            "watermark": False,
        },
    }
    if args.seed is not None:
        payload["parameters"]["seed"] = args.seed
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


def ds_poll(task_id: str, api_key: str, interval: int, timeout: int, base: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{base}{DS_QUERY_PATH.format(task_id=task_id)}"
    deadline = time.time() + timeout
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
        time.sleep(interval)
    die(f"dashscope timed out after {timeout}s (task {task_id})")


class TaskFailed(Exception):
    pass


# ---- model candidate chains ---------------------------------------------------

def volc_candidates(args: argparse.Namespace) -> list[str]:
    chain = [VOLC_MODELS["fast"], VOLC_MODELS["normal"], VOLC_MODELS["mini"]]
    # fast only supports 720p; skip it for 1080p
    if args.resolution.lower() == "1080p":
        chain = [m for m in chain if m != VOLC_MODELS["fast"]]
    return chain


def ds_candidates(args: argparse.Namespace, mode: str) -> list[str]:
    # Mode-level capability checks (apply to every model in the chain)
    # happyhorse 系列最短 3 秒；wan2.7 托底同链，统一要求 ≥3（脚本规划已遵守）
    if args.duration < 3:
        die("百炼视频生成最短 3 秒；请将 --duration 提到 ≥3 或拆分片段")
    # i2v 仅首帧，不支持首+尾帧
    if mode == "i2v" and args.last_frame:
        die("i2v 不支持首+尾帧（仅首帧）；请去掉 --last-frame")
    # r2v 仅参考图，不支持参考视频、不支持首帧
    if mode == "r2v" and args.ref_video:
        die("r2v 仅支持参考图（--ref-image）；不支持 --ref-video")
    if mode == "r2v" and args.image:
        die(
            "r2v 仅支持参考图（--ref-image）；"
            "不要传 --image 或 --prev-segment（r2v 不收首帧）"
        )
    return list(DS_MODEL_CHAIN[mode])


# ---- orchestration ------------------------------------------------------------

def resolve_platform() -> str:
    has_ds = bool(os.environ.get("MODELSTUDIO_API_KEY", "").strip() or os.environ.get("DASHSCOPE_API_KEY", "").strip())
    has_volc = bool(os.environ.get("AWK_GEN_KEY", "").strip())
    if has_ds:
        return "dashscope"
    if has_volc:
        return "volcengine"
    print(
        "[error] 未检测到任何视频生成平台的环境变量（MODELSTUDIO_API_KEY / AWK_GEN_KEY 均未设置）。\n"
        "[hint] 请改用 pexels-footage 和 pixabay-footage 技能搜集素材：\n"
        "       1) pexels-footage 搜索并下载 9:16 竖屏素材（按片段时长设 --min-duration/--max-duration）\n"
        "       2) pexels 无结果时用 pixabay-footage 兜底\n"
        "       3) 下载后按脚本片段编号重命名放入 artifacts/，再用 check.py 自检\n"
        "       若要启用 AI 直生成，请配置 MODELSTUDIO_API_KEY（阿里云百炼，优先）或 AWK_GEN_KEY（火山引擎）。",
        file=sys.stderr,
    )
    sys.exit(2)


def resolve_mode(args: argparse.Namespace) -> str:
    if args.ref_video or args.ref_image:
        return "r2v"
    if args.image:
        return "i2v"
    return "t2v"


def run_one(platform: str, model: str, args: argparse.Namespace, api_key: str) -> str:
    """Submit + poll for a single model. Returns video URL or raises."""
    if platform == "volcengine":
        task_id = volc_submit(model, args, api_key)
        log(f"volcengine task submitted: {task_id} (model={model})")
        return volc_poll(task_id, api_key, args.poll_interval, args.timeout)
    base = ds_base_for_model(model)
    task_id = ds_submit(model, args, api_key, base)
    log(f"dashscope task submitted: {task_id} (model={model} base={base})")
    return ds_poll(task_id, api_key, args.poll_interval, args.timeout, base)


def generate(platform: str, candidates: list[str], args: argparse.Namespace, api_key: str) -> str:
    """Try candidate models in order. HttpError/TaskFailed trigger fallback
    unless the user explicitly pinned --model (then only transient retries)."""
    pinned = args.model is not None
    models = candidates if pinned else candidates
    last_err = ""
    for idx, model in enumerate(models):
        for attempt in range(1, 4):  # up to 3 transient retries per model
            try:
                return run_one(platform, model, args, api_key)
            except TaskFailed as exc:
                last_err = str(exc)
                log(f"model {model} task failed: {last_err}")
                break  # task-level failure → fall back to next model, no retry
            except HttpError as exc:
                last_err = str(exc)
                if exc.code in RETRYABLE_HTTP and attempt < 3:
                    log(f"model {model} HTTP {exc.code}, retrying ({attempt}/2)")
                    time.sleep(3 * attempt)
                    continue
                log(f"model {model} submit error: {last_err}")
                break  # fall back to next model
        if pinned:
            break  # respect explicit user choice — no chain walk
        if idx < len(models) - 1:
            log(f"falling back to next model: {models[idx + 1]}")
    die(f"all model attempts failed; last error: {last_err}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Video AIGC generation via Volcengine Seedance or Aliyun DashScope (auto-detected)."
    )
    parser.add_argument("--prompt", required=True, help="画面+音频描述（声画同出）")
    parser.add_argument("--image", default=None, help="首帧图片：URL 或本地路径（→ i2v）")
    parser.add_argument("--prev-segment", default=None, dest="prev_segment",
                        help="上一段视频本地路径：脚本自动抽取其末帧作为本段首帧（人物故事首尾帧对齐）。与 --image 互斥")
    parser.add_argument("--last-frame", default=None, dest="last_frame", help="尾帧图片：URL 或本地路径（i2v 首尾帧）")
    parser.add_argument("--ref-image", default=None, dest="ref_image", help="参考图片：URL 或本地路径（→ r2v，角色/主体一致性）")
    parser.add_argument("--ref-video", default=None, dest="ref_video", help="参考视频 URL（→ r2v，需公网 URL）")
    parser.add_argument("--ref-audio", default=None, dest="ref_audio", help="驱动/参考音频 URL（需公网 URL）")
    parser.add_argument("--negative-prompt", default=None, dest="negative_prompt", help="反向提示词")
    parser.add_argument("--duration", type=int, default=8, help="时长（秒），默认 8")
    parser.add_argument("--ratio", default="9:16", choices=sorted(VALID_RATIOS), help="宽高比，默认 9:16")
    parser.add_argument("--resolution", default="720P", choices=["720P", "1080P"], help="分辨率，默认 720P")
    parser.add_argument("--no-audio", action="store_false", dest="audio", help="关闭声画同出（默认开启）")
    parser.add_argument("--no-prompt-extend", action="store_false", dest="prompt_extend", help="关闭 DashScope prompt 智能改写")
    parser.add_argument("--platform", default=None, choices=["volcengine", "dashscope"], help="覆盖平台自动检测")
    parser.add_argument("--model", default=None, help="指定模型 id（关闭候选链 fallback）")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=15, dest="poll_interval", help="轮询间隔秒，默认 15")
    parser.add_argument("--timeout", type=int, default=900, help="整体超时秒，默认 900")
    parser.add_argument("--output", required=True, help="输出 MP4 路径（相对工作区，须在 output_videos/tmp/fragments/artifacts 下）")
    args = parser.parse_args()

    if args.duration < 2 or args.duration > 15:
        die("--duration 必须在 2–15 秒之间")

    # --prev-segment: extract last frame of the previous segment and use it as
    # the first frame. Enables人物故事模式 A.1 首尾帧对齐: each segment starts
    # from the exact end frame of the previous one.
    prev_segment_frame: Path | None = None
    if args.prev_segment:
        if args.image:
            die("--prev-segment 与 --image 互斥：首帧由上一段末帧决定")
        prev_segment_frame = extract_last_frame(Path(args.prev_segment))
        args.image = str(prev_segment_frame)

    platform = args.platform or resolve_platform()
    mode = resolve_mode(args)

    if platform == "volcengine":
        api_key = (os.environ.get("AWK_GEN_KEY") or "").strip()
        if not api_key:
            die("AWK_GEN_KEY 未设置")
        candidates = [args.model] if args.model else volc_candidates(args)
    else:
        api_key = (os.environ.get("MODELSTUDIO_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip()
        if not api_key:
            die("MODELSTUDIO_API_KEY / DASHSCOPE_API_KEY 未设置")
        candidates = [args.model] if args.model else ds_candidates(args, mode)

    output_path = ensure_safe_output(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(
        f"platform={platform} mode={mode} candidates={candidates} "
        f"duration={args.duration}s ratio={args.ratio} resolution={args.resolution} audio={args.audio}"
    )
    video_url = generate(platform, candidates, args, api_key)
    download(video_url, output_path)

    meta = output_path.with_suffix(".json")
    meta.write_text(
        json.dumps(
            {
                "platform": platform,
                "mode": mode,
                "model_candidates": candidates,
                "duration": args.duration,
                "ratio": args.ratio,
                "resolution": args.resolution,
                "audio": args.audio,
                "video_url": video_url,
                "file": str(output_path),
                "prev_segment": args.prev_segment,
                "first_frame_from_prev": str(prev_segment_frame) if prev_segment_frame else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[done] video saved: {output_path}")
    print(f"[done] metadata:    {meta}")


if __name__ == "__main__":
    main()
