# encoding: utf-8
"""PC session state and non-public defaults provided by OFB Relay."""
from __future__ import annotations

import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.parse import unquote


from xhs_utils.relay import RemoteReference, compute

REFERENCE_PROFILE = RemoteReference('pc')

DS_REFRESH_INTERVAL_MS = 15 * 60 * 1000
TIGA_REFRESH_INTERVAL_MS = 5 * 60 * 1000


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_ets_timestamp(timestamp_ms: int) -> int:
    """Match the normal browser `ets` writer (avoid a final decimal digit 1)."""
    value = int(timestamp_ms)
    return value + 1 if value % 10 == 1 else value


def initial_pc_cookies(
    a1: str,
    web_id: str,
    *,
    ab_request_id: str,
    timestamp_ms: Optional[int] = None,
    loadts_ms: Optional[int] = None,
    web_build: Optional[str] = None,
    app_id: Optional[str] = None,
) -> Dict[str, str]:
    """Build the post-navigation anonymous Cookie set in browser order.

    ``abRequestId`` is issued by the initial ``www`` navigation.  It is not
    ``webId`` and must not be forged as ``MD5(a1)``.
    """
    timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
    loadts = int(loadts_ms if loadts_ms is not None else timestamp)
    if not ab_request_id:
        raise ValueError('initial_pc_cookies requires server-issued abRequestId')
    return {
        'abRequestId': str(ab_request_id),
        'ets': str(normalize_ets_timestamp(timestamp)),
        'webBuild': str(web_build or REFERENCE_PROFILE['release']['webBuild']),
        'xsecappid': str(app_id or REFERENCE_PROFILE['release']['appId']),
        'loadts': str(loadts),
        'a1': str(a1),
        'webId': str(web_id),
    }


def _storage_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(unquote(str(value or '')))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def parse_cookie_kv(cookies: Any) -> Dict[str, str]:
    if isinstance(cookies, Mapping):
        return {str(key): str(value) for key, value in cookies.items()}
    result: Dict[str, str] = {}
    for item in str(cookies or '').split(';'):
        item = item.strip()
        if not item:
            continue
        key, sep, value = item.partition('=')
        if sep:
            result[key.strip()] = value
    return result


def cookie_header(cookies: Mapping[str, Any]) -> str:
    return '; '.join(f'{key}={value}' for key, value in cookies.items())


@dataclass
class B1RuntimeState:
    """Opaque page state passed to OFB Relay for fingerprint generation."""

    started_at: int
    profile_name: str = 'login'
    generated_at_offset_ms: Optional[int] = None
    time_origin_ms: float = 0.0
    overrides: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def reference(cls, started_at: Optional[int] = None,
                  profile_name: str = 'login') -> 'B1RuntimeState':
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
class PcSessionState:
    loadts: int
    dsllt: int
    ets: int
    mns_seq: int = 0
    fingerprint_ready: bool = False
    last_tiga_update_time: int = 0
    profile_count: int = 0
    sign_count: int = 0
    tab_device_id: str = ''
    rwp_fingerprint: str = ''
    rwp_login_token: Dict[str, Any] = field(default_factory=dict)
    unread_state: Dict[str, Any] = field(default_factory=dict)

    def next_seq(self) -> int:
        self.mns_seq += 1
        return self.mns_seq

    def next_sign_count(self) -> int:
        self.sign_count += 1
        return self.sign_count

    def ensure_dsllt(self, timestamp_ms: int, force: bool = False) -> int:
        timestamp = int(timestamp_ms)
        if force or timestamp - int(self.dsllt) >= DS_REFRESH_INTERVAL_MS:
            self.dsllt = timestamp
        return int(self.dsllt)

    def needs_tiga_refresh(self, timestamp_ms: int) -> bool:
        return (
            not self.last_tiga_update_time
            or int(timestamp_ms) - int(self.last_tiga_update_time)
            >= TIGA_REFRESH_INTERVAL_MS
        )

    def mark_tiga_updated(self, timestamp_ms: Optional[int] = None) -> int:
        self.last_tiga_update_time = int(
            timestamp_ms if timestamp_ms is not None else now_ms()
        )
        return self.last_tiga_update_time

    def mark_profile_reported(self) -> int:
        self.profile_count += 1
        self.fingerprint_ready = True
        return self.profile_count

    def ensure_tab_device_id(self) -> str:
        if not self.tab_device_id:
            self.tab_device_id = str(uuid.uuid4())
        return self.tab_device_id

    def ensure_rwp_fingerprint(self, timestamp_ms: Optional[int] = None) -> str:
        if not self.rwp_fingerprint:
            self.rwp_fingerprint = str(
                int(timestamp_ms if timestamp_ms is not None else now_ms())
            )
        return self.rwp_fingerprint

    def set_rwp_login_token(self, token: Mapping[str, Any]) -> None:
        self.rwp_login_token = dict(token)

    def current_rwp_login_token(
        self,
        user_id: str,
        timestamp_ms: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        token = dict(self.rwp_login_token or {})
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        if (
            not token
            or str(token.get('uid') or '') != str(user_id or '')
            or int(token.get('expiredAt') or 0) <= timestamp
        ):
            self.rwp_login_token = {}
            return None
        return token

    def snapshot(self) -> Dict[str, Any]:
        return {
            'loadts': int(self.loadts),
            'dsllt': int(self.dsllt),
            'ets': int(self.ets),
            'mnsSeq': int(self.mns_seq),
            'fingerprintReady': bool(self.fingerprint_ready),
            'lastTigaUpdateTime': int(self.last_tiga_update_time),
            'p1': int(self.profile_count),
            'sc': int(self.sign_count),
            'XHS_TAB_DEVICE_ID': self.ensure_tab_device_id(),
            'XHS_RWP_FINGERPRINT': self.ensure_rwp_fingerprint(),
            'RWP_LOGIN_TOKEN': dict(self.rwp_login_token or {}),
            'unread': dict(self.unread_state or {}),
        }


@dataclass
class PcDeviceProfile:
    """跨 b1/MNS/X-S-Common/RAP/webprofile 共用的显式运行时输入。"""

    cookies: Any = ''
    local_storage: Any = field(default_factory=dict)
    session_storage: Any = field(default_factory=dict)
    fixed_b1: str = ''
    web_build: str = ''
    release: Dict[str, Any] = field(default_factory=lambda: dict(REFERENCE_PROFILE['release']))
    b1_state: Optional[B1RuntimeState] = None
    session: Optional[PcSessionState] = None
    mns_overrides: Dict[str, Any] = field(default_factory=dict)
    rap_fingerprint_hex: str = ''
    web_profile_fields: Dict[str, Any] = field(default_factory=dict)
    web_profile_i12_seed: Optional[int] = None
    web_profile_fi: Optional[int] = None
    source: str = 'reference'
    browser_exact_inputs: bool = False
    _cookie_map: Dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _release_web_build: Optional[str] = field(default=None, init=False, repr=False)
    _named_b1_states: Dict[str, B1RuntimeState] = field(
        default_factory=dict, init=False, repr=False
    )
    _named_b1_values: Dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self._cookie_map = parse_cookie_kv(self.cookies)
        self.web_profile_fields = {
            str(key): value for key, value in dict(self.web_profile_fields or {}).items()
        }
        if self.web_profile_i12_seed is not None:
            self.web_profile_i12_seed = int(self.web_profile_i12_seed)
            if not 0 <= self.web_profile_i12_seed <= 255:
                raise ValueError('web_profile_i12_seed must be in [0, 255]')
        if self.web_profile_fi is not None:
            self.web_profile_fi = int(self.web_profile_fi)
            if self.web_profile_fi < 0:
                raise ValueError('web_profile_fi must be >= 0')
        local_state = _storage_mapping(self.local_storage)
        tab_state = _storage_mapping(self.session_storage)
        started = int(self._cookie_map.get('loadts') or now_ms())
        if self.session is None:
            # websectiga is produced by the seccallback program before the
            # A successful webprofile report is the only transition that moves
            # subsequent requests to the steady MNS tier.
            ready = bool(self._cookie_map.get('gid'))
            self.session = PcSessionState(
                loadts=started,
                dsllt=int(local_state.get('dsllt') or started),
                ets=int(
                    self._cookie_map.get('ets')
                    or normalize_ets_timestamp(started)
                ),
                fingerprint_ready=ready,
                last_tiga_update_time=int(
                    local_state.get('last_tiga_update_time') or 0
                ),
                profile_count=int(local_state.get('p1') or 0),
                sign_count=int(local_state.get('sc') or 0),
                tab_device_id=str(tab_state.get('XHS_TAB_DEVICE_ID') or ''),
                rwp_fingerprint=str(tab_state.get('XHS_RWP_FINGERPRINT') or ''),
                rwp_login_token=_json_object(
                    local_state.get('RWP_LOGIN_TOKEN') or {}
                ),
                unread_state=_json_object(self._cookie_map.get('unread') or {}),
            )
        self.session.ensure_tab_device_id()
        self.session.ensure_rwp_fingerprint(started)
        self.local_storage = local_state
        self.session_storage = tab_state
        self._sync_storage_maps()
        if self.b1_state is None:
            self.b1_state = B1RuntimeState.reference(started_at=started)
        if not self.web_build:
            self.web_build = (
                self._cookie_map.get('webBuild')
                or str(self.release['webBuild'])
            )
        self._sync_release_for_web_build()

    def _sync_release_for_web_build(self) -> None:
        if self._release_web_build == self.web_build:
            return
        self.release.update(compute('pc', 'release', {'web_build': self.web_build}))
        self._release_web_build = self.web_build

    @property
    def cookie_map(self) -> Dict[str, str]:
        return dict(self._cookie_map)

    @property
    def document_cookie(self) -> str:
        """Cookie view available to browser JavaScript/signing code."""
        hidden = {
            'acw_tc',
            'web_session',
            'secure_session',
            'id_token',
            'customer-sso-sid',
            'access-token-creator.xiaohongshu.com',
            'galaxy_creator_session_id',
        }
        return cookie_header({
            key: value
            for key, value in self._cookie_map.items()
            if key not in hidden
        })

    def update_cookies(self, cookies: Any) -> None:
        updates = parse_cookie_kv(cookies)
        old_websectiga = self._cookie_map.get('websectiga')
        self._cookie_map.update(updates)
        self.cookies = cookie_header(self._cookie_map)
        if updates.get('webBuild'):
            self.web_build = updates['webBuild']
            self._sync_release_for_web_build()
        if updates.get('loadts'):
            self.session.loadts = int(updates['loadts'])
        if updates.get('ets'):
            self.session.ets = int(updates['ets'])
        if updates.get('unread'):
            self.session.unread_state = _json_object(updates['unread'])
        if updates.get('websectiga') and updates['websectiga'] != old_websectiga:
            self.session.mark_tiga_updated()
        if updates.get('gid'):
            self.session.fingerprint_ready = True

    def resolve_mns_tier(self, api: str,
                         explicit_tier: Optional[str] = None) -> str:
        result = compute('pc', 'resolve-tier', {
            'api': api, 'tier': explicit_tier,
            'fingerprint_ready': self.session.fingerprint_ready,
        })
        return str(result['tier'])

    def set_mns_stage(self, tier: str, *, env_const: int,
                      env_fp_tail: Any, evidence: str = 'override') -> None:
        self.mns_overrides[str(tier)] = {
            'env_const': env_const, 'env_fp_tail': env_fp_tail,
        }

    def next_sign_context(self, api: str, *, tier: Optional[str] = None,
                          mns_profile: Optional[str] = None,
                          timestamp_ms: Optional[int] = None,
                          version: Optional[int] = None) -> Dict[str, Any]:
        result = compute('pc', 'next-sign-context', {
            'api': api, 'tier': tier, 'mns_profile': mns_profile,
            'timestamp_ms': timestamp_ms, 'version': version,
            'session': self.session.snapshot(),
            'release': dict(self.release),
            'web_build': self.web_build,
            'local_storage': dict(self.local_storage),
            'overrides': dict(self.mns_overrides),
        })
        context = result.get('context')
        if not isinstance(context, dict) or not context.get('tier') or not context.get('token'):
            raise RuntimeError('OFB Relay 未返回 PC 签名上下文')
        self.session.next_seq()
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
        if profile_name:
            key = str(profile_name)
            cached = self._named_b1_values.get(key)
            if cached:
                return cached
            state = self._named_b1_states.get(key)
            if state is None:
                state = B1RuntimeState.reference(
                    started_at=self.session.loadts,
                    profile_name=key,
                )
                self._named_b1_states[key] = state
            if state.generated_at_offset_ms is not None:
                timestamp = int(
                    self.session.loadts + state.generated_at_offset_ms
                )
            value = generate_b1(state.to_b1_options(timestamp))
            self._named_b1_values[key] = value
            return value
        return generate_b1(state.to_b1_options(timestamp))

    def profile_data_options(self, timestamp_ms: Optional[int] = None) -> Dict[str, Any]:
        """Return explicit inputs for the zero-host webprofile calculation."""
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        options: Dict[str, Any] = {
            'fields': dict(self.web_profile_fields or {}),
            'timestamp_ms': timestamp,
            'ets': int(self.session.ets),
            'document_cookie': self.document_cookie,
            'time_origin': self.session.loadts,
        }
        if self.web_profile_i12_seed is not None:
            options['i12_seed'] = int(self.web_profile_i12_seed)
        if self.web_profile_fi is not None:
            options['telemetry_fi'] = int(self.web_profile_fi)
        return options

    def profile_data_from_capture(self, fields: Mapping[str, Any]) -> str:
        """Encrypt a complete browser-captured profile field map unchanged.

        The caller must supply all fields from one Network request.  This
        prevents a partial capture from silently mixing browser and local
        values, which changes ciphertext length and triggers risk controls.
        """
        from .runtime import generate_profile_data
        values = dict(fields or {})
        return generate_profile_data(fields=values, exact_fields=True)

    def dsl_pair(
        self,
        dsl: str,
        *,
        timestamp_ms: Optional[int] = None,
        refreshed: bool = False,
    ) -> str:
        if not dsl:
            raise ValueError('_dsl 为空')
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        dsllt = self.session.ensure_dsllt(timestamp, force=refreshed)
        return f'{dsllt};{dsl}'

    def mark_fingerprint_ready(self, ready: bool = True) -> None:
        self.session.fingerprint_ready = bool(ready)
        self._sync_storage_maps()

    def needs_tiga_refresh(self, timestamp_ms: Optional[int] = None) -> bool:
        timestamp = int(timestamp_ms if timestamp_ms is not None else now_ms())
        return self.session.needs_tiga_refresh(timestamp)

    def mark_tiga_updated(self, timestamp_ms: Optional[int] = None) -> int:
        value = self.session.mark_tiga_updated(timestamp_ms)
        self._sync_storage_maps()
        return value

    def mark_profile_reported(self) -> int:
        value = self.session.mark_profile_reported()
        self._sync_storage_maps()
        return value

    def _sync_storage_maps(self) -> None:
        local_state = _storage_mapping(self.local_storage)
        local_state.update({
            'dsllt': str(int(self.session.dsllt)),
            'last_tiga_update_time': str(int(self.session.last_tiga_update_time)),
            'p1': str(int(self.session.profile_count)),
            'sc': str(int(self.session.sign_count)),
        })
        if self.session.rwp_login_token:
            local_state['RWP_LOGIN_TOKEN'] = json.dumps(
                self.session.rwp_login_token,
                ensure_ascii=False,
                separators=(',', ':'),
            )
        elif 'RWP_LOGIN_TOKEN' in local_state:
            local_state['RWP_LOGIN_TOKEN'] = ''
        tab_state = _storage_mapping(self.session_storage)
        tab_state.update({
            'XHS_TAB_DEVICE_ID': self.session.ensure_tab_device_id(),
            'XHS_RWP_FINGERPRINT': self.session.ensure_rwp_fingerprint(),
        })
        self.local_storage = local_state
        self.session_storage = tab_state

    def browser_storage_snapshot(self) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Return generated browser storage state without exposing internals."""
        self._sync_storage_maps()
        return dict(self.local_storage), dict(self.session_storage)

    def update_storage(
        self,
        local_storage: Optional[Mapping[str, Any]] = None,
        session_storage: Optional[Mapping[str, Any]] = None,
    ) -> None:
        local_state = _storage_mapping(local_storage or {})
        tab_state = _storage_mapping(session_storage or {})
        if local_storage is not None:
            merged_local = _storage_mapping(self.local_storage)
            merged_local.update(local_state)
            self.local_storage = merged_local
        if session_storage is not None:
            merged_session = _storage_mapping(self.session_storage)
            merged_session.update(tab_state)
            self.session_storage = merged_session
        if local_state.get('dsllt'):
            self.session.dsllt = int(local_state['dsllt'])
        if local_state.get('last_tiga_update_time'):
            self.session.last_tiga_update_time = int(
                local_state['last_tiga_update_time']
            )
        if local_state.get('p1') is not None:
            self.session.profile_count = int(local_state['p1'])
        if local_state.get('sc') is not None:
            self.session.sign_count = int(local_state['sc'])
        if 'RWP_LOGIN_TOKEN' in local_state:
            self.session.rwp_login_token = _json_object(
                local_state.get('RWP_LOGIN_TOKEN') or {}
            )
        if tab_state.get('XHS_TAB_DEVICE_ID'):
            self.session.tab_device_id = str(tab_state['XHS_TAB_DEVICE_ID'])
        if tab_state.get('XHS_RWP_FINGERPRINT'):
            self.session.rwp_fingerprint = str(
                tab_state['XHS_RWP_FINGERPRINT']
            )
        self._sync_storage_maps()

    def state_snapshot(self) -> Dict[str, Any]:
        snapshot = self.session.snapshot()
        snapshot.update({
            'webBuild': str(self.web_build),
            'xsecappid': str(self.release['appId']),
        })
        return snapshot


__all__ = [
    'REFERENCE_PROFILE',
    'DS_REFRESH_INTERVAL_MS',
    'TIGA_REFRESH_INTERVAL_MS',
    'B1RuntimeState',
    'PcSessionState',
    'PcDeviceProfile',
    'parse_cookie_kv',
    'cookie_header',
    'normalize_ets_timestamp',
    'initial_pc_cookies',
    'now_ms',
]
