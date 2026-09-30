"""Small protocol encoder/decoder for the fields used by the IM client."""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid


MAX_WIRE_BYTES = 1024 * 1024


def varint(value: int) -> bytes:
    if not isinstance(value, int) or value < 0 or value > 2**64 - 1:
        raise ValueError("INVALID_WIRE_INTEGER")
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def number(field: int, value: int) -> bytes:
    return varint(field << 3) + varint(value)


def blob(field: int, value: bytes) -> bytes:
    return varint((field << 3) | 2) + varint(len(value)) + value


def text(field: int, value: str) -> bytes:
    return blob(field, value.encode("utf-8"))


def _pair(key: str, value: str) -> bytes:
    return blob(15, text(1, key) + text(2, value))


def envelope(
    command: int,
    body: bytes,
    ua: str,
    *,
    identity_token: str = "",
    identity_device_id: str = "",
    device: dict | None = None,
) -> bytes:
    """Build a platform request envelope; Relay supplies only dynamic fields."""
    sdk_version = os.environ.get("DOUYIN_IM_SDK_VERSION", "")
    build_number = os.environ.get("DOUYIN_IM_BUILD_NUMBER", "")
    if not sdk_version or not build_number:
        raise ValueError("IM_PROTOCOL_CONFIG_MISSING")
    device = device or {}
    headers = {
        "session_aid": "6383",
        "session_did": "0",
        "app_name": "douyin_pc",
        "priority_region": "cn",
        "user_agent": ua,
        "cookie_enabled": "true",
        "browser_language": "zh-CN",
        "browser_platform": str(device.get("browser_platform", "Win32")),
        "browser_name": "Mozilla",
        "browser_version": ua.removeprefix("Mozilla/"),
        "browser_online": "true",
        "screen_width": str(device.get("screen_width", 1920)),
        "screen_height": str(device.get("screen_height", 1080)),
        "referer": "https://www.douyin.com/jingxuan",
        "timezone_name": "Asia/Shanghai",
        "deviceId": "0",
        "is-retry": "0",
    }
    if identity_token:
        headers["identity_security_token"] = json.dumps(
            {"token": identity_token}, separators=(",", ":")
        )
        headers["identity_security_device_id"] = identity_device_id
        headers["identity_security_aid"] = ""
    result = b"".join(
        (
            number(1, command),
            number(2, secrets.randbelow(1000) + 10000),
            text(3, sdk_version),
            number(5, 3),
            number(6, 0),
            text(7, build_number),
            blob(8, blob(command, body)),
            text(9, "0"),
            text(11, "douyin_pc"),
            text(14, "360000"),
        )
    )
    result += b"".join(_pair(key, value) for key, value in headers.items())
    result += number(18, 4) + text(21, "douyin_web") + text(22, "web_sdk")
    return result


def create_body(my_id: int, to_id: int) -> bytes:
    return number(1, 1) + blob(2, varint(to_id) + varint(my_id))


def conversation_body(conversation_id: str, short_id: int) -> bytes:
    data = text(1, conversation_id) + number(2, short_id) + number(3, 1)
    return blob(1, data)


def send_text_body(
    conversation_id: str, short_id: int, ticket: str, message: str
) -> bytes:
    return send_content_body(
        conversation_id,
        short_id,
        ticket,
        7,
        {"aweType": 700, "type": 0, "richTextInfos": [], "text": message},
    )


def send_content_body(
    conversation_id: str, short_id: int, ticket: str, message_type: int, content: dict
) -> bytes:
    message_id = str(uuid.uuid4())
    payload = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    result = (
        text(1, conversation_id) + number(2, 1) + number(3, short_id) + text(4, payload)
    )
    for key, value in (
        ("s:mentioned_users", ""),
        ("s:client_message_id", message_id),
        ("s:stime", f"{int(time.time() * 1000)}.{secrets.randbelow(100000):05d}"),
    ):
        result += blob(5, text(1, key) + text(2, value))
    return result + number(6, message_type) + text(7, ticket) + text(8, message_id)


def fields(data: bytes) -> dict[int, list[int | bytes]]:
    if len(data) > MAX_WIRE_BYTES:
        raise ValueError("WIRE_RESPONSE_TOO_LARGE")
    result: dict[int, list[int | bytes]] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        field, wire = tag >> 3, tag & 7
        if field == 0:
            raise ValueError("INVALID_WIRE_FIELD")
        if wire == 0:
            value, offset = _read_varint(data, offset)
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            if offset + length > len(data):
                raise ValueError("TRUNCATED_WIRE_RESPONSE")
            value = data[offset : offset + length]
            offset += length
        elif wire == 1:
            if offset + 8 > len(data):
                raise ValueError("TRUNCATED_WIRE_RESPONSE")
            value = data[offset : offset + 8]
            offset += 8
        elif wire == 5:
            if offset + 4 > len(data):
                raise ValueError("TRUNCATED_WIRE_RESPONSE")
            value = data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError("UNSUPPORTED_WIRE_TYPE")
        result.setdefault(field, []).append(value)
    return result


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("TRUNCATED_WIRE_RESPONSE")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError("INVALID_WIRE_VARINT")


def first(data: dict[int, list[int | bytes]], field: int) -> int | bytes | None:
    values = data.get(field, [])
    return values[0] if values else None


def string(value: int | bytes | None) -> str:
    if not isinstance(value, bytes):
        return ""
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("INVALID_WIRE_TEXT") from exc


def parse_response(data: bytes, *, expect_conversation: bool = False) -> dict:
    outer = fields(data)
    error = string(first(outer, 3))
    message = string(first(outer, 4))
    if error or (message and message != "OK"):
        raise ValueError("PLATFORM_IM_REJECTED")
    if not expect_conversation:
        if message != "OK":
            raise ValueError("PLATFORM_IM_UNCONFIRMED")
        return {"accepted": True}
    body = first(outer, 6)
    if not isinstance(body, bytes):
        raise ValueError("CONVERSATION_MISSING")
    response_body = fields(body)
    listing = first(response_body, 609) or first(response_body, 610)
    if not isinstance(listing, bytes):
        raise ValueError("CONVERSATION_MISSING")
    listing_fields = fields(listing)
    item = first(listing_fields, 1)
    if not isinstance(item, bytes):
        raise ValueError("CONVERSATION_MISSING")
    conversation = fields(item)
    conversation_id = string(first(conversation, 1))
    short_id = first(conversation, 2)
    ticket = string(first(conversation, 4))
    if not conversation_id or not isinstance(short_id, int) or not ticket:
        raise ValueError("CONVERSATION_INCOMPLETE")
    return {
        "conversation_id": conversation_id,
        "conversation_short_id": short_id,
        "ticket": ticket,
    }
