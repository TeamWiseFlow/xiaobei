#!/usr/bin/env python3
"""
pixabay_search.py — Search and download copyright-free images / video clips from Pixabay.

Environment Variables:
  PIXABAY_API_KEY  Pixabay API key (required, register free at pixabay.com/api/docs)

Usage:
  python3 pixabay_search.py --terms "sunset,ocean waves" --aspect 9:16 --output-dir ./footage
  python3 pixabay_search.py --terms "business,technology" --type image --aspect 16:9 --output-dir ./images
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
PIXABAY_PHOTO_API = "https://pixabay.com/api/"

ASPECT_MIN_WIDTH = {
    "9:16":  1080,
    "16:9":  1920,
    "1:1":   1080,
}

# Pixabay image API uses "horizontal" / "vertical" (no "square")
PIXABAY_ORIENTATION = {
    "9:16":  "vertical",
    "16:9":  "horizontal",
    "1:1":   "",  # Pixabay has no square filter; we accept all then filter locally
}


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(json.dumps({"ok": False, "error": f"{name} is not set"}))
        sys.exit(1)
    return val


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()[:12]


def search_pixabay_photos(term: str, aspect: str, api_key: str) -> list[dict]:
    """Search Pixabay for photos matching term and orientation."""
    orientation = PIXABAY_ORIENTATION.get(aspect, "")
    min_w = ASPECT_MIN_WIDTH.get(aspect, 1080)

    params = {"q": term, "image_type": "photo", "per_page": 50, "key": api_key}
    if orientation:
        params["orientation"] = orientation
    url = f"{PIXABAY_PHOTO_API}?{urlencode(params)}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"Photo search failed for '{term}': {e}")
        return []

    results = []
    for img in data.get("hits", []):
        # Prefer largeImageURL for quality
        img_url = img.get("largeImageURL") or img.get("webformatURL") or ""
        if not img_url:
            continue
        iw = int(img.get("imageWidth", 0))
        ih = int(img.get("imageHeight", 0))
        # For 1:1 aspect, filter approximately square images locally
        if aspect == "1:1" and iw > 0 and ih > 0:
            ratio = iw / ih
            if ratio < 0.9 or ratio > 1.1:
                continue
        if iw >= min_w:
            results.append({
                "url": img_url,
                "term": term,
                "width": iw,
                "height": ih,
            })
    return results


def search_pixabay_videos(term: str, aspect: str, min_duration: int, max_duration: int | None, api_key: str) -> list[dict]:
    """Search Pixabay for video clips."""
    min_w = ASPECT_MIN_WIDTH[aspect]
    params = {"q": term, "video_type": "all", "per_page": 50, "key": api_key}
    url = f"{PIXABAY_VIDEO_API}?{urlencode(params)}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"Video search failed for '{term}': {e}")
        return []

    results = []
    for v in data.get("hits", []):
        dur = v.get("duration", 0)
        if dur < min_duration:
            continue
        if max_duration is not None and dur > max_duration:
            continue
        for quality in ("large", "medium", "small", "tiny"):
            vf = v.get("videos", {}).get(quality, {})
            if int(vf.get("width", 0)) >= min_w:
                results.append({
                    "url": vf["url"],
                    "duration": dur,
                    "term": term,
                })
                break
    # Sort by closeness to the ideal duration (midpoint of min/max, or just above min)
    ideal = max_duration if max_duration is not None else min_duration + 10
    results.sort(key=lambda r: abs(r["duration"] - ideal))
    return results


def download_image(url: str, output_dir: Path, term: str) -> str | None:
    """Download a single image. Returns local path or None on failure."""
    url_clean = url.split("?")[0]
    ext = ".jpg"
    for candidate in (".png", ".webp", ".jpeg", ".jpg"):
        if candidate in url_clean.lower():
            ext = candidate
            break
    filename = f"pixabay-{term[:20].replace(' ', '-')}-{md5(url_clean)}{ext}"
    dest = output_dir / filename

    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)

    try:
        resp = requests.get(url, timeout=(60, 120), stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        if dest.stat().st_size > 0:
            return str(dest)
    except Exception as e:
        log(f"Download failed: {e}")
        if dest.exists():
            dest.unlink()
    return None


def download_video(url: str, output_dir: Path, term: str) -> str | None:
    """Download a single clip. Returns local path or None on failure."""
    url_clean = url.split("?")[0]
    filename = f"pixabay-{term[:20].replace(' ', '-')}-{md5(url_clean)}.mp4"
    dest = output_dir / filename

    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)

    try:
        resp = requests.get(url, timeout=(60, 240), stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        if dest.stat().st_size > 0:
            return str(dest)
    except Exception as e:
        log(f"Download failed: {e}")
        if dest.exists():
            dest.unlink()
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Search and download Pixabay images / video clips")
    parser.add_argument("--terms", required=True)
    parser.add_argument("--type", default="video", choices=["image", "video"],
                        help="Media type: image or video (default: video)")
    parser.add_argument("--aspect", default="9:16",
                        choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--min-duration", type=int, default=5,
                        help="Minimum video clip duration in seconds (video only, default: 5)")
    parser.add_argument("--max-duration", type=int, default=None,
                        help="Maximum video clip duration in seconds (video only). Clips exceeding this are filtered out.")
    parser.add_argument("--max-clips", type=int, default=1,
                        help="Maximum total files to download (default: 1 for video, 15 for image)")
    args = parser.parse_args()

    api_key = require_env("PIXABAY_API_KEY")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # For video, enforce max-clips=1 to prevent batch downloads
    effective_max_clips = 1 if args.type == "video" else min(args.max_clips, 15)

    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    media_type: str = args.type
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    if media_type == "image":
        for term in terms:
            log(f"Searching Pixabay photos: '{term}' ({args.aspect})")
            items = search_pixabay_photos(term, args.aspect, api_key)
            log(f"  Found {len(items)} candidate images")
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)
            time.sleep(0.5)
    else:
        for term in terms:
            log(f"Searching Pixabay videos: '{term}' ({args.aspect})")
            items = search_pixabay_videos(term, args.aspect, args.min_duration, args.max_duration, api_key)
            log(f"  Found {len(items)} candidate clips")
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)
            time.sleep(0.5)

    downloaded: list[str] = []
    for item in all_results:
        if len(downloaded) >= effective_max_clips:
            break
        label = item.get("term", "")
        if media_type == "image":
            log(f"Downloading image for '{label}'...")
            path = download_image(item["url"], output_dir, label)
        else:
            dur = item.get("duration", "?")
            log(f"Downloading clip for '{label}' ({dur}s)...")
            path = download_video(item["url"], output_dir, label)
        if path:
            downloaded.append(path)
            log(f"  Saved: {Path(path).name}")
        time.sleep(0.3)

    field = "images" if media_type == "image" else "clips"
    label = "images" if media_type == "image" else "clips"
    print(f"\n✅ Downloaded {len(downloaded)} {label} to {args.output_dir}")
    print("\n__RESULT_JSON__")
    print(json.dumps({
        "ok": True,
        field: downloaded,
        "total": len(downloaded),
        "output_dir": str(output_dir.resolve()),
    }, ensure_ascii=False))

    if not downloaded:
        sys.exit(1)


if __name__ == "__main__":
    main()
