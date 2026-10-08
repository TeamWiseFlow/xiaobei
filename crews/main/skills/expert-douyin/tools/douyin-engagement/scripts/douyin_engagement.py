#!/usr/bin/env python3
"""Fetch public/creator metrics over HTTP, then update published-track."""
import argparse
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from publish_browser import Browser, publish_lock

SOURCE = 'douyin:creator_item_list'
BASIC_FIELDS = {'view_count': 'plays', 'like_count': 'likes', 'comment_count': 'comments',
                'share_count': 'shares', 'favorite_count': 'favorites'}
PAGE_SIZE, MAX_PAGES = 50, 10
CREATOR_URL = 'https://creator.douyin.com/web/api/creator/item/list'
PUBLIC_SOURCE = 'douyin:aweme_detail'
PUBLIC_FIELDS = {'likeCount': 'likes', 'commentCount': 'comments',
                 'shareCount': 'shares', 'collectCount': 'favorites'}


class CreatorError(ValueError):
    def __init__(self, code, *, stage=None, reason=None):
        super().__init__(code)
        self.stage = stage
        self.reason = reason


PROFILE_ERRORS = (ValueError, OSError, RuntimeError, subprocess.SubprocessError,
                  TypeError, AttributeError)
NOT_LAUNCHED = "Browser not launched. Send 'open' command first."


def profile_error(exc, stage):
    # Report controlled diagnostics; CLI output may contain private profile data.
    if isinstance(exc, FileNotFoundError):
        reason = 'CLI_NOT_FOUND'
    elif isinstance(exc, subprocess.TimeoutExpired):
        reason = 'CLI_TIMEOUT'
    elif isinstance(exc, (ValueError, TypeError, AttributeError)):
        reason = 'CLI_RESPONSE_INVALID'
    elif str(exc) == NOT_LAUNCHED:
        reason = 'BROWSER_NOT_LAUNCHED'
    else:
        reason = 'CLI_COMMAND_FAILED'
    return CreatorError('PROFILE_SESSION_UNAVAILABLE', stage=stage, reason=reason)


def profile_snapshot():
    """Load a cold profile, or reuse a live browser without changing its mode/page."""
    browser = Browser()
    stage, close_on_failure, ready = 'info', False, False
    try:
        state = browser.command('info')
        if not isinstance(state, dict) or not isinstance(state.get('running'), bool):
            raise CreatorError('PROFILE_SESSION_INVALID', stage=stage,
                               reason='CLI_RESPONSE_INVALID')
        running = state['running']
        if running:
            if isinstance(state.get('headed'), bool):
                browser.headed = state['headed']
            elif isinstance(state.get('headless'), bool):
                browser.headed = not state['headless']
            else:
                raise CreatorError('PROFILE_SESSION_INVALID', stage=stage,
                                   reason='CLI_RESPONSE_INVALID')
        else:
            close_on_failure, stage = True, 'open'
            browser.command('open', 'about:blank')
        stage = 'cookies'
        try:
            cookies = browser.command('cookies')
        except RuntimeError as exc:
            # A reachable daemon can exist before it has launched a browser.
            if not running or str(exc) != NOT_LAUNCHED:
                raise
            close_on_failure, stage = True, 'open'
            browser.command('open', 'about:blank')
            stage = 'cookies'
            cookies = browser.command('cookies')
        stage = 'identity'
        identity = browser.command('identity')
        records = cookies.get('cookies') if isinstance(cookies, dict) else None
        ua = identity.get('userAgent') if isinstance(identity, dict) else None
        if not isinstance(records, list) or not isinstance(ua, str) or not ua:
            raise CreatorError('PROFILE_SESSION_INVALID', stage='snapshot',
                               reason='CREDENTIAL_RESPONSE_INVALID')
        ready = True
        return records, ua
    except CreatorError:
        raise
    except PROFILE_ERRORS as exc:
        raise profile_error(exc, stage) from exc
    finally:
        if ready or close_on_failure:
            try:
                browser.close()
            except PROFILE_ERRORS as exc:
                if ready:
                    raise profile_error(exc, 'close') from exc


@contextmanager
def profile_http_session():
    """Read credentials in memory; close the browser before HTTP reads."""
    records, ua = profile_snapshot()
    client = requests.Session()
    client.headers.update({'User-Agent': ua, 'Accept': 'application/json, text/plain, */*',
                           'Accept-Language': 'zh-CN,zh;q=0.9'})
    try:
        for cookie in records:
            if not isinstance(cookie, dict):
                continue
            domain = str(cookie.get('domain', '')).lower()
            if domain.lstrip('.') != 'douyin.com' and not domain.endswith('.douyin.com'):
                continue
            if not isinstance(cookie.get('name'), str) or not isinstance(cookie.get('value'), str):
                continue
            expires = cookie.get('expires', -1)
            if isinstance(expires, (int, float)) and expires > 0 and expires <= time.time():
                continue
            client.cookies.set(cookie['name'], cookie['value'], domain=domain,
                               path=cookie.get('path') or '/', secure=bool(cookie.get('secure')))
        if not any(cookie.name in {'sessionid', 'sessionid_ss', 'sid_tt'} and cookie.value
                   for cookie in client.cookies):
            raise CreatorError('SESSION_EXPIRED', stage='cookies', reason='AUTH_COOKIE_MISSING')
        yield client
    finally:
        client.close()


def track(*args):
    result = subprocess.run(['published-track', *map(str, args)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise CreatorError('PUBLISHED_TRACK_FAILED')
    return json.loads(result.stdout)


def item_id(value):
    text = str(value or '')
    if re.fullmatch(r'[0-9]{15,22}', text):
        return text
    parsed = urlsplit(text)
    if parsed.scheme != 'https' or parsed.hostname != 'www.douyin.com':
        raise CreatorError('ITEM_ID_REQUIRED')
    match = re.search(r'/(?:video|note|slides)/([0-9]{15,22})(?:/|$)', parsed.path)
    if match:
        return match.group(1)
    modal_id = parse_qs(parsed.query).get('modal_id', [''])[0]
    match = re.fullmatch(r'[0-9]{15,22}', modal_id)
    if not match:
        raise CreatorError('ITEM_ID_REQUIRED')
    return match.group(1) if match.lastindex else match.group(0)


def _creator_page(client, cursor=None):
    params = {'count': str(PAGE_SIZE), 'order_by': '1', 'fields': 'metrics,review,visibility',
              'need_cooperation': 'true', 'need_long_article': 'true'}
    if cursor is not None:
        params['max_cursor'] = str(cursor)
    try:
        response = client.get(CREATOR_URL, params=params,
                              headers={'Referer': 'https://creator.douyin.com/'},
                              timeout=30, allow_redirects=False)
    except requests.Timeout as exc:
        raise CreatorError('CREATOR_TIMEOUT') from exc
    except requests.RequestException as exc:
        raise CreatorError('CREATOR_REQUEST_FAILED') from exc
    if response.status_code in (401, 403) or (300 <= response.status_code < 400 and
            'login' in response.headers.get('Location', '').lower()):
        raise CreatorError('SESSION_EXPIRED', stage='creator', reason='AUTH_REJECTED')
    if response.status_code != 200:
        raise CreatorError('CREATOR_HTTP_ERROR')
    try:
        # Python JSON keeps 19-digit IDs and pagination cursors exact.
        data = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise CreatorError('CREATOR_RESPONSE_INVALID') from exc
    if not isinstance(data, dict):
        raise CreatorError('CREATOR_RESPONSE_INVALID')
    if data.get('status_code') in (8, '8'):
        raise CreatorError('CREATOR_AUTH_RETRY')
    if data.get('status_code') in (1002, 1003, '1002', '1003'):
        raise CreatorError('SESSION_EXPIRED', stage='creator', reason='AUTH_REJECTED')
    if data.get('status_code') not in (0, '0', None):
        raise CreatorError('CREATOR_PLATFORM_REJECTED')
    if not isinstance(data.get('items'), list):
        raise CreatorError('CREATOR_ITEMS_INVALID')
    return data


def creator_page(client, cursor=None):
    for attempt in range(3):
        try:
            return _creator_page(client, cursor)
        except CreatorError as exc:
            if str(exc) != 'CREATOR_AUTH_RETRY':
                raise
            if attempt == 2:
                raise CreatorError('SESSION_EXPIRED', stage='creator',
                                   reason='AUTH_RETRY_EXHAUSTED') from exc
            time.sleep(2)


def metric_number(value, *, count=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0 or (count and number != number.to_integral_value()):
        return None
    return int(number) if number == number.to_integral_value() else float(number)


def normalize_metrics(item):
    raw = item.get('metrics')
    if not isinstance(raw, dict):
        raw = {}
    basic, deep = {}, {}
    for key, value in raw.items():
        number = metric_number(value, count=key in BASIC_FIELDS)
        if number is None:
            continue
        if key in BASIC_FIELDS:
            basic[BASIC_FIELDS[key]] = number
        else:
            deep[key] = number
    unavailable = sorted(set(BASIC_FIELDS.values()) - basic.keys())
    return {'metrics': basic, 'deep': deep, 'source': SOURCE,
            'field_sources': {key: SOURCE for key in basic},
            'unavailable': unavailable,
            'unavailable_reasons': {key: 'CREATOR_METRIC_MISSING' for key in unavailable},
            'complete': not unavailable, 'review': item.get('review'), 'visibility': item.get('visibility')}


def creator_items(client, identifiers):
    pending, found = set(identifiers), {}
    cursor, seen = None, set()
    for _ in range(MAX_PAGES):
        data = creator_page(client, cursor)
        for item in data['items']:
            if not isinstance(item, dict):
                raise CreatorError('CREATOR_ITEMS_INVALID')
            ident = str(item.get('id', ''))
            if ident in pending:
                found[ident] = normalize_metrics(item)
                pending.remove(ident)
        if not pending:
            return found, {}
        more = data.get('has_more')
        if more in (False, 0, '0'):
            return found, {ident: 'CREATOR_ITEM_NOT_FOUND' for ident in pending}
        if more not in (True, 1, '1'):
            raise CreatorError('CREATOR_PAGINATION_INVALID')
        cursor = data.get('max_cursor')
        if isinstance(cursor, bool) or not re.fullmatch(r'\d+', str(cursor)) or str(cursor) in seen:
            raise CreatorError('CREATOR_CURSOR_INVALID')
        seen.add(str(cursor))
    return found, {ident: 'CREATOR_PAGE_LIMIT' for ident in pending}


def public_metrics(client, identifiers):
    if not identifiers:
        return {}
    prepared = client.prepare_request(requests.Request('GET', 'https://www.douyin.com/'))
    payload = {'identifiers': sorted(set(identifiers)),
               'cookieStr': prepared.headers.get('Cookie', ''), 'ua': client.headers['User-Agent']}
    try:
        result = subprocess.run(['node', '--experimental-strip-types',
                                 str(Path(__file__).with_name('fetch-retro-data.ts'))],
                                input=json.dumps(payload), capture_output=True, text=True,
                                timeout=70 * len(payload['identifiers']) + 10)
        data = json.loads(result.stdout)
        if result.returncode or data.get('ok') is not True or not isinstance(data.get('results'), dict):
            raise ValueError('invalid public response')
        return data['results']
    except (ValueError, OSError, subprocess.SubprocessError):
        return {ident: {'ok': False, 'error': 'PUBLIC_DETAIL_REQUEST_FAILED'} for ident in identifiers}


def fetch_metrics(client, identifiers):
    try:
        found, missing = creator_items(client, identifiers)
    except CreatorError as exc:
        if str(exc) in {'SESSION_EXPIRED', 'CREATOR_TIMEOUT', 'CREATOR_HTTP_ERROR'}:
            raise
        found, missing = {}, {ident: str(exc) for ident in identifiers}
    # Creator values take priority. Public detail fills only its four counters.
    public_ids = [ident for ident in identifiers if ident not in found or
                  any(key != 'plays' for key in found[ident]['unavailable'])]
    public = public_metrics(client, public_ids)
    for ident in identifiers:
        result = found.get(ident) or normalize_metrics({})
        reason = missing.get(ident, 'CREATOR_METRIC_MISSING')
        result['unavailable_reasons'] = {key: reason for key in result['unavailable']}
        fallback = public.get(ident, {})
        for key, value in fallback.get('stats', {}).items():
            target = PUBLIC_FIELDS.get(key)
            number = metric_number(value, count=True)
            if target and target not in result['metrics'] and number is not None:
                result['metrics'][target] = number
                result['field_sources'][target] = PUBLIC_SOURCE
                result['unavailable_reasons'].pop(target, None)
        result['unavailable'] = sorted(set(BASIC_FIELDS.values()) - result['metrics'].keys())
        result['complete'] = not result['unavailable']
        if fallback.get('error'):
            result['public_error'] = fallback['error']
        found[ident] = result
    return found


def update(row, result):
    if not result['metrics'] and not result['deep']:
        raise CreatorError('METRICS_UNAVAILABLE')
    args = ['update-metrics', '--platform', 'douyin', '--id', str(row['id'])]
    for key, value in result['metrics'].items():
        args += ['--' + key, str(value)]
    with tempfile.TemporaryDirectory(prefix='douyin-metrics-') as directory:
        if result['deep']:
            path = Path(directory) / 'deep.json'
            path.write_text(json.dumps(result['deep'], ensure_ascii=False), encoding='utf-8')
            args += ['--deep-file', str(path), '--deep-source', SOURCE]
        if not track(*args).get('ok'):
            raise CreatorError('METRICS_UPDATE_FAILED')


def main():
    p = argparse.ArgumentParser(prog='douyin-engagement')
    p.add_argument('command', choices=('check', 'list', 'fetch', 'daily'))
    p.add_argument('--row-id', type=int)
    a = p.parse_args()
    if a.command == 'fetch' and a.row_id is None:
        raise CreatorError('ROW_ID_REQUIRED')
    rows = [] if a.command == 'check' else track('query', '--platform', 'douyin',
                         *(['--limit', '30'] if a.command != 'fetch' else []))
    if not isinstance(rows, list):
        raise CreatorError('PUBLISHED_TRACK_BAD_RESPONSE')
    if a.command == 'list':
        return {'ok': True, 'rows': rows}
    if a.command == 'fetch':
        rows = [row for row in rows if row['id'] == a.row_id]
        if not rows:
            raise CreatorError('ROW_NOT_FOUND')
    selected, outcomes = [], []
    for row in rows:
        try:
            selected.append((row, item_id(row.get('publish_url'))))
        except CreatorError as exc:
            outcomes.append({'row_id': row['id'], 'ok': False, 'error': str(exc)})
    if selected or a.command == 'check':
        with publish_lock():
            with profile_http_session() as client:
                if a.command == 'check':
                    creator_page(client)
                    return {'ok': True, 'creator': True, 'session': 'douyin',
                            'transport': 'http', 'session_source': 'camoufox_profile'}
                found = fetch_metrics(client, [ident for _, ident in selected])
        for row, ident in selected:
            result = found.get(ident)
            if not result['metrics'] and not result['deep']:
                outcomes.append({'row_id': row['id'], 'ok': False, 'error': 'METRICS_UNAVAILABLE', **result})
                continue
            try:
                update(row, result)
                outcomes.append({'row_id': row['id'], 'aweme_id': ident, 'ok': True, **result})
            except CreatorError as exc:
                outcomes.append({'row_id': row['id'], 'ok': False, 'error': str(exc)})
    return {'ok': all(item['ok'] for item in outcomes),
            'complete': all(item.get('complete', False) for item in outcomes),
            'scanned': len(outcomes), 'outcomes': outcomes}


def error_result(exc):
    code = str(exc) if isinstance(exc, CreatorError) else 'CREATOR_FETCH_FAILED'
    result = {'ok': False, 'error': code}
    if isinstance(exc, CreatorError):
        for key in ('stage', 'reason'):
            if getattr(exc, key):
                result[key] = getattr(exc, key)
    if code == 'SESSION_EXPIRED':
        result['hint'] = '登录态缺失或失效；执行 douyin-publish login，完成后重跑 check'
    elif code in {'PROFILE_SESSION_UNAVAILABLE', 'PROFILE_SESSION_INVALID'}:
        result['hint'] = 'Camoufox profile 初始化或读取失败，登录状态尚未确认；按 stage/reason 排查，不自动重登'
    else:
        result['hint'] = '按错误原因排查，保留已有指标，不自动重登或重发'
    return result


if __name__ == '__main__':
    try:
        result = main()
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result['ok'] else 1)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        result = error_result(exc)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(2 if result['error'] == 'SESSION_EXPIRED' else 1)
