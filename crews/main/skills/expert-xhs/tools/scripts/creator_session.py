"""Shared Creator HTTP session for xhs-publish and xhs-engagement."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Iterator
from uuid import uuid4
from zoneinfo import ZoneInfo


CREATOR_SCRIPTS = Path(__file__).resolve().parent
SESSION_FILE = Path(
    os.environ.get(
        "XHS_CREATOR_SESSION_FILE",
        str(Path.home() / ".openclaw" / "logins" / "xhs-creator-local.json"),
    )
).expanduser()
OBSERVATION_FILE = Path(
    os.environ.get(
        "XHS_CREATOR_OBSERVATION_FILE",
        str(Path.home() / ".openclaw" / "logs" / "xhs-creator-observe.jsonl"),
    )
).expanduser()
DAILY_STATE_DIR = Path.home() / ".openclaw" / "logs" / "xhs-creator-daily"


class CreatorSessionMissing(RuntimeError):
    pass


class CreatorApiFailure(RuntimeError):
    def __init__(self, message: str, *, code: int | str | None = None):
        super().__init__(message)
        self.code = code


def claim_daily_run() -> bool:
    """Allow one Creator daily list attempt per Shanghai calendar day."""
    _read_session()
    DAILY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    path = DAILY_STATE_DIR / f"{date}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"date": date, "claimed_at": datetime.now(timezone.utc).isoformat()}, stream)
        stream.write("\n")
    return True


def _imports():
    root = str(CREATOR_SCRIPTS)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from xhs_utils.xhs_creator import XHSCreatorAuth
        from apis.xhs_creator_apis import XHS_Creator_Apis
    except ImportError as exc:
        raise RuntimeError(
            f"Creator dependency missing: {exc}; install root requirements.txt"
        ) from exc
    return XHSCreatorAuth, XHS_Creator_Apis


def _read_session() -> dict:
    if not SESSION_FILE.is_file():
        raise CreatorSessionMissing(
            "本地 Creator 会话不存在；运行 xhs-publish login 扫码初始化"
        )
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorSessionMissing("本地 Creator 会话文件无法读取") from exc
    if not isinstance(data, dict) or not isinstance(data.get("cookies"), dict):
        raise CreatorSessionMissing("本地 Creator 会话文件格式无效")
    cookies = data["cookies"]
    if not cookies.get("a1") or not any(
        cookies.get(key)
        for key in ("web_session", "galaxy_creator_session_id", "customer-sso-sid")
    ):
        raise CreatorSessionMissing("本地 Creator 会话缺少登录凭据")
    return data


def _write_session(auth, *, login_id: str | None = None) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "version": 1,
        "login_id": login_id or uuid4().hex,
        "source": "Creator local QR",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "cookies": auth.profile.cookie_map,
        "host_cookie_state": auth._cookie_store.export_state(),
        "local_storage": dict(auth.profile.local_storage),
        "session_storage": dict(auth.profile.session_storage),
        "dsl": auth.profile.dsl,
        "web_profile_fields": dict(auth.profile.web_profile_fields),
        "session_state": auth.profile.session.snapshot(),
    }
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=SESSION_FILE.parent,
        prefix=".xhs-creator-local-", delete=False,
    )
    try:
        os.chmod(handle.name, 0o600)
        with handle:
            json.dump(state, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, SESSION_FILE)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def observe(operation: str, outcome: str, **details) -> None:
    """Append a credential-free outcome for the staged observation period."""
    OBSERVATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "outcome": outcome,
        **details,
    }
    fd = os.open(
        OBSERVATION_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


@contextmanager
def creator_api() -> Iterator:
    """Open an HTTP Creator client and persist refreshed cookies on exit."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = SESSION_FILE.with_suffix(".lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        state = _read_session()
        auth_class, api_class = _imports()
        auth = auth_class.from_cookie(
            state["cookies"],
            host_cookie_state=state.get("host_cookie_state") or {},
            local_storage=state.get("local_storage") or {},
            session_storage=state.get("session_storage") or {},
            dsl=state.get("dsl") or "",
            web_profile_fields=state.get("web_profile_fields") or {},
        )
        saved_session = state.get("session_state") or {}
        for field, key in (
            ("dsllt", "dsllt"),
            ("mns_seq", "mnsSeq"),
            ("profile_count", "p1"),
            ("sign_count", "sc"),
        ):
            if key in saved_session:
                setattr(auth.profile.session, field, int(saved_session[key]))
        try:
            yield api_class(auth)
        finally:
            try:
                _write_session(auth, login_id=state.get("login_id"))
            finally:
                auth.close()
    finally:
        os.close(lock_fd)


def login_local() -> None:
    auth_class, api_class = _imports()
    qr_image = Path(os.environ.get(
        "XHS_CREATOR_QR_IMAGE",
        "/tmp/qr-xhs.png",
    )).expanduser()
    os.environ["XHS_CREATOR_QR_IMAGE"] = str(qr_image)
    try:
        auth = auth_class.from_qrcode_login(show_in_terminal=True)
        try:
            success, message, data = api_class(auth).get_user_info()
            if not success:
                code = data.get("code") if isinstance(data, dict) else None
                raise CreatorApiFailure(message, code=code)
            _write_session(auth)
            observe("login", "ok")
        finally:
            auth.close()
    except Exception:
        observe("login", "failed")
        raise
    finally:
        qr_image.unlink(missing_ok=True)
