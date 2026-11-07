"""Douyin transport: platform traffic is local; dynamic fields come from Relay."""

from __future__ import annotations
import base64
import json
import re
import uuid
from functools import wraps
from urllib.parse import parse_qsl, quote, unquote_plus, urlencode, urlsplit, urlunsplit
import requests
from relay_sign import RelaySignError, douyin_v2
from .session import ApiSession, DEFAULT_SESSION, SessionError, session_lock, write_private
from .verification import creator_verification

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
# Platform-assigned upload nodes vary by region and are only valid for media.
MEDIA_UPLOAD_HOST = re.compile(
    r"tos-[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?\.(?:douyin|snssdk|bytedancevod)\.com"
)
STATIC_HEADERS = {
    "accept",
    "content-type",
    "referer",
    "origin",
    "x-tt-passport-trace-id",
    "agw-js-conv",
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
    def __init__(self, code, *, status=None, missing_fields=None, response_info=None, response_prefix=None, response_headers=None, verification=None, request_info=None, diagnostic_file=None, relay_info=None):
        super().__init__(code)
        self.code, self.status = code, status
        self.missing_fields = list(missing_fields or [])
        self.response_info = response_info
        self.response_prefix = response_prefix
        self.response_headers = response_headers
        self.verification = verification
        self.request_info = request_info
        self.diagnostic_file = diagnostic_file
        self.relay_info = relay_info


def public_error_info(exc):
    info = {key: value for key in ("response_info", "request_info", "diagnostic_file", "relay_info", "preparation_step")
            if (value := getattr(exc, key, None)) is not None}
    status = getattr(exc, "status", None)
    if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
        info["http_status"] = status
    return info


def platform_error_context(state, profile, method, url, data, response):
    parsed = urlsplit(url)
    shapes = {}
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        name = key if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key) else "<other>"
        shapes.setdefault(name, []).append({"type": "string", "length": len(value), "empty": not bool(value)})
    info = {"profile": profile, "method": method, "host": parsed.hostname,
            "path": parsed.path, "query_shape": shapes}
    messages = {key: data[key][:2048] for key in ("status_msg", "status_message", "message")
                if isinstance(data.get(key), str)}
    base = data.get("BaseResp")
    if isinstance(base, dict) and isinstance(base.get("StatusMessage"), str):
        messages["BaseResp.StatusMessage"] = base["StatusMessage"][:2048]
    diagnostic = state.path.parent / "diagnostics" / ("platform-" + uuid.uuid4().hex + ".json")
    try:
        write_private(diagnostic, {"status_code": data["status_code"], "messages": messages,
                                   "request": info, "response": response_info(response)})
    except (OSError, SessionError):
        return info, None
    return info, str(diagnostic)


def response_info(response):
    body = response.content
    prefix = body[:512].lstrip().lower()
    info = {
        "http_status": response.status_code,
        "content_type": str(response.headers.get("content-type", "")).split(";", 1)[0][:128],
        "body_bytes": len(body),
        "body_kind": "empty" if not body else "html" if prefix.startswith((b"<!doctype html", b"<html")) else "other",
        "header_names": sorted(str(name).lower() for name in response.headers),
    }
    log_id = response.headers.get("x-tt-logid", "")
    if isinstance(log_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", log_id):
        info["log_id"] = log_id
    return info


def private_response_headers(response):
    # Decision values can contain private material; never put them in response_info.
    return {
        str(name).lower(): str(value)[:8192]
        for name, value in response.headers.items()
        if str(name).lower() in {"content-type", "x-tt-logid", "bd_passport_security_gateway"}
        or str(name).lower().startswith(("x-tt-verify-", "bd-ticket-guard-"))
    }


def session():
    try:
        return ApiSession(API_SESSION_FILE)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc


def require_runtime(state):
    try:
        state.require_runtime()
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc


def adopt_runtime(state, result):
    if "runtime" in result or "runtime_expires_at" in result:
        try:
            state.set_runtime(result)
        except SessionError as exc:
            raise DouyinRequestError(str(exc)) from exc
        state.save()


def _session(host):
    state = session()
    require_runtime(state)
    return state.cookies("https://" + host + "/"), state.ua


def _url(url, *, media=False, websocket=False):
    p = urlsplit(url)
    allowed = (
        p.hostname in ALLOWED_HOSTS
        or media
        and (
            p.hostname in GATEWAY_HOSTS
            or MEDIA_UPLOAD_HOST.fullmatch(p.hostname or "")
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
        if exc.code == "RUNTIME_EXPIRED" and inputs.get("runtime"):
            try:
                current = session()
                if current.state.get("relay_runtime") == inputs["runtime"]:
                    current.mark_runtime_expired()
            except DouyinRequestError:
                pass
        raise DouyinRequestError(exc.code, status=exc.status, relay_info=exc.relay_info) from exc
    except (requests.RequestException, RuntimeError) as exc:
        raise DouyinRequestError("SIGN_UNAVAILABLE", relay_info={"source": "relay", "reason": "client_error",
            "profile": profile, "operation": operation, "http_status": None,
            "exception_type": type(exc).__name__}) from exc
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
    require_runtime(state)
    if expected_uid is not None and str(state.state.get("uid", "")) != str(
        expected_uid
    ):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    cookie, ua = state.cookies(url.replace("wss://", "https://", 1)), state.ua
    inputs = {"method": method, "url": url, "body": "", "ua": ua, "cookie": cookie}
    if state.state.get("relay_runtime"):
        inputs["runtime"] = state.state["relay_runtime"]
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
            "runtime",
        }:
            raise DouyinRequestError("INVALID_RELAY_FIELDS")
        inputs.update(fields)
    result = _dynamic(profile, operation, inputs)
    adopt_runtime(state, result)
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
    require_runtime(state)
    return result


def _send(method, url, *, headers, data, timeout):
    from .transport import send
    try:
        return send(method, url, headers=headers, data=data, timeout=timeout,
                    scope=API_SESSION_FILE)
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
    capture_response=False,
    payload=None,
    body_text=None,
    expected_uid=None,
    verify_identity=False,
    empty_result=None,
    before_send=None,
    query_tail=None,
    on_response=None,
):
    if before_send is not None and not callable(before_send):
        raise DouyinRequestError("INVALID_SEND_CALLBACK")
    if on_response is not None and not callable(on_response):
        raise DouyinRequestError("INVALID_RESPONSE_CALLBACK")
    _url(url, media=profile == "media")
    method = method.upper()
    reply_read = (profile == "web" and method == "GET" and urlsplit(url).hostname == "www.douyin.com"
                  and urlsplit(url).path == "/aweme/v1/web/comment/list/reply/")
    if query_tail is not None and (not reply_read or not isinstance(query_tail, dict)
            or set(query_tail) - {"verifyFp", "fp"} or any(not isinstance(v, str) for v in query_tail.values())):
        raise DouyinRequestError("INVALID_QUERY_TAIL")
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
    require_runtime(state)
    if expected_uid is not None and str(state.state.get("uid", "")) != str(
        expected_uid
    ):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    cookie, ua = (
        state.cookies("https://creator.douyin.com/" if profile == "media" else url),
        state.ua,
    )
    inputs = {"method": method, "url": url, "body": text, "ua": ua, "cookie": cookie}
    if state.state.get("relay_runtime"):
        inputs["runtime"] = state.state["relay_runtime"]
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
    if any(k.lower() == "agw-js-conv" and v != "str" for k, v in static_headers.items()):
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
            "runtime",
        }:
            raise DouyinRequestError("INVALID_RELAY_FIELDS")
        inputs.update(fields)
    dynamic = _dynamic(profile, operation, inputs)
    adopt_runtime(state, dynamic)
    signed_url = _merge_query(url, dynamic["query"])
    if query_tail:
        signed_url = append_params(signed_url, query_tail)
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
    require_runtime(state)
    wire_headers = {
            "User-Agent": ua,
            **({"Cookie": cookie} if profile != "media" else {}),
            "Accept": next((v for k, v in static_headers.items() if k.lower() == "accept"), "application/json"),
            **({
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            } if profile == "creator" else {}),
            **{k: v for k, v in static_headers.items() if k.lower() != "accept"},
            **headers,
        }
    if profile == "creator":
        lower = {k.lower(): v for k, v in wire_headers.items()}
        lower.update({"accept-encoding": "gzip, deflate, br, zstd", "priority": "u=1, i"})
        order = ("x-tt-session-dtrait", "bd-ticket-guard-web-version", "bd-ticket-guard-client-data",
                 "bd-ticket-guard-web-sign-type", "user-agent", "accept", "x-secsdk-csrf-token",
                 "content-type", "bd-ticket-guard-ree-public-key", "bd-ticket-guard-version", "origin",
                 "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest", "referer", "accept-encoding",
                 "accept-language", "cookie", "priority")
        wire_headers = {**{k: lower.pop(k) for k in order if k in lower}, **lower}
    if reply_read:
        wire_headers = {k: v for k, v in wire_headers.items()
                        if k.lower() not in {"uifid", "x-tt-session-dtrait"}
                        and not k.lower().startswith("bd-ticket-guard-")}
    if before_send is not None:
        before_send()
    response = _send(
        method,
        signed_url,
        headers=wire_headers,
        data=wire,
        timeout=timeout,
    )
    if on_response is not None:
        on_response(response)
    try:
        state.harvest(response, url)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc
    if return_response:
        return response
    verification = creator_verification(dict(response.headers)) if profile == "creator" else None
    if verification:
        raise DouyinRequestError(
            "PLATFORM_VERIFICATION_REQUIRED", status=response.status_code,
            response_info=response_info(response),
            response_prefix=response.content[:512] if capture_response else None,
            response_headers=private_response_headers(response) if capture_response else None,
            verification=verification,
        )
    if response.status_code == 401:
        raise DouyinRequestError("PLATFORM_AUTH_REJECTED", status=response.status_code)
    if response.status_code == 403:
        raise DouyinRequestError("PLATFORM_RISK_CONTROL", status=403,
                                 response_info=response_info(response))
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
        if b"Uifid Not Found" in response.content[:4096]:
            raise DouyinRequestError("PLATFORM_UIFID_MISSING", status=response.status_code) from exc
        raise DouyinRequestError(
            "PLATFORM_NON_JSON", status=response.status_code,
            response_info=response_info(response),
            response_prefix=response.content[:512] if capture_response else None,
            response_headers=private_response_headers(response) if capture_response else None,
        ) from exc
    if not isinstance(data, dict):
        raise DouyinRequestError("PLATFORM_BAD_RESPONSE")
    status = data.get("status_code")
    if status not in (None, 0, "0"):
        if not isinstance(status, (str, int)) or not re.fullmatch(r"-?[0-9]{1,10}", str(status)):
            raise DouyinRequestError("PLATFORM_BAD_RESPONSE")
        request_info, diagnostic = platform_error_context(state, profile, method, url, data, response)
        raise DouyinRequestError(
            "PLATFORM_LOGIN_REJECTED"
            if str(status) == "8"
            else "PLATFORM_STATUS_" + str(status),
            status=response.status_code, response_info=response_info(response),
            request_info=request_info, diagnostic_file=diagnostic,
        )
    if verify_identity:
        user = data.get("user") or data.get("user_info")
        if not user and str(data.get("user_uid", "")).isdigit():
            user = {"uid": str(data["user_uid"])}
            data["user"] = user
        if not isinstance(user, dict) or not str(user.get("uid", "")).isdigit():
            raise DouyinRequestError("SELF_PROFILE_MISSING")
        state.state.update(uid=str(user["uid"]), sec_uid=user.get("sec_uid", ""))
        identity_url = urlsplit(url)
        if (identity_url.hostname == "www.douyin.com" and identity_url.path == "/aweme/v1/web/query/user/"
                and re.fullmatch(r"[1-9][0-9]{0,19}", str(data.get("id", "")))):
            ident = str(data["id"])
            state.state.setdefault("tokens", {}).update(device_id=ident, webid=ident)
            state.state.setdefault("token_sources", {})["webid"] = "query-user.id"
        state.save()
    return data
