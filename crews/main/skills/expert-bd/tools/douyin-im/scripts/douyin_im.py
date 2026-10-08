#!/usr/bin/env python3
"""Douyin PC IM client. Protocol and platform traffic stay on this host."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.http import DouyinRequestError, _session, prepare, request, session  # noqa: E402
from douyin_utils.im_media import upload_attachment
from douyin_utils.message import MessagePayload
from douyin_utils.ws import listen
from douyin_utils.api import call, item_id
from im_wire import (
    conversation_body,
    create_body,
    envelope,
    parse_response,
    send_text_body,
    send_content_body,
)

IM_HOST = "imapi.douyin.com"
IM_BASE = "https://imapi.douyin.com"
STATE_DIR = Path.home() / ".openclaw" / "douyin-im"


def numeric(value: str) -> int:
    if not re.fullmatch(r"\d{1,20}", value) or int(value) > 2**63 - 1:
        raise ValueError("INVALID_USER_ID")
    return int(value)


def state_path(my_id: int, to_id: int) -> Path:
    return STATE_DIR / f"{my_id}-{to_id}.json"


def load_state(path: str) -> dict:
    file = Path(path).expanduser().resolve()
    if not file.is_file() or file.stat().st_mode & 0o077:
        raise ValueError("CONVERSATION_FILE_UNSAFE")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("CONVERSATION_FILE_INVALID") from exc
    required = (
        "my_user_id",
        "to_user_id",
        "conversation_id",
        "conversation_short_id",
        "ticket",
    )
    if not isinstance(data, dict) or any(not data.get(key) for key in required):
        raise ValueError("CONVERSATION_FILE_INVALID")
    numeric(str(data["my_user_id"]))
    numeric(str(data["to_user_id"]))
    numeric(str(data["conversation_short_id"]))
    if not isinstance(data["conversation_id"], str) or not isinstance(
        data["ticket"], str
    ):
        raise ValueError("CONVERSATION_FILE_INVALID")
    return data


def save_state(my_id: int, to_id: int, conversation: dict) -> Path:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)
    target = state_path(my_id, to_id)
    value = {"my_user_id": str(my_id), "to_user_id": str(to_id), **conversation}
    descriptor, temp_name = tempfile.mkstemp(prefix=".conversation-", dir=STATE_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target


def identity_token() -> tuple[str, str]:
    trace_id = uuid.uuid4().hex[:8]
    data = request(
        "passport",
        "request",
        "GET",
        "https://www.douyin.com/passport/safe/get_identity_security_token/",
        params={
            "passport_jssdk_version": "4.2.3",
            "passport_jssdk_type": "lite",
            "is_from_ttaccountsdk": 1,
            "aid": 6383,
            "language": "zh",
            "scene": "web_im",
            "auto_retry_req": 0,
            "skip_verify": "false",
            "identity_token_force_get_tag": 0,
            "biz_trace_id": trace_id,
            "id_token_version": "1.2.10",
        },
        static_headers={
            "Referer": "https://www.douyin.com/chat?isPopup=1",
            "X-TT-Passport-Trace-ID": trace_id,
            "Accept": "application/json, text/javascript",
        },
    )
    if not isinstance(data, dict) or data.get("message") not in (None, "success"):
        raise DouyinRequestError("IDENTITY_TOKEN_REJECTED")
    values = data.get("data") or {}
    token = values.get("identity_security_token")
    device_id = values.get("device_id")
    if not isinstance(token, str) or not token:
        raise DouyinRequestError("IDENTITY_TOKEN_MISSING")
    return token, str(device_id or "")


def create(my_id: int, to_id: int) -> dict:
    url = IM_BASE + "/v2/conversation/create"
    _, ua = _session(IM_HOST)
    unsigned = envelope(
        609,
        create_body(my_id, to_id),
        ua,
        device=session().state.get("device", {}),
        protocol=session().state.get("im_protocol", {}),
    )
    data = prepare(
        "im",
        "prepare",
        url,
        unsigned,
        fields={"my_user_id": str(my_id), "to_user_id": str(to_id)},
        expected_uid=my_id,
    )
    encoded = data.get("envelope_extension_base64")
    if not isinstance(encoded, str) or not encoded:
        raise DouyinRequestError("IM_PREPARE_INCOMPLETE")
    try:
        extension = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise DouyinRequestError("IM_PREPARE_INCOMPLETE") from exc
    if len(extension) > 4096:
        raise DouyinRequestError("IM_PREPARE_INCOMPLETE")
    response = request(
        "im",
        "request",
        "POST",
        url,
        raw_body=unsigned + extension,
        expected_uid=my_id,
        context=data.get("context"),
        content_type="application/x-protobuf",
        binary_response=True,
    )
    conversation = parse_response(response, expect_conversation=True, expected_command=609)
    participants = re.fullmatch(r"0:1:(\d+):(\d+)", conversation["conversation_id"])
    if not participants or set(participants.groups()) != {str(my_id), str(to_id)}:
        raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
    return conversation


def inspect(state: dict) -> dict:
    url = IM_BASE + "/v2/conversation/get_info_list"
    _, ua = _session(IM_HOST)
    body = conversation_body(
        str(state["conversation_id"]), int(state["conversation_short_id"])
    )
    response = request(
        "im",
        "request",
        "POST",
        url,
        raw_body=envelope(
            610,
            body,
            ua,
            device=session().state.get("device", {}),
            protocol=session().state.get("im_protocol", {}),
        ),
        expected_uid=state["my_user_id"],
        content_type="application/x-protobuf",
        binary_response=True,
    )
    conversation = parse_response(response, expect_conversation=True, expected_command=610)
    if (
        conversation["conversation_id"] != state["conversation_id"]
        or conversation["conversation_short_id"] != int(state["conversation_short_id"])
    ):
        raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
    return conversation


def send(state: dict, message: str | dict, message_type: int = 7) -> dict:
    token, device_id = identity_token()
    _, ua = _session(IM_HOST)
    body = (
        send_text_body(
            str(state["conversation_id"]),
            int(state["conversation_short_id"]),
            str(state["ticket"]),
            message,
        )
        if isinstance(message, str)
        else send_content_body(
            str(state["conversation_id"]),
            int(state["conversation_short_id"]),
            str(state["ticket"]),
            message_type,
            message,
        )
    )
    raw = envelope(
        100,
        body,
        ua,
        identity_token=token,
        identity_device_id=device_id,
        device=session().state.get("device", {}),
        protocol=session().state.get("im_protocol", {}),
    )
    response = request(
        "im",
        "request",
        "POST",
        IM_BASE + "/v1/message/send",
        raw_body=raw,
        expected_uid=state["my_user_id"],
        content_type="application/x-protobuf",
        binary_response=True,
    )
    return parse_response(response, expected_command=100)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="douyin-im")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("create")
    cmd.add_argument("--my-user-id", required=True)
    cmd.add_argument("--to-user-id", required=True)
    cmd.add_argument("--confirm", action="store_true")
    cmd = sub.add_parser("info")
    cmd.add_argument("--conversation-file", required=True)
    for command in ("send", "send-to"):
        cmd = sub.add_parser(command)
        if command == "send":
            cmd.add_argument("--conversation-file", required=True)
        else:
            cmd.add_argument("--to-user-id", required=True)
        cmd.add_argument(
        "--kind",
        choices=(
            "text",
            "image",
            "video",
            "file",
            "audio",
            "sticker",
            "card-video",
            "card-photos",
            "card-web",
            "card-user",
        ),
        default="text",
    )
        cmd.add_argument("--text")
        cmd.add_argument("--file")
        cmd.add_argument("--thumb")
        cmd.add_argument("--content-file")
        cmd.add_argument("--share")
        cmd.add_argument("--encrypted", action="store_true")
        cmd.add_argument("--confirm", action="store_true")
    cmd = sub.add_parser("listen")
    cmd.add_argument("--device-id")
    cmd.add_argument("--duration", type=int, default=60)
    cmd.add_argument("--max-events", type=int, default=100)
    cmd.add_argument("--output")
    args = parser.parse_args(argv)
    if args.command == "send-to":
        to_id = numeric(args.to_user_id)
        if not args.confirm:
            print(json.dumps({"ok": True, "preview": True, "action": "send-to",
                              "to_user_id": str(to_id), "kind": args.kind, "text": args.text}, ensure_ascii=False))
            return 0
        my_id = numeric(str(session().state.get("uid", "")))
        if my_id == to_id:
            raise ValueError("RECIPIENT_IS_SELF")
        if args.kind == "text" and not (args.text or "").strip():
            raise ValueError("MESSAGE_LENGTH_OUT_OF_RANGE")
        args.conversation_file = str(save_state(my_id, to_id, create(my_id, to_id)))
        args.command = "send"
    if args.command == "listen":
        device = args.device_id or session().state.get("tokens", {}).get("device_id")
        if not device:
            raise ValueError("DEVICE_ID_MISSING")
        result = listen(
            "im",
            device_id=str(device),
            duration=args.duration,
            max_events=args.max_events,
            output=args.output,
        )
    elif args.command == "create":
        my_id, to_id = numeric(args.my_user_id), numeric(args.to_user_id)
        if my_id == to_id:
            raise ValueError("RECIPIENT_IS_SELF")
        if not args.confirm:
            result = {
                "ok": True,
                "preview": True,
                "action": "create",
                "my_user_id": str(my_id),
                "to_user_id": str(to_id),
            }
        else:
            if str(session().state.get("uid", "")) != str(my_id):
                raise ValueError("API_ACCOUNT_MISMATCH")
            path = save_state(my_id, to_id, create(my_id, to_id))
            result = {
                "ok": True,
                "conversation_file": str(path),
                "to_user_id": str(to_id),
            }
    else:
        state = load_state(args.conversation_file)
        if args.command == "info":
            if str(session().state.get("uid", "")) != state["my_user_id"]:
                raise ValueError("API_ACCOUNT_MISMATCH")
            current = inspect(state)
            path = save_state(
                int(state["my_user_id"]), int(state["to_user_id"]), current
            )
            result = {
                "ok": True,
                "conversation_file": str(path),
                "to_user_id": state["to_user_id"],
            }
        elif not args.confirm:
            result = {
                "ok": True,
                "preview": True,
                "kind": args.kind,
                "to_user_id": state["to_user_id"],
                "text": args.text,
            }
        else:
            if str(session().state.get("uid", "")) != state["my_user_id"]:
                raise ValueError("API_ACCOUNT_MISMATCH")
            content = (
                json.loads(Path(args.content_file).expanduser().read_text())
                if args.content_file
                else None
            )
            if content is not None and not isinstance(content, dict):
                raise ValueError("MESSAGE_OBJECT_REQUIRED")
            if args.kind == "text":
                content = (args.text or "").strip()
                if not content or len(content) > 1000:
                    raise ValueError("MESSAGE_LENGTH_OUT_OF_RANGE")
                msg_type = 7
            elif args.kind in ("image", "video", "file"):
                if not args.file:
                    raise ValueError("MEDIA_FILE_REQUIRED")
                msg_type, content = upload_attachment(
                    args.file, args.kind, state["my_user_id"], args.thumb
                )
            elif args.kind in ("audio", "sticker"):
                if not content:
                    raise ValueError(
                        "VOICE_CONTENT_REQUIRED"
                        if args.kind == "audio"
                        else "STICKER_CONTENT_REQUIRED"
                    )
                msg_type = (
                    (109 if args.encrypted else 17) if args.kind == "audio" else 5
                )
            else:
                if args.kind == "card-user" and not content and args.share:
                    raise ValueError("USER_CARD_OBJECT_REQUIRED")
                if not content and args.share:
                    content = (
                        call("detail", {"aweme_id": item_id(args.share)}).get(
                            "aweme_detail"
                        )
                        if args.kind in ("card-video", "card-photos")
                        else args.share
                    )
                if not content:
                    raise ValueError("CARD_CONTENT_REQUIRED")
                builder, msg_type = {
                    "card-video": (MessagePayload.build_share_aweme_content, 8),
                    "card-photos": (MessagePayload.build_share_photos_content, 77),
                    "card-web": (MessagePayload.build_share_web_content, 26),
                    "card-user": (MessagePayload.build_user_card_content, 25),
                }[args.kind]
                content = builder(content)
            accepted = send(state, content, msg_type)
            result = {
                "ok": True,
                "accepted": accepted["accepted"],
                "to_user_id": state["to_user_id"],
                "kind": args.kind,
            }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DouyinRequestError, ValueError, OSError) as exc:
        code = (
            exc.code
            if isinstance(exc, DouyinRequestError)
            else str(exc)
            if str(exc).isupper()
            else "IM_CLIENT_ERROR"
        )
        print(json.dumps({"ok": False, "error": code}))
        raise SystemExit(
            2
            if code
            in ("API_SESSION_MISSING", "API_SESSION_EXPIRED", "PLATFORM_AUTH_REJECTED")
            else 1
        )
