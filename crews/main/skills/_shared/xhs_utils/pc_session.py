"""Persist the standalone XHS PC login without using browser/login-manager state."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator


LOGIN_DIR = Path.home() / '.openclaw' / 'logins'
SESSION_FILE = Path(os.environ.get('XHS_PC_SESSION_FILE', LOGIN_DIR / 'xhs-pc-local.json')).expanduser()
LOCK_FILE = SESSION_FILE.with_suffix('.lock')


class SessionMissing(RuntimeError):
    pass


@contextmanager
def session_lock() -> Iterator[None]:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_session() -> dict:
    try:
        data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise SessionMissing('PC 会话不存在；运行 xhs-hunter login 扫码') from exc
    except (OSError, ValueError) as exc:
        raise SessionMissing('PC 会话文件无法读取') from exc
    if not isinstance(data, dict) or not isinstance(data.get('cookies'), dict):
        raise SessionMissing('PC 会话格式无效')
    if not data['cookies'].get('a1') or not data['cookies'].get('web_session'):
        raise SessionMissing('PC 会话缺少 a1 或 web_session；请重新扫码')
    return data


def load_auth():
    from xhs_utils.xhs_pc import XHSPcAuth

    state = read_session()
    return XHSPcAuth.from_cookie(
        state['cookies'],
        host_cookie_state=state.get('host_cookie_state') or {},
        local_storage=state.get('local_storage') or {},
        session_storage=state.get('session_storage') or {},
        dsl=state.get('dsl') or '',
        user_id=state.get('user_id') or '',
    )


def save_auth(auth) -> None:
    local, session = auth.profile.browser_storage_snapshot()
    data = {
        'version': 1,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'cookies': auth.profile.cookie_map,
        'host_cookie_state': auth._cookie_store.export_state(),
        'local_storage': local,
        'session_storage': session,
        'dsl': auth.dsl,
        'user_id': auth.user_id,
    }
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, path = tempfile.mkstemp(prefix='.xhs-pc-session-', dir=SESSION_FILE.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
        os.replace(path, SESSION_FILE)
    finally:
        if os.path.exists(path):
            os.unlink(path)
