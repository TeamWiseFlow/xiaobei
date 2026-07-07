#!/usr/bin/env python3
"""Publish videos to Bilibili via relay proxy (Phase 3.1 — D1 全 proxy).

依赖：
- 用户环境变量 `RELAY_BASE_URL`（默认 `https://relay.wiseflow.example.com`，entrypoint 注入）
- 用户环境变量 `OFB_KEY`（产品方发放）
- Python 3 stdlib（urllib / email / mimetypes）
- 无第三方依赖
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from email.generator import BytesGenerator
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from io import BytesIO
from pathlib import Path
from typing import Optional

# ── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_RELAY_BASE_URL = "https://relay.wiseflow.example.com"
RELAY_ENDPOINT = "/api/v1/publish/bilibili/submit"
REQUEST_TIMEOUT_S = 600  # 上传视频可能慢（10 分钟级）
MAX_TITLE_LEN = 80
MAX_TAGS = 10
MAX_TAG_LEN = 20


# ── env 校验 ────────────────────────────────────────────────────────────────

def require_env() -> tuple[str, str]:
    """校验必需的环境变量：RELAY_BASE_URL + OFB_KEY。"""
    relay = os.environ.get("RELAY_BASE_URL", "").rstrip("/")
    ofb_key = os.environ.get("OFB_KEY", "")
    if not relay:
        sys.stderr.write("[bilibili-publish] ERROR: RELAY_BASE_URL not set\n")
        sys.exit(2)
    if not ofb_key:
        sys.stderr.write(
            "[bilibili-publish] ERROR: OFB_KEY 未配置。OFB_KEY 是 VIP Club 会员凭证，"
            "由 ofb 掌柜签发——请向 ofb 掌柜索取该 key，交由 IT engineer 写入 "
            "daemon.env 后重启实例。\n"
        )
        sys.exit(2)
    return relay, ofb_key


# ── Multipart 构建 ─────────────────────────────────────────────────────────

def _add_text_field(mp: MIMEMultipart, name: str, value: str) -> None:
    field = MIMEText(value, "plain", "utf-8")
    field.add_header("Content-Disposition", "form-data", name=name)
    mp.attach(field)


def _add_file_field(mp: MIMEMultipart, name: str, path: Path) -> None:
    """添加文件字段。Content-Type 由 mimetypes 推断。"""
    import mimetypes
    ctype, _ = mimetypes.guess_type(str(path))
    if ctype is None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split("/", 1)
    with open(path, "rb") as f:
        part = MIMEBase(maintype, subtype)
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition", "form-data",
        name=name, filename=path.name,
    )
    part.add_header("Content-Type", ctype)
    mp.attach(part)


def build_multipart(
    *,
    title: str,
    desc: str,
    tid: int,
    tags: str,
    copyright: int,
    video_path: Path,
    cover_path: Optional[Path],
) -> tuple[bytes, str]:
    """构造 multipart/form-data 实体，返回 (body_bytes, content_type)。"""
    mp = MIMEMultipart("form-data")
    _add_text_field(mp, "title", title)
    _add_text_field(mp, "desc", desc)
    _add_text_field(mp, "tid", str(tid))
    _add_text_field(mp, "tags", tags)
    _add_text_field(mp, "copyright", str(copyright))
    _add_file_field(mp, "video", video_path)
    if cover_path is not None:
        _add_file_field(mp, "cover", cover_path)

    # 序列化
    buf = BytesIO()
    gen = BytesGenerator(buf, mangle_from_=False, maxheaderlen=0)
    gen.flatten(mp, unixfrom=False)
    body = buf.getvalue()

    # 提取 boundary 供 Content-Type 用
    # email 默认 boundary 是 `===============<random>==`；从 body 第一行抓
    boundary_line = body.split(b"\r\n", 1)[0]
    boundary = boundary_line.removeprefix(b"--")
    content_type = f"multipart/form-data; boundary={boundary.decode('ascii')}"
    return body, content_type


# ── Relay HTTP 调用 ─────────────────────────────────────────────────────────

def relay_submit(
    *,
    relay_url: str,
    ofb_key: str,
    title: str,
    desc: str,
    tid: int,
    tags: str,
    copyright: int,
    video_path: Path,
    cover_path: Optional[Path],
    timeout: int = REQUEST_TIMEOUT_S,
) -> dict:
    """multipart POST 到 relay /api/v1/publish/bilibili/submit。"""
    if not video_path.is_file():
        sys.stderr.write(f"[bilibili-publish] ERROR: video not found: {video_path}\n")
        sys.exit(1)

    body, content_type = build_multipart(
        title=title, desc=desc, tid=tid, tags=tags, copyright=copyright,
        video_path=video_path, cover_path=cover_path,
    )
    url = f"{relay_url}{RELAY_ENDPOINT}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-OFB-Key": ofb_key,
            "Content-Type": content_type,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode(errors="replace")
        sys.stderr.write(f"[bilibili-publish] HTTP {e.code}: {err_body}\n")
        try:
            err = json.loads(err_body)
            sys.stderr.write(f"[bilibili-publish] error code: {err.get('error', 'unknown')}\n")
        except json.JSONDecodeError:
            pass
        sys.exit(1)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish video to Bilibili via relay proxy (D1 全 proxy)"
    )
    parser.add_argument("--title", required=True, help=f"Video title (max {MAX_TITLE_LEN} chars)")
    parser.add_argument("--video", required=True, help="Video file path (mp4)")
    parser.add_argument("--cover", help="Cover image path (jpg/png, optional)")
    parser.add_argument("--desc", default="", help="Video description")
    parser.add_argument("--tid", type=int, default=122, help="Partition ID (default: 122=野生技术协会)")
    parser.add_argument("--tags", required=True, help="Comma-separated tags (max 10, each ≤ 20 chars)")
    parser.add_argument("--copyright", type=int, default=1, choices=[1, 2], help="1=self-made, 2=repost")
    args = parser.parse_args()

    # 入参校验
    if len(args.title) > MAX_TITLE_LEN:
        sys.stderr.write(f"[bilibili-publish] ERROR: title exceeds {MAX_TITLE_LEN} chars\n")
        sys.exit(1)
    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]
    if len(tags_list) > MAX_TAGS:
        sys.stderr.write(f"[bilibili-publish] ERROR: more than {MAX_TAGS} tags\n")
        sys.exit(1)
    for t in tags_list:
        if len(t) > MAX_TAG_LEN:
            sys.stderr.write(f"[bilibili-publish] ERROR: tag '{t}' exceeds {MAX_TAG_LEN} chars\n")
            sys.exit(1)

    video_path = Path(args.video).resolve()
    cover_path = Path(args.cover).resolve() if args.cover else None

    # env
    relay, ofb_key = require_env()

    # 调 relay
    sys.stderr.write(f"[bilibili-publish] posting to {relay}{RELAY_ENDPOINT} ...\n")
    result = relay_submit(
        relay_url=relay,
        ofb_key=ofb_key,
        title=args.title,
        desc=args.desc,
        tid=args.tid,
        tags=args.tags,
        copyright=args.copyright,
        video_path=video_path,
        cover_path=cover_path,
    )

    # 输出
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
