"""Typed IM requests and a bounded reader for platform response variants."""

from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from .proto import Request_pb2 as pb


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
    protocol: dict | None = None,
) -> bytes:
    """Build a platform request envelope; Relay supplies only dynamic fields."""
    protocol = protocol or {}
    sdk_version = os.environ.get("DOUYIN_IM_SDK_VERSION") or protocol.get("sdk_version", "")
    build_number = os.environ.get("DOUYIN_IM_BUILD_NUMBER") or protocol.get("build_number", "")
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
        if identity_device_id:
            headers["identity_security_device_id"] = identity_device_id
        headers["identity_security_aid"] = ""
    result = pb.Request(cmd=command, sequence_id=secrets.randbelow(1001) + 10000,
                        sdk_version=sdk_version, refer=3, build_number=build_number,
                        device_id="0", device_platform="douyin_pc", version_code="360000",
                        auth_type=4, biz="douyin_web", access="web_sdk")
    name = {609: "create_conversation_v2_body", 610: "get_conversation_info_list_v2_body",
            100: "send_message_body"}.get(command)
    if not name:
        raise ValueError("IM_COMMAND_UNSUPPORTED")
    getattr(result.body, name).ParseFromString(body)
    result.headers.update(headers)
    return result.SerializeToString()


def create_body(my_id: int, to_id: int) -> bytes:
    return pb.CreateConversationV2RequestBody(
        conversation_type=1, participants=[to_id, my_id]).SerializeToString()


def conversation_body(conversation_id: str, short_id: int) -> bytes:
    return pb.GetConversationInfoListV2RequestBody(data=pb.GetConversationInfoListV2ResponseBodyData(
        conversation_id=conversation_id, conversation_short_id=short_id,
        conversation_type=1)).SerializeToString()


def send_text_body(conversation_id, short_id, ticket, message, *, client_message_id=None):
    return send_content_body(conversation_id, short_id, ticket, 7,
        {"aweType": 700, "type": 0, "richTextInfos": [], "text": message},
        client_message_id=client_message_id)


def send_content_body(conversation_id, short_id, ticket, message_type, content,
                      *, client_message_id=None):
    ident = client_message_id or str(uuid.uuid4())
    if str(uuid.UUID(ident)) != ident:
        raise ValueError("INVALID_CLIENT_MESSAGE_ID")
    result = pb.SendMessageRequestBody(conversation_id=conversation_id, conversation_type=1,
        conversation_short_id=short_id, content=json.dumps(content, ensure_ascii=False,
        separators=(",", ":")), message_type=message_type, ticket=ticket, client_message_id=ident)
    for key, value in (("s:mentioned_users", ""), ("s:client_message_id", ident),
                       ("s:stime", f"{int(time.time() * 1000)}.{secrets.randbelow(100000):05d}")):
        result.ext.add(key=key, value=value)
    return result.SerializeToString()


def validate_extension(encoded):
    """A create extension can add only one request signature field."""
    values = fields(encoded)
    if set(values) != {25} or len(values[25]) != 1 or not string(values[25][0]):
        raise ValueError("IM_PREPARE_INCOMPLETE")
    return encoded


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


def send_result(sent, expected_client_message_id=None):
    """Read the send body shared by JSON and binary IM envelopes."""
    if isinstance(sent, bytes):
        values = fields(sent)
        if any(len(values.get(k, [])) > 1 for k in (1, 3, 4, 5)):
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
        if first(values, 4) is not None and not isinstance(first(values, 4), bytes):
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
        sent = {"server_message_id": first(values, 1), "status": first(values, 3),
                "client_message_id": string(first(values, 4)), "check_code": first(values, 5)}
    if any(value is not None and (type(value) not in (int, str) or value not in (0, "0"))
           for value in (sent.get("status"), sent.get("check_code"))):
        raise ValueError("PLATFORM_IM_REJECTED")
    returned_client_id = sent.get("client_message_id")
    if expected_client_message_id and returned_client_id and returned_client_id != expected_client_message_id:
        raise ValueError("PLATFORM_IM_RESPONSE_MISMATCH")
    ident = sent.get("server_message_id")
    if (type(ident) not in (int, str) or not str(ident).isascii() or not str(ident).isdigit()
            or not 0 < int(ident) < 2**63):
        raise ValueError("PLATFORM_IM_UNCONFIRMED")
    return {"accepted": True, "evidence": "business-response", "server_message_id": str(ident)}


def parse_response(
    data: bytes, *, expect_conversation: bool = False, expected_command: int | None = None,
    expected_client_message_id: str | None = None,
) -> dict:
    """Accept the platform's JSON or protobuf response without logging tickets."""
    if len(data) > MAX_WIRE_BYTES:
        raise ValueError("WIRE_RESPONSE_TOO_LARGE")
    if not data:
        raise ValueError("PLATFORM_IM_UNCONFIRMED")
    if data.lstrip().startswith((b"{", b"[")):
        try:
            result = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE") from exc
        if not isinstance(result, dict):
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
        status = result.get("status_code")
        if status is not None and (type(status) not in (int, str) or status not in (0, "0")):
            raise ValueError("PLATFORM_IM_REJECTED")
        message = result.get("message")
        if message is not None and not isinstance(message, str):
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
        if message and message != "OK" or result.get("error_desc") not in (None, "", "OK"):
            raise ValueError("PLATFORM_IM_REJECTED")
        command = result.get("cmd")
        if expected_command is not None and str(command) != str(expected_command):
            raise ValueError("PLATFORM_IM_UNCONFIRMED")
        if expect_conversation and status is None and (message != "OK" or result.get("error_desc")):
            raise ValueError("PLATFORM_IM_UNCONFIRMED")
        if not expect_conversation:
            body = result.get("body")
            sent = body.get("send_message_body") if isinstance(body, dict) else None
            if isinstance(sent, dict):
                return send_result(sent, expected_client_message_id)
            elif message != "OK" and not (status in (0, "0") and result.get("error_desc") == "OK"):
                raise ValueError("PLATFORM_IM_UNCONFIRMED")
            return {"accepted": True, "evidence": "platform-ack"}
        names = {
            609: "create_conversation_v2_body",
            610: "get_conversation_info_list_v2_body",
        }
        name = names.get(expected_command or command)
        body = result.get("body")
        if not name or not isinstance(body, dict):
            raise ValueError("CONVERSATION_MISSING")
        listing = body.get(name)
        if listing is None and name == "get_conversation_info_list_v2_body":
            listing = body.get("get_conversation_info_list_v2_response_body")
        if not isinstance(listing, dict):
            raise ValueError("CONVERSATION_MISSING")
        conversation = listing.get("conversation")
        if not isinstance(conversation, dict):
            items = listing.get("conversation_info_list")
            if (
                not isinstance(items, list)
                or len(items) != 1
                or not isinstance(items[0], dict)
            ):
                raise ValueError("CONVERSATION_MISSING")
            conversation = items[0]
        if any(listing.get(k) not in (None, 0, "0") for k in ("status", "check_code")):
            raise ValueError("PLATFORM_IM_REJECTED")
    else:
        try:
            outer = fields(data)
        except ValueError as exc:
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE") from exc
        if any(len(outer.get(k, [])) > 1 for k in (1, 3, 4, 6)):
            raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
        status = first(outer, 3)
        numeric_status = isinstance(status, int)
        # Current envelopes put status_code at 3, error_desc at 4 and log_id at 7.
        # The description is "OK" on success; log_id is never an error message.
        message = string(first(outer, 4))
        if (
            (numeric_status and status != 0)
            or (not numeric_status and string(status))
            or (message and message != "OK")
        ):
            raise ValueError("PLATFORM_IM_REJECTED")
        if expected_command is not None and first(outer, 1) != expected_command:
            raise ValueError("PLATFORM_IM_UNCONFIRMED")
        if not expect_conversation:
            body = first(outer, 6)
            if isinstance(body, bytes):
                response_body = fields(body)
                if len(response_body.get(100, [])) > 1:
                    raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
                sent = first(response_body, 100)
                if sent is not None:
                    if not isinstance(sent, bytes):
                        raise ValueError("PLATFORM_IM_INVALID_RESPONSE")
                    return send_result(sent, expected_client_message_id)
            if message != "OK":
                raise ValueError("PLATFORM_IM_UNCONFIRMED")
            return {"accepted": True, "evidence": "platform-ack"}
        body = first(outer, 6)
        if not isinstance(body, bytes):
            raise ValueError("CONVERSATION_MISSING")
        response_body = fields(body)
        listing = (
            first(response_body, expected_command)
            if expected_command
            else first(response_body, 609) or first(response_body, 610)
        )
        if not isinstance(listing, bytes):
            raise ValueError("CONVERSATION_MISSING")
        item = first(fields(listing), 1)
        if not isinstance(item, bytes):
            raise ValueError("CONVERSATION_MISSING")
        item_fields = fields(item)
        if not isinstance(first(item_fields, 2), int):
            nested = first(item_fields, 1)
            if not isinstance(nested, bytes):
                raise ValueError("CONVERSATION_MISSING")
            item_fields = fields(nested)
        conversation = {
            "conversation_id": string(first(item_fields, 1)),
            "conversation_short_id": first(item_fields, 2),
            "ticket": string(first(item_fields, 4)),
        }
    conversation_id = conversation.get("conversation_id")
    short_id = conversation.get("conversation_short_id")
    ticket = conversation.get("ticket")
    if (
        not isinstance(conversation_id, str)
        or not conversation_id
        or isinstance(short_id, bool)
        or not isinstance(short_id, (str, int))
        or not str(short_id).isdigit()
        or not 0 < int(short_id) < 2**63
        or not isinstance(ticket, str)
        or not ticket
    ):
        raise ValueError("CONVERSATION_INCOMPLETE")
    return {
        "conversation_id": conversation_id,
        "conversation_short_id": int(short_id),
        "ticket": ticket,
    }
