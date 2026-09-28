"""OFB Relay client for XHS computed values. Platform HTTP stays in this process."""

from __future__ import annotations

import os
import re
from typing import Any

import requests


RELAY_BASE_URL = os.environ.get('RELAY_BASE_URL', 'https://relay.openclaw-for-business.com').rstrip('/')
_TIMEOUT = 45


class XhsRelayError(RuntimeError):
    pass


def compute(profile: str, operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if profile not in {'pc', 'creator'}:
        raise ValueError('unsupported XHS profile')
    key = os.environ.get('OFB_KEY')
    if not key:
        raise XhsRelayError('SIGN_UNAVAILABLE: OFB_KEY 未配置')
    try:
        response = requests.post(
            f'{RELAY_BASE_URL}/api/v1/sign/xhs/v2',
            headers={'Content-Type': 'application/json', 'X-OFB-Key': key},
            json={'version': 2, 'profile': profile, 'operation': operation, 'inputs': inputs},
            timeout=_TIMEOUT,
        )
        envelope = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise XhsRelayError('SIGN_UNAVAILABLE: OFB Relay 请求或响应失败') from exc
    if not isinstance(envelope, dict) or not response.ok or not envelope.get('success'):
        code = envelope.get('error') if isinstance(envelope, dict) else None
        safe_code = str(code) if re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', str(code)) else 'RELAY_ERROR'
        raise XhsRelayError(f'SIGN_UNAVAILABLE: OFB Relay {operation} 失败 ({response.status_code}, {safe_code})')
    data = envelope.get('data')
    if not isinstance(data, dict):
        raise XhsRelayError(f'SIGN_UNAVAILABLE: OFB Relay {operation} 响应缺少 data')
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
