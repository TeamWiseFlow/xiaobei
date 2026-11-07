#!/usr/bin/env python3
"""Douyin IM CLI: explicit targets, bounded listening and durable send receipts."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils import im_client as client, im_store as store
from douyin_utils.api import call, item_id
from douyin_utils.http import DouyinRequestError, session, public_error_info
from douyin_utils.im_media import upload_attachment
from douyin_utils.message import MessagePayload
from douyin_utils.session import SessionError, session_lock
from douyin_utils.ws import listen

KINDS = ("text", "image", "video", "file", "audio", "sticker", "card-video",
         "card-photos", "card-web", "card-user")
numeric = client.numeric


def file_hash(value):
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("MEDIA_FILE_MISSING")
    if path.stat().st_size > 10 * 1024**2:
        raise ValueError("IM_FILE_TOO_LARGE")
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()


def draft(args):
    value = {"kind": args.kind, "encrypted": args.encrypted}
    content = store.read(args.content_file) if args.content_file else None
    if args.kind == "text":
        text = (args.text or "").strip()
        if not text or len(text) > 1000:
            raise ValueError("MESSAGE_LENGTH_OUT_OF_RANGE")
        value["text"] = text
    elif args.kind in {"image", "video", "file"}:
        if not args.file:
            raise ValueError("MEDIA_FILE_REQUIRED")
        value["file"], value["file_hash"] = file_hash(args.file)
        if args.thumb:
            value["thumb"], value["thumb_hash"] = file_hash(args.thumb)
    elif args.kind in {"audio", "sticker"}:
        if not content:
            raise ValueError("VOICE_CONTENT_REQUIRED" if args.kind == "audio" else "STICKER_CONTENT_REQUIRED")
        value["content"] = content
    else:
        if args.kind == "card-user" and not content:
            raise ValueError("USER_CARD_OBJECT_REQUIRED")
        if not content and not args.share:
            raise ValueError("CARD_CONTENT_REQUIRED")
        if args.share and args.kind in {"card-video", "card-photos"}:
            value["share"] = str(item_id(args.share))
        elif args.share:
            value["share"] = args.share
        value["content"] = content
    return value


def materialize(value, uid):
    kind = value["kind"]
    if kind == "text":
        return 7, value["text"]
    if kind in {"image", "video", "file"}:
        for field in ("file", "thumb"):
            if field in value and file_hash(value[field])[1] != value[field + "_hash"]:
                raise ValueError("IM_INPUT_CHANGED")
        return upload_attachment(value["file"], kind, uid, value.get("thumb"))
    content = value.get("content")
    if kind in {"audio", "sticker"}:
        return ((109 if value["encrypted"] else 17) if kind == "audio" else 5), content
    if not content and value.get("share"):
        content = (call("detail", {"aweme_id": value["share"]}, expected_uid=uid).get("aweme_detail")
                   if kind in {"card-video", "card-photos"} else value["share"])
    if not content:
        raise ValueError("CARD_CONTENT_REQUIRED")
    builder, message_type = {
        "card-video": (MessagePayload.build_share_aweme_content, 8),
        "card-photos": (MessagePayload.build_share_photos_content, 77),
        "card-web": (MessagePayload.build_share_web_content, 26),
        "card-user": (MessagePayload.build_user_card_content, 25),
    }[kind]
    return message_type, builder(content)


def reply_target(args, uid):
    events = store.read(args.event_file, lines=True)
    matches = [e for e in events if isinstance(e, dict) and e.get("type") == "im_message"
               and str(e.get("server_message_id")) == args.message_id]
    if args.conversation_id:
        matches = [e for e in matches if e.get("conversation_id") == args.conversation_id]
    if len(matches) != 1:
        raise ValueError("REPLY_EVENT_NOT_UNIQUE")
    event = matches[0]
    if (event.get("account_uid") != uid or event.get("direction") != "incoming"
            or event.get("sender") == uid or not numeric(event.get("server_message_id"))):
        raise ValueError("REPLY_EVENT_ACCOUNT_MISMATCH")
    state = {"my_user_id": uid, "to_user_id": event["sender"],
             "conversation_id": event["conversation_id"],
             "conversation_short_id": event.get("conversation_short_id"), "ticket": "refresh-required"}
    client.participants(state)
    args.request_id = args.request_id or "reply-" + store.digest([uid, state["conversation_id"], args.message_id])
    return state


def conversation(uid, to_id, fingerprint, existing=None):
    path = store.conversation_path(uid, to_id)
    state = existing
    if not state and (path.exists() or path.is_symlink()):
        state = store.load_conversation(path)
    if state:
        my_id, target = client.participants(state)
        if str(my_id) != uid or str(target) != str(to_id):
            raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
        current = client.inspect(state)
    else:
        current = client.create(int(uid), int(to_id))
    if client.binding() != fingerprint:
        raise ValueError("IM_SESSION_CHANGED")
    return store.save_conversation(uid, to_id, current, fingerprint)


def execute_send(args):
    value = draft(args)
    existing = store.load_conversation(args.conversation_file) if args.command == "send" else None
    # Preview does not read a login session or contact the platform.
    if args.command == "reply":
        if args.confirm:
            uid = str(numeric(session().state.get("uid", "")))
        else:
            events = store.read(args.event_file, lines=True)
            owners = {str(e.get("account_uid")) for e in events if isinstance(e, dict)
                      and str(e.get("server_message_id")) == args.message_id}
            if len(owners) != 1:
                raise ValueError("REPLY_EVENT_NOT_UNIQUE")
            uid = owners.pop()
        existing = reply_target(args, uid)
    to_id = str(numeric(existing["to_user_id"] if existing else args.to_user_id))
    if not args.confirm:
        return {"ok": True, "preview": True, "action": args.command,
                "to_user_id": to_id, "kind": args.kind, "request_id": args.request_id}
    uid = str(numeric(session().state.get("uid", "")))
    if uid == to_id:
        raise ValueError("RECIPIENT_IS_SELF")
    if existing and existing["my_user_id"] != uid:
        raise ValueError("API_ACCOUNT_MISMATCH")
    fingerprint = client.binding()
    input_hash = store.digest({"target": to_id, "content": value,
        "reply_to": args.message_id if args.command == "reply" else None})
    # One local lock covers receipt, conversation and media preparation across processes.
    with session_lock(store.STATE_DIR / "send"):
        path, receipt, proceed = store.start(uid, to_id, args.request_id, input_hash, fingerprint)
        if not proceed:
            return store.public(receipt, path)
        intent_written = False
        stage = "account"
        try:
            client.account(uid)
            if client.binding() != fingerprint:
                raise ValueError("IM_SESSION_CHANGED")
            stage = "conversation"
            _, state = conversation(uid, to_id, fingerprint, existing)
            store.update(path, receipt, "preparing", kind=args.kind, conversation_id=state["conversation_id"])
            if "content" not in receipt:
                stage = "content_prepare"
                msg_type, content = materialize(value, uid)
                store.update(path, receipt, "prepared", message_type=msg_type, content=content)

            def intent():
                nonlocal intent_written
                if client.binding() != fingerprint:
                    raise ValueError("IM_SESSION_CHANGED")
                store.update(path, receipt, "submitting")
                intent_written = True

            stage = "message_prepare"
            result = client.send(state, receipt["content"], receipt["message_type"],
                                 client_message_id=receipt["client_message_id"], before_send=intent,
                                 on_response=lambda response: store.capture_response(path, receipt, response))
            if receipt["status"] != "submitting":
                raise ValueError("IM_SEND_INTENT_MISSING")
            store.update(path, receipt, "accepted", **result)
        except (DouyinRequestError, ValueError, OSError, SessionError) as exc:
            code = exc.code if isinstance(exc, DouyinRequestError) else str(exc)
            code = code if code.isupper() and len(code) < 100 else "IM_CLIENT_ERROR"
            status = ("rejected" if code == "PLATFORM_IM_REJECTED" else "unknown") if intent_written else "preparing"
            store.update(path, receipt, status, error=code,
                         stage="message_submit" if intent_written else getattr(exc, "im_stage", stage),
                         **public_error_info(exc))
        return store.public(receipt, path)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="douyin-im")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("create")
    cmd.add_argument("--my-user-id", required=True)
    cmd.add_argument("--to-user-id", required=True)
    cmd.add_argument("--confirm", action="store_true")
    cmd = sub.add_parser("info")
    cmd.add_argument("--conversation-file", required=True)
    cmd = sub.add_parser("status")
    cmd.add_argument("--request-id", required=True)
    for name in ("send", "send-to", "reply"):
        cmd = sub.add_parser(name)
        if name == "send":
            cmd.add_argument("--conversation-file", required=True)
        elif name == "send-to":
            cmd.add_argument("--to-user-id", required=True)
        else:
            cmd.add_argument("--event-file", required=True)
            cmd.add_argument("--message-id", required=True)
            cmd.add_argument("--conversation-id")
        cmd.add_argument("--request-id")
        cmd.add_argument("--kind", choices=KINDS, default="text")
        for option in ("text", "file", "thumb", "content-file", "share"):
            cmd.add_argument("--" + option)
        cmd.add_argument("--encrypted", action="store_true")
        cmd.add_argument("--confirm", action="store_true")
    cmd = sub.add_parser("listen")
    cmd.add_argument("--device-id")
    cmd.add_argument("--duration", type=int, default=60)
    cmd.add_argument("--max-events", type=int, default=100)
    cmd.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command in {"send", "send-to", "reply"}:
        result = execute_send(args)
    elif args.command == "status":
        uid = str(numeric(session().state.get("uid", "")))
        path = store.receipt_path(uid, args.request_id)
        with session_lock(store.STATE_DIR / "send"):
            receipt = store.read(path)
            if receipt.get("my_user_id") != uid:
                raise ValueError("API_ACCOUNT_MISMATCH")
            if receipt["status"] == "submitting":
                store.update(path, receipt, "unknown", error="PREVIOUS_SEND_INTERRUPTED")
            result = store.public(receipt, path)
            result["ok"] = True
    elif args.command == "listen":
        uid, _ = client.account()
        device = str(session().state.get("tokens", {}).get("device_id", ""))
        numeric(device)
        if args.device_id and args.device_id != device:
            raise ValueError("DEVICE_ID_ACCOUNT_MISMATCH")
        result = listen("im", device_id=device, duration=args.duration,
                        max_events=args.max_events, output=args.output, expected_uid=uid)
    else:
        existing = store.load_conversation(args.conversation_file) if args.command == "info" else None
        uid = str(numeric(existing["my_user_id"] if existing else args.my_user_id))
        to_id = str(numeric(existing["to_user_id"] if existing else args.to_user_id))
        if uid == to_id:
            raise ValueError("RECIPIENT_IS_SELF")
        if args.command == "create" and not args.confirm:
            result = {"ok": True, "preview": True, "my_user_id": uid, "to_user_id": to_id}
        else:
            with session_lock(store.STATE_DIR / "send"):
                _, fingerprint = client.account(uid)
                path, _ = conversation(uid, to_id, fingerprint, existing)
            result = {"ok": True, "conversation_file": str(path), "to_user_id": to_id}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DouyinRequestError, ValueError, OSError, SessionError) as exc:
        code = exc.code if isinstance(exc, DouyinRequestError) else str(exc)
        code = code if code.isupper() and len(code) < 100 else "IM_CLIENT_ERROR"
        print(json.dumps({"ok": False, "error": code, **public_error_info(exc)}))
        raise SystemExit(2 if code in {"API_SESSION_MISSING", "API_SESSION_EXPIRED", "PLATFORM_AUTH_REJECTED"} else 1)
