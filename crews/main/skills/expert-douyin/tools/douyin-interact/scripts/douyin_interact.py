#!/usr/bin/env python3
"""Bounded Douyin work interactions through the client HTTP transport."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.http import DouyinRequestError
from douyin_utils.api import call  # noqa: E402


BASE = "https://www.douyin.com"


def work_id(value: str) -> str:
    if value.isdigit() and 15 <= len(value) <= 22:
        return value
    match = re.search(r"/(?:video|note|slides)/(\d{15,22})(?:[/?#]|$)", value)
    if not match:
        raise ValueError("INVALID_AWEME_ID")
    return match.group(1)


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="douyin-interact")
    sub = command.add_subparsers(dest="action", required=True)
    for name in (
        "like",
        "unlike",
        "favorite",
        "unfavorite",
        "comment",
        "reply",
        "collection-move",
        "collection-remove",
    ):
        part = sub.add_parser(name)
        part.add_argument("--url", required=True, help="作品链接或数字 ID")
        if name in {"comment", "reply"}:
            part.add_argument("--text", required=True)
            if name == "reply":
                part.add_argument("--comment-id", required=True)
                part.add_argument("--reply-to-reply-id")
        if name.startswith("collection-"):
            part.add_argument("--collection-id", required=True)
            part.add_argument("--collection-name", default="")
        part.add_argument("--confirm", action="store_true", help="确认执行写操作")
    return command


def main() -> int:
    args = parser().parse_args()
    aweme_id = work_id(args.url)
    if args.action in {"like", "unlike"}:
        path = "/aweme/v1/web/commit/item/digg/"
        body = {
            "aweme_id": aweme_id,
            "item_type": "0",
            "type": "1" if args.action == "like" else "0",
        }
    elif args.action in {"favorite", "unfavorite"}:
        path = "/aweme/v1/web/aweme/collect/"
        body = {
            "aweme_id": aweme_id,
            "aweme_type": "0",
            "action": "1" if args.action == "favorite" else "0",
        }
    elif args.action.startswith("collection-"):
        if not args.collection_id.isdigit():
            raise ValueError("INVALID_COLLECTION_ID")
        body = {
            "item_ids": aweme_id,
            "collects_name": args.collection_name,
            "to_collects_id"
            if args.action == "collection-move"
            else "from_collects_id": args.collection_id,
        }
    else:
        path = "/aweme/v1/web/comment/publish"
        text = args.text.strip()
        if not text or len(text) > 500:
            raise ValueError("COMMENT_LENGTH_OUT_OF_RANGE")
        body = {
            "aweme_id": aweme_id,
            "text": text,
            "text_extra": "[]",
            "comment_send_celltime": "0",
            "comment_video_celltime": "0",
            "one_level_comment_rank": "-1",
            "paste_edit_method": "non_paste",
        }
        if args.action == "reply":
            if not args.comment_id.isdigit():
                raise ValueError("INVALID_COMMENT_ID")
            body["reply_id"] = args.comment_id
            if args.reply_to_reply_id:
                if not args.reply_to_reply_id.isdigit():
                    raise ValueError("INVALID_REPLY_ID")
                body["reply_to_reply_id"] = args.reply_to_reply_id
    if not args.confirm:
        print(
            json.dumps(
                {
                    "ok": True,
                    "preview": True,
                    "action": args.action,
                    "aweme_id": aweme_id,
                    "text": body.get("text"),
                },
                ensure_ascii=False,
            )
        )
        return 0
    data = call(
        args.action.replace("-", "_")
        if args.action.startswith("collection-")
        else "like"
        if args.action in {"like", "unlike"}
        else "favorite"
        if args.action in {"favorite", "unfavorite"}
        else "comment",
        body,
        confirm=True,
    )
    print(
        json.dumps(
            {"ok": True, "action": args.action, "aweme_id": aweme_id, "response": data},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DouyinRequestError, ValueError) as exc:
        code = exc.code if isinstance(exc, DouyinRequestError) else str(exc)
        print(json.dumps({"ok": False, "error": code}, ensure_ascii=False))
        raise SystemExit(
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
