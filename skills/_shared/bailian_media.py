"""Workspace-only Bailian HTTP, local media upload, and checkpoint helpers."""
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import uuid

import requests


class APIError(RuntimeError):
    pass


def workspace():
    wsid = os.environ.get('WORKSPACE_ID', '').strip()
    key = next((os.environ.get(k, '').strip() for k in ('MODELSTUDIO_API_KEY', 'DASHSCOPE_API_KEY')
                if os.environ.get(k, '').strip()), '')
    if not wsid or not key:
        raise ValueError('需要百炼业务空间 WORKSPACE_ID + MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY；不回退 Agent Plan 或火山')
    if not re.fullmatch(r'[A-Za-z0-9-]+', wsid):
        raise ValueError('WORKSPACE_ID 格式无效')
    return f'https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1', key


def request(base, key, path, payload=None, *, async_task=False, timeout=90):
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json',
               'X-DashScope-OssResourceResolve': 'enable'}
    if async_task:
        headers['X-DashScope-Async'] = 'enable'
    try:
        response = requests.request('GET' if payload is None else 'POST', base + path,
                                    json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        # Never retry a create request whose submission outcome is unknown.
        raise APIError(f'网络错误 {type(exc).__name__}；创建请求结果可能不确定，请先检查远端任务/音色列表') from None
    try:
        data = response.json()
    except ValueError:
        raise APIError(f'HTTP {response.status_code}：接口返回非 JSON') from None
    if response.status_code >= 400 or data.get('code'):
        code = data.get('code') or (data.get('error') or {}).get('code') or 'unknown'
        # API messages may echo signed URLs or input data. Keep logs credential-free.
        raise APIError(f'HTTP {response.status_code} code={code} request_id={data.get("request_id", "-")}')
    return data


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def media_info(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('媒体无法解码：' + str(path))
    info = json.loads(result.stdout)
    seconds = float(info.get('format', {}).get('duration', 0))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('媒体时长无效')
    return seconds, info.get('streams', [])


def download(url, path, *, max_bytes=100 * 1024 * 1024):
    if not url.startswith(('https://', 'http://')):
        raise ValueError('下载地址必须为 HTTP(S) URL')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.part')
    try:
        with requests.get(url, stream=True, timeout=(15, 180)) as response:
            response.raise_for_status()
            size = 0
            with temp.open('wb') as output:
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError('下载文件超过大小上限')
                    output.write(chunk)
        temp.replace(path)
    except requests.RequestException as exc:
        raise APIError(f'下载失败：{type(exc).__name__}') from None
    finally:
        temp.unlink(missing_ok=True)
    return path


def upload(base, key, path, model):
    """Temporary storage is model-bound: upload separately for detection and generation."""
    from urllib.parse import urlencode
    path = Path(path)
    policy = request(base, key, '/uploads?' + urlencode({'action': 'getPolicy', 'model': model}))['data']
    if path.stat().st_size > float(policy.get('max_file_size_mb', 100)) * 1024 * 1024:
        raise ValueError('媒体超过上传服务允许的大小')
    object_key = policy['upload_dir'].rstrip('/') + '/' + uuid.uuid4().hex + path.suffix.lower()
    fields = {
        'OSSAccessKeyId': policy['oss_access_key_id'], 'policy': policy['policy'],
        'Signature': policy['signature'], 'key': object_key,
        'x-oss-object-acl': policy['x_oss_object_acl'],
        'x-oss-forbid-overwrite': policy['x_oss_forbid_overwrite'], 'success_action_status': '200',
    }
    try:
        with path.open('rb') as source:
            response = requests.post(policy['upload_host'], data=fields,
                                     files={'file': (path.name, source, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')}, timeout=120)
        if response.status_code not in (200, 204):
            raise APIError(f'临时媒体上传失败 HTTP {response.status_code}')
    except requests.RequestException as exc:
        raise APIError(f'临时媒体上传失败：{type(exc).__name__}') from None
    return 'oss://' + object_key
