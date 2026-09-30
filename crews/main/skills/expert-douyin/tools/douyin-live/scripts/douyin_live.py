#!/usr/bin/env python3
"""Live snapshots, products, ranks, room writes and bounded event streams."""

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import call, ENDPOINTS
from douyin_utils.http import DouyinRequestError, session
from douyin_utils.ws import listen

LIVE_METHODS = {k: v for k, v in ENDPOINTS.items() if v["profile"] == "live"}


def numeric(value):
    if not re.fullmatch(r"\d{1,20}", str(value)):
        raise ValueError("INVALID_ID")
    return str(value)


def room(value):
    if value.startswith("https://"):
        m = re.fullmatch(r"https://live\.douyin\.com/(\d{1,20})(?:[/?#].*)?", value)
        if not m:
            raise ValueError("INVALID_ROOM_URL")
        return m[1]
    return numeric(value)


def snapshot(web_rid):
    response = call("room", {"web_rid": web_rid})
    rooms = (response.get("data") or {}).get("data")
    if not isinstance(rooms, list) or not rooms:
        raise DouyinRequestError("LIVE_ROOM_MISSING")
    return rooms[0]


def ident(value, key):
    return str(value.get(key + "_str") or value.get(key) or "")


def pk_context(web_rid):
    current = snapshot(web_rid)
    room_id = ident(current, "id")
    owner = current.get("owner") or {}
    anchor = ident(owner, "id")
    channel = ident(current.get("linker_map") or {}, "1")
    result = {
        "room_id": room_id,
        "anchor_id": anchor,
        "channel_id": channel,
        "battle_id": None,
        "anchors": [],
    }
    if not channel:
        return result
    response = call(
        "linkmic", {"room_id": room_id, "anchor_id": anchor, "channel_id": channel}
    )
    stats = (response.get("data") or {}).get("battle_stats") or {}
    settings = stats.get("battle_settings") or {}
    result.update(
        battle_id=ident(settings, "battle_id") or None,
        channel_id=ident(settings, "channel_id") or channel,
        finished=settings.get("finished"),
        battle_stats=stats,
    )
    anchors = {
        anchor: {
            "anchor_id": anchor,
            "nickname": owner.get("nickname", ""),
            "room_id": room_id,
        }
    }
    for uid, value in (stats.get("user_infos") or {}).items():
        user = value.get("user") or {}
        uid = ident(user, "user_id") or ident(user, "id") or str(uid)
        anchors[uid] = {
            "anchor_id": uid,
            "nickname": user.get("nick_name") or user.get("nickname", ""),
            "room_id": ident(value, "room_id"),
        }
    for row in (stats.get("battle_scores") or []) + (stats.get("battle_armies") or []):
        uid = ident(row, "user_id") or ident(row, "anchor_id")
        if uid:
            anchors.setdefault(uid, {"anchor_id": uid, "nickname": "", "room_id": None})
    result["anchors"] = list(anchors.values())
    return result


def main():
    p = argparse.ArgumentParser(prog="douyin-live")
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("room", "pk", "pk-rank", "listen", "products"):
        s = sub.add_parser(command)
        s.add_argument("--room", required=True)
        if command == "pk-rank":
            s.add_argument("--side", choices=("current", "both"), default="current")
        if command == "listen":
            s.add_argument("--duration", type=int, default=60)
            s.add_argument("--max-events", type=int, default=100)
            s.add_argument("--output")
            s.add_argument("--user-unique-id")
    s = sub.add_parser("rank")
    s.add_argument("--room-id", required=True)
    s.add_argument("--anchor-id", required=True)
    s.add_argument("--sec-anchor-id", required=True)
    s = sub.add_parser("ticket-rank")
    s.add_argument("--room-id", required=True)
    s = sub.add_parser("chat")
    s.add_argument("--room-id", required=True)
    s.add_argument("--text", required=True)
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("like")
    s.add_argument("--room-id", required=True)
    s.add_argument("--count", type=int, default=1)
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("call")
    s.add_argument("method", choices=LIVE_METHODS)
    s.add_argument("--params", default="{}")
    s.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    if a.command == "call":
        return {
            "ok": True,
            "data": call(a.method, json.loads(a.params), confirm=a.confirm),
        }
    if a.command == "room":
        return {"ok": True, "data": snapshot(room(a.room))}
    if a.command == "pk":
        return {"ok": True, "data": pk_context(room(a.room))}
    if a.command == "pk-rank":
        before = pk_context(room(a.room))
        if not before["battle_id"]:
            return {"ok": True, "state": "not_in_pk", "context": before, "ranks": {}}
        anchors = (
            [before["anchor_id"]]
            if a.side == "current"
            else [i["anchor_id"] for i in before["anchors"]]
        )
        ranks = {
            uid: call("pk_rank", {"channel_id": before["channel_id"], "anchor_id": uid})
            for uid in anchors
        }
        after = pk_context(room(a.room))
        same = all(
            before[k] == after[k]
            for k in ("room_id", "anchor_id", "channel_id", "battle_id")
        )
        return {
            "ok": True,
            "state": "ok" if same else "context_changed",
            "context": before,
            "context_after": after,
            "ranks": ranks,
        }
    if a.command in ("listen", "products"):
        current = snapshot(room(a.room))
        room_id = ident(current, "id")
        owner = current.get("owner") or {}
        if a.command == "products":
            return {
                "ok": True,
                "data": call(
                    "products", {"room_id": room_id, "author_id": ident(owner, "id")}
                ),
            }
        user_id = a.user_unique_id or session().state.get("tokens", {}).get("webid")
        if not user_id:
            raise ValueError("DEVICE_ID_MISSING")
        return listen(
            "live",
            room_id=room_id,
            user_unique_id=numeric(user_id),
            duration=a.duration,
            max_events=a.max_events,
            output=a.output,
        )
    if a.command == "rank":
        return {
            "ok": True,
            "data": call(
                "contribution_rank",
                {
                    "room_id": numeric(a.room_id),
                    "anchor_id": numeric(a.anchor_id),
                    "sec_anchor_id": a.sec_anchor_id,
                },
            ),
        }
    if a.command == "ticket-rank":
        return {
            "ok": True,
            "data": call("ticket_rank", {"room_id": numeric(a.room_id)}),
        }
    if a.command == "chat":
        text = a.text.strip()
        if not text or len(text) > 200:
            raise ValueError("CHAT_LENGTH_OUT_OF_RANGE")
        result = call(
            "live_chat",
            {"room_id": numeric(a.room_id), "content": text},
            confirm=a.confirm,
        )
    else:
        if not 1 <= a.count <= 20:
            raise ValueError("LIKE_COUNT_OUT_OF_RANGE")
        result = call(
            "live_like",
            {"room_id": numeric(a.room_id), "count": str(a.count)},
            body={},
            confirm=a.confirm,
        )
    return {"ok": True, "data": result}


if __name__ == "__main__":
    try:
        r = main()
        print(json.dumps(r, ensure_ascii=False))
    except (DouyinRequestError, ValueError, OSError) as e:
        code = (
            e.code
            if isinstance(e, DouyinRequestError)
            else str(e)
            if str(e).isupper()
            else "LIVE_CLIENT_ERROR"
        )
        print(json.dumps({"ok": False, "error": code}))
        sys.exit(
            2
            if code
            in (
                "API_SESSION_MISSING",
                "API_SESSION_EXPIRED",
                "PLATFORM_AUTH_REJECTED",
                "PLATFORM_LOGIN_REJECTED",
            )
            else 1
        )
