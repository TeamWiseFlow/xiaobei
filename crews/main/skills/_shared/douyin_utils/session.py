"""Private, scoped state for the Douyin API client."""

from __future__ import annotations
import base64
import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_SESSION = Path(
    os.environ.get(
        "DOUYIN_API_SESSION", str(Path.home() / ".openclaw/douyin-api/session.json")
    )
).expanduser()
SECURITY_FIELDS = {
    "ticket",
    "ts_sign",
    "private_key",
    "server_cert",
    "dtrait_blob",
    "sec_ts",
    "csrf_token",
}
COOKIE_ORDER = (
    "bd_ticket_guard_client_web_domain", "n_mh", "has_biz_token",
    "__security_server_data_status", "_bd_ticket_crypt_doamin",
    "SEARCH_RESULT_LIST_TYPE", "live_use_vvc", "store-region", "store-region-src",
    "d_ticket", "is_staff_user", "enter_pc_once", "hevc_supported",
    "passport_csrf_token", "passport_csrf_token_default", "UIFID", "uid_tt",
    "uid_tt_ss", "sid_tt", "sessionid", "sessionid_ss", "bd_ticket_guard_ts_sign_id",
    "__security_mc_1_s_sdk_crypt_sdk", "__security_mc_1_s_sdk_cert_key",
    "__security_mc_1_s_sdk_sign_data_key_web_protect", "is_dbsc",
    "is_support_rtm_web_ts", "stream_recommend_feed_params", "home_can_add_dy_2_desktop",
    "strategyABtestKey", "publish_badge_show_info", "is_dash_user", "sid_guard",
    "session_tlb_tag", "sid_ucp_v1", "ssid_ucp_v1", "IsDouyinActive",
    "x-web-secsdk-uid", "ttwid", "csrf_session_id", "s_v_web_id", "odin_tt", "x_tt_token", "fpk1", "fpk2",
)


class SessionError(RuntimeError):
    pass


def cookie_key(cookie):
    return (cookie.get("name"), str(cookie.get("domain", "")).lstrip(".").lower(),
            cookie.get("path", "/"))


def latest_cookies(cookies):
    # A leading domain dot is ignored for cookie identity. Keep the latest value
    # while retaining its hostOnly and Secure attributes for scope checks.
    return list({cookie_key(cookie): cookie for cookie in cookies if isinstance(cookie, dict)}.values())


def runtime_fields(result):
    runtime, expires = result.get("runtime"), result.get("runtime_expires_at")
    if (not isinstance(runtime, str) or not runtime or type(expires) is not int
            or not 0 < expires <= 2**53 - 1):
        raise SessionError("INVALID_RELAY_RESPONSE")
    return runtime, expires


def read_private(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise SessionError("API_SESSION_MISSING")
    if path.stat().st_mode & 0o077:
        raise SessionError("API_SESSION_UNSAFE")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise SessionError("API_SESSION_INVALID") from exc
    if not isinstance(value, dict):
        raise SessionError("API_SESSION_INVALID")
    return value


def write_private(path, value):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink():
        raise SessionError("API_SESSION_UNSAFE")
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def session_lock(path=DEFAULT_SESSION):
    path = Path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


class ApiSession:
    def __init__(self, path=DEFAULT_SESSION):
        self.path = Path(path)
        self.configured_path = self.path
        self.state = read_private(self.path)
        if set(self.state) == {"active_session_file"}:
            target = self.state["active_session_file"]
            if not isinstance(target, str) or not Path(target).is_absolute() or Path(target) == self.path:
                raise SessionError("API_SESSION_INVALID")
            self.path = Path(target)
            self.state = read_private(self.path)
        if (
            not isinstance(self.state.get("userAgent"), str)
            or not self.state["userAgent"]
        ):
            raise SessionError("API_SESSION_INVALID")
        expiry = self.state.get("runtime_expires_at")
        if expiry is not None and (type(expiry) is not int or not 0 < expiry <= 2**53 - 1):
            raise SessionError("API_SESSION_INVALID")
        if not isinstance(self.state.get("cookies"), list):
            raise SessionError("API_SESSION_INVALID")
        if any(c in self.state["userAgent"] for c in "\r\n") or any(
            not isinstance(self.state.get(k, {}), dict)
            for k in ("security", "security_by_host", "csrf", "tokens", "token_sources", "device")
        ):
            raise SessionError("API_SESSION_INVALID")

    @property
    def runtime_expired(self):
        expiry = self.state.get("runtime_expires_at")
        return bool(self.state.get("runtime_expired") or expiry is not None and expiry <= time.time())

    def require_runtime(self):
        if self.runtime_expired:
            raise SessionError("RUNTIME_EXPIRED")

    def set_runtime(self, result):
        runtime, expires = runtime_fields(result)
        self.state.update(relay_runtime=runtime, runtime_expires_at=expires)
        self.state.pop("runtime_expired", None)

    def mark_runtime_expired(self):
        self.state["runtime_expired"] = True
        self.save()

    @property
    def ua(self):
        return self.state["userAgent"]

    def cookies(self, url):
        parsed = urlsplit(url)
        host, path = parsed.hostname, parsed.path or "/"
        selected = []
        for c in latest_cookies(self.state["cookies"]):
            if (
                not isinstance(c, dict)
                or not isinstance(c.get("name"), str)
                or not isinstance(c.get("value"), str)
            ):
                continue
            domain = str(c.get("domain", "")).lstrip(".")
            scoped = host == domain or (
                not c.get("hostOnly", not str(c.get("domain", "")).startswith("."))
                and host.endswith("." + domain)
            )
            prefix = c.get("path", "/")
            matches = path == prefix or path.startswith(
                prefix if prefix.endswith("/") else prefix + "/"
            )
            if (
                not domain
                or c["name"] == "msToken"
                or not scoped
                or not matches
                or c.get("expires", 0) > 0
                and c["expires"] <= time.time()
            ):
                continue
            if any(x in c["name"] + c["value"] for x in "\r\n;"):
                raise SessionError("API_SESSION_INVALID")
            selected.append(c)
        rank = {name: index for index, name in enumerate(COOKIE_ORDER)}
        selected.sort(key=lambda c: (-len(c.get("path", "/")),
                                    rank.get(c["name"], len(rank))))
        return "; ".join(c["name"] + "=" + c["value"] for c in selected)

    def security(self, host):
        value = {
            k: v
            for k, v in self.state.get("security", {}).items()
            if k in SECURITY_FIELDS and k != "csrf_token" and isinstance(v, str) and v
        }
        scoped = self.state.get("security_by_host", {}).get(host, {})
        value.update(
            {
                k: v
                for k, v in scoped.items()
                if k in SECURITY_FIELDS
                and k != "csrf_token"
                and isinstance(v, str)
                and v
            }
        )
        csrf = self.state.get("csrf", {}).get(host, {})
        if csrf.get("expires_at", 0) > time.time() and csrf.get("token"):
            value["csrf_token"] = csrf["token"]
        return value

    def merge_cookies(self, entries):
        jar = self.state["cookies"]
        jar[:] = latest_cookies(jar)
        previous = {
            c.get("name"): c.get("value")
            for c in jar
            if c.get("name") in ("sessionid", "sessionid_ss")
        }
        changed = any(
            c.get("name") in previous and c.get("value") != previous[c["name"]]
            for c in entries
        )
        if changed:
            self.state.pop("uid", None)
            self.state.pop("sec_uid", None)
            self.state.pop("relay_security_expires_at", None)
            self.state.pop("csrf", None)
            self.state.pop("login_context", None)
            self.state.pop("session_channels", None)
            for name in ("msToken", "creator_msToken"):
                self.state.get("tokens", {}).pop(name, None)
            for material in [
                self.state.get("security", {}),
                *self.state.get("security_by_host", {}).values(),
            ]:
                for name in ("ticket", "ts_sign", "sec_ts", "csrf_token"):
                    material.pop(name, None)
        for c in entries:
            key = cookie_key(c)
            jar[:] = [
                old
                for old in jar
                if cookie_key(old) != key
            ]
            if c.get("value") and not (c.get("expires", 0) > 0 and c["expires"] <= time.time()):
                jar.append(c)

    def harvest(self, response, url, *, persist=True):
        host = urlsplit(url).hostname
        entries = []
        jar = getattr(
            getattr(response, "cookies", None), "jar", getattr(response, "cookies", [])
        )
        for c in jar:
            domain = c.domain or host
            if domain.lstrip(".") != host and not host.endswith(
                "." + domain.lstrip(".")
            ):
                continue
            entries.append(
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": domain,
                    "path": c.path or "/",
                    "hostOnly": not c.domain_specified,
                    "secure": c.secure,
                    "expires": c.expires or -1,
                }
            )
        if not persist:
            return entries
        self.merge_cookies(entries)
        headers = getattr(response, "headers", {})
        token = headers.get("x-ms-token") or next(
            (c["value"] for c in entries if c["name"] == "msToken"), None
        )
        if token:
            from urllib.parse import parse_qs
            creator = host == "creator.douyin.com" or parse_qs(urlsplit(url).query).get("ms_appid") == ["2906"]
            self.state.setdefault("tokens", {})["creator_msToken" if creator else "msToken"] = token
        sec = self.state.setdefault("security", {})
        if headers.get("bd-ticket-guard-sec-ts"):
            sec["sec_ts"] = headers["bd-ticket-guard-sec-ts"]
        material = headers.get("bd-ticket-guard-server-data")
        if material:
            try:
                values = json.loads(base64.b64decode(material, validate=True))
                for k in ("ticket", "ts_sign"):
                    if isinstance(values.get(k), str):
                        sec[k] = values[k]
                if values.get("ts_sign"):
                    self.merge_cookies([{"name": "bd_ticket_guard_ts_sign_id", "value": values["ts_sign"],
                                         "domain": ".douyin.com", "path": "/", "hostOnly": False}])
            except (ValueError, TypeError):
                raise SessionError("PLATFORM_SECURITY_RESPONSE_INVALID")
        self.save()

        return entries

    def save(self):
        write_private(self.path, self.state)
