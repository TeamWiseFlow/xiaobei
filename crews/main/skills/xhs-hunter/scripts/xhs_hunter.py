#!/usr/bin/env python3
"""Agent-facing XHS PC HTTP hunter. All output is JSON."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import inspect
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse
from uuid import uuid4

from xhs_utils.pc_session import LOGIN_DIR, SESSION_FILE, SessionMissing, load_auth, save_auth, session_lock
from xhs_utils.runtime_logs import logged_worker_command
from xhs_utils.verification import VerificationRequired
import verification_flow


STATUS_FILE = SESSION_FILE.with_name('xhs-pc-login-status.json')
LOGIN_LOCK = SESSION_FILE.with_name('xhs-pc-login.lock')
QR_FILE = SESSION_FILE.with_name('xhs-pc-qr.png')
WORKER_LOG = Path.home() / '.openclaw' / 'logs' / 'xhs-pc-login.log'
QR_READY_TIMEOUT = 90
LOGIN_JOB_TIMEOUT = 420
COUNT_FIELDS = ('liked_count', 'collected_count', 'comment_count', 'share_count')


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str))


def _count_number(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    raw = str(value).strip().replace(',', '').replace('，', '')
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*([千万亿]?)', raw)
    if not match:
        return None
    factor = {'': 1, '千': 1000, '万': 10000, '亿': 100000000}[match.group(2)]
    try:
        return int(Decimal(match.group(1)) * factor)
    except InvalidOperation:
        return None


def _with_numeric_counts(value: dict) -> dict:
    result = dict(value)
    for key in COUNT_FIELDS:
        if key in value:
            result[f'{key}_num'] = _count_number(value[key])
    for key in ('interact_info', 'note_card'):
        if isinstance(value.get(key), dict):
            result[key] = _with_numeric_counts(value[key])
    return result


def _search_note_cards(items: list) -> list:
    return [item for item in items if isinstance(item, dict)
            and item.get('model_type') == 'note'
            and isinstance(item.get('note_card'), dict)
            and str(item['note_card'].get('display_title') or
                    item['note_card'].get('title') or '').strip()]


def _note_has_content(note: dict) -> bool:
    metrics = note.get('metrics') or {}
    return bool(note.get('title') or note.get('content') or
                any(value is not None and value != '' for key, value in metrics.items()
                    if key in COUNT_FIELDS))


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(f'.{path.name}.{os.getpid()}')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def login_status() -> dict:
    try:
        data = json.loads(STATUS_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _process_identity(pid) -> str | None:
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


def _alive(pid, identity=None) -> bool:
    current = _process_identity(pid)
    return current is not None and (identity is None or current == identity)


@contextmanager
def _login_lock():
    LOGIN_LOCK.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(LOGIN_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _fail_login_locked(current, error, message):
    current.update({'state': 'failed', 'error': error, 'message': message,
                    'finished_at': datetime.now(timezone.utc).isoformat()})
    _atomic_json(STATUS_FILE, current)
    QR_FILE.unlink(missing_ok=True)
    return current


def _refresh_login_locked(worker=None):
    current = login_status()
    if current.get('state') != 'pending':
        return current
    pid, identity = current.get('pid'), current.get('process_identity')
    if worker is not None and worker.pid == pid and worker.poll() is not None:
        reason = ('LOGIN_WORKER_EXITED', '登录后台任务已退出；本次扫码结果未完成，请重新运行 xhs-hunter login')
    elif not _alive(pid, identity):
        reason = ('LOGIN_WORKER_EXITED', '登录后台任务已退出；本次扫码结果未完成，请重新运行 xhs-hunter login')
    elif not identity or not current.get('owner_identity'):
        reason = ('LOGIN_JOB_UNTRACKED', '旧登录任务缺少进程标识，请重新运行 xhs-hunter login')
    elif not _alive(current.get('owner_pid'), current['owner_identity']):
        reason = ('LOGIN_OWNER_EXITED', '登录命令已结束；本次扫码结果未完成，请重新运行 xhs-hunter login')
    elif not isinstance(current.get('expires_at'), (int, float)) or time.time() >= current['expires_at']:
        reason = ('LOGIN_TIMEOUT', '登录任务已超时，请重新运行 xhs-hunter login')
    else:
        return current
    _fail_login_locked(current, *reason)
    # Only signal the recorded process when its identity still matches.
    if identity and _alive(pid, identity):
        try:
            os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    return current


def refresh_login_status(worker=None):
    with _login_lock():
        return _refresh_login_locked(worker)


def _fail_login(run_id, error, message):
    with _login_lock():
        current = login_status()
        if current.get('run_id') == run_id and current.get('state') == 'pending':
            return _fail_login_locked(current, error, message)
        return current


def _login_result(current):
    state = current.get('state', 'missing')
    if state == 'success':
        return {'ok': True, 'state': 'authenticated', 'session_path': str(SESSION_FILE)}, 0
    if state == 'awaiting_verification':
        return {'ok': False, 'state': state, 'verification': current.get('verification'),
                'message': current.get('message')}, 4
    if state == 'failed':
        return {'ok': False, 'state': state, 'error': current.get('error', 'LOGIN_FAILED'),
                'message': current.get('message'), 'qr_path': None, 'log_path': str(WORKER_LOG)}, 1
    return {'ok': False, 'state': state,
            'message': '登录任务运行中，尚未取得最终登录结果' if state == 'pending' else '请先运行 xhs-hunter login',
            'qr_path': str(QR_FILE) if state == 'pending' and QR_FILE.is_file() else None}, 1


def _reap_login_worker(worker):
    try:
        worker.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        try:
            worker.terminate()
        except ProcessLookupError:
            pass
    try:
        worker.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(worker.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        worker.wait(timeout=2)


class _LoginCancelled(BaseException):
    pass


def start_login() -> int:
    worker, run_id = None, None
    owns_run = False
    handlers = {}
    def cancel(_signum, _frame):
        raise _LoginCancelled()
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(signum, cancel)
        with _login_lock():
            current = _refresh_login_locked()
            if current.get('state') != 'pending':
                QR_FILE.unlink(missing_ok=True)
                run_id = uuid4().hex
                owns_run = True
                current = {'state': 'pending', 'run_id': run_id,
                           'started_at': datetime.now(timezone.utc).isoformat(),
                           'expires_at': time.time() + LOGIN_JOB_TIMEOUT,
                           'owner_pid': os.getpid(), 'owner_identity': _process_identity(os.getpid())}
                _atomic_json(STATUS_FILE, current)
                WORKER_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                worker = subprocess.Popen(
                    logged_worker_command(WORKER_LOG, [sys.executable, __file__, '_login-worker', run_id]),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env={**os.environ, 'XHS_PC_QR_IMAGE': str(QR_FILE)},
                )
                current.update({'pid': worker.pid, 'process_identity': _process_identity(worker.pid)})
                _atomic_json(STATUS_FILE, current)
            run_id = current['run_id']

        deadline = time.monotonic() + max(0, current['expires_at'] - time.time())
        qr_deadline = time.monotonic() + QR_READY_TIMEOUT
        qr_emitted = False
        while True:
            current = refresh_login_status(worker)
            if current.get('run_id') != run_id:
                emit({'ok': False, 'state': 'failed', 'error': 'LOGIN_TASK_CHANGED',
                      'message': '登录任务已变化，请查询当前任务'})
                return 1
            if current.get('state') != 'pending':
                result, code = _login_result(current)
                emit(result)
                return code
            if time.monotonic() >= deadline:
                current = _fail_login(run_id, 'LOGIN_TIMEOUT', '登录任务已超时，请重新运行 xhs-hunter login')
                continue
            try:
                qr_ready = QR_FILE.is_file() and QR_FILE.stat().st_size > 0
            except FileNotFoundError:
                qr_ready = False
            if not qr_emitted and qr_ready:
                emit({'ok': True, 'state': 'awaiting_scan', 'qr_path': str(QR_FILE),
                      'message': '将二维码图片交给用户扫码；保持当前任务运行，用户确认后运行 login-confirm'})
                sys.stdout.flush()
                qr_emitted = True
            if not qr_emitted and time.monotonic() >= qr_deadline:
                current = _fail_login(run_id, 'QR_NOT_READY', '登录二维码准备超时，请重新运行 xhs-hunter login')
                continue
            time.sleep(0.25)
    except (_LoginCancelled, KeyboardInterrupt):
        if owns_run:
            _fail_login(run_id, 'LOGIN_CANCELLED', '登录任务已取消，请重新运行 xhs-hunter login')
        emit({'ok': False, 'state': 'failed', 'error': 'LOGIN_CANCELLED', 'message': '登录任务已取消'})
        return 1
    except Exception:
        if owns_run and run_id:
            _fail_login(run_id, 'LOGIN_START_FAILED', '登录任务启动失败，请查看私有登录日志')
        raise
    finally:
        try:
            if worker is not None:
                _reap_login_worker(worker)
        finally:
            for signum, previous in handlers.items():
                signal.signal(signum, previous)


def login_worker(run_id: str) -> int:
    client = None
    verification = None
    try:
        from xhs_utils.xhs_pc import XHSPcAuth
        from xhs_utils.xhs_pc.login import XHSLoginApi

        client = XHSLoginApi()
        render_qr = client.show_qrcode_image
        def show_current_qr(url):
            with _login_lock():
                current = _refresh_login_locked()
                if current.get('run_id') != run_id or current.get('state') != 'pending':
                    raise RuntimeError('登录任务已变化，拒绝写入旧二维码')
                return render_qr(url)
        client.show_qrcode_image = show_current_qr
        cookies = client.qrcode_login(show_in_terminal=False)
        if not cookies:
            raise RuntimeError('扫码登录未返回正式会话')
        local, session = client.profile.browser_storage_snapshot()
        auth = XHSPcAuth.from_cookie(
            cookies, local_storage=local, session_storage=session,
            host_cookie_state=client.host_cookie_state(), dsl=client.dsl)
        try:
            guard = os.open(LOGIN_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(guard, fcntl.LOCK_EX)
                current = _refresh_login_locked()
                if current.get('run_id') != run_id or current.get('state') != 'pending':
                    raise RuntimeError('登录任务已变化，拒绝写入旧会话')
                with session_lock():
                    save_auth(auth)
            finally:
                fcntl.flock(guard, fcntl.LOCK_UN)
                os.close(guard)
        finally:
            auth.close()
        state, message = 'success', 'PC 本地 HTTP 会话已就位'
    except VerificationRequired as exc:
        try:
            verification = verification_flow.capture(client, exc, run_id=run_id)
            state, message = 'awaiting_verification', '需要用户安全验证；运行 xhs-hunter verify-start'
        except Exception:
            state, message = 'failed', '无法保存登录安全验证任务，请查看私有登录日志'
    except Exception as exc:
        state, message = 'failed', f'{type(exc).__name__}: {str(exc)[:160]}'
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                state, message = 'failed', '登录资源关闭失败，请查看私有登录日志'
    fd = os.open(LOGIN_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = login_status()
        if current.get('run_id') == run_id and current.get('state') == 'pending':
            current.update({'state': state, 'message': message,
                            'finished_at': datetime.now(timezone.utc).isoformat()})
            if verification:
                current['verification'] = verification
            _atomic_json(STATUS_FILE, current)
            QR_FILE.unlink(missing_ok=True)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return 0 if state == 'success' else 1


def phone_login() -> int:
    from xhs_utils.xhs_pc import XHSPcAuth

    auth = XHSPcAuth.from_phone_login()
    try:
        with session_lock():
            save_auth(auth)
    finally:
        auth.close()
    emit({'ok': True, 'session_path': str(SESSION_FILE)})
    return 0


def check_login() -> int:
    with session_lock():
        auth = load_auth()
        try:
            from xhs_utils.xhs_pc.api import XHS_Apis

            success, message, response = XHS_Apis(auth).get_user_me()
            if success:
                save_auth(auth)
        finally:
            auth.close()
    if not success:
        emit({'ok': False, 'error': 'PC_REJECTED', 'message': message})
        return 1
    data = response.get('data') if isinstance(response, dict) else {}
    emit({'ok': True, 'user_id': auth.user_id, 'nickname': (data or {}).get('nickname'),
          'session_path': str(SESSION_FILE)})
    return 0


def _methods() -> dict:
    from xhs_utils.xhs_pc.api import XHS_Apis

    return {
        name: member for name, member in inspect.getmembers(XHS_Apis)
        if callable(member) and not name.startswith('_') and name not in {'close'}
    }


def call_method(name: str, args: list | None = None, kwargs: dict | None = None) -> dict:
    methods = _methods()
    if name not in methods or name == 'bootstrap':
        raise ValueError(f'未知 PC 接口 {name}；运行 methods 查看可用接口')
    verification = None
    with session_lock():
        auth = load_auth()
        try:
            from xhs_utils.xhs_pc.api import XHS_Apis

            result = getattr(XHS_Apis(auth), name)(*(args or []), **(kwargs or {}))
            save_auth(auth)
        except VerificationRequired as exc:
            verification = exc
        finally:
            auth.close()
    if verification:
        return verification_flow.capture(auth, verification)
    if isinstance(result, tuple) and len(result) == 3:
        success, message, data = result
        return {'ok': bool(success), 'method': name, 'message': str(message), 'data': data}
    return {'ok': True, 'method': name, 'data': result}


def bounded_user_notes(user_url: str, count: int) -> dict:
    parsed = urlparse(user_url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}:
        raise ValueError('请提供小红书用户主页 HTTPS 链接')
    if not parsed.path.startswith('/user/profile/'):
        raise ValueError('用户主页路径应为 /user/profile/<user_id>')
    user_id = parsed.path.rstrip('/').split('/')[-1]
    if not re.fullmatch(r'[A-Za-z0-9]+', user_id):
        raise ValueError('用户主页链接缺少 user_id')
    from urllib.parse import parse_qs

    query = parse_qs(parsed.query)
    token = (query.get('xsec_token') or [''])[0]
    source = (query.get('xsec_source') or ['pc_search'])[0]
    notes, cursor = [], ''
    with session_lock():
        auth = load_auth()
        try:
            from xhs_utils.xhs_pc.api import XHS_Apis

            api = XHS_Apis(auth)
            for _ in range(min(10, (count + 19) // 20 + 1)):
                success, message, payload = api.get_user_note_info(user_id, cursor, token, source)
                if not success:
                    save_auth(auth)
                    return {'ok': False, 'message': str(message), 'data': notes}
                data = (payload or {}).get('data') or {}
                page = data.get('notes') or []
                notes.extend(page)
                new_cursor = str(data.get('cursor') or '')
                if len(notes) >= count or not page or not data.get('has_more') or new_cursor == cursor:
                    break
                cursor = new_cursor
            save_auth(auth)
        finally:
            auth.close()
    return {'ok': True, 'data': [_with_numeric_counts(note) for note in notes[:count]]}


def bounded_feed(category: str, count: int) -> dict:
    notes, cursor, refresh_type, note_index = [], '', 1, 0
    with session_lock():
        auth = load_auth()
        try:
            from xhs_utils.xhs_pc.api import XHS_Apis

            api = XHS_Apis(auth)
            for _ in range(min(10, (count + 19) // 20 + 1)):
                success, message, payload = api.get_homefeed_recommend(
                    category, cursor, refresh_type, note_index)
                if not success:
                    save_auth(auth)
                    return {'ok': False, 'message': str(message), 'data': notes}
                data = (payload or {}).get('data') or {}
                page = data.get('items') or []
                notes.extend(page)
                new_cursor = str(data.get('cursor_score') or '')
                if len(notes) >= count or not page or new_cursor == cursor:
                    break
                cursor, refresh_type, note_index = new_cursor, 3, note_index + len(page)
            save_auth(auth)
        finally:
            auth.close()
    return {'ok': True, 'data': notes[:count]}


def _note_url(value: str) -> str:
    value = value.strip()
    if not value.startswith('https://') or re.search(r'\s', value):
        match = re.search(r'https://[^\s<>"“”]+', value)
        if not match:
            raise ValueError('请提供小红书笔记 HTTPS 链接或 xhslink 短链')
        value = match.group(0).rstrip('。，、；！）)]}')
    parsed = urlparse(value)
    if parsed.scheme == 'https' and parsed.hostname in {'xhslink.com', 'www.xhslink.com',
                                                          'xhslink.cn', 'www.xhslink.cn'}:
        import requests

        try:
            with requests.get(value, stream=True, timeout=(10, 15)) as response:
                response.raise_for_status()
                value = response.url
        except requests.RequestException as exc:
            raise ValueError(f'小红书短链展开失败：{type(exc).__name__}；未获取笔记详情') from None
        parsed = urlparse(value)
    for _ in range(5):
        if (parsed.scheme == 'http' and parsed.hostname in {'www.xiaohongshu.com', 'xiaohongshu.com'}
                and not parsed.username and not parsed.password and parsed.port in (None, 80)):
            # App share redirects may embed an absolute HTTP note URL inside HTTPS login.
            parsed = parsed._replace(scheme='https', netloc=parsed.hostname)
        if (parsed.scheme != 'https' or parsed.hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError('小红书链接解析失败：目标不是受支持的小红书 HTTPS 地址')
        match = re.fullmatch(r'/(?:explore|discovery/item)/([A-Za-z0-9]+)/?', parsed.path)
        if match:
            return urlunparse(parsed._replace(path=f'/explore/{match.group(1)}'))
        target = (parse_qs(parsed.query).get('redirectPath') or [''])[0]
        if not target:
            break
        # Login redirects retain the original note and its matching xsec_token.
        for _ in range(3):
            if target.startswith(('/', 'https://', 'http://')):
                break
            decoded = unquote(target)
            if decoded == target:
                break
            target = decoded
        value = urljoin('https://www.xiaohongshu.com/', target)
        parsed = urlparse(value)
    raise ValueError('小红书链接解析失败：重定向后没有有效笔记路径；请重新分享笔记链接')


def _media_https_url(value: str) -> str:
    parsed = urlparse(value)
    hostname = parsed.hostname or ''
    if parsed.scheme == 'http' and (
        hostname == 'xiaohongshu.com' or hostname.endswith('.xiaohongshu.com')
        or hostname == 'xhscdn.com' or hostname.endswith('.xhscdn.com')
    ):
        return urlunparse(parsed._replace(scheme='https'))
    return value


def normalize_note(raw: dict, url: str) -> dict:
    items = ((raw or {}).get('data') or {}).get('items') or []
    if not items:
        raise ValueError('笔记详情无 items')
    item = items[0]
    card = item.get('note_card') or {}
    user = card.get('user') or {}
    interaction = card.get('interact_info') or {}
    images = []
    for image in card.get('image_list') or []:
        infos = image.get('info_list') or []
        address = next((info.get('url') for info in reversed(infos) if info.get('url')), None)
        if address:
            images.append(_media_https_url(address))
    video = card.get('video') or {}
    streams = ((video.get('media') or {}).get('stream') or {})
    if not isinstance(streams, dict):
        streams = {}
    preferred_codecs = ('h264', 'EF4', 'h265', 'EF5')
    codec_order = (*preferred_codecs, *(name for name in streams if name not in preferred_codecs))
    video_url = None
    for codec in codec_order:
        entries = streams.get(codec)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            backup_urls = entry.get('backup_urls')
            if not isinstance(backup_urls, list):
                backup_urls = []
            video_url = next((value for value in (entry.get('master_url'), entry.get('url'), *backup_urls)
                              if isinstance(value, str) and value), None)
            if video_url:
                break
        if video_url:
            break
    if not video_url:
        origin_key = (video.get('consumer') or {}).get('origin_video_key')
        if origin_key:
            video_url = f'https://sns-video-bd.xhscdn.com/{origin_key}'
    return {
        'note_id': item.get('id'), 'url': url, 'type': card.get('type'),
        'title': card.get('title') or '', 'content': card.get('desc') or '',
        'author': {'user_id': user.get('user_id'), 'nickname': user.get('nickname'),
                   'avatar': user.get('avatar')},
        'publish_time_ms': card.get('time'), 'ip_location': card.get('ip_location'),
        'tags': [tag.get('name') for tag in card.get('tag_list') or [] if tag.get('name')],
        'metrics': _with_numeric_counts({key: interaction.get(key) for key in COUNT_FIELDS}),
        'images': images, 'video_url': _media_https_url(video_url) if video_url else None,
    }


def _download(url: str, path: Path) -> None:
    import requests

    url = _media_https_url(url)
    parsed = urlparse(url)
    hostname = parsed.hostname or ''
    if parsed.scheme != 'https' or not (
        hostname == 'xiaohongshu.com' or hostname.endswith('.xiaohongshu.com')
        or hostname == 'xhscdn.com' or hostname.endswith('.xhscdn.com')
    ):
        raise ValueError(f'非小红书媒体域名: {hostname}')
    with requests.get(url, stream=True, timeout=(15, 60)) as response:
        response.raise_for_status()
        with path.open('wb') as stream:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    stream.write(chunk)


def fetch_note(url: str, output_dir: str | None = None, download_media: bool = False,
               video_only: bool = False) -> dict:
    url = _note_url(url)
    response = call_method('get_note_info', [url])
    if not response['ok']:
        return response
    note = normalize_note(response['data'], url)
    if not _note_has_content(note):
        return {'ok': False, 'error': 'NOTE_UNAVAILABLE',
                'message': '笔记详情为空；token 无效或笔记不可见，请从搜索或用户列表重新获取对应链接',
                'url': url}
    if video_only and (note.get('type') != 'video' or not note.get('video_url')):
        return {'ok': False, 'error': 'VIDEO_REQUIRED',
                'message': '图文请使用 expert-xhs workflow 分析，下载使用 xhs-hunter'}
    return save_note(note, output_dir, download_media, video_only=video_only)


def save_note(note: dict, output_dir: str | None, download_media: bool,
              *, video_only: bool = False) -> dict:
    result = {'ok': True, 'note': note}
    if output_dir:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'note.json').write_text(json.dumps(note, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result['note_path'] = str(directory / 'note.json')
        if download_media:
            files = []
            for index, image in enumerate([] if video_only else note['images'], 1):
                target = directory / f'image-{index:02d}.jpg'
                _download(image, target)
                files.append(str(target))
            if note['video_url']:
                target = directory / 'video.mp4'
                _download(note['video_url'], target)
                files.append(str(target))
            result['media_paths'] = files
    elif download_media:
        raise ValueError('--download-media 需要 --output-dir')
    return result


def collect(source: str, target: str, *, count: int, output_dir: str,
            download_media: bool, xlsx: bool) -> dict:
    if not 1 <= count <= 100:
        raise ValueError('--count 必须在 1 至 100 之间')
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if source == 'search':
        listing = call_method('search_some_note', [target, count])
        if not listing['ok']:
            return listing
        cards = _search_note_cards(listing['data'])
        urls = [f"https://www.xiaohongshu.com/explore/{item['id']}"
                f"?xsec_token={quote(item.get('xsec_token') or '')}&xsec_source=pc_search"
                for item in cards if item.get('id')]
    elif source == 'user':
        listing = bounded_user_notes(target, count)
        if not listing['ok']:
            return listing
        urls = [f"https://www.xiaohongshu.com/explore/{item['note_id']}"
                f"?xsec_token={quote(item.get('xsec_token') or '')}&xsec_source=pc_user"
                for item in listing['data'] if item.get('note_id')]
    else:
        path = Path(target).expanduser()
        urls = [line.strip() for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.startswith('#')][:count]
    notes, errors = [], []
    verification = None
    with session_lock():
        auth = load_auth()
        try:
            from xhs_utils.xhs_pc.api import XHS_Apis

            api = XHS_Apis(auth)
            for index, input_url in enumerate(urls, 1):
                try:
                    url = _note_url(input_url)
                    success, message, payload = api.get_note_info(url)
                    if not success:
                        errors.append({'url': input_url, 'message': str(message)})
                        continue
                    note = normalize_note(payload, url)
                    if not _note_has_content(note):
                        raise ValueError('笔记详情为空；token 无效或笔记不可见')
                    note_dir = directory / f'note-{index:03d}'
                    save_note(note, str(note_dir), download_media)
                    notes.append(note)
                except VerificationRequired as exc:
                    verification = exc
                    break
                except Exception as exc:
                    errors.append({'url': input_url, 'message': f'{type(exc).__name__}: {str(exc)[:160]}'})
            save_auth(auth)
        finally:
            auth.close()
    index_path = directory / 'notes.json'
    index_path.write_text(json.dumps({'notes': notes, 'errors': errors}, ensure_ascii=False,
                                     indent=2) + '\n', encoding='utf-8')
    if verification:
        return {**verification_flow.capture(auth, verification),
                'count': len(notes), 'index_path': str(index_path)}
    result = {'ok': bool(notes), 'count': len(notes), 'failed': len(errors),
              'index_path': str(index_path), 'errors': errors}
    if xlsx and notes:
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = '笔记'
        fields = ('note_id', 'url', 'type', 'title', 'content', 'author',
                  'publish_time_ms', 'ip_location', 'tags', 'metrics', 'images', 'video_url')
        sheet.append(fields)
        for note in notes:
            sheet.append([json.dumps(note.get(field), ensure_ascii=False)
                          if isinstance(note.get(field), (dict, list))
                          else str(note.get(field) or '') for field in fields])
            for cell in sheet[sheet.max_row]:
                cell.data_type = 's'
        excel_path = directory / 'notes.xlsx'
        workbook.save(excel_path)
        result['excel_path'] = str(excel_path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='小红书 PC 端搜索、笔记、用户、评论与媒体采集')
    subs = parser.add_subparsers(dest='command', required=True)
    login_parser = subs.add_parser('login', help='输出二维码并保持登录任务运行，直到成功、验证或失败')
    # Accept the previous opt-in flag; retaining the root is now the default.
    login_parser.add_argument('--keep-alive', action='store_true',
                              help=argparse.SUPPRESS)
    subs.add_parser('login-confirm', help='查询扫码进度并验证 PC 登录态')
    subs.add_parser('login-phone', help='交互式手机号验证码登录')
    subs.add_parser('check', help='校验已保存的 PC 登录态')
    subs.add_parser('methods', help='列出全部可调用 PC 接口及参数')
    subs.add_parser('verify-start', help='准备当前安全验证，发送一次短信或生成验证二维码')
    verify = subs.add_parser('verify-code', help='提交当前安全验证的短信验证码')
    verify.add_argument('--code-file', required=True, help='权限 0600 的六位验证码文件')
    subs.add_parser('verify-confirm', help='查询验证二维码状态并续接原登录')
    generic = subs.add_parser('call', help='调用任一 PC 公开接口')
    generic.add_argument('method')
    generic.add_argument('--args', default='[]', help='JSON 数组')
    generic.add_argument('--kwargs', default='{}', help='JSON 对象')
    search = subs.add_parser('search-notes')
    search.add_argument('keyword')
    search.add_argument('--count', type=int, default=20)
    search.add_argument('--sort', type=int, default=0, choices=range(5))
    search.add_argument('--type', type=int, default=0, choices=range(3))
    users = subs.add_parser('search-users')
    users.add_argument('keyword')
    users.add_argument('--count', type=int, default=20)
    note = subs.add_parser('fetch')
    note.add_argument('url')
    note.add_argument('--output-dir')
    note.add_argument('--download-media', action='store_true')
    note.add_argument('--video-only', action='store_true', help='只接受视频且只下载视频文件')
    comments = subs.add_parser('comments')
    comments.add_argument('url')
    comments.add_argument('--limit', type=int, help='最多读取前 N 条一级评论，范围 1..1000')
    comments.add_argument('--no-inner', action='store_true', help='不读取二级评论')
    user_notes = subs.add_parser('user-notes')
    user_notes.add_argument('url')
    user_notes.add_argument('--count', type=int, default=20)
    feed = subs.add_parser('feed')
    feed.add_argument('category')
    feed.add_argument('--count', type=int, default=20)
    batch = subs.add_parser('collect', help='批量采集笔记，保存 JSON、媒体和可选 Excel')
    batch.add_argument('source', choices=('search', 'user', 'urls'))
    batch.add_argument('target', help='关键词、用户主页 URL 或每行一条笔记 URL 的文件')
    batch.add_argument('--count', type=int, default=20)
    batch.add_argument('--output-dir', required=True)
    batch.add_argument('--download-media', action='store_true')
    batch.add_argument('--xlsx', action='store_true')
    args = parser.parse_args()

    try:
        if args.command == 'login':
            return start_login()
        if args.command == '_login-worker':
            return login_worker(args.run_id)
        if args.command == 'login-phone':
            return phone_login()
        if args.command in {'verify-start', 'verify-code', 'verify-confirm'}:
            result = (verification_flow.start() if args.command == 'verify-start'
                      else verification_flow.confirm(args.code_file if args.command == 'verify-code' else None))
            emit(result)
            return 0 if result.get('ok') else 4
        if args.command == 'login-confirm':
            state = refresh_login_status()
            if state.get('state') == 'success':
                return check_login()
            result, code = _login_result(state)
            emit(result)
            return code
        if args.command == 'check':
            return check_login()
        if args.command == 'methods':
            emit({'ok': True, 'methods': {
                name: str(inspect.signature(method)) for name, method in _methods().items()
                if name != 'bootstrap'
            }})
            return 0
        if args.command == 'call':
            positional = json.loads(args.args)
            named = json.loads(args.kwargs)
            if not isinstance(positional, list) or not isinstance(named, dict):
                raise ValueError('--args 必须是 JSON 数组，--kwargs 必须是 JSON 对象')
            result = call_method(args.method, positional, named)
        elif args.command == 'search-notes':
            if not 1 <= args.count <= 100:
                raise ValueError('--count 必须在 1 至 100 之间')
            result = call_method('search_some_note', [args.keyword, args.count],
                                 {'sort_type_choice': args.sort, 'note_type': args.type})
            if result['ok']:
                raw = result['data'] or []
                result['data'] = _search_note_cards(raw)
                result['filtered_out'] = len(raw) - len(result['data'])
        elif args.command == 'search-users':
            if not 1 <= args.count <= 100:
                raise ValueError('--count 必须在 1 至 100 之间')
            result = call_method('search_some_user', [args.keyword, args.count])
        elif args.command == 'fetch':
            result = fetch_note(args.url, args.output_dir, args.download_media, args.video_only)
        elif args.command == 'comments':
            if args.limit is not None and not 1 <= args.limit <= 1000:
                raise ValueError('--limit 必须在 1 至 1000 之间')
            result = call_method('get_note_all_comment', [_note_url(args.url)],
                                 {'limit': args.limit, 'include_inner': not args.no_inner})
        elif args.command == 'user-notes':
            if not 1 <= args.count <= 100:
                raise ValueError('--count 必须在 1 至 100 之间')
            result = bounded_user_notes(args.url, args.count)
        elif args.command == 'feed':
            if not 1 <= args.count <= 100:
                raise ValueError('--count 必须在 1 至 100 之间')
            result = bounded_feed(args.category, args.count)
        elif args.command == 'collect':
            result = collect(args.source, args.target, count=args.count,
                             output_dir=args.output_dir, download_media=args.download_media,
                             xlsx=args.xlsx)
        else:
            parser.error('未知命令')
        emit(result)
        return 0 if result.get('ok') else (4 if result.get('error') == 'VERIFICATION_REQUIRED' else 1)
    except SessionMissing as exc:
        emit({'ok': False, 'error': 'SESSION_MISSING', 'message': str(exc)})
        return 2
    except VerificationRequired as exc:
        if args.command.startswith('verify-'):
            emit({'ok': False, **exc.public(), 'message': '验证请求再次受限；保留原任务，请勿重复发码'})
            return 4
        if args.command == 'login-phone':
            emit({'ok': False, **exc.public(), 'supported': False,
                  'message': '当前手机号登录需要同账号网页安全验证；完成后重新发起登录'})
            return 4
        try:
            result = verification_flow.capture_saved(exc)
        except (OSError, ValueError) as error:
            emit({'ok': False, 'error': 'VERIFICATION_STATE_UNAVAILABLE', 'message': str(error)[:160]})
            return 4
        emit(result)
        return 4
    except Exception as exc:
        emit({'ok': False, 'error': type(exc).__name__, 'message': str(exc)[:300]})
        return 1


if __name__ == '__main__':
    # Internal worker is deliberately absent from the user-visible help.
    if len(sys.argv) == 3 and sys.argv[1] == '_login-worker':
        raise SystemExit(login_worker(sys.argv[2]))
    raise SystemExit(main())
