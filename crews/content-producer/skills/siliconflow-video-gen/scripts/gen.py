#!/usr/bin/env python3
"""SiliconFlow video generation — stdlib only (no httpx/requests).

Flow:
  1. POST /v1/video/submit  → requestId
  2. Poll POST /v1/video/status every --poll-interval seconds
  3. When status == 'Succeed', download video to --out-dir
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

SUBMIT_URL = "https://api.siliconflow.cn/v1/video/submit"
STATUS_URL = "https://api.siliconflow.cn/v1/video/status"

T2V_MODEL = "Wan-AI/Wan2.2-T2V-A14B"
I2V_MODEL = "Wan-AI/Wan2.2-I2V-A14B"
VALID_SIZES = {"1280x720", "720x1280", "960x960"}


def post_json(url, payload, api_key, timeout=60):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"[error] HTTP {e.code}: {body}", file=sys.stderr)
        sys.exit(1)


def submit_job(payload, api_key):
    result = post_json(SUBMIT_URL, payload, api_key, timeout=60)
    rid = result.get("requestId")
    if not rid:
        print(f"[error] No requestId in response: {result}", file=sys.stderr)
        sys.exit(1)
    return rid


def poll_until_done(request_id, api_key, poll_interval, timeout):
    deadline = time.time() + timeout
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        result = post_json(STATUS_URL, {"requestId": request_id}, api_key, timeout=30)
        status = result.get("status", "")
        print(f"[info] poll #{attempt}: status={status}")
        if status == "Succeed":
            return result
        if status == "Failed":
            reason = result.get("reason", "unknown")
            print(f"[error] Generation failed: {reason}", file=sys.stderr)
            sys.exit(1)
        # InQueue or InProgress — wait and retry
        time.sleep(poll_interval)
    print(f"[error] Timed out after {timeout}s", file=sys.stderr)
    sys.exit(1)


def download_video(url, dest_path):
    """Stream-download the video file to dest_path."""
    print(f"[info] Downloading video → {dest_path}")
    req = urllib.request.Request(url, headers={"User-Agent": "wiseflow-video-gen/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        dest_path.write_bytes(resp.read())


def main():
    parser = argparse.ArgumentParser(description="SiliconFlow video generation")
    parser.add_argument("--prompt", required=True, help="Video description")
    parser.add_argument(
        "--model",
        default=T2V_MODEL,
        choices=[T2V_MODEL, I2V_MODEL],
        help="Model ID",
    )
    parser.add_argument(
        "--image",
        default=None,
        help="Image URL or base64 data URI (required for I2V model)",
    )
    parser.add_argument(
        "--image-size",
        default="1280x720",
        choices=sorted(VALID_SIZES),
        dest="image_size",
        help="Video resolution",
    )
    parser.add_argument("--negative-prompt", default=None, dest="negative_prompt")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=10, dest="poll_interval")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out-dir", default=None, dest="out_dir")
    args = parser.parse_args()

    if args.model == I2V_MODEL and not args.image:
        print(f"[error] --image is required when using model '{I2V_MODEL}'", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("[error] SILICONFLOW_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    ts = int(time.time())
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"./tmp/sf-video-{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "image_size": args.image_size,
    }
    if args.image:
        payload["image"] = args.image
    if args.negative_prompt:
        payload["negative_prompt"] = args.negative_prompt
    if args.seed is not None:
        payload["seed"] = args.seed

    print(f"[info] Submitting job: model={args.model} size={args.image_size}")
    request_id = submit_job(payload, api_key)
    print(f"[info] Job submitted. requestId={request_id}")
    print(f"[info] Polling every {args.poll_interval}s (timeout={args.timeout}s)…")

    result = poll_until_done(request_id, api_key, args.poll_interval, args.timeout)

    videos = result.get("results", {}).get("videos", [])
    if not videos:
        print(f"[error] No videos in result: {result}", file=sys.stderr)
        sys.exit(1)

    video_url = videos[0].get("url", "")
    if not video_url:
        print("[error] Empty video URL in result", file=sys.stderr)
        sys.exit(1)

    video_path = out_dir / f"video_{request_id[:8]}.mp4"
    download_video(video_url, video_path)

    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"[done] Video saved to: {video_path}")
    print(f"[done] Metadata: {result_path}")


if __name__ == "__main__":
    main()
