#!/usr/bin/env python3
"""Agent-facing atomic KOL and distributor research commands."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys

from xhs_utils.pc_session import SessionMissing, load_auth, save_auth, session_lock


PGY_READ_METHODS = frozenset({
    'get_all_categories', 'get_track', 'get_user_by_page', 'get_some_user',
    'get_user_detail', 'get_user_fans_detail', 'get_user_fans_history',
    'get_user_notes_detail', 'get_self_info', 'get_self_info_signed',
})
QIANFAN_READ_METHODS = frozenset({
    'get_all_categories', 'get_user_by_page', 'get_some_user',
    'get_user_detail', 'get_user_cooperation', 'get_user_shop',
    'get_user_item', 'get_user_fans',
})
ATTEMPTS_FILE = Path.home() / '.openclaw' / 'logs' / 'xhs-pgy-invite-attempts.jsonl'


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, default=str))


def _api(platform: str):
    if platform == 'pgy':
        from apis.xhs_pugongying_apis import PuGongYingAPI

        return PuGongYingAPI()
    from apis.xhs_qianfan_apis import QianFanAPI

    return QianFanAPI()


def _methods(platform: str) -> dict:
    api = _api(platform)
    names = PGY_READ_METHODS if platform == 'pgy' else QIANFAN_READ_METHODS
    return {name: str(inspect.signature(getattr(api, name))) for name in sorted(names)}


def _result_ok(value) -> bool:
    if not isinstance(value, dict):
        return True
    if value.get('success') is False:
        return False
    code = value.get('code')
    if code is not None:
        return code in (0, '0', 200, '200')
    return value.get('success') is True or 'data' in value or 'result' in value


def _execute(platform: str, action):
    with session_lock():
        auth = load_auth()
        try:
            result = action(_api(platform), dict(auth.profile.cookie_map))
            return result
        finally:
            try:
                save_auth(auth)
            finally:
                auth.close()


def call(platform: str, method: str, kwargs: dict) -> dict:
    names = PGY_READ_METHODS if platform == 'pgy' else QIANFAN_READ_METHODS
    if method not in names:
        raise ValueError(f'未知或不可直接调用的方法 {method}；运行 methods 查看可用方法')
    if 'cookies' in kwargs:
        raise ValueError('Cookie 由本地 PC 会话加载，不接受命令行传入')
    result = _execute(platform, lambda api, cookies: getattr(api, method)(cookies=cookies, **kwargs))
    return {'ok': _result_ok(result), 'method': method, 'data': result}


def check(platform: str) -> dict:
    method = 'get_self_info' if platform == 'pgy' else 'get_all_categories'
    return call(platform, method, {})


def search(platform: str, choice: str, count: int) -> dict:
    if not 1 <= count <= 100:
        raise ValueError('--count 必须为 1..100')

    def action(api, cookies):
        categories = api.get_all_categories(cookies)
        if platform == 'pgy':
            from xhs_utils.xhs_pugongying_util import generate_pugongying_data

            category_filter = generate_pugongying_data(choice, categories)
            brand_info = api.get_self_info(cookies)
            brand_data = (brand_info.get('data') or {}) if isinstance(brand_info, dict) else {}
            if not _result_ok(brand_info) or not brand_data.get('userId'):
                raise ValueError('蒲公英品牌身份未验证，无法筛选达人')
            brand_user_id = brand_data['userId']
        else:
            category_filter = choice
        users = []
        total = None
        for page in range(1, min(7, (count + 19) // 20 + 2)):
            if platform == 'pgy':
                batch, total = api.get_user_by_page(
                    page, cookies, category_filter, brand_user_id=brand_user_id)
            else:
                batch, total = api.get_user_by_page(category_filter, categories, page, cookies)
            if not batch:
                break
            users.extend(batch)
            if len(users) >= count or (total is not None and page * 20 >= int(total)):
                break
        return {'users': users[:count], 'total': total}

    result = _execute(platform, action)
    return {'ok': True, 'choice': choice, **result}


def profile(platform: str, user_id: str) -> dict:
    if not user_id.strip():
        raise ValueError('user_id 不能为空')

    def action(api, cookies):
        methods = (
            ('summary', 'get_user_detail'),
            ('fans', 'get_user_fans_detail'),
            ('fans_history', 'get_user_fans_history'),
            ('notes', 'get_user_notes_detail'),
        ) if platform == 'pgy' else (
            ('summary', 'get_user_detail'),
            ('cooperation', 'get_user_cooperation'),
            ('shops', 'get_user_shop'),
            ('items', 'get_user_item'),
            ('fans', 'get_user_fans'),
        )
        result = {}
        errors = {}
        for key, method in methods:
            try:
                result[key] = getattr(api, method)(user_id, cookies)
                if not _result_ok(result[key]):
                    response = result[key]
                    errors[key] = str(response.get('msg') or response.get('message') or
                                      response.get('code') or '平台拒绝') if isinstance(response, dict) else '平台拒绝'
            except Exception as exc:
                result[key] = {'error': type(exc).__name__, 'message': str(exc)[:160]}
                errors[key] = str(exc)[:160]
        return result, errors

    data, errors = _execute(platform, action)
    return {'ok': any(_result_ok(value) and not (isinstance(value, dict) and 'error' in value)
                      for value in data.values()), 'user_id': user_id,
            'data': data, 'errors': errors}


def _proposal(path: str) -> dict:
    value = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('邀约方案必须是 JSON 对象')
    required = ('user_id', 'product_name', 'publish_start', 'publish_end',
                'content', 'contact_info')
    missing = [key for key in required if not value.get(key)]
    if missing:
        raise ValueError('邀约方案缺少字段：' + ', '.join(missing))
    return {key: str(value[key]) for key in required}


def invite(proposal_path: str, send: bool) -> dict:
    proposal = _proposal(proposal_path)
    payload = json.dumps(proposal, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    if not send:
        return {'ok': True, 'state': 'preview', 'proposal': proposal, 'proposal_sha256': digest,
                'message': '请先让用户确认全部邀约字段，再加 --send 提交一次'}
    with session_lock():
        auth = load_auth()
        try:
            api = _api('pgy')
            cookies = dict(auth.profile.cookie_map)
            brand_info = api.get_self_info(cookies)
            identity = (brand_info.get('data') or {}) if isinstance(brand_info, dict) else {}
            if not _result_ok(brand_info) or not identity.get('userId') or not identity.get('nickName'):
                raise ValueError('蒲公英品牌身份未验证，邀约未提交')
            ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(ATTEMPTS_FILE, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                with os.fdopen(os.dup(fd), 'r', encoding='utf-8') as reader:
                    for line in reader:
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get('proposal_sha256') == digest:
                            raise ValueError('相同邀约已尝试提交；请先到平台核实结果，避免重复发送')
                attempt = {'at': datetime.now(timezone.utc).isoformat(),
                           'proposal_sha256': digest, 'user_id': proposal['user_id'],
                           'state': 'attempted'}
                os.write(fd, (json.dumps(attempt, ensure_ascii=False) + '\n').encode('utf-8'))
                os.fsync(fd)
                try:
                    result = api.send_invite(
                        proposal['user_id'], cookies, proposal['product_name'],
                        [proposal['publish_start'], proposal['publish_end']],
                        proposal['content'], proposal['contact_info'], brand_info=brand_info)
                except Exception as exc:
                    return {'ok': False, 'state': 'unknown', 'proposal_sha256': digest,
                            'message': f'{type(exc).__name__}: {str(exc)[:180]}; 请到蒲公英后台核实后再处理'}
                finally:
                    save_auth(auth)
                return {'ok': _result_ok(result),
                        'state': 'submitted' if _result_ok(result) else 'rejected',
                        'proposal_sha256': digest, 'data': result}
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        finally:
            auth.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='蒲公英 KOL 与千帆分销商数据工具')
    parser.add_argument('platform', choices=('pgy', 'qianfan'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('methods')
    sub.add_parser('check')
    categories = sub.add_parser('categories')
    search_parser = sub.add_parser('search')
    search_parser.add_argument('--choice', default='-1',
                               help='类目索引表达式；-1 表示全部，先用 categories 查看索引')
    search_parser.add_argument('--count', type=int, default=20)
    detail = sub.add_parser('profile')
    detail.add_argument('user_id')
    generic = sub.add_parser('call')
    generic.add_argument('method')
    generic.add_argument('--kwargs', default='{}')
    invitation = sub.add_parser('invite')
    invitation.add_argument('--proposal', required=True, help='邀约方案 JSON 文件路径')
    invitation.add_argument('--send', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'methods':
            result = {'ok': True, 'methods': _methods(args.platform)}
        elif args.command == 'check':
            result = check(args.platform)
        elif args.command == 'categories':
            result = call(args.platform, 'get_all_categories', {})
        elif args.command == 'search':
            result = search(args.platform, args.choice, args.count)
        elif args.command == 'profile':
            result = profile(args.platform, args.user_id)
        elif args.command == 'call':
            kwargs = json.loads(args.kwargs)
            if not isinstance(kwargs, dict):
                raise ValueError('--kwargs 需要 JSON 对象')
            result = call(args.platform, args.method, kwargs)
        else:
            if args.platform != 'pgy':
                raise ValueError('千帆接口没有发起合作邀约能力')
            result = invite(args.proposal, args.send)
        emit(result)
        return 0 if result.get('ok') else 1
    except SessionMissing as exc:
        emit({'ok': False, 'error': 'SESSION_MISSING', 'message': str(exc)})
        return 2
    except Exception as exc:
        emit({'ok': False, 'error': type(exc).__name__, 'message': str(exc)[:250]})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
