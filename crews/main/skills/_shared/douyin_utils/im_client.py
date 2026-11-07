"""Local IM protocol operations using the shared API login and Relay signing."""
import base64
import hashlib
import json
import re
import time
import uuid
from functools import wraps
from .http import DouyinRequestError, _session, prepare, request, session
from . import http
from .session import session_lock
from .api import call
from .login import refresh_channel, refresh_security, security_fields
from .im_wire import (conversation_body, create_body, envelope, parse_response,
                      send_text_body, send_content_body, validate_extension)

IM_HOST = "imapi.douyin.com"
IM_BASE = "https://imapi.douyin.com"


def operation(stage, path=None):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except DouyinRequestError as exc:
                if not getattr(exc, "im_stage", None):
                    exc.im_stage = stage
                if path and exc.request_info is None:
                    exc.request_info = {"profile": "passport" if stage == "identity_token" else "im",
                        "method": "GET" if stage == "identity_token" else "POST",
                        "host": "www.douyin.com" if stage == "identity_token" else IM_HOST,
                        "path": path}
                raise
        return wrapped
    return decorate


def cookie_values(current, url="https://www.douyin.com/"):
    return dict(part.strip().split("=", 1) for part in current.cookies(url).split(";") if "=" in part)


def binding(current=None):
    current = current or session()
    cookies = cookie_values(current)
    token = cookies.get("sessionid") or cookies.get("sessionid_ss")
    if not token:
        raise DouyinRequestError("API_SESSION_EXPIRED")
    value = [str(current.state.get("uid", "")), current.ua,
             cookies.get("sessionid", ""), cookies.get("sessionid_ss", "")]
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def numeric(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("INVALID_USER_ID")
    if not re.fullmatch(r"[1-9][0-9]{0,18}", str(value)) or int(value) >= 2**63:
        raise ValueError("INVALID_USER_ID")
    return int(value)


def account(expected_uid=None):
    current = session()
    uid = str(numeric(current.state.get("uid", "")))
    if expected_uid is not None and uid != str(expected_uid):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    fingerprint = binding(current)
    if (current.state.get("relay_security_expires_at", 0) < time.time() + 60 or
            not {"ticket", "ts_sign", "private_key"} <= security_fields(current)):
        refresh_security(uid)
    if binding() != fingerprint:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    main_token()
    call("self", expected_uid=uid)
    if binding() != fingerprint or str(session().state.get("uid")) != uid:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    return uid, fingerprint


def main_token():
    state = session().state
    token = state.get("tokens", {}).get("msToken")
    if not token or state.get("session_channels", {}).get("web", 0) < time.time() + 30:
        refresh_channel("web")
        token = session().state.get("tokens", {}).get("msToken")
    if not token:
        raise DouyinRequestError("SESSION_TOKEN_MISSING")
    return token


def fingerprint_params():
    fp = cookie_values(session()).get("s_v_web_id")
    return {"verifyFp": fp, "fp": fp} if fp else {}


def participants(state):
    my_id, to_id = numeric(state.get("my_user_id")), numeric(state.get("to_user_id"))
    match = re.fullmatch(r"0:1:([1-9][0-9]*):([1-9][0-9]*)", str(state.get("conversation_id", "")))
    if my_id == to_id or not match or set(match.groups()) != {str(my_id), str(to_id)}:
        raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
    numeric(state.get("conversation_short_id"))
    if not isinstance(state.get("ticket"), str) or not state["ticket"]:
        raise ValueError("CONVERSATION_INCOMPLETE")
    return my_id, to_id


@operation("identity_token", "/passport/safe/get_identity_security_token/")
def identity_token(expected_uid) -> tuple[str, str]:
    current = session()
    if str(current.state.get("uid", "")) != str(expected_uid):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    fingerprint = binding(current)
    cache = current.state.get("im_identity", {})
    if cache.get("binding") == fingerprint and cache.get("expires_at", 0) > time.time():
        return cache["token"], cache.get("device_id", "")
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
            "msToken": main_token(),
        },
        expected_uid=expected_uid,
        static_headers={
            "Referer": "https://www.douyin.com/chat?isPopup=1",
            "X-TT-Passport-Trace-ID": trace_id,
            "Accept": "application/json, text/javascript",
        },
    )
    if not isinstance(data, dict) or data.get("message") not in (None, "success"):
        raise DouyinRequestError("IDENTITY_TOKEN_REJECTED")
    values = data.get("data") or {}
    if not isinstance(values, dict):
        raise DouyinRequestError("IDENTITY_TOKEN_MISSING")
    token = values.get("identity_security_token")
    device_id = values.get("device_id")
    if not isinstance(token, str) or not token:
        raise DouyinRequestError("IDENTITY_TOKEN_MISSING")
    with session_lock(http.API_SESSION_FILE):
        current = session()
        if binding(current) != fingerprint:
            raise DouyinRequestError("API_ACCOUNT_MISMATCH")
        current.state["im_identity"] = {"binding": fingerprint, "token": token,
            "device_id": str(device_id or ""), "expires_at": time.time() + 240}
        current.save()
    return token, str(device_id or "")


@operation("conversation_create", "/v2/conversation/create")
def create(my_id: int, to_id: int) -> dict:
    my_id, to_id = numeric(my_id), numeric(to_id)
    if my_id == to_id:
        raise ValueError("RECIPIENT_IS_SELF")
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
    if not isinstance(data.get("context"), str) or not data["context"]:
        raise DouyinRequestError("IM_PREPARE_INCOMPLETE")
    validate_extension(extension)
    response = request(
        "im", "request", "POST", url,
        raw_body=unsigned + extension,
        expected_uid=my_id,
        context=data.get("context"),
        content_type="application/x-protobuf",
        static_headers={"Accept": "application/x-protobuf", "Referer": "https://www.douyin.com/"},
        binary_response=True,
    )
    conversation = parse_response(response, expect_conversation=True, expected_command=609)
    match = re.fullmatch(r"0:1:([0-9]+):([0-9]+)", conversation["conversation_id"])
    if not match or set(match.groups()) != {str(my_id), str(to_id)}:
        raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
    return conversation


@operation("conversation_refresh", "/v2/conversation/get_info_list")
def inspect(state: dict) -> dict:
    participants(state)
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
        static_headers={"Accept": "application/x-protobuf", "Referer": "https://www.douyin.com/"},
        binary_response=True,
    )
    conversation = parse_response(response, expect_conversation=True, expected_command=610)
    if (
        conversation["conversation_id"] != state["conversation_id"]
        or conversation["conversation_short_id"] != int(state["conversation_short_id"])
    ):
        raise ValueError("CONVERSATION_ACCOUNT_MISMATCH")
    return conversation


@operation("message_prepare", "/v1/message/send")
def send(state, message, message_type=7, *, client_message_id=None, before_send=None, on_response=None):
    participants(state)
    client_message_id = client_message_id or str(uuid.uuid4())
    token, device_id = identity_token(state["my_user_id"])
    _, ua = _session(IM_HOST)
    body = (
        send_text_body(
            str(state["conversation_id"]),
            int(state["conversation_short_id"]),
            str(state["ticket"]),
            message,
            client_message_id=client_message_id,
        )
        if isinstance(message, str)
        else send_content_body(
            str(state["conversation_id"]),
            int(state["conversation_short_id"]),
            str(state["ticket"]),
            message_type,
            message,
            client_message_id=client_message_id,
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
        params={"msToken": main_token(), **fingerprint_params()},
        raw_body=raw,
        before_send=before_send,
        on_response=on_response,
        expected_uid=state["my_user_id"],
        content_type="application/x-protobuf",
        static_headers={"Accept": "application/x-protobuf", "Referer": "https://www.douyin.com/"},
        binary_response=True,
    )
    try:
        return parse_response(response, expected_command=100, expected_client_message_id=client_message_id)
    except ValueError as exc:
        raise DouyinRequestError(str(exc)) from exc
