"""OFB Relay client for XHS computed values. Platform HTTP stays in this process."""

from __future__ import annotations

import os
import re
import json
import hashlib
import time
import tempfile
from pathlib import Path
from typing import Any

import requests
from xhs_utils.relay_transport import post as relay_post, RelayBudgetError


RELAY_BASE_URL = os.environ.get('RELAY_BASE_URL', 'https://relay.openclaw-for-business.com').rstrip('/')
_TIMEOUT = 45
_CACHE_OPERATIONS = {'reference-profile', 'release', 'route-policy', 'resolve-tier'}
_MEMORY_CACHE = {}


def _cache_path(profile, operation, inputs, key):
    if operation == 'route-policy' and isinstance(inputs.get('api'), str):
        # Policy depends on the route, while cursors and search parameters vary per request.
        inputs = {**inputs, 'api': inputs['api'].split('?', 1)[0]}
    digest = hashlib.sha256(json.dumps([RELAY_BASE_URL, hashlib.sha256(key.encode()).hexdigest(),
        profile, operation, inputs], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    home = Path(os.environ.get('RELAY_BUDGET_HOME', str(Path(os.environ.get('OPENCLAW_HOME', str(Path.home()/'.openclaw'))) / 'cache/relay-budget-v1')))
    return home / ('metadata-' + digest + '.json')


class XhsRelayError(RuntimeError):
    pass


def compute(profile: str, operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if profile not in {'pc', 'creator'}:
        raise ValueError('unsupported XHS profile')
    key = os.environ.get('OFB_KEY')
    if not key:
        raise XhsRelayError('SIGN_UNAVAILABLE: OFB_KEY 未配置')
    ttl = max(0, min(300, float(os.environ.get('XHS_RELAY_CACHE_TTL', '300'))))
    cache = _cache_path(profile, operation, inputs, key) if ttl and operation in _CACHE_OPERATIONS else None
    if cache:
        value = _MEMORY_CACHE.get(str(cache))
        if value is None:
            try: value = json.loads(cache.read_text())
            except (OSError, ValueError): pass
        if isinstance(value, dict) and isinstance(value.get('at'), (int, float)) and 0 <= time.time() - value['at'] < ttl and isinstance(value.get('data'), dict):
            _MEMORY_CACHE[str(cache)] = value
            return json.loads(json.dumps(value['data']))
    try:
        response = relay_post(
            f'{RELAY_BASE_URL}/api/v1/sign/xhs/v2',
            key=key, request=requests.post,
            headers={'Content-Type': 'application/json', 'X-OFB-Key': key},
            json={'version': 2, 'profile': profile, 'operation': operation, 'inputs': inputs},
            timeout=_TIMEOUT,
        )
        if response.status_code == 429:
            raise XhsRelayError('RELAY_RATE_LIMITED: Relay 仍繁忙，请按等待提示继续原步骤')
        envelope = response.json()
    except RelayBudgetError as exc:
        raise XhsRelayError('RELAY_RATE_LIMITED: 共享调用预算繁忙，请按等待提示继续原步骤') from exc
    except (requests.RequestException, ValueError) as exc:
        raise XhsRelayError('SIGN_UNAVAILABLE: OFB Relay 请求或响应失败') from exc
    if not isinstance(envelope, dict) or not response.ok or not envelope.get('success'):
        code = envelope.get('error') if isinstance(envelope, dict) else None
        safe_code = str(code) if re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', str(code)) else 'RELAY_ERROR'
        raise XhsRelayError(f'SIGN_UNAVAILABLE: OFB Relay {operation} 失败 ({response.status_code}, {safe_code})')
    data = envelope.get('data')
    if not isinstance(data, dict):
        raise XhsRelayError(f'SIGN_UNAVAILABLE: OFB Relay {operation} 响应缺少 data')
    if cache:
        value = {'at': time.time(), 'data': data}
        _MEMORY_CACHE[str(cache)] = value
        try:
            cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=cache.parent, prefix='.metadata-')
            with os.fdopen(fd, 'w') as stream: json.dump(value, stream)
            os.replace(name, cache)
        except OSError:
            pass
    return data


class RemoteReference:
    """Load non-public device defaults only when a session needs them."""

    def __init__(self, profile: str):
        self.profile = profile
        self._value = None

    def _load(self) -> dict:
        if self._value is None:
            value = compute(self.profile, 'reference-profile', {})
            if not value.get('release'):
                raise XhsRelayError('SIGN_UNAVAILABLE: Relay 未返回设备配置')
            self._value = value
        return self._value

    def __getitem__(self, key: str):
        return self._load()[key]

    def get(self, key: str, default=None):
        return self._load().get(key, default)
