"""PC computed values supplied by OFB Relay."""
from __future__ import annotations

from typing import Any, Mapping, Optional

from xhs_utils.relay import compute


def generate_b1(options: Optional[Mapping[str, Any]] = None, timeout: float = 10.0) -> str:
    del timeout
    return str(compute('pc', 'b1', {'options': dict(options or {})})['b1'])


def run_signer(api: str, data: Any = '', *, a1: str, cookie: str,
               b1: Optional[str], dsl_pair: str, tier: str,
               sign_context: Mapping[str, Any], timeout: float = 30.0) -> dict:
    del timeout
    if not cookie or not a1:
        raise ValueError('PC signing requires authenticated Cookie')
    if not sign_context.get('token'):
        raise ValueError('OFB Relay 签名上下文缺少 token')
    result = compute('pc', 'sign', {
        'api': api, 'data': data, 'cookie': cookie, 'b1': b1,
        'dsl_pair': dsl_pair, 'tier': tier,
        'sign_context': dict(sign_context),
    })
    if not result.get('xs') or not result.get('xt'):
        raise RuntimeError('OFB Relay PC 签名响应不完整')
    return result


def create_web_ssk_handshake(timeout: float = 10.0) -> dict:
    del timeout
    result = compute('pc', 'web-ssk-create', {})
    if not result.get('private_key_base64') or not result.get('client_public_key_base64'):
        raise RuntimeError('OFB Relay web-ssk-create 响应不完整')
    return result


def accept_web_ssk(private_key_base64: str, encrypted_ssk_base64: str,
                   timeout: float = 10.0) -> str:
    del timeout
    result = compute('pc', 'web-ssk-accept', {
        'private_key_base64': private_key_base64,
        'encrypted_ssk_base64': encrypted_ssk_base64,
    })
    return str(result['ssk_base64'])


def generate_websectiga(scripting_code: str, *,
                         profile: Optional[Mapping[str, Any]] = None,
                         timeout: float = 20.0) -> str:
    del timeout
    result = compute('pc', 'websectiga', {
        'scripting_code': scripting_code, 'profile': dict(profile or {}),
    })
    return str(result['websectiga'])


def generate_profile_data(*, fields: Optional[Mapping[str, Any]] = None,
                          timestamp_ms: Optional[int] = None,
                          ets: Optional[int] = None,
                          document_cookie: Optional[str] = None,
                          time_origin: Optional[float] = None,
                          i12_seed: Optional[int] = None,
                          telemetry_fi: Optional[int] = None,
                          exact_fields: bool = False,
                          timeout: float = 10.0) -> str:
    del timeout
    result = compute('pc', 'profile-data', {
        'fields': dict(fields or {}), 'timestamp_ms': timestamp_ms,
        'ets': ets, 'document_cookie': document_cookie,
        'time_origin': time_origin, 'i12_seed': i12_seed,
        'telemetry_fi': telemetry_fi, 'exact_fields': exact_fields,
    })
    return str(result['profileData'])


__all__ = ['generate_b1', 'run_signer', 'create_web_ssk_handshake',
           'accept_web_ssk', 'generate_websectiga', 'generate_profile_data']
