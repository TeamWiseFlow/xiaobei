"""relay_sign.py — client 侧调用 relay sign 服务的统一入口（Python）

平台规则：relay 只计算签名，
实际平台调用（登录 / 抓取 / 互动 / 上传 / 发布）**必须 client 端完成**。本模块供
其他平台的 Python skill 共用。RELAY_BASE_URL + OFB_KEY 由 entrypoint 从 daemon.env 注入。

"""

import json
import os
import re
from typing import Any
from urllib.parse import urlsplit

import requests

# 默认指向官方中转 relay（VIP Club 会员默认走我们中转，零配置起手）。
# 仅当用户自建 relay 时才需要在 daemon.env 覆盖 RELAY_BASE_URL。
RELAY_BASE_URL = os.environ.get(
    "RELAY_BASE_URL", "https://relay.openclaw-for-business.com"
)
_TIMEOUT = 30


class RelaySignError(RuntimeError):
    def __init__(self, code: str, status: int | None = None, *, relay_info=None):
        self.code = code
        self.status = status
        self.relay_info = relay_info
        super().__init__(code)


def _relay_info(reason, context, response=None, exception=None):
    # Never copy exception messages, response bodies, credentials or query values.
    info = {"source": "relay", "reason": reason, **context, "http_status": None}
    if exception is not None:
        info["exception_type"] = type(exception).__name__
    if response is not None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            info["http_status"] = status
        headers = getattr(response, "headers", {})
        kind = str(headers.get("content-type", "")).split(";", 1)[0].lower()
        if re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", kind):
            info["content_type"] = kind
        body = getattr(response, "content", None)
        if isinstance(body, bytes):
            prefix = body[:64].lstrip().lower()
            info.update(body_bytes=len(body), body_kind="empty" if not body else
                "html" if prefix.startswith((b"<!doctype html", b"<html")) else
                "json" if prefix.startswith((b"{", b"[")) else "other")
    return info


def _douyin_context(profile, operation, inputs):
    context = {"profile": profile, "operation": operation}
    action = inputs.get("action")
    if isinstance(action, str) and re.fullmatch(r"[a-z-]{1,40}", action):
        context["action"] = action
    target = inputs.get("url")
    if isinstance(target, str):
        parsed = urlsplit(target)
        context["platform_host"] = parsed.hostname
        context["platform_path"] = "/upload/v1/<store>" if parsed.path.startswith("/upload/v1/") else parsed.path
        context["platform_method"] = inputs.get("method")
    return context


def _ofb_key() -> str:
    key = os.environ.get("OFB_KEY")
    if not key:
        raise RuntimeError(
            "OFB_KEY 未配置。OFB_KEY 是 VIP Club 会员凭证，由 ofb 掌柜签发——"
            "请向 ofb 掌柜索取该 key，交由 IT engineer 写入 daemon.env 后重启实例。"
        )
    return key


def _post(path: str, body: dict, *, context=None, require_object=False) -> Any:
    try:
        key = _ofb_key()
    except RuntimeError as exc:
        if context is None:
            raise
        raise RelaySignError("OFB_KEY_MISSING", relay_info=_relay_info("configuration", context)) from exc
    try:
        resp = requests.post(
            f"{RELAY_BASE_URL}{path}",
            headers={"Content-Type": "application/json", "X-OFB-Key": key},
            json=body,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        if context is None:
            raise
        if isinstance(exc, requests.Timeout):
            reason = "timeout"
        elif isinstance(exc, requests.exceptions.SSLError):
            reason = "tls"
        elif isinstance(exc, requests.exceptions.ContentDecodingError):
            reason = "response_decode"
        elif isinstance(exc, requests.exceptions.InvalidJSONError):
            reason = "request_encode"
        elif isinstance(exc, requests.ConnectionError):
            reason = "connection"
        else:
            reason = "request"
        info = _relay_info(reason, context, getattr(exc, "response", None), exc)
        raise RelaySignError("SIGN_UNAVAILABLE", info["http_status"], relay_info=info) from exc
    def failure(code, reason, exception=None):
        return RelaySignError(code, resp.status_code,
            relay_info=_relay_info(reason, context, resp, exception) if context is not None else None)
    try:
        env = resp.json()
    except ValueError as exc:
        raise failure("SIGN_UNAVAILABLE", "response_decode", exc) from exc
    if not isinstance(env, dict):
        raise failure("SIGN_UNAVAILABLE", "response_shape")
    if not resp.ok or not env.get("success"):
        code = env.get("error")
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,39}", code):
            code = "SIGN_UNAVAILABLE"
        raise failure(code, "relay_error")
    if "data" not in env or require_object and not isinstance(env["data"], dict):
        raise failure("INVALID_RELAY_RESPONSE", "response_data")
    return env["data"]


def douyin_v2(profile: str, operation: str, inputs: dict) -> dict:
    """Request per-operation dynamic fields; platform traffic stays on the client."""
    data = _post(
        "/api/v1/sign/douyin/v2",
        {"version": 2, "profile": profile, "operation": operation, "inputs": inputs},
        context=_douyin_context(profile, operation, inputs), require_object=True,
    )
    if not isinstance(data, dict):
        raise RuntimeError("relay douyin v2 returned invalid data")
    return data


def douyin_health() -> dict:
    key = os.environ.get("OFB_KEY")
    if not key:
        raise RelaySignError("OFB_KEY_MISSING")
    try:
        response = requests.get(
            f"{RELAY_BASE_URL}/api/v1/sign/douyin/v2/health",
            headers={"X-OFB-Key": key},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise RelaySignError("SIGN_UNAVAILABLE") from exc
    try:
        envelope = response.json()
    except ValueError as exc:
        raise RelaySignError("SIGN_UNAVAILABLE", response.status_code) from exc
    if not isinstance(envelope, dict):
        raise RelaySignError("INVALID_RELAY_RESPONSE", response.status_code)
    if not response.ok or not envelope.get("success"):
        code = envelope.get("error")
        raise RelaySignError(
            code if isinstance(code, str) and code.isupper() else "SIGN_UNAVAILABLE",
            response.status_code,
        )
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise RelaySignError("INVALID_RELAY_RESPONSE")
    return {
        k: data[k]
        for k in ("version", "ready", "materialsLoaded", "profiles", "operations")
        if k in data
    }
