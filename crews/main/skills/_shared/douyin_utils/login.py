"""Automatic API login. Relay computes opaque requests; this client sends them."""

from __future__ import annotations

import os
import time
import uuid
from urllib.parse import urlsplit

import requests
from relay_sign import RelaySignError, douyin_v2

from .http import DouyinRequestError, _send, session, require_runtime
from .session import DEFAULT_SESSION, ApiSession, SessionError, runtime_fields, read_private, session_lock, write_private
from .verification import (login_verification, login_verification_status,
                           validate_login_verification, validate_creator_verification)

LOGIN_HOSTS = {
    "www.douyin.com",
    "login.douyin.com",
    "passport.douyin.com",
    "sso.douyin.com",
    "ttwid.bytedance.com",
    "mssdk.bytedance.com",
}
CLIENT_FIELDS = {"userAgent", "device", "im_protocol", "im_ws"}
REFRESH_ROUTES = {
    ("POST", "www.douyin.com", "/passport/user_info/get_sec_ts/"),
    ("POST", "www.douyin.com", "/passport/ticket_guard/get_client_cert/"),
    ("POST", "mssdk.bytedance.com", "/web/r/token"),
    ("POST", "mssdk.bytedance.com", "/web/common"),
}
MFA_ROUTES = {
    "mfa-send": {"/passport/web/send_code/"},
    "mfa-code": {"/passport/web/validate_code/"},
    "mfa-confirm": {"/passport/upsms/verify/", "/passport/upsms/chain_mobile/verify/"},
    "mfa-face-prepare": {"/passport/safe/get_auth_ticket/v1/"},
    "mfa-face-check": {"/passport/safe/verify_auth_ticket/"},
}
MFA_ACTIONS = {*MFA_ROUTES, "mfa-prepare", "mfa-resume"}
MFA_ACTIONS |= {"sms-" + action for action in MFA_ACTIONS}
CREATOR_ROUTES = {
    "verify-prepare": ("GET", {"/passport/safe/query_decision/"}),
    "verify-send": ("POST", {"/passport/web/send_code/"}),
    "verify-code": ("POST", {"/passport/web/validate_code/"}),
    "verify-confirm": ("POST", {"/passport/upsms/verify/", "/passport/upsms/chain_mobile/verify/"}),
}


def compute(operation, inputs):
    try:
        value = douyin_v2("passport", operation, inputs)
    except RelaySignError as exc:
        raise DouyinRequestError(exc.code, status=exc.status) from exc
    except (RuntimeError, requests.RequestException) as exc:
        raise DouyinRequestError(
            "OFB_KEY_MISSING" if not os.environ.get("OFB_KEY") else "SIGN_UNAVAILABLE"
        ) from exc
    if not isinstance(value, dict) or not isinstance(value.get("runtime"), str):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    try:
        runtime_fields(value)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc
    return value


def adopt(state, result, *, save=True):
    try:
        state.set_runtime(result)
    except SessionError as exc:
        raise DouyinRequestError(str(exc)) from exc
    client = result.get("client", {})
    if not isinstance(client, dict) or set(client) - CLIENT_FIELDS - {
        "security_fields_present",
        "security_expires_at",
        "cookies",
        "tokens",
    }:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if client:
        ua = client.get("userAgent")
        if not isinstance(ua, str) or not ua or any(c in ua for c in "\r\n"):
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")
        for name in CLIENT_FIELDS:
            if name in client:
                if name != "userAgent" and not isinstance(client[name], dict):
                    raise DouyinRequestError("INVALID_RELAY_RESPONSE")
                if name == "userAgent" or client[name]:
                    state.state[name] = client[name]
        if "security_fields_present" in client:
            state.state["relay_security_fields"] = client["security_fields_present"]
        if "security_expires_at" in client:
            expires = client["security_expires_at"]
            if not isinstance(expires, int) or isinstance(expires, bool) or expires <= 0:
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            state.state["relay_security_expires_at"] = expires
        for cookie in client.get("cookies", []):
            if not isinstance(cookie, dict) or str(cookie.get("domain", "")).lstrip(
                "."
            ) not in LOGIN_HOSTS | {"douyin.com", "creator.douyin.com"}:
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
        state.merge_cookies(client.get("cookies", []))
        state.state.setdefault("tokens", {}).update(client.get("tokens", {}))
    if save:
        state.save()


def initialize(*, restart=False):
    with session_lock(DEFAULT_SESSION):
        legacy = None
        target = DEFAULT_SESSION
        if restart:
            if DEFAULT_SESSION.exists():
                write_private(DEFAULT_SESSION.with_name(f"session.abandoned-{time.time_ns()}.json"),
                              read_private(DEFAULT_SESSION))
                DEFAULT_SESSION.unlink()
            target = DEFAULT_SESSION.parent / "sessions" / ("login-" + uuid.uuid4().hex) / "session.json"
        if DEFAULT_SESSION.exists():
            state = ApiSession(DEFAULT_SESSION)
            require_runtime(state)
            if not state.state.get("relay_runtime"):
                if state.state.get("uid") or any(
                    c.get("name") in {"sessionid", "sessionid_ss"} and c.get("value")
                    for c in state.state["cookies"]
                ):
                    raise DouyinRequestError("API_SESSION_LEGACY_REQUIRES_NEW_PATH")
                legacy = state.state
        if not DEFAULT_SESSION.exists() or legacy is not None:
            result = compute("initialize", {})
            client = result.get("client", {})
            if not isinstance(client, dict) or not client.get("userAgent"):
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            if legacy is not None:
                write_private(
                    DEFAULT_SESSION.with_name(
                        f"session.pre-auto-{time.time_ns()}.json"
                    ),
                    legacy,
                )
            write_private(
                target,
                {
                    "formatVersion": 3,
                    "created_at": time.time(),
                    "cookies": [],
                    "userAgent": client["userAgent"],
                },
            )
            state = ApiSession(target)
            adopt(state, result)
            if restart:
                write_private(DEFAULT_SESSION, {"active_session_file": str(target.absolute())})
    if not state.state.get("initialized"):
        flow("bootstrap")
    state = session()
    return {
        "ok": True,
        "initialized": True,
        "session_file": str(state.path),
        "runtime_expires_at": state.state.get("runtime_expires_at"),
        "next": "qr",
    }


def validate_plan(plan, *, hosts=LOGIN_HOSTS):
    if not isinstance(plan, dict) or set(plan) != {
        "method",
        "url",
        "headers",
        "body",
        "request_id",
    }:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    p = urlsplit(plan["url"])
    if (
        p.scheme != "https"
        or p.hostname not in hosts
        or p.port not in (None, 443)
        or p.username
        or p.password
        or p.fragment
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if (
        plan["method"] not in {"GET", "POST"}
        or not isinstance(plan["body"], str)
        or len(plan["body"].encode()) > 256 * 1024
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    headers = plan["headers"]
    if not isinstance(headers, dict) or len({k.lower() for k in headers}) != len(
        headers
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    for key, value in headers.items():
        if (
            not isinstance(key, str)
            or not isinstance(value, str)
            or any(c in key + value for c in "\r\n\0")
            or key.lower()
            in {"host", "content-length", "connection", "transfer-encoding"}
        ):
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")


def validate_mfa_plan(action, plan):
    validate_plan(plan)
    target = urlsplit(plan["url"])
    if any(c.isspace() for c in plan["url"]) or "\\" in plan["url"] or any(
        token in target.path.lower() for token in ("%2f", "%5c", "%00", "%2e", "/../", "/./")
    ):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    base = action.removeprefix("sms-")
    if base == "mfa-resume":
        allowed = (plan["method"] == "POST" and target.hostname == "login.douyin.com"
                   and target.path == ("/passport/web/sms_login/" if action.startswith("sms-")
                                      else "/passport/web/check_qrconnect/")) or (
            plan["method"] == "GET" and target.hostname in {
                "www.douyin.com", "login.douyin.com", "passport.douyin.com", "sso.douyin.com"
            } and (target.path == "/" or target.path.startswith("/passport/")
                   or target.path in {"/check_login/", "/sso/check_login/"}) and not plan["body"]
        )
    else:
        allowed = (plan["method"] == "POST" and target.hostname == "www.douyin.com"
                   and target.path in MFA_ROUTES.get(base, set()))
    if not allowed:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")


def validate_flow_plan(action, plan):
    if action in MFA_ACTIONS:
        validate_mfa_plan(action, plan)
        return
    creator = action in CREATOR_ROUTES
    validate_plan(plan, hosts={"creator.douyin.com"} if creator else LOGIN_HOSTS)
    target = urlsplit(plan["url"])
    if creator:
        method, paths = CREATOR_ROUTES[action]
        if (plan["method"] != method or target.path not in paths
                or any(c.isspace() for c in plan["url"]) or "\\" in plan["url"]
                or any(token in target.path.lower() for token in ("%2f", "%5c", "%00", "%2e"))
                or method == "GET" and plan["body"]):
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    elif action == "refresh" and (plan["method"], target.hostname, target.path) not in REFRESH_ROUTES:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")


def adopt_creator_verification(state, result, action):
    try:
        value = validate_creator_verification(result.get("verification"))
    except ValueError as exc:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE") from exc
    previous = state.state.get("creator_verification")
    if action != "verify-prepare" and (not previous or previous["id"] != value["id"]
                                       or previous["log_id"] != value["log_id"]):
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    state.state["creator_verification"] = value


def adopt_verification(state, result, action):
    value = result.get("verification")
    if value is None and action not in MFA_ACTIONS:
        return
    try:
        value = validate_login_verification(value)
    except ValueError as exc:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE") from exc
    previous = state.state.get("login_verification")
    expected_scene = "sms_login" if action.startswith("sms-") else "qr_connect"
    if value["scene"] != expected_scene:
        raise DouyinRequestError("LOGIN_MFA_CONTEXT_MISMATCH")
    if previous and (value["id"] != previous["id"] or value["methods"] != previous["methods"]
                     or value["expires_at"] != previous["expires_at"]
                     or previous.get("method") and value.get("method") != previous["method"]):
        raise DouyinRequestError("LOGIN_MFA_CONTEXT_MISMATCH")
    if value["login_confirmed"] and action not in {"mfa-resume", "sms-mfa-resume"}:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if action == "poll" and value["status"] not in {"prepared", "expired"}:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    if action == "sms-login" and value["status"] not in {"prepared", "unsupported", "expired"}:
        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    data = result.get("data")
    if data is not None:
        expected = ({"status": "confirmed", "authenticated_cookie": True,
                     "identity_verified": False, "next": "self"} if value["login_confirmed"]
                    else {"status": "verification_required", "error_code": 2046})
        if data != expected:
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")
    state.state["login_verification"] = value
    state.state["login_identity_pending"] = True
    if not previous:
        state.state.pop("uid", None)
        state.state.pop("sec_uid", None)


def flow(action, fields=None, *, consume_mfa=False):
    """Persist each response before advancing, so computation retries send no SMS twice."""
    fields = fields or {}
    creator = action in CREATOR_ROUTES
    flow_key = "creator_verification_flow" if creator else "login_flow"
    with session_lock(DEFAULT_SESSION):
        state = session()
        require_runtime(state)
        if creator and str(state.state.get("uid", "")) != fields.get("uid"):
            raise DouyinRequestError("API_ACCOUNT_MISMATCH")
        saved = state.state.get(flow_key, {})
        verification = login_verification_status(state.state)
        if saved.get("verification_result") and not consume_mfa:
            raise DouyinRequestError("LOGIN_VERIFICATION_REQUIRED", verification=verification)
        if (state.state.get("login_verification")
                and (state.state.get("login_identity_pending") or verification["status"] != "login-confirmed")
                and action not in MFA_ACTIONS):
            raise DouyinRequestError("LOGIN_VERIFICATION_FLOW_UNSUPPORTED" if verification.get("type") == "UNSUPPORTED"
                                     else "LOGIN_MFA_REQUIRED", verification=verification)
        if saved and (saved.get("action") != action or saved.get("fields") != fields):
            raise DouyinRequestError("VERIFICATION_ACTION_PENDING" if creator else "LOGIN_ACTION_PENDING")
        if consume_mfa and (not saved.get("response") or action not in {"poll", "sms-login"}
                            or action == "poll" and not login_verification(saved["response"].get("body"))):
            raise DouyinRequestError("LOGIN_MFA_CHALLENGE_INVALID")
        for _ in range(40):
            require_runtime(state)
            saved = state.state.setdefault(
                flow_key, {"action": action, "fields": fields}
            )
            plan = saved.get("request")
            if plan and not saved.get("response"):
                validate_flow_plan(action, plan)
                if saved.get("sent") and action in {"sms-send", "sms-login", *MFA_ACTIONS, *CREATOR_ROUTES}:
                    raise DouyinRequestError("VERIFICATION_STEP_RESULT_UNKNOWN" if creator else "LOGIN_STEP_RESULT_UNKNOWN")
                saved["sent"] = True
                state.save()
                require_runtime(state)
                response = _send(
                    plan["method"],
                    plan["url"],
                    headers=plan["headers"],
                    data=plan["body"].encode() if plan["body"] else None,
                    timeout=30,
                )
                response_cookies = state.harvest(response, plan["url"])
                # The landing HTML is not a computation input; retain structured responses.
                text = (
                    response.text
                    if "json" in response.headers.get("content-type", "").lower()
                    or response.text.lstrip().startswith("{")
                    else ""
                )
                if len(text.encode()) > 256 * 1024:
                    raise DouyinRequestError("LOGIN_RESPONSE_TOO_LARGE")
                saved["response"] = {
                    "request_id": plan["request_id"],
                    "status": response.status_code,
                    "headers": {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower()
                        in {
                            "content-type",
                            "location",
                            "x-ms-token",
                            "bd-ticket-guard-sec-ts",
                            "bd-ticket-guard-server-data",
                            "x-secsdk-csrf-token",
                            "x-ware-csrf-token",
                            "x-tt-verify-passport-decision",
                        }
                    },
                    "cookies": response_cookies,
                    "body": text,
                }
                state.save()
                if response.status_code >= 400:
                    raise DouyinRequestError("VERIFICATION_REJECTED" if creator else "LOGIN_PLATFORM_REJECTED", status=response.status_code)
            if action == "poll" and saved.get("response"):
                verification = login_verification(saved["response"].get("body"))
                if verification and not consume_mfa:
                    # Preserve the actual response. Replaying it is not another platform poll.
                    raise DouyinRequestError("LOGIN_MFA_REQUIRED", status=saved["response"].get("status"),
                                            verification=verification)
            inputs = {
                "ua": state.ua,
                "runtime": state.state["relay_runtime"],
                "action": action,
                "fields": fields,
            }
            if saved.get("response"):
                inputs["response"] = saved["response"]
            try:
                result = compute("flow", inputs)
            except DouyinRequestError as exc:
                if exc.code == "RUNTIME_EXPIRED":
                    state.mark_runtime_expired()
                raise
            if consume_mfa and (result.get("complete") is not True
                                or not isinstance(result.get("result"), dict)
                                or not result["result"].get("verification")):
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            if result.get("complete") is True:
                payload = result.get("result", {})
                if not isinstance(payload, dict):
                    raise DouyinRequestError("INVALID_RELAY_RESPONSE")
                data = payload.get("data") or {}
                if (isinstance(data, dict) and payload.get("error_code", data.get("error_code")) == 2046
                        and not payload.get("verification")):
                    # Preserve the exact response and its original runtime for future contract integration.
                    # A completed calculation is not a completed login or a resumable MFA contract.
                    saved["verification_result"] = payload
                    saved["completed_runtime"] = result["runtime"]
                    saved["completed_runtime_expires_at"] = result["runtime_expires_at"]
                    state.state["login_identity_pending"] = True
                    state.save()
                    raise DouyinRequestError("LOGIN_VERIFICATION_REQUIRED",
                                            verification=login_verification_status(state.state))
                if creator:
                    adopt_creator_verification(state, payload, action)
                else:
                    adopt_verification(state, payload, action)
                if action in MFA_ACTIONS or payload.get("verification"):
                    client = result.get("client")
                    if client and (not isinstance(client, dict)
                                   or not creator and not payload.get("verification", {}).get("login_confirmed")
                                   or client.get("userAgent") != state.ua):
                        raise DouyinRequestError("INVALID_RELAY_RESPONSE")
                original_runtime = state.state.get("relay_runtime")
                original_expiry = state.state.get("runtime_expires_at")
                adopt(state, result, save=False)
                if (action == "sms-login" and payload.get("verification", {}).get("type") == "UNSUPPORTED"
                        and saved.get("response")):
                    # Keep the exact original input privately; this is evidence, never a retry queue.
                    diagnostic = state.path.parent / "diagnostics" / f"sms-login-unsupported-{payload['verification']['id']}.json"
                    write_private(diagnostic, {
                        "formatVersion": 1, "ua": state.ua,
                        "runtime": original_runtime, "runtime_expires_at": original_expiry,
                        "login_flow": saved, "relay_result": result,
                    })
                    state.state["login_verification_diagnostic_file"] = str(diagnostic)
                state.state.pop(flow_key, None)
                if action == "bootstrap":
                    state.state["initialized"] = True
                state.save()
                return payload
            plan = result.get("request")
            if action in MFA_ACTIONS and "client" in result:
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            validate_flow_plan(action, plan)
            adopt(state, result, save=False)
            state.state[flow_key] = {
                "action": action,
                "fields": fields,
                "request": plan,
            }
            state.save()
        raise DouyinRequestError("LOGIN_STEP_LIMIT")


def prepare_mfa(*, sms=False):
    """Consume a saved challenge without resending QR checks or SMS login."""
    state = session()
    require_runtime(state)
    pending = state.state.get("login_flow", {})
    original = "sms-login" if sms else "poll"
    if (pending.get("action") == original and pending.get("response")
            and (sms or login_verification(pending["response"].get("body")))):
        flow(original, pending["fields"], consume_mfa=True)
    state = session()
    if not state.state.get("login_verification"):
        paused = login_verification_status(state.state)
        if paused:
            raise DouyinRequestError("LOGIN_VERIFICATION_FLOW_UNSUPPORTED", verification=paused)
        raise DouyinRequestError("LOGIN_MFA_CHALLENGE_INVALID")
    if state.state["login_verification"]["scene"] != ("sms_login" if sms else "qr_connect"):
        raise DouyinRequestError("LOGIN_MFA_CONTEXT_MISMATCH")
    return flow("sms-mfa-prepare" if sms else "mfa-prepare")


def mfa_fields(action, *, method=None, code=None):
    """Use the saved challenge ID and method; agents never assemble these fields."""
    state = session()
    require_runtime(state)
    value = login_verification_status(state.state)
    if not value or not value.get("id"):
        raise DouyinRequestError("LOGIN_MFA_REQUIRED", verification=value)
    if value["status"] == "expired":
        raise DouyinRequestError("LOGIN_MFA_EXPIRED", verification=value)
    if value.get("type") == "UNSUPPORTED":
        raise DouyinRequestError("LOGIN_VERIFICATION_FLOW_UNSUPPORTED", verification=value)
    if value["scene"] != ("sms_login" if action.startswith("sms-") else "qr_connect"):
        raise DouyinRequestError("LOGIN_MFA_CONTEXT_MISMATCH", verification=value)
    base = action.removeprefix("sms-")
    expected = {
        "mfa-send": "prepared", "mfa-code": "awaiting-code", "mfa-confirm": "awaiting-up-sms",
        "mfa-face-prepare": "prepared", "mfa-face-check": "awaiting-face", "mfa-resume": "ticket-issued",
    }
    if value["status"] != expected[base]:
        raise DouyinRequestError("LOGIN_MFA_ACTION_PENDING", verification=value)
    fields = {"verification_id": value["id"]}
    if base == "mfa-resume":
        return fields
    method = method or value.get("method")
    required_method = {"mfa-code": "mobile_sms_verify", "mfa-confirm": "mobile_up_sms_verify",
                       "mfa-face-prepare": "face_verify", "mfa-face-check": "face_verify"}.get(base)
    if (method not in value["methods"] or required_method and method != required_method
            or value.get("method") and method != value["method"]):
        raise DouyinRequestError("LOGIN_MFA_METHOD_UNSUPPORTED", verification=value)
    fields["method"] = method
    if base == "mfa-code":
        fields["code"] = code
    return fields


def security_fields(state):
    return set(state.state.get("security", {})) | set(
        state.state.get("relay_security_fields", [])
    )


def refresh_security(expected_uid):
    """Refresh the current account without starting a new login or rotating its key."""
    state = session()
    if not state.state.get("relay_runtime"):
        raise DouyinRequestError("LOGIN_INIT_REQUIRED")
    if str(state.state.get("uid", "")) != str(expected_uid):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    pending = state.state.get("login_flow", {})
    if pending.get("action") == "refresh":
        fields = pending["fields"]
        if fields.get("uid") != str(expected_uid):
            raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    else:
        fields = {"uid": str(expected_uid), "cookie": state.cookies("https://www.douyin.com/")}
    result = flow("refresh", fields)
    if str(session().state.get("uid", "")) != str(expected_uid):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    return result
