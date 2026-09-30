"""Douyin transport: platform traffic is local; dynamic fields come from Relay."""

from __future__ import annotations
import base64
import json
from functools import wraps
from pathlib import Path
from urllib.parse import quote, unquote_plus, urlencode, urlsplit, urlunsplit
import requests
from relay_sign import RelaySignError, douyin_v2
from .session import ApiSession, DEFAULT_SESSION, SessionError, session_lock

API_SESSION_FILE = DEFAULT_SESSION
ALLOWED_HOSTS = {
    "www.douyin.com",
    "creator.douyin.com",
    "live.douyin.com",
    "imapi.douyin.com",
    "passport.douyin.com",
    "login.douyin.com",
    "sso.douyin.com",
    "frontier-im.douyin.com",
    "webcast100-ws-web-hl.douyin.com",
}
GATEWAY_HOSTS = {"imagex.bytedanceapi.com", "vod.bytedanceapi.com"}
STATIC_HEADERS = {
    "accept",
    "content-type",
    "referer",
    "origin",
    "x-tt-passport-trace-id",
}
COOKIE_FIELDS = {
    "__ac_signature",
    "bd_ticket_guard_client_data",
    "bd_ticket_guard_client_data_v2",
}


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with session_lock(API_SESSION_FILE):
            return function(*args, **kwargs)

    return wrapped


class DouyinRequestError(RuntimeError):
    def __init__(self, code, *, status=None):
        super().__init__(code)
        self.code, self.status = code, status


def session():
    try:
        return ApiSession(API_SESSION_FILE)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc


def _session(host):
    state = session()
    return state.cookies("https://" + host + "/"), state.ua


def _url(url, *, media=False, websocket=False):
    p = urlsplit(url)
    allowed = (
        p.hostname in ALLOWED_HOSTS
        or media
        and (
            p.hostname in GATEWAY_HOSTS
            or any(
                (p.hostname or "").endswith("." + suffix)
                for suffix in (
                    "bytedance.com",
                    "bytedance.net",
                    "byteimg.com",
                    "byteupload.com",
                )
            )
        )
    )
    if (
        p.scheme != ("wss" if websocket else "https")
        or not allowed
        or p.username
        or p.password
        or p.fragment
        or p.port not in (None, 443)
    ):
        raise DouyinRequestError("INVALID_PLATFORM_URL")
    if any(x in p.path for x in ("/../", "/./", "\\")):
        raise DouyinRequestError("INVALID_PLATFORM_URL")


def append_params(url, params):
    p = urlsplit(url)
    extra = urlencode(params, doseq=True)
    return urlunsplit(
        p._replace(query=p.query + ("&" if p.query and extra else "") + extra)
    )


def _merge_query(url, dynamic):
    if not isinstance(dynamic, dict):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    p = urlsplit(url)
    original = (
        [
            part
            for part in p.query.split("&")
            if unquote_plus(part.partition("=")[0]) not in dynamic
        ]
        if p.query
        else []
    )
    for k, v in dynamic.items():
        if not isinstance(k, str) or not isinstance(v, (str, int, float)):
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")
        original.append(quote(k, safe="") + "=" + quote(str(v), safe=""))
    return urlunsplit(p._replace(query="&".join(original)))


def _dynamic(profile, operation, inputs):
    try:
        value = douyin_v2(profile, operation, inputs)
    except RelaySignError as exc:
        raise DouyinRequestError(exc.code, status=exc.status) from exc
    except (requests.RequestException, RuntimeError) as exc:
        raise DouyinRequestError("SIGN_UNAVAILABLE") from exc
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("query"), dict)
        or not isinstance(value.get("headers"), dict)
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or k.lower() in {"host", "cookie", "user-agent", "content-length"}
        or any(c in k + v for c in "\r\n")
        for k, v in value["headers"].items()
    ) or len({k.lower() for k in value["headers"]}) != len(value["headers"]):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    return value


@serialized
def prepare(
    profile,
    operation,
    url,
    body=b"",
    *,
    fields=None,
    method="POST",
    security=None,
    context=None,
    static_headers=None,
    expected_uid=None,
):
    _url(url, media=profile == "media", websocket=operation == "websocket")
    method = method.upper()
    if method not in {"GET", "POST", "PUT"}:
        raise DouyinRequestError("INVALID_METHOD")
    if static_headers and any(
        not isinstance(k, str)
        or k.lower() not in STATIC_HEADERS
        or not isinstance(v, str)
        or any(c in v for c in "\r\n")
        for k, v in static_headers.items()
    ):
        raise DouyinRequestError("INVALID_STATIC_HEADERS")
    state = session()
    if expected_uid is not None and str(state.state.get("uid", "")) != str(
        expected_uid
    ):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    cookie, ua = state.cookies(url.replace("wss://", "https://", 1)), state.ua
    inputs = {"method": method, "url": url, "body": "", "ua": ua, "cookie": cookie}
    if body:
        inputs["body_base64"] = base64.b64encode(body).decode()
    if security is None:
        security = {} if profile == "media" else state.security(urlsplit(url).hostname)
    if security:
        inputs["security"] = security
    if context:
        inputs["context"] = context
    if static_headers:
        inputs["headers"] = static_headers
    if fields:
        if set(fields) & set(inputs) or set(fields) & {
            "method",
            "url",
            "cookie",
            "ua",
            "body",
            "body_base64",
            "security",
        }:
            raise DouyinRequestError("INVALID_RELAY_FIELDS")
        inputs.update(fields)
    result = _dynamic(profile, operation, inputs)
    returned = result.get("cookies", {})
    if (
        not isinstance(returned, dict)
        or set(returned) - COOKIE_FIELDS
        or any(
            not isinstance(v, str) or any(c in v for c in "\r\n;")
            for v in returned.values()
        )
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if returned:
        state.merge_cookies(
            [
                {
                    "name": k,
                    "value": v,
                    "domain": urlsplit(url).hostname,
                    "path": "/",
                    "hostOnly": True,
                }
                for k, v in returned.items()
            ]
        )
        state.save()
    return result


def _send(method, url, *, headers, data, timeout):
    # TLS fingerprint transport has no browser process or persistent browser profile.
    from curl_cffi import requests as http

    try:
        return http.request(
            method,
            url,
            headers=headers,
            data=data,
            timeout=timeout,
            allow_redirects=False,
            impersonate="chrome",
            quote=False,
        )
    except Exception as exc:
        raise DouyinRequestError("PLATFORM_NETWORK_ERROR") from exc


@serialized
def request(
    profile,
    operation,
    method,
    url,
    *,
    params=None,
    body=None,
    context=None,
    timeout=30,
    body_encoding="json",
    raw_body=None,
    content_type=None,
    binary_response=False,
    static_headers=None,
    security=None,
    fields=None,
    return_response=False,
    payload=None,
    body_text=None,
    expected_uid=None,
    verify_identity=False,
    empty_result=None,
):
    _url(url, media=profile == "media")
    method = method.upper()
    if method not in {"GET", "POST", "PUT"}:
        raise DouyinRequestError("INVALID_METHOD")
    if params:
        url = append_params(url, params)
    if (
        body_encoding not in {"json", "form"}
        or sum(v is not None for v in (body, raw_body, payload, body_text)) > 1
    ):
        raise DouyinRequestError("INVALID_BODY_ENCODING")
    text = (
        ""
        if body is None
        else urlencode(body, doseq=True)
        if body_encoding == "form"
        else json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    )
    if body_text is not None:
        if not isinstance(body_text, str):
            raise DouyinRequestError("INVALID_BODY_ENCODING")
        text = body_text
    if method == "GET" and (text or raw_body is not None or payload is not None):
        raise DouyinRequestError("INVALID_BODY_ENCODING")
    state = session()
    if expected_uid is not None and str(state.state.get("uid", "")) != str(
        expected_uid
    ):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    cookie, ua = (
        state.cookies("https://creator.douyin.com/" if profile == "media" else url),
        state.ua,
    )
    inputs = {"method": method, "url": url, "body": text, "ua": ua, "cookie": cookie}
    if raw_body is not None:
        inputs["body_base64"] = base64.b64encode(raw_body).decode()
    if context:
        inputs["context"] = context
    if security is None:
        security = {} if profile == "media" else state.security(urlsplit(url).hostname)
    if security:
        inputs["security"] = security
    static_headers = dict(static_headers or {})
    if content_type:
        static_headers["content-type"] = content_type
    if body is not None:
        static_headers.setdefault(
            "content-type",
            "application/x-www-form-urlencoded"
            if body_encoding == "form"
            else "application/json",
        )
    if any(
        k.lower() not in STATIC_HEADERS
        or not isinstance(v, str)
        or "\r" in v
        or "\n" in v
        for k, v in static_headers.items()
    ) or len({k.lower() for k in static_headers}) != len(static_headers):
        raise DouyinRequestError("INVALID_STATIC_HEADERS")
    if static_headers:
        inputs["headers"] = static_headers
    if fields:
        if set(fields) & {
            "method",
            "url",
            "body",
            "body_base64",
            "ua",
            "cookie",
            "security",
            "context",
            "headers",
        }:
            raise DouyinRequestError("INVALID_RELAY_FIELDS")
        inputs.update(fields)
    dynamic = _dynamic(profile, operation, inputs)
    signed_url = _merge_query(url, dynamic["query"])
    headers = dynamic["headers"]
    if any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or k.lower() in {"host", "cookie", "user-agent", "content-length"}
        or "\r" in v
        or "\n" in v
        for k, v in headers.items()
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if {k.lower() for k in headers} & {k.lower() for k in static_headers}:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    returned = dynamic.get("cookies", {})
    if (
        not isinstance(returned, dict)
        or set(returned) - COOKIE_FIELDS
        or any(
            not isinstance(k, str)
            or not isinstance(v, str)
            or any(c in v for c in "\r\n;")
            for k, v in returned.items()
        )
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if returned:
        host = urlsplit(url).hostname
        state.merge_cookies(
            [
                {"name": k, "value": v, "domain": host, "path": "/", "hostOnly": True}
                for k, v in returned.items()
            ]
        )
        cookie = state.cookies(url)
        state.save()
    wire = (
        payload
        if payload is not None
        else raw_body
        if raw_body is not None
        else text.encode()
        if body is not None or body_text is not None
        else None
    )
    response = _send(
        method,
        signed_url,
        headers={
            "User-Agent": ua,
            **({"Cookie": cookie} if profile != "media" else {}),
            "Accept": "application/json",
            **static_headers,
            **headers,
        },
        data=wire,
        timeout=timeout,
    )
    try:
        state.harvest(response, url)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc
    if return_response:
        return response
    if response.status_code in (401, 403):
        raise DouyinRequestError("PLATFORM_AUTH_REJECTED", status=response.status_code)
    if response.status_code == 429:
        raise DouyinRequestError("PLATFORM_RATE_LIMITED", status=429)
    if not 200 <= response.status_code < 300:
        raise DouyinRequestError("PLATFORM_HTTP_ERROR", status=response.status_code)
    if binary_response:
        return response.content
    if not response.content and empty_result is not None:
        return dict(empty_result)
    try:
        data = json.loads(response.content)
    except (ValueError, UnicodeError) as exc:
        raise DouyinRequestError(
            "PLATFORM_NON_JSON", status=response.status_code
        ) from exc
    if not isinstance(data, dict):
        raise DouyinRequestError("PLATFORM_BAD_RESPONSE")
    status = data.get("status_code")
    if status not in (None, 0, "0"):
        raise DouyinRequestError(
            "PLATFORM_LOGIN_REJECTED"
            if str(status) == "8"
            else "PLATFORM_STATUS_" + str(status)
        )
    if verify_identity:
        user = data.get("user") or data.get("user_info")
        if not user and str(data.get("user_uid", "")).isdigit():
            user = {"uid": str(data["user_uid"])}
            data["user"] = user
        if not isinstance(user, dict) or not str(user.get("uid", "")).isdigit():
            raise DouyinRequestError("SELF_PROFILE_MISSING")
        state.state.update(uid=str(user["uid"]), sec_uid=user.get("sec_uid", ""))
        if str(data.get("id", "")).isdigit():
            state.state.setdefault("tokens", {})["device_id"] = str(data["id"])
        state.save()
    return data
