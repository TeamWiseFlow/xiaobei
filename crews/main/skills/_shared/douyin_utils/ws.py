"""Bounded WebSocket listeners. Handshake dynamics are supplied by Relay."""

import gzip
import io
import json
import os
import time
from urllib.parse import urlencode
from google.protobuf.json_format import MessageToDict
from .proto import Live_pb2, Response_pb2
from .pk import PKMessageHandler, PK_MESSAGES
from .http import DouyinRequestError, _merge_query, prepare, session

MAX_FRAME = 4 * 1024 * 1024


def live_decode(data, pk_handler):
    if len(data) > MAX_FRAME:
        raise ValueError("WS_FRAME_TOO_LARGE")
    frame = Live_pb2.PushFrame.FromString(data)
    if frame.payloadType in ("hb", "ack") or not frame.payload:
        return [], None
    raw = frame.payload
    if raw.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:
            raw = f.read(MAX_FRAME + 1)
        if len(raw) > MAX_FRAME:
            raise ValueError("WS_FRAME_TOO_LARGE")
    result = Live_pb2.LiveResponse.FromString(raw)
    ack = None
    if result.needAck:
        ack = Live_pb2.PushFrame(
            logId=frame.logId, payloadType="ack", payload=result.internalExt.encode()
        ).SerializeToString()
    events = []
    for item in result.messagesList:
        try:
            canonical = item.method.removeprefix("Webcast")
            if canonical in PK_MESSAGES:
                event = pk_handler.handle(item.method, item.payload, item.msgId)
                if event:
                    events.append(event)
                continue
            cls = getattr(Live_pb2, canonical, None)
            if cls is None:
                events.append(
                    {
                        "type": item.method,
                        "msg_id": str(item.msgId),
                        "unsupported": True,
                    }
                )
                continue
            message = cls.FromString(item.payload)
            events.append(
                {
                    "type": item.method,
                    "msg_id": str(item.msgId),
                    "data": MessageToDict(message, preserving_proto_field_name=True),
                }
            )
        except Exception:
            events.append({"type": "decode_error", "msg_id": str(item.msgId)})
    return events, ack


def im_decode(data):
    if len(data) > MAX_FRAME:
        raise ValueError("WS_FRAME_TOO_LARGE")
    frame = Live_pb2.PushFrame.FromString(data)
    if frame.payloadType == "pb":
        response = Response_pb2.Response.FromString(frame.payload)
        if not response.body.HasField("new_message_notify"):
            return []
        msg = response.body.new_message_notify.message
        try:
            content = json.loads(msg.content)
        except ValueError:
            content = {"text": msg.content}
        return [
            {
                "type": "im_message",
                "sender": str(msg.sender),
                "conversation_id": msg.conversation_id,
                "index": str(msg.index_in_conversation),
                "message_type": msg.message_type,
                "content": content,
            }
        ]
    if frame.payloadType == "text/json":
        return [{"type": "im_control", "data": json.loads(frame.payload)}]
    return []


def listen(
    profile,
    *,
    room_id=None,
    user_unique_id=None,
    device_id=None,
    duration=60,
    max_events=100,
    output=None,
    reconnect=2,
):
    if (
        not 1 <= duration <= 3600
        or not 1 <= max_events <= 10000
        or not 0 <= reconnect <= 5
    ):
        raise ValueError("INVALID_LISTENER_LIMIT")
    from websocket import create_connection, WebSocketTimeoutException

    deadline = time.monotonic() + duration
    count = 0
    connected = False
    verified = False
    seen = set()
    pk = PKMessageHandler()
    stream = None
    if output:
        fd = os.open(
            os.path.expanduser(output),
            os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )
        os.fchmod(fd, 0o600)
        stream = os.fdopen(fd, "a", encoding="utf-8")

    def emit(event):
        text = json.dumps(event, ensure_ascii=False)
        if stream:
            stream.write(text + "\n")
            stream.flush()
        else:
            print(text, flush=True)

    try:
        for attempt in range(reconnect + 1):
            if time.monotonic() >= deadline or count >= max_events:
                break
            state = session()
            if profile == "live":
                query = {
                    "app_name": "douyin_web",
                    "version_code": "180800",
                    "webcast_sdk_version": "1.0.14-beta.0",
                    "update_version_code": "1.0.14-beta.0",
                    "compress": "gzip",
                    "device_platform": "web",
                    "cookie_enabled": "true",
                    "browser_language": "zh-CN",
                    "browser_platform": state.state.get("device", {}).get(
                        "browser_platform", "Win32"
                    ),
                    "browser_name": "Mozilla",
                    "browser_version": state.ua.removeprefix("Mozilla/"),
                    "browser_online": "true",
                    "tz_name": "Asia/Shanghai",
                    "host": "https://live.douyin.com",
                    "aid": "6383",
                    "live_id": "1",
                    "did_rule": "3",
                    "endpoint": "live_pc",
                    "support_wrds": "1",
                    "user_unique_id": user_unique_id,
                    "identity": "audience",
                    "need_persist_msg_count": "15",
                    "insert_task_id": "",
                    "live_reason": "",
                    "room_id": room_id,
                    "heartbeatDuration": "0",
                }
                url = (
                    "wss://webcast100-ws-web-hl.douyin.com/webcast/im/push/v2/?"
                    + urlencode(query)
                )
                fields = {
                    "room_id": str(room_id),
                    "user_unique_id": str(user_unique_id),
                }
                host = "live.douyin.com"
            else:
                token = next(
                    (
                        c["value"]
                        for c in state.state["cookies"]
                        if c.get("name") == "sessionid"
                    ),
                    None,
                )
                if not token:
                    raise DouyinRequestError("API_SESSION_EXPIRED")
                config = state.state.get("im_ws", {})
                if not config.get("fpid"):
                    raise ValueError("IM_PROTOCOL_CONFIG_MISSING")
                query = {
                    "aid": "6383",
                    "device_platform": "douyin_pc",
                    "fpid": config["fpid"],
                    "device_id": str(device_id),
                    "token": token,
                }
                url = "wss://frontier-im.douyin.com/ws/v2?" + urlencode(query)
                fields = {"device_id": str(device_id)}
                host = "www.douyin.com"
            dynamic = prepare(profile, "websocket", url, method="GET", fields=fields)
            headers = dynamic.get("headers", {})
            if any(
                k.lower() in ("cookie", "host", "user-agent", "content-length")
                for k in headers
            ):
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            connection = None
            try:
                connection = create_connection(
                    _merge_query(url, dynamic["query"]),
                    header={"User-Agent": state.ua, **headers},
                    cookie=state.cookies("https://" + host + "/"),
                    origin="https://" + host,
                    timeout=min(10, max(1, deadline - time.monotonic())),
                    enable_multithread=True,
                    subprotocols=["binary", "base64", "pbbp2"]
                    if profile == "im"
                    else None,
                )
                connected = True
                pk = PKMessageHandler()
                next_heartbeat = time.monotonic() + 5
                while time.monotonic() < deadline and count < max_events:
                    if profile == "live" and time.monotonic() >= next_heartbeat:
                        connection.send_binary(
                            Live_pb2.PushFrame(payloadType="hb").SerializeToString()
                        )
                        next_heartbeat = time.monotonic() + 5
                    connection.settimeout(min(2, max(0.1, deadline - time.monotonic())))
                    try:
                        data = connection.recv()
                    except WebSocketTimeoutException:
                        continue
                    if not data:
                        break
                    if not isinstance(data, bytes):
                        continue
                    if profile == "live":
                        events, ack = live_decode(data, pk)
                        verified = True
                    else:
                        events = im_decode(data)
                        ack = None
                        verified = True
                    if ack:
                        connection.send_binary(ack)
                    for event in events:
                        key = event.get("msg_id") or (
                            str(event.get("conversation_id"))
                            + ":"
                            + str(event.get("index"))
                            if event.get("index")
                            else None
                        )
                        if key and key in seen:
                            continue
                        if key:
                            seen.add(key)
                        emit(event)
                        count += 1
                        if count >= max_events:
                            break
            except (DouyinRequestError, ValueError):
                raise
            except Exception:
                if attempt == reconnect:
                    raise DouyinRequestError("WEBSOCKET_DISCONNECTED")
                time.sleep(min(2**attempt, max(0, deadline - time.monotonic())))
            finally:
                if connection:
                    connection.close()
        return {
            "ok": True,
            "connected": connected,
            "frames_verified": verified,
            "events": count,
        }
    finally:
        if stream:
            stream.close()
