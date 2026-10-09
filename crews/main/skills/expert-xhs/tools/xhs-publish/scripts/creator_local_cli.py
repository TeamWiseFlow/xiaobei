#!/usr/bin/env python3
"""Create a Creator QR in the background and manage the persisted session."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from creator_session import CreatorSessionMissing, SESSION_FILE, creator_api, login_local, observe  # noqa: E402

LOGIN_DIR = SESSION_FILE.parent
STATUS_FILE = LOGIN_DIR / "xhs-creator-login-status.json"
LOCK_FILE = LOGIN_DIR / "xhs-creator-login.lock"
WORKER_LOG = Path.home() / ".openclaw" / "logs" / "xhs-creator-login.log"
QR_FILE = Path(os.environ.get("XHS_CREATOR_QR_IMAGE", "/tmp/qr-xhs.png")).expanduser()
LOGIN_CONFIRM_SETTLE_SECONDS = 8


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def status() -> dict:
    try:
        value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_status(value: dict) -> None:
    LOGIN_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATUS_FILE.with_name(f".{STATUS_FILE.name}.{os.getpid()}")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, STATUS_FILE)
    finally:
        temp.unlink(missing_ok=True)


def process_alive(pid: object) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False


def login() -> int:
    LOGIN_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        current = status()
        if current.get("state") == "pending" and process_alive(current.get("pid")):
            pass
        else:
            QR_FILE.unlink(missing_ok=True)
            run_id = uuid4().hex
            current = {
                "state": "pending", "run_id": run_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            save_status(current)
            WORKER_LOG.parent.mkdir(parents=True, exist_ok=True)
            log_fd = os.open(WORKER_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                worker = subprocess.Popen(
                    [sys.executable, __file__, "worker", run_id],
                    stdin=subprocess.DEVNULL, stdout=log_fd, stderr=log_fd,
                    start_new_session=True,
                    env={**os.environ, "XHS_CREATOR_QR_IMAGE": str(QR_FILE)},
                )
            finally:
                os.close(log_fd)
            current = status()
            if current.get("run_id") == run_id and current.get("state") == "pending":
                current["pid"] = worker.pid
                save_status(current)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = status()
        if QR_FILE.is_file() and QR_FILE.stat().st_size > 0:
            emit({"ok": True, "qr_path": str(QR_FILE), "state": "awaiting_scan",
                  "message": "将二维码图片发给用户，随后停止并等待用户确认扫码"})
            return 0
        if current.get("state") == "success":
            emit({"ok": True, "state": "authenticated", "message": "Creator 会话已就位"})
            return 0
        if current.get("state") == "failed":
            emit({"ok": False, "error": "LOGIN_FAILED", "message": current.get("message", "二维码登录失败")})
            return 1
        if current.get("pid") and not process_alive(current["pid"]):
            emit({"ok": False, "error": "LOGIN_WORKER_EXITED", "message": "二维码登录进程提前退出，查看私有登录日志"})
            return 1
        time.sleep(0.25)
    emit({"ok": False, "error": "QR_NOT_READY", "message": "二维码尚未生成；登录进程仍可能在运行，可稍后重试 login"})
    return 1


def worker(run_id: str) -> int:
    try:
        login_local()
        state, message = "success", "Creator 本地 HTTP 会话已就位"
    except Exception as exc:
        state, message = "failed", str(exc)[:200]
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        current = status()
        if current.get("run_id") == run_id:
            current.update({"state": state, "message": message,
                            "finished_at": datetime.now(timezone.utc).isoformat()})
            save_status(current)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    return 0 if state == "success" else 1


def check() -> int:
    try:
        with creator_api() as api:
            success, message, response = api.get_user_info()
        code = response.get("code") if isinstance(response, dict) else None
        if not success:
            observe("check", "rejected", code=code)
            emit({"ok": False, "error": "CREATOR_REJECTED", "code": code, "message": message})
            return 2 if code in (401, 403, "401", "403") else 1
        observe("check", "ok")
        emit({"ok": True, "message": "Creator API 登录态就位", "session_path": str(SESSION_FILE)})
        return 0
    except CreatorSessionMissing as exc:
        emit({"ok": False, "error": "SESSION_MISSING", "message": str(exc)})
        return 2
    except Exception as exc:
        observe("check", "error", error_type=type(exc).__name__)
        emit({"ok": False, "error": "CHECK_FAILED", "message": str(exc)[:200]})
        return 1


def login_confirm() -> int:
    current = status()
    deadline = time.monotonic() + LOGIN_CONFIRM_SETTLE_SECONDS
    while current.get("state") == "pending" and time.monotonic() < deadline:
        time.sleep(0.5)
        current = status()
    if current.get("state") == "pending":
        emit({"ok": False, "error": "LOGIN_PENDING", "message": "扫码确认尚未完成；稍后再运行 login-confirm"})
        return 2
    if current.get("state") == "failed":
        emit({"ok": False, "error": "LOGIN_FAILED", "message": current.get("message", "二维码已过期或登录失败")})
        return 2
    if current.get("state") != "success":
        emit({"ok": False, "error": "NO_LOGIN_ATTEMPT", "message": "先运行 xhs-publish login"})
        return 2
    return check()


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "check"
    if command == "login":
        return login()
    if command == "login-confirm":
        return login_confirm()
    if command == "check":
        return check()
    if command == "worker" and len(argv) == 2:
        return worker(argv[1])
    emit({"ok": False, "error": "UNKNOWN_COMMAND"})
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
