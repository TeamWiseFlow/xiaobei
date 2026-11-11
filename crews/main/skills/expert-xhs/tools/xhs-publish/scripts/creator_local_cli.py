#!/usr/bin/env python3
"""Own the Creator QR login process and manage its persisted result."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from creator_session import CreatorSessionMissing, SESSION_FILE, creator_api, login_local, observe  # noqa: E402
from xhs_utils.runtime_logs import logged_worker_command  # noqa: E402

LOGIN_DIR = SESSION_FILE.parent
STATUS_FILE = LOGIN_DIR / "xhs-creator-login-status.json"
LOCK_FILE = LOGIN_DIR / "xhs-creator-login.lock"
WORKER_LOG = Path.home() / ".openclaw" / "logs" / "xhs-creator-login.log"
QR_FILE = Path(os.environ.get("XHS_CREATOR_QR_IMAGE", "/tmp/qr-xhs.png")).expanduser()
LOGIN_CONFIRM_SETTLE_SECONDS = 8
QR_READY_TIMEOUT = 90
LOGIN_JOB_TIMEOUT = 420


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False))


def status() -> dict:
    try:
        value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get('state') not in {'pending', 'success', 'failed'}:
            return {'state': 'failed', 'error': 'LOGIN_STATE_INVALID', 'message': '登录任务状态损坏，请重新运行 xhs-publish login'}
        return value
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {'state': 'failed', 'error': 'LOGIN_STATE_INVALID', 'message': '登录任务状态无法读取，请重新运行 xhs-publish login'}


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


def process_identity(pid: object) -> str | None:
    if isinstance(pid, bool):
        return None
    try:
        pid = int(pid)
        if pid <= 0:
            return None
        os.kill(pid, 0)
        if sys.platform.startswith('linux'):
            fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            return None if fields[0] in {'Z', 'X'} else f'linux:{fields[19]}'
        result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=', '-o', 'lstart='],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=2)
        fields = result.stdout.strip().split(maxsplit=1)
        return fields[1] if result.returncode == 0 and len(fields) == 2 and not fields[0].startswith(('Z', 'X')) else None
    except (OSError, ValueError, TypeError, IndexError, subprocess.TimeoutExpired):
        return None


def process_alive(pid, identity=None) -> bool:
    current = process_identity(pid)
    return current is not None and (identity is None or current == identity)


@contextmanager
def login_lock():
    LOGIN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def qr_path(current):
    return Path(current.get('qr_path') or QR_FILE)


def fail_locked(current, error, message):
    current.update({'state': 'failed', 'error': error, 'message': message,
                    'finished_at': datetime.now(timezone.utc).isoformat()})
    save_status(current)
    qr_path(current).unlink(missing_ok=True)
    return current


def refresh_locked(child=None):
    current = status()
    if current.get('state') != 'pending':
        return current
    pid, identity = current.get('pid'), current.get('process_identity')
    if child is not None and child.pid == pid and child.poll() is not None:
        reason = ('LOGIN_WORKER_EXITED', 'Creator 登录后台任务已退出；请重新运行 xhs-publish login')
    elif not process_alive(pid, identity):
        reason = ('LOGIN_WORKER_EXITED', 'Creator 登录后台任务已退出；请重新运行 xhs-publish login')
    elif not identity or not current.get('owner_identity'):
        reason = ('LOGIN_JOB_UNTRACKED', '旧登录任务缺少进程标识，请重新运行 xhs-publish login')
    elif not process_alive(current.get('owner_pid'), current['owner_identity']):
        reason = ('LOGIN_OWNER_EXITED', '原登录命令已结束；请重新运行 xhs-publish login')
    elif not isinstance(current.get('expires_at'), (int, float)) or time.time() >= current['expires_at']:
        reason = ('LOGIN_TIMEOUT', 'Creator 登录任务已超时，请重新运行 xhs-publish login')
    else:
        return current
    fail_locked(current, *reason)
    if identity and process_alive(pid, identity):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    return current


def refresh_status(child=None):
    with login_lock():
        return refresh_locked(child)


def fail_run(run_id, error, message):
    with login_lock():
        current = status()
        if current.get('run_id') == run_id and current.get('state') == 'pending':
            fail_locked(current, error, message)


def result(current):
    state = current.get('state', 'missing')
    if state == 'success':
        return {'ok': True, 'state': 'authenticated', 'message': 'Creator 会话已就位'}, 0
    if state == 'pending':
        return {'ok': False, 'state': state, 'error': 'LOGIN_PENDING',
                'message': '登录任务运行中，尚未取得最终登录结果',
                'qr_path': str(qr_path(current)) if qr_path(current).is_file() else None}, 2
    if state == 'failed':
        return {'ok': False, 'state': state, 'error': current.get('error', 'LOGIN_FAILED'),
                'message': current.get('message', 'Creator 登录失败'), 'qr_path': None,
                'log_path': str(WORKER_LOG)}, 1
    return {'ok': False, 'state': state, 'error': 'NO_LOGIN_ATTEMPT',
            'message': '先运行 xhs-publish login'}, 2


def reap_worker(child):
    try:
        child.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        try:
            child.terminate()
        except ProcessLookupError:
            pass
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=2)


class LoginCancelled(BaseException):
    pass


def login() -> int:
    child, run_id, owns_run = None, None, False
    handlers = {}
    def cancel(_signum, _frame):
        raise LoginCancelled()
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(signum, cancel)
        with login_lock():
            current = refresh_locked()
            if current.get('state') != 'pending':
                run_id, owns_run = uuid4().hex, True
                image = QR_FILE.with_name(f'{QR_FILE.stem}-{run_id}{QR_FILE.suffix}')
                current = {'state': 'pending', 'run_id': run_id, 'qr_path': str(image),
                           'started_at': datetime.now(timezone.utc).isoformat(),
                           'expires_at': time.time() + LOGIN_JOB_TIMEOUT,
                           'owner_pid': os.getpid(), 'owner_identity': process_identity(os.getpid())}
                save_status(current)
                WORKER_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                child = subprocess.Popen(
                    logged_worker_command(WORKER_LOG, [sys.executable, __file__, 'worker', run_id]),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True, env={**os.environ, 'XHS_CREATOR_QR_IMAGE': str(image)})
                current.update({'pid': child.pid, 'process_identity': process_identity(child.pid)})
                save_status(current)
            run_id = current['run_id']
        deadline = time.monotonic() + max(0, current['expires_at'] - time.time())
        qr_deadline = time.monotonic() + QR_READY_TIMEOUT
        emitted = False
        while True:
            current = refresh_status(child)
            if current.get('run_id') != run_id:
                emit({'ok': False, 'state': 'failed', 'error': 'LOGIN_TASK_CHANGED', 'message': '登录任务已变化，请查询当前任务'})
                return 1
            if current.get('state') != 'pending':
                payload, code = result(current)
                emit(payload)
                return code
            if time.monotonic() >= deadline:
                fail_run(run_id, 'LOGIN_TIMEOUT', 'Creator 登录任务已超时，请重新运行 xhs-publish login')
                continue
            try:
                ready = qr_path(current).is_file() and qr_path(current).stat().st_size > 0
            except FileNotFoundError:
                ready = False
            if not emitted and ready:
                emit({'ok': True, 'state': 'awaiting_scan', 'qr_path': str(qr_path(current)),
                      'message': '将二维码图片发给用户；保持当前任务运行，用户确认后运行 login-confirm'})
                sys.stdout.flush()
                emitted = True
            if not emitted and time.monotonic() >= qr_deadline:
                fail_run(run_id, 'QR_NOT_READY', 'Creator 二维码准备超时，请重新运行 xhs-publish login')
                continue
            time.sleep(0.25)
    except (LoginCancelled, KeyboardInterrupt):
        if owns_run:
            fail_run(run_id, 'LOGIN_CANCELLED', 'Creator 登录任务已取消')
        emit({'ok': False, 'state': 'failed', 'error': 'LOGIN_CANCELLED', 'message': 'Creator 登录任务已取消'})
        return 1
    except Exception:
        if owns_run and run_id:
            fail_run(run_id, 'LOGIN_START_FAILED', 'Creator 登录任务启动失败，请查看私有日志')
        raise
    finally:
        try:
            if child is not None:
                reap_worker(child)
        finally:
            for signum, previous in handlers.items():
                signal.signal(signum, previous)


@contextmanager
def commit_guard(run_id):
    with login_lock():
        current = refresh_locked()
        if current.get('run_id') != run_id or current.get('state') != 'pending':
            raise RuntimeError('Creator 登录任务已变化或结束，拒绝写入旧会话')
        yield


def worker(run_id: str) -> int:
    with login_lock():
        current = status()
        if current.get('run_id') != run_id or current.get('state') != 'pending':
            return 1
    try:
        login_local(commit_guard=lambda: commit_guard(run_id), show_in_terminal=False)
        state, message = "success", "Creator 本地 HTTP 会话已就位"
    except Exception as exc:
        state, message = "failed", str(exc)[:200]
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        current = status()
        if current.get("run_id") == run_id and current.get('state') == 'pending':
            current.update({"state": state, "message": message,
                            "finished_at": datetime.now(timezone.utc).isoformat()})
            save_status(current)
            qr_path(current).unlink(missing_ok=True)
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
    current = refresh_status()
    deadline = time.monotonic() + LOGIN_CONFIRM_SETTLE_SECONDS
    while current.get("state") == "pending" and time.monotonic() < deadline:
        time.sleep(0.5)
        current = refresh_status()
    if current.get('state') == 'success':
        return check()
    payload, code = result(current)
    emit(payload)
    return code


def main(argv: list[str]) -> int:
    # Internal worker cannot be entered through the public wrapper.
    if len(argv) == 2 and argv[0] == 'worker':
        return worker(argv[1])
    parser = argparse.ArgumentParser(prog='xhs-publish', description='Creator 登录与会话管理')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('login', help='输出扫码图片并保持任务运行，直到登录完成或失败')
    commands.add_parser('login-confirm', help='查询当前登录任务并验证已完成的会话')
    commands.add_parser('check', help='验证已保存的 Creator 会话')
    args = parser.parse_args(argv)
    try:
        return {'login': login, 'login-confirm': login_confirm, 'check': check}[args.command]()
    except Exception as exc:
        emit({'ok': False, 'error': 'LOGIN_COMMAND_FAILED', 'message': str(exc)[:200]})
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
