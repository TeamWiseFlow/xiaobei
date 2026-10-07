#!/usr/bin/env python3
"""Bounded collection and downloads through the independent Douyin API session."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urljoin
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from douyin_utils.api import ENDPOINTS, call, collect, item_id
from douyin_utils.http import DouyinRequestError

READ_METHODS = {
    k: v
    for k, v in ENDPOINTS.items()
    if not v.get("write") and not v.get("sensitive") and v["profile"] == "web"
}


def normalize(raw):
    def media(v):
        return next(
            (s for s in (v or {}).get("url_list", []) if isinstance(s, str) and s), ""
        )

    video = raw.get("video") or {}
    images = [media(i) for i in (raw.get("images") or [])]
    images = [i for i in images if i]
    stats = raw.get("statistics") or {}
    metrics = {
        out: stats[src]
        for src, out in {
            "digg_count": "likes",
            "comment_count": "comments",
            "share_count": "shares",
            "collect_count": "favorites",
        }.items()
        if isinstance(stats.get(src), (int, float)) and stats[src] >= 0
    }
    author = raw.get("author") or {}
    return {
        "content_id": str(raw.get("aweme_id", "")),
        "kind": "note" if images else "video",
        "title": raw.get("desc", ""),
        "desc": raw.get("desc", ""),
        "author": {
            "uid": str(author.get("uid_str") or author.get("uid") or ""),
            "sec_uid": author.get("sec_uid", ""),
            "nickname": author.get("nickname", ""),
            "signature": author.get("signature", ""),
        },
        "create_time": raw.get("create_time"),
        "metrics": metrics,
        "video_url": media(video.get("play_addr_h264") or video.get("play_addr")),
        "images": images,
        "cover_url": media(video.get("cover")),
        "duration_ms": video.get("duration"),
        "width": video.get("width"),
        "height": video.get("height"),
        "hashtags": [
            e["hashtag_name"]
            for e in (raw.get("text_extra") or [])
            if e.get("hashtag_name")
        ],
    }


def download(url, target):
    def check(value):
        p = urlsplit(value)
        if (
            p.scheme != "https"
            or p.port not in (None, 443)
            or p.username
            or p.password
            or not any(
                (p.hostname or "").endswith("." + d) or p.hostname == d
                for d in (
                    "douyinvod.com",
                    "douyin.com",
                    "byteimg.com",
                    "ibytedtos.com",
                    "pstatp.com",
                    "snssdk.com",
                    "bytecdn.cn",
                    "bytedance.com",
                )
            )
        ):
            raise ValueError("MEDIA_HOST_REJECTED")

    current = url
    for _ in range(5):
        check(current)
        response = requests.get(
            current,
            headers={"Referer": "https://www.douyin.com/"},
            timeout=120,
            allow_redirects=False,
            stream=True,
        )
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("MEDIA_REDIRECT_MISSING")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            response.close()
            raise ValueError("MEDIA_DOWNLOAD_FAILED")
        break
    else:
        raise ValueError("MEDIA_TOO_MANY_REDIRECTS")
    written = 0
    try:
        with target.open("xb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                written += len(chunk)
                if written > 2 * 1024**3:
                    raise ValueError("MEDIA_TOO_LARGE")
                stream.write(chunk)
        if not written:
            raise ValueError("MEDIA_EMPTY")
    except Exception:
        if written:
            target.unlink(missing_ok=True)
        raise
    finally:
        response.close()


def main():
    p = argparse.ArgumentParser(prog="douyin-hunter")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("methods")
    for name in ("call", "collect"):
        s = sub.add_parser(name)
        s.add_argument("method", choices=READ_METHODS)
        s.add_argument("--params", default="{}")
        s.add_argument("--count", type=int, default=20)
        s.add_argument("--output-dir")
    s = sub.add_parser("fetch")
    s.add_argument("--url")
    s.add_argument("--id")
    s.add_argument("--output-dir")
    s.add_argument("--download-media", action="store_true")
    s = sub.add_parser("comments")
    s.add_argument("--url")
    s.add_argument("--id")
    s.add_argument("--count", type=int, default=20)
    s.add_argument("--output")
    s.add_argument("--comment-id")
    s = sub.add_parser("user-posts")
    s.add_argument("--user", required=True)
    s.add_argument("--count", type=int, default=20)
    s = sub.add_parser("search")
    s.add_argument(
        "--type", choices=("video", "general", "user", "live"), default="video"
    )
    s.add_argument("--keyword", required=True)
    s.add_argument("--count", type=int, default=20)
    s.add_argument("--sort-type", default="0")
    s.add_argument("--publish-time", default="0")
    a = p.parse_args()
    if a.command == "methods":
        return {"ok": True, "methods": READ_METHODS}
    if a.command == "check":
        data = call("self")
        user = data.get("user") or data.get("user_info")
        if not isinstance(user, dict) or not user.get("uid"):
            raise DouyinRequestError("SELF_PROFILE_MISSING")
        return {
            "ok": True,
            "uid": str(user["uid"]),
            "nickname": user.get("nickname", ""),
        }
    if a.command in ("call", "collect"):
        params = json.loads(a.params)
        if not isinstance(params, dict):
            raise ValueError("PARAMS_OBJECT_REQUIRED")
        result = (
            {"ok": True, "data": call(a.method, params)}
            if a.command == "call"
            else collect(a.method, params, a.count)
        )
        if a.output_dir:
            d = Path(a.output_dir).expanduser().resolve()
            d.mkdir(parents=True, exist_ok=True)
            (d / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
        return result
    if a.command == "fetch":
        if a.download_media and not a.output_dir:
            raise ValueError("OUTPUT_DIR_REQUIRED")
        raw = call("detail", {"aweme_id": item_id(a.id or a.url or "")}).get(
            "aweme_detail"
        )
        if not isinstance(raw, dict) or not raw.get("aweme_id"):
            raise DouyinRequestError("ITEM_DETAIL_MISSING")
        note = normalize(raw)
        paths = []
        if a.output_dir:
            d = Path(a.output_dir).expanduser().resolve()
            d.mkdir(parents=True, exist_ok=True)
            (d / "note.json").write_text(json.dumps(note, ensure_ascii=False, indent=2))
            if a.download_media:
                files = (
                    [(u, f"image-{i:02}.jpg") for i, u in enumerate(note["images"], 1)]
                    if note["kind"] == "note"
                    else [(note["video_url"], "video.mp4")]
                )
                if not files or any(not u for u, _ in files):
                    raise ValueError("MEDIA_URL_MISSING")
                for u, name in files:
                    download(u, d / name)
                    paths.append(str(d / name))
        return {"ok": True, "note": note, "media_paths": paths}
    if a.command == "comments":
        ident = item_id(a.id or a.url or "")
        result = collect(
            "replies" if a.comment_id else "comments",
            {"item_id": ident, "comment_id": a.comment_id}
            if a.comment_id
            else {"aweme_id": ident},
            a.count,
        )
        if a.output:
            Path(a.output).expanduser().write_text(
                json.dumps(result, ensure_ascii=False, indent=2)
            )
        return result
    if a.command == "user-posts":
        return collect(
            "user_posts",
            {"sec_user_id": a.user.split("/user/")[-1].split("?")[0]},
            a.count,
        )
    return collect(
        {
            "video": "search_video",
            "general": "search_general",
            "user": "search_users",
            "live": "search_live",
        }[a.type],
        {
            "keyword": a.keyword,
            **(
                {"sort_type": a.sort_type, "publish_time": a.publish_time}
                if a.type == "video"
                else {}
            ),
        },
        a.count,
    )


if __name__ == "__main__":
    try:
        result = main()
        print(json.dumps(result, ensure_ascii=False))
    except (DouyinRequestError, ValueError, OSError) as e:
        code = (
            e.code
            if isinstance(e, DouyinRequestError)
            else str(e)
            if isinstance(e, ValueError) and str(e).isupper()
            else "CLIENT_INPUT_ERROR"
        )
        print(json.dumps({"ok": False, "error": code}))
        sys.exit(
            2
            if code
            in (
                "API_SESSION_MISSING",
                "API_SESSION_EXPIRED",
                "PLATFORM_LOGIN_REJECTED",
                "PLATFORM_AUTH_REJECTED",
            )
            else 1
        )
