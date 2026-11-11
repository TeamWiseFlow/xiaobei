"""Persist verification separately from authenticated PC state."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from urllib.parse import urlencode
from uuid import uuid4

from xhs_utils.pc_session import SESSION_FILE, load_auth, save_auth, session_lock
from xhs_utils.verification import VerificationRequired

JOB_FILE = SESSION_FILE.with_name('xhs-pc-verification.json')
JOB_LOCK = JOB_FILE.with_suffix('.lock')
QR_FILE = JOB_FILE.with_suffix('.png')
LOGIN_STATUS = SESSION_FILE.with_name('xhs-pc-login-status.json')
LOGIN_LOCK = SESSION_FILE.with_name('xhs-pc-login.lock')


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1_000_000:
            raise ValueError('验证材料必须是当前用户的私有普通文件')
        with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as stream:
            return stream.read()
    finally:
        os.close(fd)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.xhs-verify-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _lock(path=None):
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path or JOB_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _account():
    if not SESSION_FILE.exists():
        return None
    data = json.loads(_read(SESSION_FILE))
    cookies = data.get('cookies') or {}
    value = [cookies.get('a1'), cookies.get('web_session'), data.get('user_id')]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def snapshot(client):
    local, session = client.profile.browser_storage_snapshot()
    return {'cookies': client.profile.cookie_map,
            'host_cookie_state': client._cookie_store.export_state(),
            'local_storage': local, 'session_storage': session,
            'dsl': client.dsl, 'login_b1': getattr(client, '_login_b1', ''),
            'webprofile_reported': getattr(client, '_webprofile_reported', False)}


def restore(data):
    from xhs_utils.xhs_core.cookies import HostCookieStore
    from xhs_utils.xhs_pc.login import XHSLoginApi

    client = XHSLoginApi(dsl=data['dsl'], local_storage=data['local_storage'],
                         session_storage=data['session_storage'])
    client._ensure_profile(dict(data['cookies']))
    client._cookie_store = HostCookieStore.from_state(data['host_cookie_state'])
    client._login_b1 = data['login_b1']
    client._webprofile_reported = data['webprofile_reported']
    return client


def capture(client, error, *, run_id=None, saved=None):
    with _lock():
        account = _account()
        if run_id:
            current = json.loads(_read(LOGIN_STATUS))
            if current.get('run_id') != run_id or current.get('state') not in {'pending', 'awaiting_verification'}:
                raise ValueError('登录任务已变化，拒绝保存旧验证')
        try:
            previous = json.loads(_read(JOB_FILE))
        except FileNotFoundError:
            previous = {}
        if (previous.get('account') == account and previous.get('expires_at', 0) > time.time()
                and previous.get('stage') in {'required', 'preparing', 'awaiting_code', 'awaiting_scan', 'passed'}
                and (not run_id or previous.get('run_id') == run_id)):
            return public(previous)
        job = {'id': uuid4().hex, 'challenge': error.challenge,
               'original': saved if saved is not None else snapshot(client), 'account': account,
               'expires_at': time.time() + 300, 'stage': 'required', 'tries': 0,
               'run_id': run_id, 'qr': getattr(client, '_pending_qr', None)}
        _write(JOB_FILE, job)
        QR_FILE.unlink(missing_ok=True)
        return public(job)


def capture_saved(error):
    # Loading Auth would bootstrap user/me again and can repeat the same blocked request.
    with session_lock():
        data = json.loads(_read(SESSION_FILE))
    cookies = data['cookies']
    requested = dict(part.strip().split('=', 1) for part in getattr(error, 'request_cookie', '').split(';') if '=' in part)
    if requested and any(requested.get(k) != cookies.get(k) for k in ('a1', 'web_session')):
        raise ValueError('触发验证后账号已变化，拒绝绑定旧验证')
    saved = {'cookies': cookies, 'local_storage': data.get('local_storage') or {},
             'session_storage': data.get('session_storage') or {},
             'host_cookie_state': data.get('host_cookie_state') or {},
             'dsl': data.get('dsl') or '', 'login_b1': '', 'webprofile_reported': False}
    return capture(None, error, saved=saved)


def public(job):
    challenge = job['challenge']
    result = VerificationRequired(challenge['status'], challenge['uuid'], challenge['type']).public()
    result.update({'ok': False, 'verification_id': job['id'], 'state': job['stage'],
                   'expires_at': job['expires_at']})
    result['next_action'] = {
        'required': 'verify-start', 'awaiting_code': 'verify-code --code-file <私有文件>',
        'awaiting_scan': 'verify-confirm', 'passed': 'verify-confirm',
        'preparing': '先核查本次发送结果，不要重复发码',
        'expired': '重新登录或重新执行原读取命令',
        'failed': '重新登录或重新执行原读取命令',
    }.get(job['stage'])
    if not result['supported']:
        result['next_action'] = '请用户在同账号网页完成验证'
    if job.get('masked_phone'):
        result['masked_phone'] = job['masked_phone']
    if job['stage'] == 'awaiting_scan' and QR_FILE.is_file():
        result['qr_path'] = str(QR_FILE)
    if job['stage'] == 'complete':
        result.update({'ok': True, 'state': 'authenticated' if job.get('run_id') else 'verified',
                       'message': '登录已续接完成' if job.get('run_id') else '验证通过，请重新执行原读取命令'})
        result.pop('error', None)
    return result


def _load():
    job = json.loads(_read(JOB_FILE))
    if job['account'] != _account():
        raise ValueError('账号已变化，拒绝继续旧验证任务')
    if job['stage'] == 'complete':
        return job
    if job['expires_at'] <= time.time():
        QR_FILE.unlink(missing_ok=True)
        raise ValueError('验证任务已过期；请重新登录或重新执行原读取命令')
    if job.get('run_id'):
        status = json.loads(_read(LOGIN_STATUS))
        if status.get('run_id') != job['run_id'] or status.get('state') != 'awaiting_verification':
            raise ValueError('登录任务已变化，拒绝继续旧二维码验证')
    return job


def _post(client, path, payload):
    from xhs_utils.http_util import REQUEST_TIMEOUT
    from xhs_utils.xhs_pc.login import build_pc_login_headers

    cookies = client.profile.cookie_map
    headers, body = client._signed_request_params(
        cookies, path, payload, sec_domain=True, tier='0201', mns_profile='security_initial')
    headers = build_pc_login_headers(headers, client._cookies_for_url(client.base_url, cookies), kind='post')
    response = client.http.post(client.base_url + path, headers=headers, data=body.encode('utf-8'),
                                proxies=client.proxies, timeout=REQUEST_TIMEOUT)
    client._merge_response_cookies(cookies, response)
    data = response.json()
    if not response.ok or data.get('code') != 0:
        raise RuntimeError('安全验证请求未通过；请核对验证码或任务状态')
    return data.get('data') or {}


def _base(job):
    c = job['challenge']
    if c['type'] == '120':
        uuid = re.sub(r'^(sg__|ae__|gcp__)', '', c['uuid'])
        return {'verifyUuid': uuid, 'verifyType': '120', 'verifyBiz': str(c['status']),
                'sourceSite': 'https://www.xiaohongshu.com/explore', 'captchaVersion': '2.0.0'}
    return {'verifyType': '124', 'verifyUuid': c['uuid'],
            'verifyBiz': str(c['status']), 'sourceSite': '/'}


def start():
    with _lock():
        job = _load()
        if job['stage'] != 'required':
            return public(job)
        if job['challenge']['type'] not in {'120', '124'}:
            return public(job)
        # Persist intent before any send/init; a repeated invocation cannot send twice.
        job['stage'] = 'preparing'
        _write(JOB_FILE, job)
        client = restore(job['original'])
        try:
            # Verification is a fresh page load; never reuse the login report cache.
            client._login_b1 = ''
            client._webprofile_reported = False
            cookies = client.profile.cookie_map
            client._initialize_security(cookies)
            client._activate(cookies)
            client.ensure_webprofile(cookies)
            cookies['xsecappid'] = 'fe-login'
            client.profile.update_cookies(cookies)
            base = _base(job)
            if job['challenge']['type'] == '120':
                data = _post(client, '/api/redcaptcha/v2/vc/init', base)
                job['masked_phone'] = next((v for v in data.values()
                                            if isinstance(v, str) and '*' in v and re.search(r'\d', v)), None)
                data = _post(client, '/api/redcaptcha/v2/vc/send', base)
                job['stage'] = 'awaiting_code'
            else:
                data = _post(client, '/api/redcaptcha/v2/qr/init', base)
                job['stage'] = 'awaiting_scan'
            if not data.get('rid'):
                raise RuntimeError('验证响应缺少任务编号；不要重复发送')
            job['rid'] = str(data['rid'])
            job['verification'] = snapshot(client)
            if job['stage'] == 'awaiting_scan':
                url = 'https://www.xiaohongshu.com/web-login/qrcode-transfer?' + urlencode({
                    'rid': job['rid'], 'verifyUuid': job['challenge']['uuid'], 'verifyType': '124'})
                old = os.environ.get('XHS_PC_QR_IMAGE')
                try:
                    os.environ['XHS_PC_QR_IMAGE'] = str(QR_FILE)
                    client.show_qrcode_image(url)
                finally:
                    if old is None:
                        os.environ.pop('XHS_PC_QR_IMAGE', None)
                    else:
                        os.environ['XHS_PC_QR_IMAGE'] = old
            _write(JOB_FILE, job)
            return public(job)
        finally:
            client.close()


def _finish(job):
    if job.get('run_id'):
        if not job.get('qr'):
            raise ValueError('原登录二维码上下文缺失，请重新登录')
        client = restore(job['original'])
        try:
            cookies = client.profile.cookie_map
            client._login_by_qrcode_status(job['qr']['qr_id'], job['qr']['code'], cookies)
            success, user, cookies = client.get_user_info(cookies)
            if not success or user.get('guest') is not False or not user.get('user_id'):
                raise RuntimeError('验证后正式登录状态未确认')
            from xhs_utils.xhs_pc import XHSPcAuth

            local, session = client.profile.browser_storage_snapshot()
            auth = XHSPcAuth.from_cookie(cookies, local_storage=local, session_storage=session,
                                        host_cookie_state=client.host_cookie_state(), dsl=client.dsl,
                                        user_id=str(user['user_id']))
            try:
                with _lock(LOGIN_LOCK), session_lock():
                    status = json.loads(_read(LOGIN_STATUS))
                    if (status.get('run_id') != job['run_id'] or status.get('state') != 'awaiting_verification'
                            or job['account'] != _account()):
                        raise ValueError('账号或登录任务已变化，拒绝写入旧登录任务')
                    save_auth(auth)
                    job['account'] = _account()
                    status.update({'state': 'success', 'message': '安全验证与登录续接完成'})
                    _write(LOGIN_STATUS, status)
            finally:
                auth.close()
        finally:
            client.close()
    job['stage'] = 'complete'
    # Finished jobs must not retain login or verification credentials.
    for key in ('original', 'verification', 'qr', 'rid'):
        job.pop(key, None)
    QR_FILE.unlink(missing_ok=True)
    _write(JOB_FILE, job)
    return public(job)


def confirm(code_file=None):
    with _lock():
        job = _load()
        if job['stage'] == 'complete':
            return public(job)
        if job['stage'] == 'passed':
            return _finish(job)
        if job['stage'] not in {'awaiting_code', 'awaiting_scan'}:
            return public(job)
        code = None
        if job['stage'] == 'awaiting_code':
            if not code_file:
                return public(job)
            code = _read(Path(code_file)).strip()
            if not re.fullmatch(r'\d{6}', code):
                raise ValueError('验证码文件必须只包含六位数字')
            if job['tries'] >= 3:
                raise ValueError('验证码重试次数已用完，请重新登录')
            job['tries'] += 1
        elif time.time() - job.get('last_poll', 0) < 1.5:
            return public(job)
        job['last_poll'] = time.time()
        _write(JOB_FILE, job)
        client = restore(job['verification'])
        try:
            base = _base(job)
            if code is not None:
                _post(client, '/api/redcaptcha/v2/vc/check', {**base, 'rid': job['rid'],
                                                           'code': code, 'checkCount': 0})
                passed = True
            else:
                data = _post(client, '/api/redcaptcha/v2/qr/status/query', {**base, 'rid': job['rid']})
                status = data.get('status')
                passed = status == 4
                if status in (3, 5, 6):
                    job['stage'] = 'expired' if status == 5 else 'failed'
                    QR_FILE.unlink(missing_ok=True)
                elif status not in (1, 2, 4):
                    raise RuntimeError('安全验证返回未知状态')
            job['verification'] = snapshot(client)
            if passed:
                job['stage'] = 'passed'
            _write(JOB_FILE, job)
        finally:
            client.close()
        return _finish(job) if passed else public(job)
