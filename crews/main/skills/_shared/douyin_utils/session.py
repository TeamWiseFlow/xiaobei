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


class SessionError(RuntimeError):
    pass


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
            for k in ("security", "security_by_host", "csrf", "tokens", "device")
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
        for c in self.state["cookies"]:
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
                or not scoped
                or not matches
                or c.get("expires", 0) > 0
                and c["expires"] <= time.time()
            ):
                continue
            if any(x in c["name"] + c["value"] for x in "\r\n;"):
                raise SessionError("API_SESSION_INVALID")
            selected.append(c)
        selected.sort(key=lambda c: -len(c.get("path", "/")))
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
            for material in [
                self.state.get("security", {}),
                *self.state.get("security_by_host", {}).values(),
            ]:
                for name in ("ticket", "ts_sign", "sec_ts", "csrf_token"):
                    material.pop(name, None)
        for c in entries:
            key = (c["name"], c["domain"], c.get("path", "/"))
            jar[:] = [
                old
                for old in jar
                if (old.get("name"), old.get("domain"), old.get("path", "/")) != key
            ]
            jar.append(c)

    def harvest(self, response, url):
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
        self.merge_cookies(entries)
        headers = getattr(response, "headers", {})
        token = headers.get("x-ms-token") or next(
            (c["value"] for c in entries if c["name"] == "msToken"), None
        )
        if token:
            self.state.setdefault("tokens", {})["msToken"] = token
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
            except (ValueError, TypeError):
                raise SessionError("PLATFORM_SECURITY_RESPONSE_INVALID")
        self.save()

        return entries

    def save(self):
        write_private(self.path, self.state)
