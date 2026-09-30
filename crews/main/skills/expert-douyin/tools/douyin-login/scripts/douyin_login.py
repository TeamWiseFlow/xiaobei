#!/usr/bin/env python3
"""Independent API login state. No browser profile or browser cookie export is read."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import call
from douyin_utils.http import DouyinRequestError, _send, _url, prepare, request, session
from douyin_utils.session import DEFAULT_SESSION, read_private, write_private, SessionError
from relay_sign import douyin_health, RelaySignError

CONFIG = Path(
    os.environ.get("DOUYIN_API_CONFIG", str(DEFAULT_SESSION.with_name("config.json")))
).expanduser()


def init():
    if DEFAULT_SESSION.exists():
        raise ValueError("API_SESSION_EXISTS")
    cfg = read_private(CONFIG)
    if not cfg.get("userAgent") or not isinstance(cfg.get("passport_query"), dict):
        raise ValueError("API_PROTOCOL_CONFIG_MISSING")
    if not (cfg.get("security") or {}).get("private_key"):
        raise ValueError("LOGIN_BOOTSTRAP_MATERIAL_MISSING")
    value = {
        **cfg,
        "cookies": cfg.get("cookies", []),
        "formatVersion": 2,
        "created_at": time.time(),
    }
    write_private(DEFAULT_SESSION, value)
    return bootstrap()


def bootstrap():
    state = session()
    url = "https://www.douyin.com/jingxuan"
    response = _send(
        "GET",
        url,
        headers={"User-Agent": state.ua, "Cookie": state.cookies(url)},
        data=None,
        timeout=30,
    )
    state.harvest(response, url)
    dynamic = prepare("passport", "bootstrap", url, method="GET")
    if dynamic.get("context"):
        state = session()
        state.state["login_context"] = {
            "token": dynamic["context"],
            "expires_at": time.time() + 110,
            "origin": "https://www.douyin.com",
        }
        state.save()
    return {"ok": True, "session_file": str(DEFAULT_SESSION), "next": "challenge"}


def passport(path, extra=None, body=None):
    state = session()
    query = dict(state.state.get("passport_query", {}))
    if not query:
        raise ValueError("API_PROTOCOL_CONFIG_MISSING")
    query.update(extra or {})
    if state.state.get("tokens", {}).get("msToken"):
        query["msToken"] = state.state["tokens"]["msToken"]
    context = state.state.get("login_context", {})
    if context.get("origin") != "https://login.douyin.com":
        context = {}
    if context and context.get("expires_at", 0) < time.time():
        raise ValueError("LOGIN_CONTEXT_EXPIRED")
    result = request(
        "passport",
        "request",
        "POST" if body is not None else "GET",
        "https://login.douyin.com/passport/web/" + path,
        params=query,
        body=body,
        body_encoding="form",
        context=context.get("token"),
        static_headers={
            "referer": "https://www.douyin.com/",
            "origin": "https://www.douyin.com",
        },
    )
    data = result.get("data") or {}
    code = result.get("error_code", data.get("error_code", 0))
    if code not in (0, None):
        raise DouyinRequestError("PASSPORT_STATUS_" + str(code))
    return result


def finish(result):
    data = result.get("data") or {}
    redirect = data.get("redirect_url") or result.get("redirect_url")
    for _ in range(5):
        if not redirect:
            break
        _url(redirect)
        state = session()
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
    profile = call("self")
    user = profile.get("user") or profile.get("user_info")
    if not isinstance(user, dict) or not user.get("uid"):
        raise DouyinRequestError("LOGIN_NOT_CONFIRMED")
    state = session()
    state.state.update(uid=str(user["uid"]), sec_uid=user.get("sec_uid", ""))
    for k in ("qr", "sms", "login_context"):
        state.state.pop(k, None)
    state.save()
    return {
        "ok": True,
        "logged_in": True,
        "uid": str(user["uid"]),
        "write_materials_ready": all(
            state.state.get("security", {}).get(k)
            for k in ("ticket", "ts_sign", "private_key", "dtrait_blob")
        ),
    }


def encode_field(value):
    return "".join(f"{byte ^ 5:02x}" for byte in value.encode())


def main():
    p = argparse.ArgumentParser(prog="douyin-login")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("bootstrap")
    sub.add_parser("status")
    sub.add_parser("relay-check")
    s = sub.add_parser("challenge")
    s.add_argument("--body-file", required=True)
    s = sub.add_parser("qr")
    s.add_argument("--output", required=True)
    s = sub.add_parser("poll")
    s.add_argument("--timeout", type=int, default=120)
    s = sub.add_parser("sms-send")
    s.add_argument("--phone-file", required=True)
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("sms-login")
    s.add_argument("--code-file", required=True)
    a = p.parse_args()
    if a.command == "relay-check":
        health = douyin_health()
        return {"ok": bool(health.get("ready")), "relay": health}
    if a.command == "init":
        return init()
    if a.command == "bootstrap":
        return bootstrap()
    if a.command == "status":
        state = session()
        return {
            "ok": True,
            "session_file": str(state.path),
            "uid": state.state.get("uid"),
            "logged_in": any(
                c.get("name") in ("sessionid", "sessionid_ss") and c.get("value")
                for c in state.state["cookies"]
            ),
            "protocol_configured": bool(state.state.get("passport_query")),
            "security_fields_present": sorted(state.state.get("security", {})),
        }
    if a.command == "challenge":
        # Challenge payload is provisioned as opaque, short-lived runtime material.
        value = read_private(a.body_file)
        if (
            not isinstance(value.get("body"), dict)
            or value.get("expires_at", 0) < time.time()
        ):
            raise ValueError("LOGIN_CHALLENGE_EXPIRED")
        passport("challenge/", {"skip_c": "1"}, value["body"])
        return {"ok": True}
    if a.command == "qr":
        data = (
            passport(
                "get_qrcode/",
                {
                    "next": "https://www.douyin.com",
                    "need_short_url": "true",
                    "need_logo": "false",
                    "is_new_login": "1",
                    "is_from_iesaccountsaas": "1",
                },
            ).get("data")
            or {}
        )
        token = data.get("token")
        url = data.get("qrcode_index_url") or data.get("qrcode_url")
        if not token or not url:
            raise DouyinRequestError("LOGIN_QR_MISSING")
        import qrcode

        target = Path(a.output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        qrcode.make(url).save(target)
        target.chmod(0o600)
        state = session()
        state.state["qr"] = {"token": token, "created_at": time.time()}
        state.save()
        return {"ok": True, "qr_file": str(target), "next": "poll"}
    if a.command == "poll":
        if not 1 <= a.timeout <= 300:
            raise ValueError("INVALID_LOGIN_TIMEOUT")
        qr = session().state.get("qr", {})
        if not qr.get("token"):
            raise ValueError("QR_SESSION_MISSING")
        deadline = time.monotonic() + a.timeout
        while time.monotonic() < deadline:
            r = passport(
                "check_qrconnect/",
                {"is_from_iesaccountsaas": "1"},
                {
                    "need_logo": "false",
                    "is_frontier": "true",
                    "token": qr["token"],
                    "is_new_login": "1",
                    "next": "https://www.douyin.com",
                    "need_short_url": "true",
                },
            )
            status = (r.get("data") or {}).get("status")
            if status == "confirmed":
                return finish(r)
            if status == "expired":
                raise ValueError("QR_EXPIRED")
            time.sleep(3)
        return {"ok": False, "error": "QR_WAIT_TIMEOUT"}
    if a.command == "sms-send":
        phone = Path(a.phone_file).expanduser().read_text().strip()
        if not re.fullmatch(r"(?:\+86)?1\d{10}", phone):
            raise ValueError("INVALID_PHONE")
        if not a.confirm:
            return {"ok": True, "preview": True, "action": "sms-send"}
        phone = "+86" + phone.removeprefix("+86")
        passport(
            "send_code/",
            {"is_from_iesaccountsaas": "1"},
            {
                "is6Digits": "1",
                "mix_mode": "1",
                "mobile": encode_field(phone),
                "type": "3731",
                "fixed_mix_mode": "1",
            },
        )
        state = session()
        state.state["sms"] = {"mobile": encode_field(phone), "sent_at": time.time()}
        state.save()
        return {"ok": True, "code_sent": True}
    code = Path(a.code_file).expanduser().read_text().strip()
    sms = session().state.get("sms", {})
    if not re.fullmatch(r"\d{6}", code) or sms.get("sent_at", 0) < time.time() - 300:
        raise ValueError("SMS_SESSION_EXPIRED")
    return finish(
        passport(
            "sms_login/",
            {"is_from_iesaccountsaas": "1"},
            {
                "service": "https://www.toutiao.com",
                "mix_mode": "1",
                "mobile": sms["mobile"],
                "code": encode_field(code),
                "fixed_mix_mode": "1",
            },
        )
    )


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
        print(json.dumps({"ok": False, "error": code}))
        sys.exit(
            2
            if code
            in ("API_SESSION_MISSING", "API_SESSION_EXPIRED", "LOGIN_NOT_CONFIRMED")
            else 1
        )
