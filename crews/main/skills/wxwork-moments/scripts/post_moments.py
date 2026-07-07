#!/usr/bin/env python3
"""post_moments.py — 企业微信朋友圈一键发布（经 relay 透传凭据）

用法：
  python3 post_moments.py "正文" [file1 file2 ...]
  python3 post_moments.py "正文" --link URL TITLE [cover_image]

凭据：WXWORK_CORP_ID + WXWORK_CORP_SECRET 来自 daemon.env（entrypoint 注入）。
relay：RELAY_BASE_URL + OFB_KEY 来自 daemon.env。

relay 端点：
  POST {RELAY_BASE_URL}/api/v1/wxwork/media/upload   multipart：corp_id+corp_secret+type+media
  POST {RELAY_BASE_URL}/api/v1/wxwork/moments/add    JSON：corp_id+corp_secret+业务字段
响应包络：{ success, data, error }；relay 在转发企业微信前会剥离 corp_id/corp_secret。
"""

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_RELAY_BASE_URL = "https://relay.openclaw-for-business.com"
IMAGE_MAX_DIM = 1248
RESIZE_TARGET = 1200


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(f">>> {msg}", flush=True)


# ── env ──────────────────────────────────────────────────────────────────────

def load_env() -> tuple[str, str, str, str]:
    corp_id = os.environ.get("WXWORK_CORP_ID", "").strip()
    corp_secret = os.environ.get("WXWORK_CORP_SECRET", "").strip()
    relay = os.environ.get("RELAY_BASE_URL", "").rstrip("/") or DEFAULT_RELAY_BASE_URL
    ofb_key = os.environ.get("OFB_KEY", "").strip()
    if not corp_id or not corp_secret:
        die(
            "WXWORK_CORP_ID / WXWORK_CORP_SECRET 未配置（daemon.env）。\n"
            "  → 请让 Agent 按 REFERENCE.md 引导你获取企业 ID + corp_secret，\n"
            "    再由 IT engineer 写入 daemon.env 并重启实例。"
        )
    if not ofb_key:
        die("OFB_KEY 未配置。OFB_KEY 是 VIP Club 会员凭证，由 ofb 掌柜签发——请向 ofb 掌柜索取该 key，交由 IT engineer 写入 daemon.env 后重启实例。")
    return corp_id, corp_secret, relay, ofb_key


# ── HTTP ─────────────────────────────────────────────────────────────────────

def http_post_multipart(url: str, fields: dict, files: dict, headers: dict | None = None, timeout: int = 120) -> dict:
    import uuid
    boundary = uuid.uuid4().hex
    parts = []
    for key, val in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{val}\r\n".encode())
    for field_name, (filename, filepath) in files.items():
        with open(filepath, "rb") as f:
            file_data = f.read()
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field_name}\"; filename=\"{filename}\"\r\n\r\n".encode()
            + file_data + b"\r\n"
        )
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    hdrs = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ── 辅助 ─────────────────────────────────────────────────────────────────────

def fetch_og_image(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
        if not m:
            m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
        return m.group(1) if m else None
    except Exception:
        return None


def download_file(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=10).read()
        Path(dest).write_bytes(data)
        return True
    except Exception:
        return False


def auto_resize_image(filepath: str) -> str:
    try:
        from PIL import Image
    except ImportError:
        return filepath
    img = Image.open(filepath)
    w, h = img.size
    if w < IMAGE_MAX_DIM or h < IMAGE_MAX_DIM:
        return filepath
    ratio = RESIZE_TARGET / max(w, h)
    nw, nh = int(w * ratio), int(h * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - RESIZE_TARGET) // 2
    top = (nh - RESIZE_TARGET) // 2
    img = img.crop((left, top, left + RESIZE_TARGET, top + RESIZE_TARGET))
    tmp = tempfile.NamedTemporaryFile(prefix="_wx_auto_resize_", suffix=".jpg", delete=False)
    tmp.close()
    img.save(tmp.name, "JPEG", quality=92, optimize=True)
    return tmp.name


def unwrap(resp: dict) -> dict:
    """容忍两种返回：flat `{ ok, ... }` 或包络 `{ success, data, error }`。"""
    if "success" in resp:
        if not resp.get("success"):
            die(f"relay 失败: {resp.get('error') or resp}")
        return resp.get("data") or {}
    return resp


def upload_media(filepath: str, media_type: str, relay: str, ofb_key: str, corp_id: str, corp_secret: str) -> str:
    filename = Path(filepath).name
    url = f"{relay}/api/v1/wxwork/media/upload"
    try:
        result = http_post_multipart(
            url,
            {"corp_id": corp_id, "corp_secret": corp_secret, "type": media_type},
            {"media": (filename, filepath)},
            headers={"X-OFB-Key": ofb_key},
        )
    except urllib.error.HTTPError as e:
        die(f"上传失败 HTTP {e.code}: {e.read().decode(errors='replace')}")
    data = unwrap(result)
    if not data.get("ok") or "media_id" not in data:
        die(f"上传失败: {result}")
    return data["media_id"]


# ── 主流程 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="企业微信朋友圈发布（经 relay）")
    parser.add_argument("text", help="朋友圈正文")
    parser.add_argument("files", nargs="*", help="图片/视频文件路径")
    parser.add_argument("--link", nargs=3, metavar=("URL", "TITLE", "COVER"), help="图文链接模式：URL 标题 [封面图]")
    args = parser.parse_args()

    text = args.text.replace("\n", "\\n").replace("\r", "")

    media_files = list(args.files) if args.files else []
    link_mode = args.link is not None
    link_url = args.link[0] if args.link else ""
    link_title = args.link[1] if args.link else ""
    link_cover = args.link[2] if args.link and len(args.link) > 2 and args.link[2] else None

    if link_cover:
        media_files = [link_cover]

    has_video = any(Path(f).suffix.lower() in {".mp4", ".mov", ".avi", ".wmv"} for f in media_files)
    if not link_mode and has_video and len(media_files) > 1:
        die("视频只能上传 1 个")
    if not link_mode and not has_video and len(media_files) > 9:
        die(f"图片最多 9 张，当前 {len(media_files)} 张")

    corp_id, corp_secret, relay, ofb_key = load_env()
    log("模式: relay")

    if link_mode and not media_files:
        log("未提供封面图，尝试从链接抓取 og:image...")
        og_url = fetch_og_image(link_url)
        if og_url:
            log(f"  og:image: {og_url}")
            og_tmp = tempfile.mktemp(suffix=".jpg")
            if download_file(og_url, og_tmp):
                media_files = [og_tmp]
                log("  封面图已下载")
            else:
                die("封面图下载失败。企业微信 link 类附件必须提供封面图")
        else:
            die("链接未包含 og:image，无法自动获取封面图。请手动指定：--link URL TITLE /path/to/cover.jpg")

    media_ids: list[str] = []
    media_type = ""
    for filepath in media_files:
        if not Path(filepath).is_file():
            die(f"文件不存在: {filepath}")
        ext = Path(filepath).suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".gif"}:
            ftype = "image"
        elif ext in {".mp4", ".mov", ".avi", ".wmv"}:
            ftype = "video"
        else:
            die(f"不支持的文件类型: {filepath}")
        media_type = ftype
        log(f"上传 {ftype}: {filepath}")
        upload_path = filepath
        if ftype == "image":
            upload_path = auto_resize_image(filepath)
            if upload_path != filepath:
                log("  ⚠ 原始分辨率超标，已自动缩放到 1200x1200")
        mid = upload_media(upload_path, ftype, relay, ofb_key, corp_id, corp_secret)
        log(f"  media_id: {mid}")
        media_ids.append(mid)

    payload: dict = {
        "corp_id": corp_id,
        "corp_secret": corp_secret,
        "text": {"content": text},
    }
    if link_mode:
        link_obj: dict = {"title": link_title, "url": link_url}
        if media_ids:
            link_obj["media_id"] = media_ids[0]
        payload["attachments"] = [{"msgtype": "link", "link": link_obj}]
    elif media_ids:
        if media_type == "video":
            payload["attachments"] = [{"msgtype": "video", "video": {"media_id": media_ids[0]}}]
        else:
            payload["attachments"] = [
                {"msgtype": "image", "image": {"media_id": mid}} for mid in media_ids
            ]

    log("发布朋友圈...")
    try:
        result = http_post_json(
            f"{relay}/api/v1/wxwork/moments/add",
            payload,
            headers={"X-OFB-Key": ofb_key},
        )
    except urllib.error.HTTPError as e:
        die(f"发布失败 HTTP {e.code}: {e.read().decode(errors='replace')}")

    data = unwrap(result)
    if not data.get("ok"):
        die(f"✗ 发布失败: {result}")

    print("✓ 发布成功")
    mid = data.get("moment_id") or data.get("jobid")
    if mid:
        print(f"  moment_id: {mid}")


if __name__ == "__main__":
    main()
