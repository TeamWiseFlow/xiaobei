#!/usr/bin/env python3
"""Publish notes to Xiaohongshu via creator COS upload + web_api v2 note creation.

Based on AiToEarn's XiaohongshuService (v2.4.0):
- Upload: creator.xiaohongshu.com/api/media/v1/upload/web/permit → COS PUT
- Note creation: edith.xiaohongshu.com/web_api/sns/v2/note
- Signing: 走 relay sign 服务
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

# relay_sign 在 skills/_shared/，本脚本在 skills/xhs-publish/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "_shared"))
from relay_sign import xhs_headers  # noqa: E402

LOGINS_DIR = Path.home() / ".openclaw" / "logins"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
XHS_ORIGIN = "https://www.xiaohongshu.com"
XHS_REFERER = "https://www.xiaohongshu.com/"
CREATOR_REFERER = "https://creator.xiaohongshu.com/"
EDITH_BASE = "https://edith.xiaohongshu.com"
CREATOR_BASE = "https://creator.xiaohongshu.com"

# AiToEarn-aligned endpoints
UPLOAD_PERMIT_URL = f"{CREATOR_BASE}/api/media/v1/upload/web/permit"
CREATE_NOTE_URL = f"{EDITH_BASE}/web_api/sns/v2/note"

FILE_BLOCK_SIZE = 5 * 1024 * 1024  # 5MB chunks for video


def output(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def err_exit(msg: str, code: int = 1) -> None:
    sys.stderr.write(f"[xhs-publish] ERROR: {msg}\n")
    output({"ok": False, "error": msg})
    sys.exit(code)


def load_cookies(cookie_file: Path | None = None) -> tuple[dict, str]:
    """Load cookies + UA from central store.

    中央存储格式（forked camoufox-cli 原生输出，= Playwright add_cookies 期望格式）：
      ~/.openclaw/logins/xhs-publish.json     → { platform, cookies: [{name, value, domain, ...}], updated_at }
      ~/.openclaw/logins/xhs-publish.ua.json  → { userAgent, platform, language, ... }
    同时导入 cookie 和 UA——同一指纹下的 cookie 才不会被风控错配。
    """
    p = cookie_file or (LOGINS_DIR / "xhs-publish.json")
    if not p.exists():
        err_exit("AUTH_EXPIRED", 2)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError:
        err_exit("AUTH_EXPIRED", 2)

    # 兼容两种格式：{platform, cookies:[...], updated_at} 包壳（login-and-verify 写）
    # 或 camoufox-cli 原生裸数组 [{name, value, domain, ...}]（直接 cookies export 输出）
    raw = data.get("cookies", "") if isinstance(data, dict) else data
    cookie_dict: dict[str, str] = {}
    if isinstance(raw, list):
        for c in raw:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            value = c.get("value")
            if name and isinstance(value, str):
                cookie_dict[name.strip()] = value.strip()
    elif isinstance(raw, str) and raw:
        # 向后兼容：旧格式字符串 "k1=v1; k2=v2"
        for item in raw.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookie_dict[k.strip()] = v.strip()

    if not cookie_dict:
        err_exit("AUTH_EXPIRED", 2)

    # UA 走独立文件（forked cli identity export 输出，与 cookies export 对称）
    ua_path = p.parent / (p.stem + ".ua.json")
    ua = DEFAULT_UA
    if ua_path.exists():
        try:
            ua_data = json.loads(ua_path.read_text())
            ua = ua_data.get("userAgent") or DEFAULT_UA
        except (json.JSONDecodeError, OSError):
            pass  # UA 文件读失败不阻断，回退 DEFAULT_UA

    # 创作者域会话字段门（xhs-publish cookie 是 creator.xiaohongshu.com 域，无 web_session）：
    # a1（设备指纹）+ 任一创作者会话 token。与 creator-session.ts presenceCheckCreator 对齐。
    # 探活（personal_info pong）由 xhs-publish check-login.ts 在发布前做，此处只做 cheap 字段门。
    CREATOR_SESSION_KEYS = (
        "galaxy_creator_session_id",
        "galaxy.creator.beaker.session.id",
        "access-token-creator.xiaohongshu.com",
        "customer-sso-sid",
    )
    if "a1" not in cookie_dict or not any(k in cookie_dict for k in CREATOR_SESSION_KEYS):
        err_exit("AUTH_EXPIRED", 2)

    return cookie_dict, ua


def cookie_str(cookie_dict: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookie_dict.items())


def extract_topics(body: str, extra_topics: list[str] | None = None) -> list[dict]:
    """Extract #话题 from body text, return AiToEarn-format hash_tag list."""
    tags = []
    seen = set()
    for m in re.finditer(r"#([^#\s]+)", body):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            tags.append({"id": "", "name": name, "type": "topic"})
    if extra_topics:
        for t in extra_topics:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                tags.append({"id": "", "name": t, "type": "topic"})
    return tags


# ---------------------------------------------------------------------------
# COS Upload Flow (AiToEarn-aligned)
# ---------------------------------------------------------------------------

def get_upload_permit(cookie_dict: dict, ua: str, scene: str) -> dict:
    """Get COS upload permit from creator API.

    scene: 'image' or 'video'
    Returns: uploadTempPermits[0] with fileIds, uploadAddr, token
    """
    url = f"{UPLOAD_PERMIT_URL}?biz_name=spectrum&scene={scene}&file_count=1&version=1&source=web"
    headers = {
        "User-Agent": ua,
        "Cookie": cookie_str(cookie_dict),
        "Referer": CREATOR_REFERER,
    }
    resp = requests.get(url, headers=headers, timeout=30)

    if resp.status_code in (401, 403):
        err_exit("AUTH_EXPIRED: creator API auth failed (need creator.xiaohongshu.com cookies)", 2)

    try:
        data = resp.json()
    except Exception:
        err_exit(f"UPLOAD_FAILED: permit API non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}")

    if data.get("code") != 0:
        err_exit(f"UPLOAD_FAILED: permit API error: {data.get('msg', data)}")

    permits = data.get("data", {}).get("uploadTempPermits", [])
    if not permits:
        err_exit(f"UPLOAD_FAILED: no uploadTempPermits in response: {data}")

    return permits[0]


def cos_upload_file(
    upload_addr: str, file_id: str, token: str,
    file_content: bytes, content_type: str | None = None,
    ua: str = "",
) -> dict:
    """PUT file to COS object storage.

    Returns: dict with response headers (x-ros-preview-url, x-ros-video-id, etc.)
    """
    upload_url = f"https://{upload_addr}/{file_id}"
    headers = {
        "Referer": CREATOR_REFERER,
        "X-Cos-Security-Token": token,
    }
    if content_type:
        headers["Content-Type"] = content_type

    resp = requests.put(upload_url, headers=headers, data=file_content, timeout=300)

    if resp.status_code not in (200, 201):
        err_exit(f"UPLOAD_FAILED: COS PUT HTTP {resp.status_code}: {resp.text[:200]}")

    return dict(resp.headers)


def cos_upload_file_chunked(
    upload_addr: str, file_id: str, token: str,
    file_path: str, content_type: str,
    ua: str = "",
) -> dict:
    """Upload large file to COS with chunking (for video > 5MB).

    Returns: dict with response headers.
    """
    upload_base = f"https://{upload_addr}/{file_id}"
    file_size = os.path.getsize(file_path)

    # Calculate chunk boundaries
    chunks = []
    offset = 0
    while offset < file_size:
        end = min(offset + FILE_BLOCK_SIZE, file_size)
        chunks.append((offset, end))
        offset = end

    if len(chunks) == 1:
        # Single chunk - direct upload
        with open(file_path, "rb") as f:
            content = f.read()
        return cos_upload_file(upload_addr, file_id, token, content, content_type, ua)

    # Multi-part upload
    # Step 1: Initiate multipart upload
    init_headers = {
        "Content-Type": content_type,
        "Referer": CREATOR_REFERER,
        "X-Cos-Security-Token": token,
    }
    init_resp = requests.post(f"{upload_base}?uploads", headers=init_headers, timeout=30)
    if init_resp.status_code not in (200, 201):
        # If response is JSON, it's an error; if XML, it's the upload ID
        try:
            err_data = init_resp.json()
            err_exit(f"UPLOAD_FAILED: multipart init error: {err_data.get('msg', err_data)}")
        except Exception:
            pass

    # Parse UploadId from XML response
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(init_resp.text)
        # Handle namespace
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"
        upload_id = root.find(f"{ns}UploadId").text
    except Exception:
        err_exit(f"UPLOAD_FAILED: cannot parse UploadId from init response: {init_resp.text[:200]}")

    if not upload_id:
        err_exit("UPLOAD_FAILED: empty UploadId")

    # Step 2: Upload parts
    part_info = []
    for i, (start, end) in enumerate(chunks):
        with open(file_path, "rb") as f:
            f.seek(start)
            chunk_data = f.read(end - start)

        part_url = f"{upload_base}?uploadId={upload_id}&partNumber={i + 1}"
        part_headers = {
            "Referer": CREATOR_REFERER,
            "X-Cos-Security-Token": token,
        }
        part_resp = requests.put(part_url, headers=part_headers, data=chunk_data, timeout=120)

        etag = part_resp.headers.get("etag", "")
        if not etag:
            err_exit(f"UPLOAD_FAILED: part {i + 1} upload failed (no etag)")

        part_info.append({"Part": {"PartNumber": i + 1, "ETag": etag}})
        sys.stderr.write(f"[xhs-publish] uploaded part {i + 1}/{len(chunks)}\n")

    # Step 3: Complete multipart upload
    # Build XML body
    parts_xml_parts = []
    for p in part_info:
        parts_xml_parts.append(
            f"<Part><PartNumber>{p['Part']['PartNumber']}</PartNumber>"
            f"<ETag>{p['Part']['ETag']}</ETag></Part>"
        )
    complete_xml = f"<CompleteMultipartUpload>{''.join(parts_xml_parts)}</CompleteMultipartUpload>"

    complete_headers = {
        "Referer": CREATOR_REFERER,
        "X-Cos-Security-Token": token,
        "Content-Type": "application/xml",
    }
    complete_resp = requests.post(
        f"{upload_base}?uploadId={upload_id}",
        headers=complete_headers, data=complete_xml, timeout=30,
    )

    if complete_resp.status_code not in (200, 201):
        try:
            err_data = complete_resp.json()
            err_exit(f"UPLOAD_FAILED: multipart complete error: {err_data.get('msg', err_data)}")
        except Exception:
            err_exit(f"UPLOAD_FAILED: multipart complete HTTP {complete_resp.status_code}")

    return dict(complete_resp.headers)


def upload_image_cos(cookie_dict: dict, ua: str, image_path: str) -> dict:
    """Upload image via COS permit flow. Returns {file_id, width, height, preview_url, type}."""
    if not os.path.exists(image_path):
        err_exit(f"UPLOAD_FAILED: image not found: {image_path}")

    # Get upload permit
    permit = get_upload_permit(cookie_dict, ua, "image")
    file_id = permit.get("fileIds", [""])[0]
    upload_addr = permit.get("uploadAddr", "")
    token = permit.get("token", "")

    if not file_id or not upload_addr:
        err_exit(f"UPLOAD_FAILED: invalid permit response: {permit}")

    # Read file and get dimensions
    file_content = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".") or "jpg"

    # Get image dimensions
    width, height = 0, 0
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            width, height = img.size
    except ImportError:
        # Fallback: try with image-size equivalent
        sys.stderr.write("[xhs-publish] WARNING: Pillow not installed, using default dimensions\n")
        width, height = 1080, 1440  # Default 3:4 ratio

    # Upload to COS
    result_headers = cos_upload_file(upload_addr, file_id, token, file_content, ua=ua)
    preview_url = result_headers.get("x-ros-preview-url", "")

    sys.stderr.write(f"[xhs-publish] uploaded image: {file_id} ({width}x{height})\n")

    return {
        "file_id": file_id,
        "width": width,
        "height": height,
        "preview_url": preview_url,
        "type": ext,
    }


def upload_video_cos(cookie_dict: dict, ua: str, video_path: str) -> dict:
    """Upload video via COS permit flow. Returns {file_id, video_id, preview_url}."""
    if not os.path.exists(video_path):
        err_exit(f"UPLOAD_FAILED: video not found: {video_path}")

    file_size = os.path.getsize(video_path)
    sys.stderr.write(f"[xhs-publish] preparing video upload ({file_size} bytes)...\n")

    # Get upload permit
    permit = get_upload_permit(cookie_dict, ua, "video")
    file_id = permit.get("fileIds", [""])[0]
    upload_addr = permit.get("uploadAddr", "")
    token = permit.get("token", "")

    if not file_id or not upload_addr:
        err_exit(f"UPLOAD_FAILED: invalid permit response: {permit}")

    # Upload to COS (chunked for large files)
    sys.stderr.write(f"[xhs-publish] uploading video (id={file_id})...\n")
    result_headers = cos_upload_file_chunked(
        upload_addr, file_id, token, video_path, "video/mp4", ua,
    )

    # Headers are case-insensitive in HTTP but dict() makes them case-sensitive
    video_id = ""
    preview_url = ""
    for k, v in result_headers.items():
        if k.lower() == "x-ros-video-id":
            video_id = v
        elif k.lower() == "x-ros-preview-url":
            preview_url = v

    if not video_id:
        err_exit(f"UPLOAD_FAILED: no x-ros-video-id in COS response headers: {list(result_headers.keys())}")

    sys.stderr.write(f"[xhs-publish] uploaded video: {video_id}\n")

    return {
        "file_id": file_id,
        "video_id": video_id,
        "preview_url": preview_url,
    }


# ---------------------------------------------------------------------------
# Note Creation (AiToEarn-aligned /web_api/sns/v2/note)
# ---------------------------------------------------------------------------

def sign_and_request(
    client,  # unused（签名走 relay，保留参数以兼容旧调用签名）
    method: str,
    url: str,
    cookie_dict: dict,
    ua: str,
    payload: dict | None = None,
    params: dict | None = None,
    referer: str = XHS_REFERER,
    origin: str = XHS_ORIGIN,
    x_rap: bool = True,
) -> requests.Response:
    """Sign request via relay sign service and send."""
    uri = url.replace(EDITH_BASE, "")
    # relay xhs_headers 返回完整 headers（含 UA / Cookie / 签名头）
    relay_headers = xhs_headers(
        uri=uri,
        cookies=cookie_dict,
        payload=payload or {},
        params=params or {},
        method=method.lower(),
        sign_format="xys",
        x_rap=x_rap,
    )

    headers = {
        "User-Agent": ua,
        "Origin": origin,
        "Referer": referer,
        "Cookie": cookie_str(cookie_dict),
        "Content-Type": "application/json;charset=UTF-8",
    }
    # relay 返回的签名头覆盖本地默认（保留 relay 算的 x-s / x-t 等）
    headers.update({k: v for k, v in relay_headers.items() if k.lower().startswith("x-")})

    resp = requests.request(
        method, url, headers=headers, json=payload, params=params, timeout=60,
    )
    return resp


def create_note_v2(
    client,  # unused（签名走 relay）
    cookie_dict: dict,
    ua: str,
    title: str,
    body: str,
    note_type: str,  # "normal" (image) or "video"
    image_infos: list[dict] | None = None,
    video_info: dict | None = None,
    hash_tag: list[dict] | None = None,
    is_private: bool = False,
) -> dict:
    """Create note via /web_api/sns/v2/note (AiToEarn-aligned format)."""
    visibility_type = 1 if is_private else 0

    # Build image_info (AiToEarn format)
    xhs_image_info = None
    if note_type == "normal" and image_infos:
        images = []
        for img in image_infos:
            images.append({
                "file_id": img["file_id"],
                "width": img["width"],
                "height": img["height"],
                "metadata": {"source": -1},
                "stickers": {"version": 2, "floating": []},
                "extra_info_json": json.dumps({
                    "mimeType": f"image/{'jpeg' if img.get('type', 'jpg') in ('jpg', 'jpeg') else img.get('type', 'jpg')}"
                }),
            })
        xhs_image_info = {"images": images}

    # Build request data (AiToEarn-aligned structure)
    request_data = {
        "common": {
            "type": note_type,
            "title": title,
            "note_id": "",
            "desc": body,
            "source": json.dumps({
                "type": "web",
                "ids": "",
                "extraInfo": json.dumps({"subType": "", "systemId": "web"}),
            }),
            "business_binds": json.dumps({
                "version": 1,
                "noteId": 0,
                "bizType": 0,
                "noteOrderBind": {},
                "notePostTiming": {"postTime": ""},
                "noteCollectionBind": {"id": ""},
            }),
            "ats": [],
            "hash_tag": hash_tag or [],
            "post_loc": {},
            "privacy_info": {
                "op_type": 1,
                "type": visibility_type,
            },
        },
        "image_info": xhs_image_info,
        "video_info": video_info,
    }

    resp = sign_and_request(
        client, "POST", CREATE_NOTE_URL, cookie_dict, ua,
        payload=request_data, referer=CREATOR_REFERER, origin=CREATOR_REFERER,
        x_rap=False,
    )
    if resp.status_code != 200:
        sys.stderr.write(f"[xhs-publish] retrying with x_rap...\n")
        resp = sign_and_request(
            client, "POST", CREATE_NOTE_URL, cookie_dict, ua,
            payload=request_data, referer=CREATOR_REFERER, origin=CREATOR_REFERER,
            x_rap=True,
        )

    if resp.status_code in (401, 403):
        err_exit("AUTH_EXPIRED", 2)

    try:
        data = resp.json()
    except Exception:
        err_exit(f"PUBLISH_FAILED: non-JSON response (HTTP {resp.status_code}): {resp.text[:200]}")

    # Check for errors
    if data.get("code") == -1:
        err_exit("PUBLISH_FAILED: signature verification failed")
    if data.get("success") is False or (data.get("result") is not None and data.get("result") != 0):
        msg = data.get("msg", str(data))
        if "login" in msg.lower() or "登录" in msg:
            err_exit("AUTH_EXPIRED", 2)
        err_exit(f"PUBLISH_FAILED: {msg}")

    return data.get("data", {})


# ---------------------------------------------------------------------------
# High-level publish functions
# ---------------------------------------------------------------------------

def publish_image_note(
    client,  # unused（签名走 relay）
    cookie_dict: dict,
    ua: str,
    title: str,
    body: str,
    image_paths: list[str],
    topics: list[dict] | None = None,
    is_private: bool = False,
) -> dict:
    if len(title) > 20:
        title = title[:20]

    # Upload images via COS
    image_infos = []
    for img_path in image_paths:
        info = upload_image_cos(cookie_dict, ua, img_path)
        image_infos.append(info)

    # Create note
    result = create_note_v2(
        client, cookie_dict, ua, title, body, "normal",
        image_infos=image_infos, hash_tag=topics, is_private=is_private,
    )

    note_id = result.get("id", "")
    url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
    return {"ok": True, "note_id": note_id, "url": url}


def publish_video_note(
    client,  # unused（签名走 relay）
    cookie_dict: dict,
    ua: str,
    title: str,
    body: str,
    video_path: str,
    cover_path: str | None = None,
    topics: list[dict] | None = None,
    is_private: bool = False,
) -> dict:
    if len(title) > 20:
        title = title[:20]

    # Upload video via COS
    video_result = upload_video_cos(cookie_dict, ua, video_path)

    # Upload cover image via COS
    cover_info = None
    if cover_path and os.path.exists(cover_path):
        cover_info = upload_image_cos(cookie_dict, ua, cover_path)

    # Build video_info (AiToEarn-aligned structure)
    video_info = {
        "fileid": video_result["file_id"],
        "file_id": video_result["file_id"],
        "video_preview_type": "full_vertical_screen",
        "timelines": [],
        "cover": None,
        "chapters": [],
        "chapter_sync_text": False,
        "segments": {
            "count": 1,
            "need_slice": False,
            "items": [{
                "mute": 0,
                "speed": 1,
                "start": 0,
                "duration": 0,
                "transcoded": 0,
                "media_source": 1,
            }],
        },
        "entrance": "web",
        "backup_covers": [],
    }

    if cover_info:
        video_info["cover"] = {
            "fileid": cover_info["file_id"],
            "file_id": cover_info["file_id"],
            "height": cover_info["height"],
            "width": cover_info["width"],
            "frame": {
                "ts": 0,
                "is_user_select": False,
                "is_upload": True,
            },
        }

    # Create note
    result = create_note_v2(
        client, cookie_dict, ua, title, body, "video",
        video_info=video_info, hash_tag=topics, is_private=is_private,
    )

    note_id = result.get("id", "")
    url = f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""
    return {"ok": True, "note_id": note_id, "url": url}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Publish note to Xiaohongshu")
    parser.add_argument("--mode", required=True, choices=["image", "video"], help="Note type")
    parser.add_argument("--title", required=True, help="Note title (max 20 chars)")
    parser.add_argument("--body", required=True, help="Note body (max 1000 chars)")
    parser.add_argument("--images", nargs="+", help="Image paths for image mode (max 18)")
    parser.add_argument("--video", help="Video file path for video mode")
    parser.add_argument("--cover", help="Cover image path")
    parser.add_argument("--topics", nargs="*", help="Extra topic names")
    parser.add_argument("--private", action="store_true", help="Set note to private")
    parser.add_argument("--cookie-file", type=Path, help="Cookie file path")
    args = parser.parse_args()

    if len(args.title) > 20:
        err_exit("TITLE_TOO_LONG: title exceeds 20 characters")
    if len(args.body) > 1000:
        err_exit("BODY_TOO_LONG: body exceeds 1000 characters")

    try:
        cookie_dict, ua = load_cookies(args.cookie_file)
    except Exception as e:
        err_exit(f"AUTH_EXPIRED: {e}", 2)

    client = None

    topics = extract_topics(args.body, args.topics)

    if args.mode == "image":
        if not args.images:
            err_exit("--images required for image mode")
        if len(args.images) > 18:
            err_exit("Too many images (max 18)")
        result = publish_image_note(
            client, cookie_dict, ua, args.title, args.body,
            args.images, topics, args.private,
        )
    else:
        if not args.video:
            err_exit("--video required for video mode")
        result = publish_video_note(
            client, cookie_dict, ua, args.title, args.body,
            args.video, args.cover, topics, args.private,
        )

    output(result)


if __name__ == "__main__":
    main()
