# encoding: utf-8
"""XHS live-room and IM transport owned by expert-bd.

All HTTP shapes in this module are taken from Chrome Network captures.  The
WebSocket helper exposes the wire envelope and implements the current captured
protobuf constructors for private messages and live-room text events.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import time
import uuid
from typing import Any, AsyncIterator, Mapping, Optional
from urllib.parse import urlencode, quote

from xhs_utils.http_util import REQUEST_TIMEOUT
from xhs_utils.xhs_pc import XHSPcAuth
from xhs_utils.xhs_pc.params import (
    build_pc_live_headers,
    build_pc_business_headers,
    generate_request_params,
    splice_str,
)


LIVE_ORIGIN = "https://live-room.xiaohongshu.com"
PUSH_URL = "wss://apppush-rws.xiaohongshu.com/rwp"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)

RSA_N = int(
    "d321555d67813eace010dc27e72ab14876a9b671c7d58d3c9c2064cd60f7e9f7"
    "9ad3799657b35a1b7654d82725408a71549d5ade11e74bbf1ec39b549ed32116a"
    "ffd4f6b03f2c9c44d91f84157b159a8a225150916e2716cc82dc8fd62385e5a"
    "01c83b784c139462a1dd45d47d96ebb4f5068c42b3de8590123a03565a9e5aed",
    16,
)
RSA_E = 65537
RSA_BYTES = 128
RSA_CHUNK_BYTES = RSA_BYTES - 11


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _b64(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    return base64.b64encode(raw).decode("ascii")


def rsa_encrypt_short_link_payload(payload: bytes) -> bytes:
    """RSAES-PKCS1-v1_5 encrypt the IM protobuf in browser-sized chunks."""
    raw = bytes(payload)
    encrypted = bytearray()
    for offset in range(0, len(raw), RSA_CHUNK_BYTES):
        chunk = raw[offset:offset + RSA_CHUNK_BYTES]
        padding_length = RSA_BYTES - len(chunk) - 3
        padding = bytearray()
        while len(padding) < padding_length:
            padding.extend(byte for byte in secrets.token_bytes(padding_length) if byte)
        encoded = b"\x00\x02" + bytes(padding[:padding_length]) + b"\x00" + chunk
        cipher = pow(int.from_bytes(encoded, "big"), RSA_E, RSA_N)
        encrypted.extend(cipher.to_bytes(RSA_BYTES, "big"))
    return bytes(encrypted)


def _require_value(value: Any, name: str) -> str:
    """Require a captured scalar instead of silently accepting an empty one."""
    if value is None or str(value) == "":
        raise ValueError(f"{name} is required from the browser capture")
    return str(value)


def _pb_varint(value: int) -> bytes:
    """Encode one protobuf unsigned varint without a runtime dependency."""
    value = int(value)
    if value < 0:
        raise ValueError("protobuf varint values must be non-negative")
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _pb_field(number: int, wire_type: int, payload: bytes) -> bytes:
    return _pb_varint((int(number) << 3) | int(wire_type)) + payload


def _pb_string(number: int, value: str) -> bytes:
    raw = str(value).encode("utf-8")
    return _pb_field(number, 2, _pb_varint(len(raw)) + raw)


def _pb_bool(number: int, value: bool) -> bytes:
    return _pb_field(number, 0, _pb_varint(1 if value else 0))


def _pb_uint(number: int, value: int) -> bytes:
    return _pb_field(number, 0, _pb_varint(int(value)))


def _pb_message(number: int, value: bytes) -> bytes:
    return _pb_field(number, 2, _pb_varint(len(value)) + value)


def _pb_read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift >= 64:
            raise ValueError("invalid protobuf varint")
    raise ValueError("truncated protobuf varint")


def _pb_read_fields(data: bytes) -> dict[int, list[tuple[int, Any]]]:
    """Read the small scalar/length-delimited subset used by the IM schema."""
    fields: dict[int, list[tuple[int, Any]]] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _pb_read_varint(data, offset)
        number, wire_type = tag >> 3, tag & 7
        if wire_type == 0:
            value, offset = _pb_read_varint(data, offset)
        elif wire_type == 2:
            length, offset = _pb_read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError("truncated protobuf field")
            value, offset = data[offset:end], end
        else:
            raise ValueError(f"unsupported protobuf wire type: {wire_type}")
        fields.setdefault(number, []).append((wire_type, value))
    return fields


def _pb_text(value: bytes) -> str:
    return value.decode("utf-8")


def encode_im_chat_command(command: Mapping[str, Any]) -> bytes:
    """Encode the captured ``ChatCommand`` message (fields 1..4)."""
    required = ("type", "useStrategy", "strategy", "info")
    missing = [key for key in required if key not in command]
    if missing:
        raise ValueError("ChatCommand missing captured fields: " + ", ".join(missing))
    # protobufjs emits fields in field-number order.  Keep the same order even
    # when a caller supplies an insertion-ordered mapping differently.
    return b"".join((
        _pb_uint(1, command["type"]),
        _pb_bool(2, command["useStrategy"]),
        _pb_uint(3, command["strategy"]),
        _pb_string(4, command["info"]),
    ))


def encode_im_chat_message(*, mid: str, ts: int, token: str, sender: str,
                           receiver: str, content: str, content_type: int,
                           nickname: str, group_chat: bool,
                           command: Optional[Mapping[str, Any]], ref_id: str,
                           trigger_source: int) -> bytes:
    """Encode browser ``ChatSendMessage`` + ``ChatOneMessage`` protobuf bytes.

    Every constructor field is mandatory at the Python boundary, including
    empty strings and an explicit ``command=None``.  This prevents callers
    from silently dropping fields that the browser supplies to protobufjs.
    Default-valued fields are omitted by protobuf wire encoding exactly as in
    the browser bundle.
    """
    command_bytes = b"" if command is None else encode_im_chat_command(command)
    send = b"".join((
        _pb_string(1, mid), _pb_uint(2, ts), _pb_string(3, token),
        _pb_string(4, sender), _pb_string(5, receiver),
        _pb_string(6, content), _pb_uint(7, content_type),
        _pb_string(8, nickname), _pb_bool(9, group_chat),
        _pb_message(10, command_bytes) if command is not None else b"",
        _pb_string(11, ref_id), _pb_uint(12, trigger_source),
    ))
    return _pb_uint(1, 1) + _pb_message(9, send)


def decode_im_chat_ack(payload: bytes | bytearray | memoryview) -> dict[str, Any]:
    """Decode ``ChatOneMessage.chatACK`` and return browser field names."""
    outer = _pb_read_fields(bytes(payload))
    ack_values = outer.get(5)
    if not ack_values:
        raise ValueError("protobuf payload does not contain ChatACK field 5")
    ack = _pb_read_fields(ack_values[-1][1])
    def scalar(number: int, default: Any = 0) -> Any:
        values = ack.get(number)
        if not values:
            return default
        wire_type, value = values[-1]
        if wire_type == 0:
            return int(value)
        return value
    return {
        "mid": _pb_text(scalar(1, b"")),
        "messageid": _pb_text(scalar(2, b"")),
        "ts": int(scalar(3, 0)),
        "token": _pb_text(scalar(4, b"")),
        "code": int(scalar(5, 0)),
        "msg": _pb_text(scalar(6, b"")),
        "storeid": int(scalar(7, 0)),
    }


def decode_im_chat_message(payload: bytes | bytearray | memoryview) -> dict[str, Any]:
    """Decode the browser ``ChatOneMessage.chatMessage`` envelope.

    ``ChatMessage`` is the inbound private-message branch (outer field 4):
    ``mid``, ``messageid``, ``ts``, ``token``, and a string ``payload``.  The
    payload is parsed as JSON when the current browser message uses JSON and
    is otherwise retained as the original string.
    """
    outer = _pb_read_fields(bytes(payload))
    values = outer.get(4)
    if not values:
        raise ValueError("protobuf payload does not contain ChatMessage field 4")
    fields = _pb_read_fields(values[-1][1])

    def text(number: int) -> str:
        entries = fields.get(number)
        return _pb_text(entries[-1][1]) if entries else ""

    def number(number: int) -> int:
        entries = fields.get(number)
        return int(entries[-1][1]) if entries else 0

    raw_payload = text(5)
    result: dict[str, Any] = {
        "mid": text(1),
        "messageid": text(2),
        "ts": number(3),
        "token": text(4),
        "payload": raw_payload,
    }
    try:
        result["payload_json"] = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        pass
    return result


def decode_im_one_message(payload: bytes | bytearray | memoryview) -> dict[str, Any]:
    """Decode the observed ``ChatOneMessage`` inbound branches."""
    data = bytes(payload)
    outer = _pb_read_fields(data)
    result: dict[str, Any] = {}
    if outer.get(4):
        result["chatMessage"] = decode_im_chat_message(data)
    if outer.get(5):
        result["chatACK"] = decode_im_chat_ack(data)
    if not result:
        raise ValueError("protobuf payload has no supported ChatOneMessage branch")
    return result


def decode_room_push(frame: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Decode captured server-push room items from one RWP ``t=4`` frame.

    Chrome receives a room frame shaped as ``b.d = {a, b, biz, t}``, where
    ``b`` is an array of items.  Each item carries a base64 UTF-8 JSON string
    in ``d`` plus the captured envelope fields ``e`` and ``m``.  The decoded
    result keeps those fields and parses ``customData`` without inventing a
    room event schema.
    """
    if not isinstance(frame, Mapping) or frame.get("t") != 4:
        return []
    data = ((frame.get("b") or {}).get("d")
            if isinstance(frame.get("b"), Mapping) else None)
    if not isinstance(data, Mapping) or data.get("biz") != "room":
        return []
    items = data.get("b")
    if not isinstance(items, list):
        return []
    decoded: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            # Keep the item visible to callers even if a future release adds
            # a non-object entry to the push batch.
            decoded.append({"payload": None, "decode_error": "item is not an object",
                             "envelope": {"raw": item}})
            continue
        if not isinstance(item.get("d"), str):
            decoded.append({"payload": None, "decode_error": "item.d is not base64 text",
                            "envelope": dict(item)})
            continue
        try:
            payload = json.loads(base64.b64decode(item["d"]).decode("utf-8"))
        except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # Do not silently discard an event (gift, audience count, or a
            # newly introduced type) merely because its encoding changed.
            decoded.append({"payload": None, "decode_error": str(exc),
                            "envelope": dict(item)})
            continue
        if not isinstance(payload, dict):
            decoded.append({"payload": payload, "decode_error": "decoded payload is not an object",
                            "envelope": dict(item)})
            continue
        custom = payload.get("customData")
        if isinstance(custom, str):
            try:
                payload["customData"] = json.loads(custom)
            except json.JSONDecodeError:
                # Preserve the browser value when a future event changes its
                # customData encoding instead of silently dropping it.
                pass
        event = {
            "payload": payload,
            # The event name is data supplied by Chrome.  Exposing it as a
            # convenience does not impose a schema on future event types.
            "event_type": (payload.get("customData", {}).get("type")
                           if isinstance(payload.get("customData"), Mapping)
                           else payload.get("command")),
            "envelope": dict(item),
        }
        decoded.append(event)
    return decoded


def encode_room_text_payload(*, room_id: str, room_type: str, command: int,
                              nickname: str, avatar: str, user_id: str,
                              content: str, priority: int, role: int) -> bytes:
    """Encode the current browser live-chat text payload as UTF-8 JSON.

    Module ``13123`` in the live page constructs this exact object before
    passing it to the RWP room dispatcher.  All profile and envelope values
    are required here so a caller cannot silently omit a browser field.
    """
    custom_data = {
        "type": "text",
        "priority": int(priority),
        "profile": {
            "nickname": str(nickname),
            "avatar": str(avatar),
            "user_id": str(user_id),
            "role": int(role),
        },
        "desc": str(content),
    }
    payload = {
        "roomId": str(room_id),
        "roomType": str(room_type),
        "command": int(command),
        "customData": _compact(custom_data),
    }
    return _compact(payload).encode("utf-8")


def _insert_after(headers: Mapping[str, str], key: str, value: str,
                  after: str) -> dict[str, str]:
    """Insert a captured live-only header at its observed relative position."""
    result: dict[str, str] = {}
    inserted = False
    for name, current in headers.items():
        if name.lower() in {key.lower(), after.lower()}:
            if name.lower() == key.lower():
                continue
        result[name] = current
        if name.lower() == after.lower():
            result[key] = value
            inserted = True
    if not inserted:
        result[key] = value
    return result


class XHSWebSocket:
    """Async push connection using the exact RWP JSON envelope observed in Chrome."""

    def __init__(self, auth: XHSPcAuth, *, uid: Optional[str] = None,
                 device_id: Optional[str] = None, fingerprint: Optional[str] = None,
                 sid: Optional[str] = None, websocket_url: str = PUSH_URL):
        self.auth = auth
        self.uid = str(uid or auth.user_id or "")
        self.device_id = str(device_id or "")
        self.fingerprint = str(fingerprint or "")
        self.sid = str(sid or "")
        self.websocket_url = websocket_url
        self.ws = None
        # Frames received while waiting for a transport ack are replayed to
        # the caller through events() instead of being dropped.
        self._pending_texts: list[str] = []

    @staticmethod
    def _storage_value(storage: Mapping[str, Any], key: str) -> str:
        value = storage.get(key, "")
        if isinstance(value, (dict, list)):
            return ""
        return str(value or "")

    @classmethod
    def from_auth_storage(cls, auth: XHSPcAuth, *, websocket_url: str = PUSH_URL) -> "XHSWebSocket":
        """Build a push client from Auth-managed browser-equivalent storage.

        The three names are the exact keys used by the current web client.  A
        missing value remains empty and is rejected by ``connect`` rather than
        being fabricated.
        """
        local = dict(getattr(auth, "local_storage", {}) or {})
        session = dict(getattr(auth, "session_storage", {}) or {})
        token = local.get("RWP_LOGIN_TOKEN", "")
        if isinstance(token, str):
            try:
                token = json.loads(token)
            except json.JSONDecodeError:
                token = {}
        session_state = getattr(getattr(auth, "profile", None), "session", None)
        if isinstance(token, Mapping) and token.get("expiredAt") is not None:
            try:
                expired = int(token["expiredAt"]) <= int(time.time() * 1000)
            except (TypeError, ValueError):
                expired = True
            if expired:
                token = {}
                auth.update_runtime_state(local_storage={"RWP_LOGIN_TOKEN": ""})
                if session_state is not None:
                    session_state.set_rwp_login_token({})
        sid = token.get("aLt", "") if isinstance(token, Mapping) else ""
        uid = token.get("uid", "") if isinstance(token, Mapping) else ""
        if isinstance(token, Mapping) and token.get("uid") and auth.user_id:
            if str(token["uid"]) != str(auth.user_id):
                raise ValueError("RWP_LOGIN_TOKEN uid does not match the authenticated user")
        if not sid and session_state is not None:
            sid = (getattr(session_state, "rwp_login_token", {}) or {}).get("aLt", "")
        device_id = cls._storage_value(session, "XHS_TAB_DEVICE_ID")
        fingerprint = cls._storage_value(session, "XHS_RWP_FINGERPRINT")
        if session_state is not None:
            device_id = device_id or str(getattr(session_state, "tab_device_id", "") or "")
            fingerprint = fingerprint or str(getattr(session_state, "rwp_fingerprint", "") or "")
        return cls(
            auth,
            uid=str(uid or auth.user_id or ""),
            sid=str(sid or ""),
            device_id=device_id,
            fingerprint=fingerprint,
            websocket_url=websocket_url,
        )

    @staticmethod
    def message_id() -> str:
        return uuid.uuid4().hex[:14] + "-" + format(int(time.time() * 1000), "x")[-11:]

    @classmethod
    def envelope(cls, *, transport_type: int, message_id: Optional[str] = None,
                 body: Optional[Mapping[str, Any]] = None) -> str:
        frame = {"v": 1, "t": transport_type}
        if message_id is not None:
            frame["m"] = message_id
        if body is not None:
            frame["b"] = body
        return _compact(frame)

    def handshake(self) -> str:
        auth_info = {"authType": "generic", "sid": self.sid,
                     "uid": self.uid, "domain": "red"}
        device = {
            "deviceId": self.device_id,
            "fingerprint": self.fingerprint,
            "platform": "browser", "os": "web", "osVersion": "10.15",
            "deviceName": "Chrome", "appVersion": "131.0.0.0",
            "userAgent": BROWSER_UA,
        }
        payload = {"appId": "xhs-pc", "authInfo": auth_info,
                   "deviceInfo": device, "serviceTag": "",
                   "bizInfos": [
                       {"bizName": "dqa_chatsearch", "serializeType": "protobuf"},
                       {"bizName": "xhs_dots_pc", "serializeType": "protobuf"},
                       {"bizName": "push", "serializeType": "json"}],
                   "roomInfo": [], "roomInfos": [], "tagInfo": [],
                   "extInfo": {}, "state": 1}
        return self.envelope(transport_type=2, message_id=self.message_id(),
                             body={"d": {"a": 1, "s": 0, "b": payload}})

    def register(self, biz_name: str, serialize_type: str) -> str:
        return self.envelope(transport_type=2, message_id=self.message_id(),
                             body={"d": {"a": 1, "s": 1,
                                          "b": {"bizInfo": {"bizName": biz_name,
                                                             "serializeType": serialize_type},
                                                "register": True}}})

    def join_room(self, room_id: str) -> str:
        return self.envelope(transport_type=2, message_id=self.message_id(),
                             body={"d": {"a": 1, "s": 8,
                                          "b": {"info": {"bizName": "room",
                                                          "roomId": str(room_id),
                                         "roomType": "LIVE"}}}})

    @classmethod
    def state_sync(cls) -> str:
        """Return the captured RWP state-sync frame (``s=6``, empty body).

        Chrome emits this transport frame periodically after room registration.
        It is distinct from the application-level ``t=0`` keepalive and must
        retain the empty ``b`` object observed on the wire.
        """
        return cls.envelope(
            transport_type=2,
            message_id=cls.message_id(),
            body={"d": {"a": 1, "s": 6, "b": {}}},
        )

    @classmethod
    def transport_heartbeat(cls) -> str:
        """Return the exact RWP keepalive frame observed in Chrome."""
        return cls.envelope(transport_type=0)

    def heartbeat(self, room_id: str, *, profile: Mapping[str, Any]) -> str:
        required = ("nickname", "avatar", "user_id", "role")
        missing = [key for key in required if key not in profile]
        if missing:
            raise ValueError("heartbeat profile missing captured fields: " + ", ".join(missing))
        ordered_profile = {key: profile[key] for key in required}
        ordered_profile.update({key: value for key, value in profile.items()
                                if key not in ordered_profile})
        custom = {"type": "viewer_heart", "priority": 0,
                  "profile": ordered_profile, "source": "web_live", "desc": ""}
        data = {"roomId": str(room_id), "roomType": "LIVE", "command": 1,
                "customData": _compact(custom)}
        return self.envelope(transport_type=3, message_id=self.message_id(),
                             body={"d": {"a": 0, "c": "liveHeartBeat", "biz": "room",
                                          "b": _b64(_compact(data)), "e": {}, "s": "rrmp.o.l"}})

    def business_frame(self, biz: str, payload: bytes | str, *, command: str,
                       service_id: str = "rrmp.o.l", action: int = 0) -> str:
        """Wrap a captured protobuf body for an RWP business channel."""
        if not biz or not command:
            raise ValueError("biz and command must be supplied from a browser capture")
        return self.envelope(transport_type=3, message_id=self.message_id(),
                             body={"d": {"a": int(action), "c": command, "biz": str(biz),
                                          "b": _b64(payload), "e": {}, "s": service_id}})

    def im_frame(self, payload: bytes | str, *, command: str) -> str:
        """Build an IM frame from the exact protobuf bytes captured from Chrome.

        ``payload`` may be raw protobuf bytes or an already serialized string.
        The protobuf schema is release-managed by XHS and is intentionally not
        guessed here; callers can pass the bytes produced by their captured UI.
        """
        # Chrome uses action=2 for client-originated IM ``sendMessage``
        # frames.  Action 0 is used by room heartbeats and server-style
        # dispatches, so it must not be reused for private-message sends.
        return self.business_frame("im", payload, command=command,
                                   service_id="rrmp.b.i", action=2)

    def room_frame(self, payload: bytes | str, *, command: str) -> str:
        """Wrap the browser's text-comment room body.

        Room receives are decoded generically, but the public send surface is
        intentionally limited to comments.  Gift/commerce commands are never
        generated or replayed by this client.
        """
        if command != "sendMessage":
            raise ValueError("room_frame only permits the captured text command sendMessage")
        return self.business_frame("room", payload, command=command)

    def room_text_frame(self, *, room_id: str, room_type: str, command: int,
                        nickname: str, avatar: str, user_id: str,
                        content: str, priority: int, role: int) -> str:
        """Build the browser's current live-room text ``sendMessage`` frame."""
        payload = encode_room_text_payload(
            room_id=room_id, room_type=room_type, command=command,
            nickname=nickname, avatar=avatar, user_id=user_id,
            content=content, priority=priority, role=role,
        )
        return self.room_frame(payload, command="sendMessage")

    async def _wait_transport_ack(self, message_id: str, *, operation: str,
                                  timeout: float = 10.0) -> dict[str, Any]:
        """Wait for the ``t=2`` reply matching ``message_id`` and require c=0.

        Unrelated frames received meanwhile are buffered and later replayed by
        ``events()``.
        """
        import asyncio
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{operation} ack not received within {timeout}s")
            message = await asyncio.wait_for(self.ws.receive(), timeout=remaining)
            if message.type.name != "TEXT":
                raise ConnectionError(
                    f"WebSocket ended while waiting for {operation} ack: {message.type.name}"
                )
            try:
                frame = json.loads(message.data)
            except json.JSONDecodeError:
                frame = None
            if not isinstance(frame, dict) or frame.get("m") != message_id:
                self._pending_texts.append(message.data)
                continue
            ack = (frame.get("b") or {}).get("a") or {}
            if ack.get("c") != 0:
                raise ConnectionError(
                    f"{operation} rejected: c={ack.get('c')} m={ack.get('m')!r}"
                )
            return frame

    async def connect(self, *, room_id: Optional[str] = None):
        import aiohttp
        if not self.uid or not self.sid or not self.device_id or not self.fingerprint:
            raise ValueError("uid, sid, device_id and fingerprint are not ready in Auth state")
        cookie_url = self.websocket_url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
        self._session = aiohttp.ClientSession(
            cookies=self.auth.cookies_for_url(cookie_url),
            headers={"User-Agent": BROWSER_UA},
        )
        self.ws = await self._session.ws_connect(
            # Chrome sends an application-level ``{"v":1,"t":0}`` frame;
            # aiohttp's protocol-level ping would be a different wire shape.
            self.websocket_url, heartbeat=None,
            origin="https://www.xiaohongshu.com",
        )
        # The browser sends register/join only after the handshake ack (the
        # ``c=0`` reply carrying socketId).  Sending them back-to-back races
        # server-side auth and every follow-up frame is rejected with
        # ``3100001 Account has not privilege``.
        handshake = self.handshake()
        await self.ws.send_str(handshake)
        await self._wait_transport_ack(json.loads(handshake)["m"], operation="handshake")
        await self.ws.send_str(self.register("im", "protobuf"))
        if room_id is not None:
            await self.ws.send_str(self.register("room", "json"))
            await self.ws.send_str(self.join_room(room_id))
        return self

    async def send_transport_heartbeat(self):
        """Send one captured application-level RWP keepalive frame."""
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send_str(self.transport_heartbeat())

    async def send_state_sync(self):
        """Send one captured ``t=2,s=6,b={}`` state-sync frame."""
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send_str(self.state_sync())

    async def send_heartbeat(self, room_id: str, *, profile: Mapping[str, Any]):
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send_str(self.heartbeat(room_id, profile=profile))

    async def send_im(self, payload: bytes | str, *, command: str):
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        await self.ws.send_str(self.im_frame(payload, command=command))

    @staticmethod
    def _captured_wire_frame(frame: str, *, operation: str) -> str:
        """Validate a complete browser-captured RWP frame before sending."""
        if not isinstance(frame, str) or not frame:
            raise ValueError(f"{operation} requires a non-empty captured frame")
        try:
            value = json.loads(frame)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{operation} frame is not valid JSON") from exc
        if not isinstance(value, dict) or value.get("v") != 1 or "t" not in value or "b" not in value:
            raise ValueError(f"{operation} frame missing captured v/t/b fields")
        body = value.get("b")
        if not isinstance(body, dict) or not isinstance(body.get("d"), dict):
            raise ValueError(f"{operation} frame missing captured b.d envelope")
        data = body["d"]
        for key in ("a", "c", "biz", "b", "e", "s"):
            if key not in data:
                raise ValueError(f"{operation} frame missing captured field b.d.{key}")
        if not isinstance(data["b"], str) or not data["b"]:
            raise ValueError(f"{operation} frame b.d.b must be captured base64")
        return frame

    async def send_captured_im_frame(self, frame: str):
        """Send one complete IM RWP frame copied from Chrome Network."""
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        frame = self._captured_wire_frame(frame, operation="send_captured_im_frame")
        data = json.loads(frame)["b"]["d"]
        if data["biz"] != "im":
            raise ValueError("captured IM frame b.d.biz must be im")
        await self.ws.send_str(frame)
        return {"frame": frame}

    async def send_captured_room_frame(self, frame: str):
        """Send one complete captured text-comment frame copied from Chrome."""
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        frame = self._captured_wire_frame(frame, operation="send_captured_room_frame")
        data = json.loads(frame)["b"]["d"]
        if data["biz"] != "room":
            raise ValueError("captured room frame b.d.biz must be room")
        if data.get("c") != "sendMessage":
            raise ValueError("only captured room sendMessage comment frames may be sent")
        try:
            payload = json.loads(base64.b64decode(data["b"]).decode("utf-8"))
            custom = payload.get("customData")
            if isinstance(custom, str):
                custom = json.loads(custom)
            if not isinstance(custom, Mapping) or custom.get("type") != "text":
                raise ValueError
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("captured room frame must contain a text comment payload") from exc
        await self.ws.send_str(frame)
        return {"frame": frame}

    def im_chat_frame(self, *, mid: str, ts: int, token: str, sender: str,
                      receiver: str, content: str, content_type: int,
                      nickname: str, group_chat: bool,
                      command: Optional[Mapping[str, Any]], ref_id: str,
                      trigger_source: int) -> tuple[str, str]:
        """Build a browser-shaped IM ``sendMessage`` frame without sending it."""
        payload = encode_im_chat_message(
            mid=mid, ts=ts, token=token, sender=sender, receiver=receiver,
            content=content, content_type=content_type, nickname=nickname,
            group_chat=group_chat, command=command, ref_id=ref_id,
            trigger_source=trigger_source,
        )
        return self.im_frame(payload, command="sendMessage"), mid

    async def send_chat_message(self, *, mid: str, ts: int, token: str,
                                sender: str, receiver: str, content: str,
                                content_type: int, nickname: str,
                                group_chat: bool,
                                command: Optional[Mapping[str, Any]],
                                ref_id: str, trigger_source: int):
        """Send an explicitly captured IM message and return its wire frame.

        ``command`` is deliberately explicit: pass ``None`` only when the
        captured browser message had no command object.  This method does not
        invent recipient, profile, or trigger fields.
        """
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        frame, message_id = self.im_chat_frame(
            mid=mid, ts=ts, token=token, sender=sender, receiver=receiver,
            content=content, content_type=content_type, nickname=nickname,
            group_chat=group_chat, command=command, ref_id=ref_id,
            trigger_source=trigger_source,
        )
        await self.ws.send_str(frame)
        return {"mid": message_id, "frame": frame}

    async def send_private_message(
        self,
        receiver: str,
        content: str,
        *,
        content_type: int = 1,
    ):
        """Send one private message using the current Chrome constructor defaults."""
        if not receiver:
            raise ValueError("receiver is required")
        if content is None:
            raise ValueError("content is required")
        if not self.auth.user_id:
            raise ValueError("auth.user_id is required; use an initialized PC Auth")
        return await self.send_chat_message(
            mid=str(uuid.uuid4()),
            ts=int(time.time() * 1000),
            token="",
            sender=str(self.auth.user_id),
            receiver=str(receiver),
            content=str(content),
            content_type=int(content_type),
            nickname="",
            group_chat=False,
            command=None,
            ref_id="",
            trigger_source=1,
        )

    async def send_room(self, payload: bytes | str, *, command: str):
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        if command != "sendMessage":
            raise ValueError("send_room only permits the captured text command sendMessage")
        await self.ws.send_str(self.room_frame(payload, command=command))

    async def send_room_text(self, *, room_id: str, room_type: str,
                             command: int, nickname: str, avatar: str,
                             user_id: str, content: str, priority: int,
                             role: int):
        """Send one browser-shaped live-room text message.

        This is intentionally a single explicit operation.  Gift and other
        room actions are receive-only; their schemas are neither inferred nor
        sent by this client.
        """
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        frame = self.room_text_frame(
            room_id=room_id, room_type=room_type, command=command,
            nickname=nickname, avatar=avatar, user_id=user_id,
            content=content, priority=priority, role=role,
        )
        await self.ws.send_str(frame)
        return {"frame": frame}

    @staticmethod
    def _decode_text_frame(data: str) -> dict[str, Any]:
        try:
            frame = json.loads(data)
        except json.JSONDecodeError:
            return {"raw": data}
        # IM protobuf bytes travel in two envelopes: a single base64 string
        # (``b.d.b``, t=3 dispatches) or a t=4 push batch where ``b.d.b`` is a
        # list of items each carrying base64 in ``d`` — the same batch shape
        # as room pushes.  Preserve the original frame and add decoded views.
        decoded_views: dict[str, Any] = {}
        try:
            payload = frame.get("b", {}).get("d", {})
            if payload.get("biz") == "im":
                body = payload.get("b")
                if isinstance(body, str) and body:
                    decoded_views["im"] = decode_im_one_message(base64.b64decode(body))
                elif isinstance(body, list):
                    items: list[dict[str, Any]] = []
                    for item in body:
                        if isinstance(item, dict) and isinstance(item.get("d"), str):
                            try:
                                items.append(decode_im_one_message(base64.b64decode(item["d"])))
                            except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
                                items.append({"decode_error": str(exc), "envelope": dict(item)})
                        else:
                            items.append({"decode_error": "item.d is not base64 text",
                                          "envelope": item if isinstance(item, dict) else {"raw": item}})
                    if items:
                        decoded_views["im"] = items
        except (AttributeError, KeyError, TypeError, ValueError, binascii.Error) as exc:
            # Preserve an IM event when a future protobuf branch or
            # encoding appears; callers can inspect the original
            # base64 in the untouched frame instead of losing it.
            decoded_views["im_error"] = str(exc)
        if "im" not in decoded_views:
            # The reply to a sent IM frame (t=3) carries the chatACK protobuf
            # in ``b.a.b``.  Handshake replies keep an object there, so only a
            # string body is attempted, and non-IM payloads simply fail to
            # parse and are left untouched.
            try:
                ack_body = frame.get("b", {}).get("a", {}).get("b")
                if isinstance(ack_body, str) and ack_body:
                    decoded_views["im"] = decode_im_one_message(base64.b64decode(ack_body))
            except (AttributeError, KeyError, TypeError, ValueError,
                    binascii.Error, UnicodeDecodeError):
                pass
        room_events = decode_room_push(frame)
        if room_events:
            decoded_views["room"] = room_events
        if decoded_views:
            frame["decoded"] = decoded_views
        return frame

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self.ws is None:
            raise RuntimeError("WebSocket is not connected")
        while self._pending_texts:
            yield self._decode_text_frame(self._pending_texts.pop(0))
        async for message in self.ws:
            if message.type.name == "TEXT":
                yield self._decode_text_frame(message.data)
            else:
                yield {"type": message.type.name, "data": message.data}

    async def close(self):
        if self.ws is not None:
            await self.ws.close()
        if getattr(self, "_session", None) is not None:
            await self._session.close()


class XHSLiveAPI:
    """Signed live-room HTTP APIs plus chat history endpoints."""

    def __init__(self, auth: XHSPcAuth):
        if not isinstance(auth, XHSPcAuth):
            raise TypeError("XHSLiveAPI requires XHSPcAuth")
        self.auth = auth
        self.http = auth.http_client
        self.base_url = LIVE_ORIGIN
        self.edith_url = auth.origin("api")

    def _request(self, origin: str, api: str, *, method: str = "GET",
                 data: Any = "", referer: str = "https://www.xiaohongshu.com/",
                 extra_headers: Optional[Mapping[str, str]] = None):
        context = self.auth.next_sign_context(api)
        b1 = self.auth.current_b1(context["now"])
        headers, cookies, body = generate_request_params(
            self.auth.cookies, api, data, method,
            user_id=self.auth.user_id, b1=b1, dsl_pair=self.auth.dsl_pair,
            doc_cookie=self.auth.sign_cookie, tier=context["tier"],
            sign_context=context,
            include_client_hints=False,
            include_trace_headers=origin != self.base_url,
        )
        headers["referer"] = referer
        target = origin + api
        headers["user-agent"] = BROWSER_UA
        if origin == self.base_url:
            headers = _insert_after(headers, "xy-common-params", "platform=web", "referer")
        for key, value in dict(extra_headers or {}).items():
            # `c_device_id` is the one current PC request that appears between
            # x-xray-traceid and x-t; other captured live metadata follows the
            # signing headers after x-s-common.
            anchor = "x-xray-traceid" if str(key).lower() == "c_device_id" else "x-s-common"
            headers = _insert_after(headers, str(key), str(value), anchor)
        wire_cookies = self.auth.cookies_for_url(target, cookies)
        if origin == self.base_url:
            headers = build_pc_live_headers(headers, wire_cookies, method=method)
        else:
            headers = build_pc_business_headers(headers, wire_cookies, api=api, method=method)
        if method.upper() == "GET":
            response = self.http.get(target, headers=headers, cookies=wire_cookies,
                                     proxies=self.auth.proxies, timeout=REQUEST_TIMEOUT)
        else:
            response = self.http.post(target, headers=headers, data=body.encode("utf-8"),
                                      cookies=wire_cookies, proxies=self.auth.proxies,
                                      timeout=REQUEST_TIMEOUT)
        response_cookies = getattr(response, "cookies", None)
        if response_cookies is not None and hasattr(response_cookies, "items"):
            updates = dict(response_cookies.items())
            if updates:
                # Preserve host-only edge cookies (notably acw_tc) for the
                # next request to this exact live or IM origin.
                self.auth.update_cookies(updates, source_url=target)
        return response.json()

    def _live_get(self, path: str, params: Mapping[str, Any]):
        return self._request(self.base_url, splice_str(path, params), method="GET")

    def list_categories(self):
        return self._live_get("/api/sns/red/live/web/feed/category", {})

    def square_feed(self, *, source: int = 13, category: str = "",
                    pre_source: str = "", size: int = 27,
                    image_formats: tuple[str, ...] = ("jpg", "webp", "avif")):
        extra = _compact({"image_formats": list(image_formats)})
        # Chrome leaves ':' and ',' readable inside the encoded extra_info value.
        query = "source={}&category={}&pre_source={}&extra_info={}&size={}".format(
            source, quote(category, safe=""), quote(pre_source, safe=""),
            quote(extra, safe=":,"), size)
        return self._request(self.base_url,
                             "/api/sns/red/live/web/feed/v1/squarefeed?" + query,
                             method="GET")

    def current_room_info(self, room_id: str, *, request_user_id: Optional[str] = None,
                          source: str = "web_live", client_type: int = 1):
        # Chrome fills this required query member from the active account when
        # the caller does not override it.  Keep the field in the signed query
        # rather than dropping it for anonymous/empty values.
        room_id = _require_value(room_id, "room_id")
        if request_user_id is None:
            request_user_id = self.auth.user_id
        request_user_id = _require_value(request_user_id, "request_user_id")
        return self._request(self.base_url, splice_str("/api/sns/red/live/web/v1/room/current_room_info", {
            "room_id": room_id, "request_user_id": request_user_id,
            "source": source, "client_type": client_type}), method="GET",
            extra_headers={"x-ratelimit-meta": f"roomId={room_id}"})

    def join_room(self, room_id: str, *, view_session_id: Optional[str] = None,
                  host_id: str = "",
                  source: str = "web_live", pre_source: str = "pc_web",
                  client_type: int = 1, app_id: int = 1):
        room_id = _require_value(room_id, "room_id")
        # Chrome generates this required field as ``<user_id>-<epoch_ms>`` for
        # each join.  An explicitly captured value is retained verbatim.
        if view_session_id is None or str(view_session_id) == "":
            view_session_id = f"{_require_value(self.auth.user_id, 'user_id')}-{int(time.time()*1000)}"
        body = {"room_id": str(room_id), "source": source, "pre_source": pre_source,
                "client_type": client_type, "app_id": app_id,
                "view_session_id": str(view_session_id)}
        meta = f"roomId={room_id}" + (f"&hostId={host_id}" if host_id else "")
        return self._request(self.base_url, "/api/sns/red/live/web/v1/center/room/join/room",
                             method="POST", data=body,
                             extra_headers={"x-ratelimit-meta": meta})

    def viewer_heart(
        self,
        room_id: str,
        host_id: str,
        heart_duration: int,
        view_session_id: Optional[str] = None,
        *,
        source: str = "web_feed",
        pre_source: str = "",
    ):
        """Report live-room viewing time using the captured JSON body shape."""
        room_id = _require_value(room_id, "room_id")
        host_id = _require_value(host_id, "host_id")
        # The browser creates a viewer-heart session independently from the
        # join-room session.  Chrome's current wire value is
        # ``<user_id>_<epoch_ms>`` (underscore, not the join-room hyphen).
        # Preserve an explicitly captured value byte-for-byte; only synthesize
        # the value when the caller has no capture at all.
        if view_session_id is None or str(view_session_id) == "":
            view_session_id = f"{_require_value(self.auth.user_id, 'user_id')}_{int(time.time()*1000)}"
        view_session_id = _require_value(view_session_id, "view_session_id")
        body = {
            "room_id": str(room_id),
            "host_id": str(host_id),
            "heart_duration": int(heart_duration),
            "source": str(source),
            "pre_source": str(pre_source),
            "view_session_id": str(view_session_id),
        }
        return self._request(
            self.base_url,
            "/api/sns/red/live/v1/web/room_user/viewer_heart",
            method="POST",
            data=body,
        )

    def join_business_base_info(self, room_id: str, *, host_id: str = "", source: str = "web_live"):
        meta = f"roomId={room_id}" + (f"&hostId={host_id}" if host_id else "")
        return self._request(self.base_url, splice_str("/api/sns/red/live/web/v1/room/join_business_base_info",
                                                        {"room_id": room_id, "source": source}), method="GET",
                             extra_headers={"x-ratelimit-meta": meta})

    def user_card(self, user_id: str, room_id: str, *, query_room_id: Optional[str] = None,
                  force_host_view: bool = True, source: str = "web_live"):
        return self._live_get("/api/sns/red/live/web/{}/user_card".format(room_id), {
            "user_id": user_id, "room_id": query_room_id or room_id,
            "force_host_view": str(force_host_view).lower(), "source": source})

    def join_comment_info(self, room_id: str, *, source: str = "web_live",
                          pre_source: str = "pc_web", track_id: str = "",
                          client_type: int = 1, host_id: str = ""):
        meta = f"roomId={room_id}" + (f"&hostId={host_id}" if host_id else "")
        return self._request(self.base_url, splice_str("/api/sns/red/live/web/v1/room/join_comment_info", {
            "room_id": room_id, "source": source, "pre_source": pre_source,
            "track_id": track_id, "client_type": client_type}), method="GET",
            extra_headers={"x-ratelimit-meta": meta})

    def aggregate_business_info(self, room_id: str, host_id: str, *, client_type: int = 1):
        return self._request(self.base_url, splice_str("/api/sns/red/live/web/v1/room/aggregate_business_info", {
            "room_id": room_id, "host_id": host_id, "client_type": client_type}), method="GET",
            extra_headers={"x-ratelimit-meta": f"roomId={room_id}&hostId={host_id}"})

    def resource_by_id(self, source_id: str | int):
        """Fetch one live resource by its captured ``source_id``.

        The live page requests this endpoint when resolving gift/effect or
        other room resources.  ``source_id`` is the only observed query
        member and is required so the signer cannot produce an incomplete
        request.
        """
        if source_id is None or str(source_id) == "":
            raise ValueError("resource_by_id requires captured source_id")
        return self._live_get(
            "/api/sns/red/live/web/resource_by_id",
            {"source_id": str(source_id)},
        )

    def gift_panel(self, host_id: str, room_id: str, *,
                   scene: str = "web_gift_panel"):
        """Fetch the browser's read-only gift panel catalogue.

        Chrome sends the query in the observed order ``host_id``, ``room_id``,
        ``scene``.  ``scene`` is kept explicit at the boundary (with the
        captured browser value as its default) so callers cannot accidentally
        omit a field that participates in signing.
        """
        if not host_id or not room_id:
            raise ValueError("gift_panel requires captured host_id and room_id")
        return self._live_get("/api/sns/red/live/web/gift/v1/gift_panel", {
            "host_id": str(host_id), "room_id": str(room_id), "scene": str(scene),
        })

    def charge_panel(self, *, biz_scene: str = "web_charge_panel"):
        """Fetch the browser's read-only wallet/charge catalogue.

        Chrome requests this panel when opening the recharge entry point.  The
        endpoint may return a server-side real-name restriction (for example
        ``code=-50032``); this method deliberately does not attempt any charge
        or payment mutation.
        """
        if not biz_scene:
            raise ValueError("charge_panel requires captured biz_scene")
        return self._live_get("/api/sns/red/live/web/pay/v1/charge_panel", {
            "biz_scene": str(biz_scene),
        })

    def user_violation(self):
        """Read the current account's live-comment violation state."""
        return self._request(
            self.base_url,
            "/api/sns/red/live/web/comment/v1/user_violation",
            method="GET",
        )

    def send_comment(self, room_id: str, comment: str, *, host_id: str,
                     source: str = "web_live", client_type: int = 1):
        """Send a live comment using the captured HTTP endpoint.

        The body order mirrors Chrome exactly: ``room_id``, ``comment``,
        ``source``, ``client_type``.  This endpoint is intentionally separate
        from the room WebSocket text frame because the browser uses both
        transports depending on the current room state.
        """
        if not room_id or not host_id or comment is None:
            raise ValueError("send_comment requires captured room_id, host_id and comment")
        body = {
            "room_id": str(room_id),
            "comment": str(comment),
            "source": str(source),
            "client_type": int(client_type),
        }
        return self._request(
            self.base_url,
            "/api/sns/v1/live/web/interaction/send_comment",
            method="POST",
            data=body,
            extra_headers={"x-ratelimit-meta": f"roomId={room_id}&hostId={host_id}"},
        )

    def mic_relation(
        self,
        room_id: str,
        user_ids: list[str],
        *,
        sequence: int,
        client_type: int = 1,
        app_id: int = 1,
        source: str = "web_live",
    ):
        """Fetch the current live mic relation using the captured JSON shape.

        The browser sends this while a room has connected-mic participants. A
        sequence value is required because it is part of the observed body;
        callers must obtain it from their browser session instead of relying
        on a default.
        """
        if not user_ids:
            raise ValueError("mic_relation user_ids must come from the browser capture")
        body = {
            "room_id": str(room_id),
            "user_ids": [str(value) for value in user_ids],
            "client_type": int(client_type),
            "app_id": int(app_id),
            "source": str(source),
            "sequence": int(sequence),
        }
        return self._request(
            self.base_url,
            "/api/sns/red/live/web/v1/line/mic_relation",
            method="POST",
            data=body,
        )

    async def connect_push(self, *, sid: str, room_id: Optional[str] = None,
                           device_id: str = "", fingerprint: str = "") -> XHSWebSocket:
        client = XHSWebSocket(
            self.auth,
            uid=self.auth.user_id,
            sid=sid,
            device_id=device_id,
            fingerprint=fingerprint,
        )
        await client.connect(room_id=room_id)
        return client

    async def connect_push_from_storage(self, *, room_id: Optional[str] = None) -> XHSWebSocket:
        """Connect using auth storage, refreshing the server RWP token if needed.

        QR/phone HTTP login does not run a browser and therefore cannot receive
        ``RWP_LOGIN_TOKEN`` in localStorage.  When the token is absent, fetch
        the browser-issued token through the authenticated ``celestial/lt``
        endpoint, then build the same WebSocket client from the updated auth.
        """
        client = XHSWebSocket.from_auth_storage(self.auth)
        if not client.sid:
            self.get_celestial_lt()
            client = XHSWebSocket.from_auth_storage(self.auth)
        await client.connect(room_id=room_id)
        return client

    # IM history/read APIs observed on the message page.
    def get_chats(self, *, limit: int = 100, complete: bool = True, page: int = 0, source: str = "pc"):
        return self._request(self.edith_url, "/api/im/web/v3/chats?" + urlencode({
            "limit": limit, "complete": str(complete).lower(), "page": page, "source": source}), method="GET")

    def get_group_chats(self, *, limit: int = 100, complete: bool = True, page: int = 0, source: str = "pc"):
        return self._request(self.edith_url, "/api/im/web/chats/group?" + urlencode({
            "limit": limit, "complete": str(complete).lower(), "page": page, "source": source}), method="GET")

    def get_chat_info(self, chat_user_ids: str | list[str]):
        ids = ",".join(chat_user_ids) if isinstance(chat_user_ids, list) else str(chat_user_ids)
        return self._request(self.edith_url, "/api/im/web/v3/chats/info?" + urlencode({"chat_user_ids": ids}), method="GET")

    def get_message_history(self, chat_user_id: str, *, last_id: int = 0, start_id: int = 0, limit: int = 30):
        return self._request(self.edith_url, "/api/im/web/messages/history?" + urlencode({
            "chat_user_id": chat_user_id, "last_id": last_id, "start_id": start_id, "limit": limit}), method="GET")

    def get_following(self, *, page: int = 1, size: int = 200):
        return self._request(self.edith_url, "/api/im/web/users/following/all?" + urlencode({"page": page, "size": size}), method="GET")

    def get_unread(self):
        return self._request(self.edith_url, "/api/im/web/chat/get_unread", method="GET")

    def get_unread_count(self):
        """Return the global notification unread counters from the chat bootstrap.

        This is the exact ``GET /api/sns/web/unread_count`` request observed
        when opening the PC message page.  It is kept separate from
        :meth:`get_unread`, which targets the IM chat unread endpoint.
        """
        return self._request(self.edith_url, "/api/sns/web/unread_count", method="GET")

    def get_web_config(self):
        """Fetch the PC web configuration (captured empty POST body)."""
        return self._request(self.edith_url, "/api/sns/web/v1/config", method="POST", data="")

    def get_system_config(self):
        """Fetch the PC system configuration used by the message bootstrap."""
        return self._request(self.edith_url, "/api/sns/web/v1/system/config", method="GET")

    def get_user_me(self):
        """Return the currently authenticated PC user profile."""
        return self._request(self.edith_url, "/api/sns/web/v2/user/me", method="GET")

    def get_recent_chats(self):
        """Return the lightweight recent-chat list used by the chat sidebar."""
        return self._request(self.edith_url, "/api/sns/v1/im/web/get_recent_chats", method="GET")

    def get_emoji_config(self):
        return self._request(self.edith_url, "/api/im/web/emoji/config", method="GET")

    def get_redmoji_version(self):
        """Return the redmoji protocol version used by the message page."""
        return self._request(self.edith_url, "/api/im/redmoji/version", method="GET")

    @staticmethod
    def _captured_params(params: Mapping[str, Any], *, operation: str) -> dict[str, Any]:
        """Copy a browser-captured parameter object without inventing fields."""
        if not isinstance(params, Mapping) or not params:
            raise ValueError(f"{operation} requires a non-empty captured parameter mapping")
        # dict() retains the caller's insertion order, which is significant
        # for the request body and query string used by the browser signer.
        return dict(params)

    def get_message_config(self, *, register_time: int):
        """Fetch message configuration with the captured ``register_time``."""
        return self._request(
            self.edith_url,
            "/api/sns/v2/message/config?" + urlencode({"register_time": int(register_time)}),
            method="GET",
        )

    def voice_convert(self, params: Mapping[str, Any]):
        """Call the captured voice-conversion GET endpoint."""
        values = self._captured_params(params, operation="voice_convert")
        return self._request(
            self.edith_url,
            "/api/im/web/voice_convert?" + urlencode(list(values.items())),
            method="GET",
        )

    def get_all_offline_messages(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="get_all_offline_messages")
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/offline?" + urlencode(list(values.items())),
            method="GET",
        )

    def report_offline_message_ack(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="report_offline_message_ack")
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/ack",
            method="POST",
            data=values,
            extra_headers={"content-type": "application/json; charset=utf-8"},
        )

    def get_group_message_history(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="get_group_message_history")
        return self._request(
            self.edith_url,
            "/api/im/web/red/group/messages/history?" + urlencode(list(values.items())),
            method="GET",
        )

    def revoke_message(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="revoke_message")
        return self._request(
            self.edith_url, "/api/im/web/messages/revoke", method="POST", data=values,
        )

    def revoke_group_all_message(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="revoke_group_all_message")
        return self._request(
            self.edith_url, "/api/im/web/v1/group/remove_all_message", method="POST", data=values,
        )

    def report_total_unread(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="report_total_unread")
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/total_unread",
            method="POST",
            data=values,
            extra_headers={"content-type": "application/json; charset=utf-8"},
        )

    def get_message_location_list(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="get_message_location_list")
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/location/list?" + urlencode(list(values.items())),
            method="GET",
        )

    def report_message_location_read(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="report_message_location_read")
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/location/read",
            method="POST",
            data=values,
            extra_headers={"content-type": "application/json; charset=utf-8"},
        )

    def add_personal_emoji(self, params: Mapping[str, Any]):
        """Add a personal emoji using the browser's form-urlencoded body."""
        values = self._captured_params(params, operation="add_personal_emoji")
        form = urlencode(list(values.items()), doseq=True)
        return self._request(
            self.edith_url,
            "/api/im/web/v1/smiles/add",
            method="POST",
            data=form,
            extra_headers={"content-type": "application/x-www-form-urlencoded; charset=utf-8"},
        )

    def delete_personal_emoji(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="delete_personal_emoji")
        return self._request(
            self.edith_url, "/api/im/web/v1/smiles/delete", method="POST", data=values,
            extra_headers={"content-type": "application/json"},
        )

    def get_smile_file_id(self):
        return self._request(self.edith_url, "/api/im/web/v1/smiles/file_id", method="GET")

    def get_stick_top_messages(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="get_stick_top_messages")
        return self._request(
            self.edith_url,
            "/api/im/web/v1/group/stick_top/messages?" + urlencode(list(values.items())),
            method="GET",
        )

    def delete_message(self, params: Mapping[str, Any]):
        values = self._captured_params(params, operation="delete_message")
        return self._request(
            self.edith_url,
            "/api/sns/v6/message/web/delete_msg?" + urlencode(list(values.items())),
            method="GET",
        )

    def send_captured_short_link_message(self, message: str):
        """Send an already encrypted short-link payload captured from Chrome."""
        if not isinstance(message, str) or not message:
            raise ValueError(
                "send_captured_short_link_message requires captured encrypted message"
            )
        return self._request(
            self.edith_url,
            "/api/im/web/short_link/send_message",
            method="POST",
            data={"message": message},
        )

    def send_short_link_message(
        self,
        receiver: str,
        content: str,
        *,
        content_type: int = 1,
    ):
        """Send a private message through the HTTP RSA short-link fallback."""
        if not receiver:
            raise ValueError("receiver is required")
        if content is None:
            raise ValueError("content is required")
        if not self.auth.user_id:
            raise ValueError("auth.user_id is required; use an initialized PC Auth")
        payload = encode_im_chat_message(
            mid=str(uuid.uuid4()),
            ts=int(time.time() * 1000),
            token="",
            sender=str(self.auth.user_id),
            receiver=str(receiver),
            content=str(content),
            content_type=int(content_type),
            nickname="",
            group_chat=False,
            command=None,
            ref_id="",
            trigger_source=1,
        )
        encrypted = rsa_encrypt_short_link_payload(payload)
        return self.send_captured_short_link_message(encrypted.decode("latin-1"))

    def get_celestial_lt(self):
        """Refresh the browser-issued RWP login token.

        The endpoint requires the current tab device id as ``c_device_id``;
        callers must provide it through the captured session storage.
        """
        session = dict(getattr(self.auth, "session_storage", {}) or {})
        device_id = str(session.get("XHS_TAB_DEVICE_ID", "") or "")
        if not device_id:
            profile = getattr(self.auth, "profile", None)
            session_state = getattr(profile, "session", None)
            device_id = str(getattr(session_state, "tab_device_id", "") or "")
        if not device_id:
            raise ValueError("XHS_TAB_DEVICE_ID is required for celestial/lt")
        result = self._request(
            self.edith_url,
            "/api/sns/web/v1/celestial/lt",
            method="GET",
            extra_headers={"c_device_id": device_id},
        )
        data = (result or {}).get("data") or {}
        # Keep the returned token available to a subsequent push connection,
        # while preserving the browser's exact response field names.
        ttl_seconds = data.get("expiredTime", data.get("expired_time"))
        expires = None
        if ttl_seconds is not None:
            try:
                ttl_seconds = int(ttl_seconds)
                expires = int(time.time() * 1000) + ttl_seconds * 1000 // 2
            except (TypeError, ValueError):
                expires = None
        token = {
            "aLt": data.get("aLt", data.get("a_lt", "")),
            "rLt": data.get("rLt", data.get("r_lt", "")),
            "expiredAt": expires,
            "uid": self.auth.user_id,
        }
        if token["aLt"]:
            local = dict(getattr(self.auth, "local_storage", {}) or {})
            local["RWP_LOGIN_TOKEN"] = json.dumps(token, ensure_ascii=False, separators=(",", ":"))
            self.auth.update_runtime_state(local_storage=local)
        return result

    def detect_message_policy(self, *, source: str = "discovery"):
        return self._request(self.edith_url, "/api/sns/v6/message/web/detect?" + urlencode({"source": source}), method="GET")

    def mark_messages_read(self, chat_list: list[Mapping[str, Any]], *, chat_total_unread_count: int = 0,
                           mute_chat_total_unread_count: int = 0, stranger_total_unread_count: int = 0):
        required = ("chat_id", "read_store_id", "unread_count", "type", "need_rm_offline")
        normalized = []
        for item in chat_list:
            missing = [key for key in required if key not in item]
            if missing:
                raise ValueError(
                    "mark_messages_read chat item missing captured fields: "
                    + ", ".join(missing)
                )
            normalized.append({key: item[key] for key in required})
            normalized[-1].update({key: value for key, value in item.items() if key not in required})
        body = {"chat_list": normalized,
                "chat_total_unread_count": chat_total_unread_count,
                "mute_chat_total_unread_count": mute_chat_total_unread_count,
                "stranger_total_unread_count": stranger_total_unread_count}
        # Chrome's message page uses this exact media-type spelling for the
        # read acknowledgement (including the space and UTF-8 casing).
        return self._request(
            self.edith_url,
            "/api/im/web/v2/messages/read",
            method="POST",
            data=body,
            extra_headers={"content-type": "application/json; charset=UTF-8"},
        )


__all__ = [
    "XHSLiveAPI", "XHSWebSocket", "LIVE_ORIGIN", "PUSH_URL", "BROWSER_UA",
    "encode_im_chat_command", "encode_im_chat_message", "decode_im_chat_ack",
    "decode_im_chat_message", "decode_im_one_message", "decode_room_push",
    "encode_room_text_payload", "rsa_encrypt_short_link_payload",
]
