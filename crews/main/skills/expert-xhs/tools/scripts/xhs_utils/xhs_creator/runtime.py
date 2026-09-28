"""Creator computed values supplied by OFB Relay."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from xhs_utils.relay import compute


def generate_b1(options: Optional[Mapping[str, Any]] = None, timeout: float = 10.0) -> str:
    del timeout
    return str(compute('creator', 'b1', {'options': dict(options or {})})['b1'])


def run_signer(api: str, data: Any = '', *, cookie: str,
               b1: Optional[str], dsl_pair: str, tier: str,
               sign_context: Mapping[str, Any], timeout: float = 30.0) -> dict:
    del timeout
    if not cookie:
        raise ValueError('Creator signing requires Cookie')
    if not sign_context.get('token'):
        raise ValueError('OFB Relay 签名上下文缺少 token')
    result = compute('creator', 'sign', {
        'api': api, 'data': data, 'cookie': cookie, 'b1': b1,
        'dsl_pair': dsl_pair, 'tier': tier,
        'sign_context': dict(sign_context),
    })
    if not result.get('xs') or not result.get('xs_common') or not result.get('xt'):
        raise RuntimeError('OFB Relay Creator 签名响应不完整')
    return result


def generate_profile_data(options: Mapping[str, Any], timeout: float = 10.0) -> str:
    del timeout
    return str(compute('creator', 'profile-data', {'options': dict(options)})['profileData'])


def generate_websectiga(scripting_code: str, *,
                         profile: Optional[Mapping[str, Any]] = None) -> str:
    return str(compute('creator', 'websectiga', {
        'scripting_code': scripting_code, 'profile': dict(profile or {}),
    })['websectiga'])


__all__ = ['generate_b1', 'run_signer', 'generate_profile_data', 'generate_websectiga']
