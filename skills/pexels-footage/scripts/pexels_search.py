#!/usr/bin/env python3
"""
pexels_search.py — Search and download copyright-free images / video clips from Pexels.

Environment Variables:
  PEXELS_API_KEY   Pexels API key (required, register free at pexels.com/api)

Usage:
  python3 pexels_search.py --terms "sunset,ocean waves" --aspect 9:16 --output-dir ./footage
  python3 pexels_search.py --terms "business,technology" --type image --aspect 16:9 --output-dir ./images
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

PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_API = "https://api.pexels.com/v1/search"

ASPECT_RESOLUTIONS = {
    "9:16":  (1080, 1920),
    "16:9":  (1920, 1080),
    "1:1":   (1080, 1080),
}

ORIENTATION_MAP = {
    "9:16":  "portrait",
    "16:9":  "landscape",
    "1:1":   "square",
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


def search_pexels_photos(term: str, aspect: str, api_key: str) -> list[dict]:
    """Search Pexels for photos matching term and orientation."""
    orientation = ORIENTATION_MAP[aspect]
    params = {"query": term, "per_page": 20, "orientation": orientation}
    url = f"{PEXELS_PHOTO_API}?{urlencode(params)}"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": api_key, "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"Photo search failed for '{term}': {e}")
        return []

    results = []
    for photo in data.get("photos", []):
        src = photo.get("src", {})
        # Prefer large2x for quality, fall back through size chain
        img_url = src.get("large2x") or src.get("large") or src.get("original") or ""
        if img_url:
            results.append({
                "url": img_url,
                "term": term,
                "photographer": photo.get("photographer", ""),
                "alt": photo.get("alt", ""),
                "width": photo.get("width", 0),
                "height": photo.get("height", 0),
            })
    return results


def search_pexels_videos(term: str, aspect: str, min_duration: int, max_duration: int | None, api_key: str) -> list[dict]:
    """Search Pexels for video clips matching term and aspect ratio."""
    w, h = ASPECT_RESOLUTIONS[aspect]
    orientation = ORIENTATION_MAP[aspect]

    params = {"query": term, "per_page": 20, "orientation": orientation}
    url = f"{PEXELS_VIDEO_API}?{urlencode(params)}"

    try:
        resp = requests.get(
            url,
            headers={"Authorization": api_key, "User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log(f"Video search failed for '{term}': {e}")
        return []

    results = []
    for v in data.get("videos", []):
        dur = v.get("duration", 0)
        if dur < min_duration:
            continue
        if max_duration is not None and dur > max_duration:
            continue
        for vf in v.get("video_files", []):
            if int(vf.get("width", 0)) == w and int(vf.get("height", 0)) == h:
                results.append({
                    "url": vf["link"],
                    "duration": dur,
                    "term": term,
                })
                break
    # Sort by closeness to the ideal duration
    ideal = max_duration if max_duration is not None else min_duration + 10
    results.sort(key=lambda r: abs(r["duration"] - ideal))
    return results


def download_image(url: str, output_dir: Path, term: str) -> str | None:
    """Download a single image. Returns local path or None on failure."""
    url_clean = url.split("?")[0]
    # Determine extension from URL or default to jpg
    ext = ".jpg"
    for candidate in (".png", ".webp", ".jpeg", ".jpg"):
        if candidate in url_clean.lower():
            ext = candidate
            break
    filename = f"pexels-{term[:20].replace(' ', '-')}-{md5(url_clean)}{ext}"
    dest = output_dir / filename

    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(60, 120),
            stream=True,
        )
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
    """Download a single video clip. Returns local path or None on failure."""
    url_clean = url.split("?")[0]
    filename = f"pexels-{term[:20].replace(' ', '-')}-{md5(url_clean)}.mp4"
    dest = output_dir / filename

    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=(60, 240),
            stream=True,
        )
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
    parser = argparse.ArgumentParser(description="Search and download Pexels images / video clips")
    parser.add_argument("--terms", required=True,
                        help="Comma-separated search terms (one per scene)")
    parser.add_argument("--type", default="video", choices=["image", "video"],
                        help="Media type: image or video (default: video)")
    parser.add_argument("--aspect", default="9:16",
                        choices=list(ASPECT_RESOLUTIONS.keys()),
                        help="Aspect ratio (default: 9:16)")
    parser.add_argument("--output-dir", required=True,
                        help="Directory to save downloaded files")
    parser.add_argument("--min-duration", type=int, default=5,
                        help="Minimum video clip duration in seconds (video only, default: 5)")
    parser.add_argument("--max-duration", type=int, default=None,
                        help="Maximum video clip duration in seconds (video only). Clips exceeding this are filtered out.")
    parser.add_argument("--max-clips", type=int, default=1,
                        help="Maximum total files to download (default: 1 for video, 15 for image)")
    args = parser.parse_args()

    api_key = require_env("PEXELS_API_KEY")
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
            log(f"Searching Pexels photos: '{term}' ({args.aspect})")
            items = search_pexels_photos(term, args.aspect, api_key)
            log(f"  Found {len(items)} candidate images")
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)
            time.sleep(0.3)
    else:
        for term in terms:
            log(f"Searching Pexels videos: '{term}' ({args.aspect})")
            items = search_pexels_videos(term, args.aspect, args.min_duration, args.max_duration, api_key)
            log(f"  Found {len(items)} candidate clips")
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)
            time.sleep(0.3)

    # Download up to max-clips
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
        time.sleep(0.2)

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
