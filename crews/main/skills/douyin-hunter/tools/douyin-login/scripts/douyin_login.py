#!/usr/bin/env python3
"""Independent API login state. No browser profile or browser cookie export is read."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import call
from douyin_utils.http import DouyinRequestError, _send, _url, session, require_runtime
from douyin_utils.login import flow, initialize, security_fields, refresh_security, prepare_mfa, mfa_fields
from douyin_utils.session import DEFAULT_SESSION, SessionError, write_private
from douyin_utils.verification import (SMS_METHODS, login_verification_status,
                                       public_login_verification, validate_login_verification)
from relay_sign import RelaySignError, douyin_health


def checked_flow(action, fields=None):
    result = flow(action, fields)
    data = result.get("data") or {}
    code = result.get("error_code", data.get("error_code", 0))
    if code == 2046:
        value = result.get("verification")
        if value:
            value = public_login_verification(validate_login_verification(value))
            raise DouyinRequestError("LOGIN_VERIFICATION_FLOW_UNSUPPORTED" if value["type"] == "UNSUPPORTED"
                                     else "LOGIN_MFA_REQUIRED", verification=value)
        raise DouyinRequestError("LOGIN_VERIFICATION_REQUIRED", verification={
            "required": True, "status": "verification_required", "error_code": 2046, "source_action": action,
        })
    if code not in (0, None):
        raise DouyinRequestError("PASSPORT_STATUS_" + str(code))
    return result


def authenticated_cookie(state):
    return any(
        part.partition("=")[0].strip() in ("sessionid", "sessionid_ss") and part.partition("=")[2]
        for part in state.cookies("https://www.douyin.com/").split(";")
    )


def save_qr(value, output):
    import qrcode

    target = Path(output).expanduser().absolute()
    if target.is_symlink():
        raise SessionError("API_SESSION_UNSAFE")
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    buffer = io.BytesIO()
    qrcode.make(value).save(buffer, format="PNG")
    fd, name = tempfile.mkstemp(prefix=".qr-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(buffer.getvalue())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return str(target)


def mfa_result(result, *, output=None):
    value = validate_login_verification(result.get("verification"))
    public = public_login_verification(value)
    prefix = "sms-" if value["scene"] == "sms_login" else ""
    next_step = {"prepared": "select-method", "awaiting-code": prefix + "mfa-code",
                 "awaiting-up-sms": prefix + "mfa-confirm", "awaiting-face": prefix + "mfa-face-check",
                 "ticket-issued": prefix + "mfa-resume", "login-confirmed": prefix + "mfa-resume",
                 "expired": "restart", "unsupported": "report-verification"}[value["status"]]
    response = {"ok": True, "logged_in": False, "verification": public, "next": next_step}
    action = value.get("user_action")
    if action:
        # Only the path is public. Instructions and face ticket remain in private files.
        path = session().path.parent / f"mfa-{value['id']}-user-action.json"
        write_private(path, {"verification_id": value["id"], **action})
        response["user_action_file"] = str(path)
        if action["kind"] == "scan-face-qr" and output:
            response["qr_file"] = save_qr(action["uri"], output)
    return response


def finish(result):
    require_runtime(session())
    data = result.get("data") or {}
    redirect = data.get("redirect_url") or result.get("redirect_url")
    for _ in range(5):
        if not redirect:
            break
        _url(redirect)
        state = session()
        require_runtime(state)
        response = _send(
            "GET",
            redirect,
            headers={"User-Agent": state.ua, "Cookie": state.cookies(redirect)},
            data=None,
            timeout=30,
        )
        state.harvest(response, redirect)
        if response.status_code not in (301, 302, 303, 307, 308):
            break
        redirect = urljoin(redirect, response.headers.get("Location", ""))
    else:
        raise ValueError("LOGIN_REDIRECT_LIMIT")
    state = session()
    require_runtime(state)
    verification = state.state.get("login_verification")
    if not authenticated_cookie(state) or verification and verification.get("status") != "login-confirmed":
        raise DouyinRequestError("LOGIN_NOT_CONFIRMED")
    profile = call("self")
    user = profile.get("user") or profile.get("user_info")
    if not isinstance(user, dict) or not str(user.get("uid", "")).isdigit():
        raise DouyinRequestError("LOGIN_NOT_CONFIRMED")
    state = session()
    state.state.update(uid=str(user["uid"]), sec_uid=user.get("sec_uid", ""))
    for k in ("qr", "sms", "login_context"):
        state.state.pop(k, None)
    state.state.pop("login_identity_pending", None)
    if state.state.get("login_verification"):
        state.state["login_verification"].pop("user_action", None)
    state.save()
    return {
        "ok": True,
        "logged_in": True,
        "uid": str(user["uid"]),
        "write_materials_ready": all(
            k in security_fields(state)
            for k in ("ticket", "ts_sign", "private_key", "dtrait_blob")
        ),
    }


def main():
    p = argparse.ArgumentParser(prog="douyin-login")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    s = sub.add_parser("restart", help="Start a new private login session; never send SMS automatically")
    s.add_argument("--confirm", action="store_true")
    sub.add_parser("bootstrap")
    sub.add_parser("refresh")
    sub.add_parser("status")
    sub.add_parser("relay-check")
    sub.add_parser("challenge")
    s = sub.add_parser("qr")
    s.add_argument("--output", required=True)
    s = sub.add_parser("poll")
    s.add_argument("--timeout", type=int, default=120)
    s = sub.add_parser("sms-send")
    s.add_argument("--phone-file", required=True)
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("sms-login")
    s.add_argument("--code-file", required=True)
    for prefix in ("", "sms-"):
        sub.add_parser(prefix + "mfa-prepare")
        s = sub.add_parser(prefix + "mfa-send")
        s.add_argument("--method", required=True, choices=SMS_METHODS)
        s.add_argument("--confirm", action="store_true")
        s = sub.add_parser(prefix + "mfa-code")
        s.add_argument("--code-file", required=True)
        s = sub.add_parser(prefix + "mfa-confirm")
        s.add_argument("--confirm", action="store_true")
        s = sub.add_parser(prefix + "mfa-face-prepare")
        s.add_argument("--output", required=True)
        s = sub.add_parser(prefix + "mfa-face-check")
        s.add_argument("--output")
        sub.add_parser(prefix + "mfa-resume")
    a = p.parse_args()
    if a.command == "relay-check":
        health = douyin_health()
        automatic = {"passport.initialize", "passport.flow"}.issubset(
            health.get("operations", [])
        )
        return {
            "ok": bool(health.get("ready")) and automatic,
            "automatic_login": automatic,
            "relay": health,
        }
    if a.command in {"init", "bootstrap", "challenge"}:
        return initialize()
    if a.command == "restart":
        if not a.confirm:
            return {"ok": True, "preview": True, "action": "restart",
                    "message": "重新登录将弃用旧登录状态，重新初始化；不会自动发送短信或验证码。"}
        return initialize(restart=True)
    if a.command == "refresh":
        user = call("self").get("user") or {}
        uid = str(user.get("uid", ""))
        if not uid.isdigit():
            raise DouyinRequestError("SELF_PROFILE_MISSING")
        refresh_security(uid)
        state = session()
        return {"ok": True, "security_fields_present": sorted(security_fields(state)),
                "expires_at": state.state.get("relay_security_expires_at")}
    if a.command == "status":
        if not DEFAULT_SESSION.exists():
            return {
                "ok": True,
                "session_file": str(DEFAULT_SESSION),
                "initialized": False,
                "cookie_present": False,
                "identity_verified": False,
                "logged_in": False,
                "next": "init",
            }
        state = session()
        cookie_present = authenticated_cookie(state)
        pending = state.state.get("login_flow", {})
        verification = login_verification_status(state.state)
        identity_verified = (cookie_present and str(state.state.get("uid", "")).isdigit()
                             and not state.runtime_expired
                             and not state.state.get("login_identity_pending")
                             and (not verification or verification.get("status") == "login-confirmed"))
        prefix = "sms-" if (verification or {}).get("scene") == "sms_login" else ""
        next_step = pending.get("action") or {
            "prepared": prefix + "mfa-prepare", "awaiting-code": prefix + "mfa-code",
            "awaiting-up-sms": prefix + "mfa-confirm", "awaiting-face": prefix + "mfa-face-check",
            "ticket-issued": prefix + "mfa-resume", "login-confirmed": prefix + "mfa-resume",
            "expired": "restart", "unsupported": "report-verification",
        }.get((verification or {}).get("status"), "qr" if state.state.get("initialized") else "init")
        if pending.get("action") == "poll" and verification:
            next_step = "mfa-prepare"
        if pending.get("verification_result"):
            next_step = "sms-mfa-prepare" if pending.get("action") == "sms-login" and pending.get("response") else "report-verification"
        if state.runtime_expired:
            next_step = "restart"
        return {
            "ok": True,
            "session_file": str(state.path),
            "uid": state.state.get("uid"),
            "cookie_present": cookie_present,
            "identity_verified": identity_verified,
            "logged_in": identity_verified,
            "initialized": bool(state.state.get("initialized")),
            "automatic_login": bool(state.state.get("relay_runtime")),
            "runtime_expires_at": state.state.get("runtime_expires_at"),
            "runtime_expired": state.runtime_expired,
            "security_fields_present": sorted(security_fields(state)),
            "pending_action": pending.get("action"),
            **({"verification": verification} if verification else {}),
            **({"diagnostic_file": state.state["login_verification_diagnostic_file"]}
               if state.state.get("login_verification_diagnostic_file") else {}),
            **({"next": next_step} if not identity_verified else {}),
            **({"message": "本次登录已超时，请重新登录。"} if state.runtime_expired else {}),
        }
    if a.command in {"mfa-prepare", "sms-mfa-prepare"}:
        return mfa_result(prepare_mfa(sms=a.command.startswith("sms-")))
    if a.command.startswith(("mfa-", "sms-mfa-")):
        state = session()
        require_runtime(state)
        value = login_verification_status(state.state)
        base = a.command.removeprefix("sms-")
        if value and value.get("scene") != ("sms_login" if a.command.startswith("sms-") else "qr_connect"):
            raise DouyinRequestError("LOGIN_MFA_CONTEXT_MISMATCH", verification=value)
        if base == "mfa-resume" and value and value.get("status") == "login-confirmed":
            return finish({})  # Retry self only; the login continuation already completed.
        stored = state.state.get("login_verification")
        if value and not state.state.get("login_flow"):
            if base == "mfa-face-prepare" and value.get("status") == "awaiting-face":
                return mfa_result({"verification": stored}, output=a.output)
            if (base == "mfa-send" and value.get("status") in {"awaiting-code", "awaiting-up-sms"}
                    and value.get("method") == a.method):
                return mfa_result({"verification": stored})
        method = getattr(a, "method", None)
        if base == "mfa-face-prepare":
            method = "face_verify"
        code = None
        if base == "mfa-code":
            path = Path(a.code_file).expanduser()
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise SessionError("API_SESSION_UNSAFE")
            code = path.read_text().strip()
            if not re.fullmatch(r"[0-9]{4,6}", code):
                raise ValueError("INVALID_VERIFY_CODE")
        fields = mfa_fields(a.command, method=method, code=code)
        if base in {"mfa-send", "mfa-confirm"} and not a.confirm:
            return {"ok": True, "preview": True, "action": a.command,
                    "verification": value, "logged_in": False}
        result = flow(a.command, fields)
        if base == "mfa-resume":
            verified = validate_login_verification(result.get("verification"))
            if not verified["login_confirmed"] or (result.get("data") or {}).get("status") != "confirmed":
                raise DouyinRequestError("LOGIN_MFA_LOGIN_UNCONFIRMED")
            return finish(result)
        return mfa_result(result, output=getattr(a, "output", None))
    if a.command == "qr":
        initialize()
        data = checked_flow("qr").get("data") or {}
        token = data.get("token")
        url = data.get("qrcode_index_url") or data.get("qrcode_url")
        if not token or not url:
            raise DouyinRequestError("LOGIN_QR_MISSING")
        target = save_qr(url, a.output)
        state = session()
        state.state["qr"] = {"token": token, "created_at": time.time()}
        state.save()
        return {"ok": True, "qr_file": target, "next": "poll"}
    if a.command == "poll":
        if not 1 <= a.timeout <= 300:
            raise ValueError("INVALID_LOGIN_TIMEOUT")
        state = session()
        require_runtime(state)
        qr = state.state.get("qr", {})
        if not qr.get("token"):
            raise ValueError("QR_SESSION_MISSING")
        deadline = time.monotonic() + a.timeout
        last_status = None
        backoff = 5.2
        while time.monotonic() < deadline:
            try:
                r = checked_flow("poll", {"token": qr["token"]})
            except DouyinRequestError as exc:
                if exc.code != "PASSPORT_STATUS_7":
                    raise
                time.sleep(min(backoff, max(0, deadline - time.monotonic())))
                backoff = min(backoff * 2, 20)
                continue
            status = (r.get("data") or {}).get("status")
            last_status = status
            if status == "confirmed":
                return finish(r)
            if status == "expired":
                raise ValueError("QR_EXPIRED")
            time.sleep(min(5.2, max(0, deadline - time.monotonic())))
        require_runtime(session())
        return {"ok": False, "error": "QR_WAIT_TIMEOUT", "qr_status": last_status}
    if a.command == "sms-send":
        phone = Path(a.phone_file).expanduser().read_text().strip()
        if not re.fullmatch(r"(?:\+86)?1\d{10}", phone):
            raise ValueError("INVALID_PHONE")
        if not a.confirm:
            return {"ok": True, "preview": True, "action": "sms-send"}
        phone = "+86" + phone.removeprefix("+86")
        initialize()
        checked_flow("sms-send", {"phone": phone})
        state = session()
        state.state["sms"] = {"phone": phone, "sent_at": time.time()}
        state.save()
        return {"ok": True, "code_sent": True}
    state = session()
    require_runtime(state)
    code = Path(a.code_file).expanduser().read_text().strip()
    sms = state.state.get("sms", {})
    if not re.fullmatch(r"\d{6}", code) or sms.get("sent_at", 0) < time.time() - 300:
        raise ValueError("SMS_SESSION_EXPIRED")
    return finish(checked_flow("sms-login", {"phone": sms["phone"], "code": code}))


if __name__ == "__main__":
    try:
        r = main()
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r.get("ok") else 1)
    except (DouyinRequestError, RelaySignError, ValueError, OSError, SessionError) as e:
        code = (
            e.code
            if isinstance(e, (DouyinRequestError, RelaySignError))
            else str(e)
            if str(e).isupper()
            else "LOGIN_CLIENT_ERROR"
        )
        result = {"ok": False, "error": code}
        if code == "RUNTIME_EXPIRED":
            result.update(message="本次登录已超时，请重新登录。", next="restart")
        if isinstance(e, DouyinRequestError) and e.verification is not None:
            result["verification"] = e.verification
            if code in {"LOGIN_MFA_REQUIRED", "LOGIN_VERIFICATION_REQUIRED"}:
                result["next"] = ("sms-mfa-prepare" if e.verification.get("scene") == "sms_login"
                                  or e.verification.get("source_action") == "sms-login" else "mfa-prepare")
            elif code == "LOGIN_VERIFICATION_FLOW_UNSUPPORTED":
                result["next"] = "report-verification"
        print(json.dumps(result))
        sys.exit(
            2
            if code
            in ("API_SESSION_MISSING", "API_SESSION_EXPIRED", "LOGIN_NOT_CONFIRMED", "LOGIN_MFA_REQUIRED",
                "LOGIN_VERIFICATION_REQUIRED", "LOGIN_VERIFICATION_FLOW_UNSUPPORTED", "RUNTIME_EXPIRED")
            else 1
        )
