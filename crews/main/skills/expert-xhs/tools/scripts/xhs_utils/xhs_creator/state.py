"""Creator session state and non-public defaults provided by OFB Relay."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


from xhs_utils.relay import RemoteReference, compute

REFERENCE_PROFILE = RemoteReference('creator')

DS_REFRESH_INTERVAL_MS = 15 * 60 * 1000

_DOCUMENT_COOKIE_ORDER = (
    'ets', 'a1', 'webId', 'gid', 'abRequestId', 'webBuild', 'xsecappid',
    'websectiga', 'sec_poison_id', 'loadts',
)


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_cookie_kv(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {
            str(key): str(item)
            for key, item in value.items()
            if key is not None and item is not None
        }
    result: Dict[str, str] = {}
    for part in str(value).split(';'):
        item = part.strip()
        if not item:
            continue
        key, separator, content = item.partition('=')
        if key:
            result[key.strip()] = content if separator else ''
    return result


def cookie_header(value: Any) -> str:
    return '; '.join(
        f'{key}={item}' for key, item in parse_cookie_kv(value).items()
    )


def document_cookie_header(value: Any) -> str:
    """Build the exact Cookie view used by Creator fingerprint field ``x57``.

    HttpOnly login tokens are deliberately excluded.  The allow-list is based
    on the decoded Creator browser profile and prevents a copied full Cookie
    from leaking authentication tokens into ``profileData``.
    """
    values = parse_cookie_kv(value)
    return '; '.join(
        f'{key}={values[key]}'
        for key in _DOCUMENT_COOKIE_ORDER
        if values.get(key) is not None and key in values
    )


@dataclass
class CreatorB1RuntimeState:
    """Opaque page state passed to OFB Relay for fingerprint generation."""

    started_at: int
    profile_name: str = 'login'
    generated_at_offset_ms: Optional[int] = None
    time_origin_ms: float = 0.0
    overrides: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def reference(cls, started_at: Optional[int] = None,
                  profile_name: str = 'login') -> 'CreatorB1RuntimeState':
        started = int(started_at if started_at is not None else now_ms())
        return cls(started_at=started, profile_name=profile_name,
                   time_origin_ms=float(started))

    def to_b1_options(self, timestamp_ms: int) -> Dict[str, Any]:
        return {'now': int(timestamp_ms), 'started_at': self.started_at,
                'profile_name': self.profile_name,
                'overrides': dict(self.overrides)}

    def update_window_state(self, **values: Any) -> None:
        self.overrides.update({key: value for key, value in values.items()
                               if value is not None})


@dataclass
class CreatorSessionState:
    loadts: int
    dsllt: int
    ets: int
    mns_seq: int = 0
    security_ready: bool = False
    profile_count: int = 0
    sign_count: int = 0

    def next_seq(self) -> int:
        self.mns_seq += 1
        return self.mns_seq

    def ensure_dsllt(self, timestamp_ms: int, force: bool = False) -> int:
        timestamp = int(timestamp_ms)
        if force or timestamp - int(self.dsllt) >= DS_REFRESH_INTERVAL_MS:
            self.dsllt = timestamp
        return int(self.dsllt)

    def snapshot(self) -> Dict[str, Any]:
        return {
            'loadts': int(self.loadts),
            'dsllt': int(self.dsllt),
            'ets': int(self.ets),
            'mnsSeq': int(self.mns_seq),
            'securityReady': bool(self.security_ready),
            'p1': int(self.profile_count),
            'sc': int(self.sign_count),
        }


@dataclass
class CreatorDeviceProfile:
    """Creator b1/MNS/X-S-Common/profileData state without browser dependencies."""

    cookies: Any = ''
    local_storage: Mapping[str, Any] = field(default_factory=dict)
    session_storage: Mapping[str, Any] = field(default_factory=dict)
    fixed_b1: str = ''
    dsl: str = ''
    ds_program: str = field(default='', repr=False)
    release: Dict[str, Any] = field(
        default_factory=lambda: dict(REFERENCE_PROFILE['release'])
    )
    b1_state: Optional[CreatorB1RuntimeState] = None
    session: Optional[CreatorSessionState] = None
    mns_overrides: Dict[str, Any] = field(default_factory=dict)
    web_profile_fields: Dict[str, Any] = field(default_factory=dict)
    source: str = 'reference'
    _cookie_map: Dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _named_b1_states: Dict[str, CreatorB1RuntimeState] = field(
        default_factory=dict, init=False, repr=False
    )
    _named_b1_values: Dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )
    _b1_state_explicit: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._cookie_map = parse_cookie_kv(self.cookies)
        local = {str(k): v for k, v in dict(self.local_storage or {}).items()}
        tab = {str(k): v for k, v in dict(self.session_storage or {}).items()}
        started = int(self._cookie_map.get('loadts') or now_ms())
        if self.session is None:
            self.session = CreatorSessionState(
                loadts=started,
                dsllt=int(local.get('dsllt') or started),
                ets=int(self._cookie_map.get('ets') or started),
                mns_seq=int(local.get('mns_seq') or 0),
                security_ready=bool(
                    self._cookie_map.get('websectiga')
                    or self._cookie_map.get('gid')
                    or self.dsl
                ),
                profile_count=int(local.get('p1') or 0),
                sign_count=int(tab.get('sc') or local.get('sc') or 0),
            )
        self._b1_state_explicit = self.b1_state is not None
        if self.b1_state is None:
            self.b1_state = CreatorB1RuntimeState.reference(started_at=started)
        self.web_profile_fields = {
            str(key): value for key, value in dict(self.web_profile_fields or {}).items()
        }

    @property
    def cookie_map(self) -> Dict[str, str]:
        return dict(self._cookie_map)

    @property
    def document_cookie(self) -> str:
        return document_cookie_header(self._cookie_map)

    def update_cookies(self, cookies: Any) -> None:
        updates = parse_cookie_kv(cookies)
        self._cookie_map.update(updates)
        self.cookies = cookie_header(self._cookie_map)
        if updates.get('loadts'):
            self.session.loadts = int(updates['loadts'])
        if updates.get('ets'):
            self.session.ets = int(updates['ets'])
        if updates.get('websectiga') or updates.get('gid'):
            self.session.security_ready = True

    def activate_security(
        self,
        dsl: str,
        ds_program: str = '',
        *,
        timestamp_ms: Optional[int] = None,
    ) -> None:
        self.dsl = str(dsl or '')
        if ds_program:
            self.ds_program = str(ds_program)
        # Creator sets dsllt when the DS program is installed, before the
        # first mns0101 request. It is not lazily created by redcaptcha/CAS.
        self.session.dsllt = int(
            timestamp_ms if timestamp_ms is not None else now_ms()
        )
        self.session.security_ready = True

    def resolve_mns_tier(self, explicit_tier: Optional[str] = None) -> str:
        return str(compute('creator', 'resolve-tier', {
            'tier': explicit_tier,
            'security_ready': self.session.security_ready,
        })['tier'])

    def set_mns_stage(self, name_or_tier: str, *, env_const: int,
                      env_fp_tail: Any, device_tag: Optional[str] = None,
                      evidence: str = 'override') -> None:
        self.mns_overrides[str(name_or_tier)] = {
            'env_const': env_const, 'env_fp_tail': env_fp_tail,
            'device_tag': device_tag,
        }

    def next_sign_context(self, *, tier: Optional[str] = None,
                          mns_profile: Optional[str] = None,
                          timestamp_ms: Optional[int] = None,
                          version: Optional[int] = None) -> Dict[str, Any]:
        result = compute('creator', 'next-sign-context', {
            'tier': tier, 'mns_profile': mns_profile,
            'timestamp_ms': timestamp_ms, 'version': version,
            'session': self.session.snapshot(),
            'release': dict(self.release),
            'local_storage': dict(self.local_storage),
            'ds_program': self.ds_program,
            'overrides': dict(self.mns_overrides),
        })
        context = result.get('context')
        if not isinstance(context, dict) or not context.get('tier') or not context.get('token'):
            raise RuntimeError('OFB Relay 未返回 Creator 签名上下文')
        self.session.next_seq()
        self.session.sign_count += 1
        return context

    def current_b1(
        self,
        timestamp_ms: Optional[int] = None,
        profile_name: Optional[str] = None,
    ) -> str:
        if self.fixed_b1:
            return self.fixed_b1
        from .runtime import generate_b1

        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        state = self.b1_state
        if profile_name and not self._b1_state_explicit:
            key = str(profile_name)
            cached = self._named_b1_values.get(key)
            if cached:
                return cached
            state = self._named_b1_states.get(key)
            if state is None:
                state = CreatorB1RuntimeState.reference(
                    started_at=self.session.loadts,
                    profile_name=key,
                )
                self._named_b1_states[key] = state
            generated_at = timestamp
            if state.generated_at_offset_ms is not None:
                generated_at = int(
                    self.session.loadts + state.generated_at_offset_ms
                )
            value = generate_b1(state.to_b1_options(generated_at))
            self._named_b1_values[key] = value
            return value
        return generate_b1(state.to_b1_options(timestamp))

    def dsl_pair(self, timestamp_ms: Optional[int] = None) -> str:
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        dsllt = self.session.ensure_dsllt(timestamp)
        return f'{dsllt};{self.dsl or "undefined"}'

    def profile_data_options(
        self,
        *,
        timestamp_ms: Optional[int] = None,
        location: str = 'https://creator.xiaohongshu.com/login',
        referer: str = 'https://creator.xiaohongshu.com/login',
    ) -> Dict[str, Any]:
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        return {
            'timestampMs': timestamp,
            'timeOrigin': float(self.b1_state.time_origin_ms),
            'documentCookie': self.document_cookie,
            'location': location,
            'referer': referer,
            'fields': dict(self.web_profile_fields),
        }

    def state_snapshot(self) -> Dict[str, Any]:
        state = self.session.snapshot()
        state.update({
            'webBuild': self.release['webBuild'],
            'xsecappid': self.release['appId'],
        })
        return state


__all__ = [
    'REFERENCE_PROFILE',
    'DS_REFRESH_INTERVAL_MS',
    'CreatorB1RuntimeState',
    'CreatorSessionState',
    'CreatorDeviceProfile',
    'parse_cookie_kv',
    'cookie_header',
    'document_cookie_header',
    'now_ms',
]
