#!/usr/bin/env python3
"""Agent-facing XHS PC HTTP hunter. All output is JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import quote, urlparse, urlunparse
from uuid import uuid4

from xhs_utils.pc_session import LOGIN_DIR, SESSION_FILE, SessionMissing, load_auth, save_auth, session_lock


STATUS_FILE = LOGIN_DIR / 'xhs-pc-login-status.json'
LOGIN_LOCK = LOGIN_DIR / 'xhs-pc-login.lock'
QR_FILE = LOGIN_DIR / 'xhs-pc-qr.png'
WORKER_LOG = Path.home() / '.openclaw' / 'logs' / 'xhs-pc-login.log'
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


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError, PermissionError):
        return False


def start_login() -> int:
    LOGIN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(LOGIN_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = login_status()
        if current.get('state') != 'pending' or not _alive(current.get('pid')):
            QR_FILE.unlink(missing_ok=True)
            run_id = uuid4().hex
            current = {'state': 'pending', 'run_id': run_id,
                       'started_at': datetime.now(timezone.utc).isoformat()}
            _atomic_json(STATUS_FILE, current)
            WORKER_LOG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            log_fd = os.open(WORKER_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                worker = subprocess.Popen(
                    [sys.executable, __file__, '_login-worker', run_id],
                    stdin=subprocess.DEVNULL, stdout=log_fd, stderr=log_fd,
                    start_new_session=True,
                    env={**os.environ, 'XHS_PC_QR_IMAGE': str(QR_FILE)},
                )
            finally:
                os.close(log_fd)
            current['pid'] = worker.pid
            _atomic_json(STATUS_FILE, current)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = login_status()
        if current.get('state') == 'success':
            emit({'ok': True, 'state': 'authenticated', 'session_path': str(SESSION_FILE)})
            return 0
        if current.get('state') == 'failed':
            emit({'ok': False, 'error': 'LOGIN_FAILED', 'message': current.get('message', '')})
            return 1
        if current.get('pid') and not _alive(current['pid']):
            emit({'ok': False, 'error': 'LOGIN_WORKER_EXITED', 'log_path': str(WORKER_LOG)})
            return 1
        if QR_FILE.is_file() and QR_FILE.stat().st_size:
            emit({'ok': True, 'state': 'awaiting_scan', 'qr_path': str(QR_FILE),
                  'message': '将二维码图片交给用户扫码；用户确认后运行 login-confirm'})
            return 0
        time.sleep(0.25)
    emit({'ok': False, 'error': 'QR_NOT_READY', 'log_path': str(WORKER_LOG)})
    return 1


def login_worker(run_id: str) -> int:
    try:
        from xhs_utils.xhs_pc import XHSPcAuth

        auth = XHSPcAuth.from_qrcode_login(show_in_terminal=False)
        try:
            with session_lock():
                save_auth(auth)
        finally:
            auth.close()
        state, message = 'success', 'PC 本地 HTTP 会话已就位'
    except Exception as exc:
        state, message = 'failed', f'{type(exc).__name__}: {str(exc)[:160]}'
    fd = os.open(LOGIN_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        current = login_status()
        if current.get('run_id') == run_id:
            current.update({'state': state, 'message': message,
                            'finished_at': datetime.now(timezone.utc).isoformat()})
            _atomic_json(STATUS_FILE, current)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    QR_FILE.unlink(missing_ok=True)
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
            from apis.xhs_pc_apis import XHS_Apis

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
    from apis.xhs_pc_apis import XHS_Apis

    return {
        name: member for name, member in inspect.getmembers(XHS_Apis)
        if callable(member) and not name.startswith('_') and name not in {'close'}
    }


def call_method(name: str, args: list | None = None, kwargs: dict | None = None) -> dict:
    methods = _methods()
    if name not in methods or name == 'bootstrap':
        raise ValueError(f'未知 PC 接口 {name}；运行 methods 查看可用接口')
    with session_lock():
        auth = load_auth()
        try:
            from apis.xhs_pc_apis import XHS_Apis

            result = getattr(XHS_Apis(auth), name)(*(args or []), **(kwargs or {}))
            save_auth(auth)
        finally:
            auth.close()
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
            from apis.xhs_pc_apis import XHS_Apis

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
            from apis.xhs_pc_apis import XHS_Apis

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
    parsed = urlparse(value)
    if parsed.scheme == 'https' and parsed.hostname in {'xhslink.com', 'www.xhslink.com',
                                                          'xhslink.cn', 'www.xhslink.cn'}:
        import requests

        with requests.get(value, stream=True, timeout=(10, 15)) as response:
            response.raise_for_status()
            value = response.url
        parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.xiaohongshu.com', 'xiaohongshu.com'}:
        raise ValueError('请提供小红书笔记 HTTPS 链接或 xhslink 短链')
    match = re.fullmatch(r'/(?:explore|discovery/item)/([A-Za-z0-9]+)/?', parsed.path)
    if not match:
        raise ValueError('笔记链接路径应为 /explore/<note_id>')
    if not parsed.path.startswith('/explore/'):
        from urllib.parse import urlunparse

        value = urlunparse(parsed._replace(path=f'/explore/{match.group(1)}'))
    return value


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
    variants = [streams.get('h264') or []] + [
        entries for name, entries in streams.items() if name != 'h264' and isinstance(entries, list)
    ]
    video_url = next((entry.get('master_url') or entry.get('url')
                      for entries in variants for entry in entries
                      if isinstance(entry, dict) and (entry.get('master_url') or entry.get('url'))), None)
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


def fetch_note(url: str, output_dir: str | None = None, download_media: bool = False) -> dict:
    url = _note_url(url)
    response = call_method('get_note_info', [url])
    if not response['ok']:
        return response
    note = normalize_note(response['data'], url)
    if not _note_has_content(note):
        return {'ok': False, 'error': 'NOTE_UNAVAILABLE',
                'message': '笔记详情为空；token 无效或笔记不可见，请从搜索或用户列表重新获取对应链接',
                'url': url}
    return save_note(note, output_dir, download_media)


def save_note(note: dict, output_dir: str | None, download_media: bool) -> dict:
    result = {'ok': True, 'note': note}
    if output_dir:
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'note.json').write_text(json.dumps(note, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        result['note_path'] = str(directory / 'note.json')
        if download_media:
            files = []
            for index, image in enumerate(note['images'], 1):
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
    with session_lock():
        auth = load_auth()
        try:
            from apis.xhs_pc_apis import XHS_Apis

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
                except Exception as exc:
                    errors.append({'url': input_url, 'message': f'{type(exc).__name__}: {str(exc)[:160]}'})
            save_auth(auth)
        finally:
            auth.close()
    index_path = directory / 'notes.json'
    index_path.write_text(json.dumps({'notes': notes, 'errors': errors}, ensure_ascii=False,
                                     indent=2) + '\n', encoding='utf-8')
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
    subs.add_parser('login', help='启动后台扫码并返回二维码图片路径')
    subs.add_parser('login-confirm', help='查询扫码进度并验证 PC 登录态')
    subs.add_parser('login-phone', help='交互式手机号验证码登录')
    subs.add_parser('check', help='校验已保存的 PC 登录态')
    subs.add_parser('methods', help='列出全部可调用 PC 接口及参数')
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
        if args.command == 'login-confirm':
            state = login_status()
            if state.get('state') == 'success':
                return check_login()
            emit({'ok': False, 'state': state.get('state', 'missing'),
                  'message': state.get('message') or '等待扫码确认',
                  'qr_path': str(QR_FILE) if state.get('state') == 'pending' and QR_FILE.is_file() else None})
            return 1
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
            result = fetch_note(args.url, args.output_dir, args.download_media)
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
        return 0 if result.get('ok') else 1
    except SessionMissing as exc:
        emit({'ok': False, 'error': 'SESSION_MISSING', 'message': str(exc)})
        return 2
    except Exception as exc:
        emit({'ok': False, 'error': type(exc).__name__, 'message': str(exc)[:300]})
        return 1


if __name__ == '__main__':
    # Internal worker is deliberately absent from the user-visible help.
    if len(sys.argv) == 3 and sys.argv[1] == '_login-worker':
        raise SystemExit(login_worker(sys.argv[2]))
    raise SystemExit(main())
