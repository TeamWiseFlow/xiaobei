#!/usr/bin/env python3
"""Atlas Cloud asynchronous image generation client."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

API_BASE = "https://api.atlascloud.ai/api/v1"
GENERATE_URL = f"{API_BASE}/model/generateImage"
UPLOAD_URL = f"{API_BASE}/model/uploadMedia"
DEFAULT_MODEL = "bytedance/seedream-v5.0-lite"
TERMINAL_SUCCESS = {"completed", "succeeded", "success"}
TERMINAL_FAILURE = {"failed", "canceled", "cancelled"}


def request_json(url: str, api_key: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "xiaobei-atlascloud-img-gen/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        raise RuntimeError(f"Atlas Cloud HTTP {error.code}: {body}") from error


def upload_file(path: Path, api_key: str) -> str:
    boundary = f"----atlascloud-{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        UPLOAD_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "xiaobei-atlascloud-img-gen/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read())
    url = result.get("data", {}).get("download_url")
    if not url:
        raise RuntimeError(f"Atlas Cloud upload returned no download_url: {result}")
    return url


def resolve_image(value: str | None, api_key: str) -> str | None:
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    path = Path(value).expanduser()
    if not path.is_file():
        raise ValueError(f"Image file not found: {path}")
    return upload_file(path, api_key)


def prediction_id(result: dict) -> str:
    value = result.get("data", {}).get("id") or result.get("id")
    if not value:
        raise RuntimeError(f"Atlas Cloud returned no prediction id: {result}")
    return str(value)


def poll_prediction(identifier: str, api_key: str, interval: float, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = request_json(f"{API_BASE}/model/prediction/{identifier}", api_key)
        data = result.get("data", result)
        status = str(data.get("status", "")).lower()
        if status in TERMINAL_SUCCESS:
            return result
        if status in TERMINAL_FAILURE:
            raise RuntimeError(f"Atlas Cloud prediction {status}: {result}")
        time.sleep(interval)
    raise TimeoutError(f"Atlas Cloud prediction timed out after {timeout:g}s")


def output_urls(result: dict) -> list[str]:
    data = result.get("data", result)
    outputs = data.get("outputs") or data.get("output") or []
    if isinstance(outputs, str):
        outputs = [outputs]
    return [item for item in outputs if isinstance(item, str) and item.startswith(("http://", "https://"))]


def download(url: str, destination: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "xiaobei-atlascloud-img-gen/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        destination.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or edit images with Atlas Cloud")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--image", help="Remote URL or local reference image")
    parser.add_argument("--params", default="{}", help="Additional model parameters as JSON")
    parser.add_argument("--out-dir")
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()

    api_key = os.environ.get("ATLASCLOUD_API_KEY", "").strip()
    if not api_key:
        print("[error] ATLASCLOUD_API_KEY not set", file=sys.stderr)
        raise SystemExit(1)
    try:
        extra = json.loads(args.params)
        if not isinstance(extra, dict):
            raise ValueError("--params must decode to a JSON object")
        image_url = resolve_image(args.image, api_key)
        payload = {"model": args.model, "prompt": args.prompt, **extra}
        if image_url:
            payload["image_url"] = image_url
        submitted = request_json(GENERATE_URL, api_key, method="POST", payload=payload)
        identifier = prediction_id(submitted)
        print(f"[info] prediction={identifier}", file=sys.stderr)
        result = poll_prediction(identifier, api_key, args.poll_interval, args.timeout)
        urls = output_urls(result)
        if not urls:
            raise RuntimeError(f"Completed prediction returned no output URLs: {result}")
        out_dir = Path(args.out_dir) if args.out_dir else Path(f"./tmp/atlascloud-img-{int(time.time())}")
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, url in enumerate(urls):
            suffix = Path(urllib.parse.urlparse(url).path).suffix
            destination = out_dir / f"{index:02d}{suffix or '.png'}"
            download(url, destination)
            print(destination)
        (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as error:
        print(f"[error] {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
