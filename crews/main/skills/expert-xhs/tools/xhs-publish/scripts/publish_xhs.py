#!/usr/bin/env python3
"""Publish one note through the local Creator HTTP client."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from creator_session import CreatorSessionMissing, creator_api, observe  # noqa: E402

def _note_id(response: dict) -> str:
    data = response.get("data") or {}
    for source in (data, response):
        if isinstance(source, dict):
            for key in ("note_id", "noteId", "id"):
                value = source.get(key)
                if value:
                    return str(value)
    return ""


def publish(args, body: str, topics: list[dict]) -> dict:
    note_info = {
        "title": args.title,
        "desc": body,
        "media_type": args.mode,
        "type": 1 if args.private else 0,
        "topics": [topic["name"] for topic in topics],
        "ai_declaration": args.ai_declaration,
    }
    if args.mode == "image":
        note_info["images"] = args.images
    else:
        note_info["video"] = args.video
        if args.cover:
            note_info["cover"] = args.cover

    try:
        with creator_api() as api:
            success, message, response = api.post_note(note_info)
    except CreatorSessionMissing:
        raise
    except Exception as exc:
        observe("publish", "unknown", error_type=type(exc).__name__)
        return {
            "ok": False,
            "error": "SUBMISSION_UNKNOWN",
            "message": f"提交结果不确定；先检查创作者后台，避免重复发布：{str(exc)[:160]}",
        }

    code = response.get("code") if isinstance(response, dict) else None
    if not success:
        observe("publish", "rejected", code=code)
        return {
            "ok": False,
            "error": "PUBLISH_REJECTED",
            "code": code,
            "message": message,
        }
    note_id = _note_id(response if isinstance(response, dict) else {})
    if not note_id:
        observe("publish", "unconfirmed")
        return {
            "ok": False,
            "error": "SUBMISSION_UNCONFIRMED",
            "message": "平台返回成功但未给出笔记 ID；先检查创作者后台，避免重复发布",
        }
    observe("publish", "ok")
    return {
        "ok": True,
        "note_id": note_id,
        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
    }


BOM = "\uFEFF"
TOPIC_RE = re.compile(r"#([^\[\]#\s" + BOM + r"]+)(\[话题\]#)?")


def normalize_body_newlines(body: str) -> str:
    return body.replace("\\r\\n", "\n").replace("\\n", "\n")


def extract_topics(body: str, extra_topics: list[str] | None = None) -> list[dict]:
    names: list[str] = []
    for match in re.finditer(r"#([^#\s\[\]]+)(?:\[话题\]#)?", body):
        name = match.group(1)
        if name not in names:
            names.append(name)
    for raw in extra_topics or []:
        name = raw.strip().lstrip("#")
        if name and name not in names:
            names.append(name)
    return [{"name": name} for name in names]


def rewrite_topics_in_body(body: str, topics: list[dict]) -> str:
    names = {topic["name"] for topic in topics}
    return TOPIC_RE.sub(
        lambda match: (
            f"{BOM}#{match.group(1)}[话题]#{BOM}"
            if not match.group(2) and match.group(1) in names else match.group(0)
        ),
        body,
    )


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布小红书 Creator 笔记")
    parser.add_argument("--mode", required=True, choices=["image", "video"])
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--images", nargs="+")
    parser.add_argument("--video")
    parser.add_argument("--cover")
    parser.add_argument("--topics", nargs="*")
    parser.add_argument("--private", action="store_true")
    parser.add_argument("--ai-declaration", action="store_true",
                        help="声明笔记含 AI 合成内容")
    args = parser.parse_args(argv)
    body = normalize_body_newlines(args.body)
    if not args.title.strip() or len(args.title) > 20:
        emit({"ok": False, "error": "TITLE_INVALID", "message": "标题须为 1–20 字"})
        return 1
    if not body.strip() or len(body) > 1000:
        emit({"ok": False, "error": "BODY_INVALID", "message": "正文须为 1–1000 字"})
        return 1
    if args.mode == "image" and not (args.images and 1 <= len(args.images) <= 18):
        emit({"ok": False, "error": "IMAGES_INVALID", "message": "图文需 1–18 张图片"})
        return 1
    if args.mode == "video" and not args.video:
        emit({"ok": False, "error": "VIDEO_REQUIRED", "message": "视频模式需 --video"})
        return 1
    topics = extract_topics(body, args.topics)
    if len(topics) > 10:
        emit({"ok": False, "error": "TOO_MANY_TOPICS", "message": "最多 10 个话题"})
        return 1
    try:
        result = publish(args, rewrite_topics_in_body(body, topics), topics)
    except CreatorSessionMissing as exc:
        emit({"ok": False, "error": "SESSION_MISSING", "message": str(exc)})
        return 2
    emit(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
