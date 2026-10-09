# encoding: utf-8
"""Unified authentication and dynamic-signing inputs for XHS platforms."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import Any, ClassVar, Mapping, Optional

from xhs_utils.xhs_core.auth import PC_PLATFORM_CONFIG, XHSAuth, XHSPlatformConfig
from xhs_utils.xhs_core.cookies import HostCookieStore

from .state import (
    B1RuntimeState,
    PcDeviceProfile,
    cookie_header,
    parse_cookie_kv,
)
from .http import PcHttpClient


PC_PARAMETER_SOURCES = {'computed_values': 'OFB Relay', 'cookies': 'platform session'}


_AUTH_FACTORY_TOKEN = object()


@dataclass
class XHSPcAuth(XHSAuth):
    """PC HTTP authentication and persisted session state; computed values use OFB Relay."""

    PLATFORM_CONFIG: ClassVar[XHSPlatformConfig] = PC_PLATFORM_CONFIG

    platform: str = 'pc'
    login_source: str = 'cookie'
    cookies: Any = ''
    b1: str = ''
    dsl: str = ''
    user_id: str = ''

    local_storage: Mapping[str, Any] = field(default_factory=dict, repr=False)
    session_storage: Mapping[str, Any] = field(default_factory=dict, repr=False)
    b1_state: Optional[B1RuntimeState] = field(default=None, repr=False)
    web_build: str = ''
    mns_env: Mapping[str, Mapping[str, Any]] = field(default_factory=dict, repr=False)
    rap_fingerprint_hex: str = field(default='', repr=False)
    web_profile_fields: Mapping[str, Any] = field(default_factory=dict, repr=False)
    web_profile_i12_seed: Optional[int] = field(default=None, repr=False)
    web_profile_fi: Optional[int] = field(default=None, repr=False)
    host_cookies: Mapping[str, Any] = field(default_factory=dict, repr=False)
    host_cookie_state: Mapping[str, Any] = field(default_factory=dict, repr=False)
    cookie_source_url: str = field(default='', repr=False)
    profile: Optional[PcDeviceProfile] = field(default=None, repr=False)
    http_client: Optional[PcHttpClient] = field(default=None, repr=False)
    _cookie_store: HostCookieStore = field(init=False, repr=False)
    _user_id_ready: bool = field(default=False, init=False, repr=False)
    _factory_token: InitVar[object] = None

    def __post_init__(self, _factory_token: object) -> None:
        if _factory_token is not _AUTH_FACTORY_TOKEN:
            raise TypeError(
                'XHSPcAuth cannot be constructed directly; use '
                'XHSPcAuth.from_cookie(), from_qrcode_login(), or '
                'from_phone_login()'
            )
        self.login_source = self._bind_platform(self.login_source)
        if self.http_client is None:
            self.http_client = PcHttpClient(proxies=self.proxies)
        cookie_map = parse_cookie_kv(self.cookies)
        self._cookie_store = (
            HostCookieStore.from_state(self.host_cookie_state)
            if self.host_cookie_state
            else HostCookieStore(self.host_cookies)
        )
        self._cookie_store.extract_host_only(
            cookie_map,
            self.cookie_source_url or self.origin('api'),
        )
        self.host_cookies = self._cookie_store.snapshot()
        self.cookies = cookie_header(cookie_map)

        if self.profile is None:
            self.profile = PcDeviceProfile(
                cookies=cookie_map,
                local_storage=self.local_storage,
                session_storage=self.session_storage,
                fixed_b1=self.b1,
                web_build=self.web_build,
                b1_state=self.b1_state,
                rap_fingerprint_hex=self.rap_fingerprint_hex,
                web_profile_fields=dict(self.web_profile_fields or {}),
                web_profile_i12_seed=self.web_profile_i12_seed,
                web_profile_fi=self.web_profile_fi,
                source=f'auth:{self.login_source}',
            )
        else:
            self.profile.update_cookies(cookie_map)
            self.profile.update_storage(self.local_storage, self.session_storage)
            if self.b1:
                self.profile.fixed_b1 = self.b1
            if self.b1_state is not None:
                self.profile.b1_state = self.b1_state
            if self.web_build:
                self.profile.web_build = self.web_build
            if self.rap_fingerprint_hex:
                self.profile.rap_fingerprint_hex = self.rap_fingerprint_hex
            if self.web_profile_fields:
                self.profile.web_profile_fields.update(
                    {str(key): value for key, value in self.web_profile_fields.items()}
                )
            if self.web_profile_i12_seed is not None:
                self.profile.web_profile_i12_seed = int(self.web_profile_i12_seed)
            if self.web_profile_fi is not None:
                self.profile.web_profile_fi = int(self.web_profile_fi)

        for tier, material in dict(self.mns_env or {}).items():
            self.profile.set_mns_stage(
                str(tier),
                env_const=int(material['envConst']),
                env_fp_tail=material.get('envFpTailHex', material.get('envFpTail')),
                evidence=str(material.get('evidence') or 'XHSPcAuth override'),
            )

        self._set_dsl(self.dsl)
        self.web_build = str(self.profile.web_build)
        self._user_id_ready = bool(self.user_id)
        self._sync_storage_from_profile()
        self.validate()

    def _sync_storage_from_profile(self) -> None:
        local, session = self.profile.browser_storage_snapshot()
        self.local_storage = local
        self.session_storage = session

    def validate(self, require_user_id: bool = False) -> None:
        cookies = self.profile.cookie_map
        if not cookies.get('a1'):
            raise ValueError(
                'XHSPcAuth.cookies must contain a1; use a saved local login '
                'Cookie or XHSPcAuth.from_qrcode_login()/from_phone_login()'
            )
        if not cookies.get('web_session'):
            raise ValueError(
                'XHSPcAuth.cookies must contain server-issued web_session; '
                'use qrcode/phone login when no saved session is available'
            )
        if require_user_id and not self.user_id:
            raise ValueError('user_id is missing; call XHS_Apis(auth).bootstrap() first')

    @staticmethod
    def parameter_sources() -> dict:
        """Return the complete ownership boundary for reversed PC parameters."""
        return {name: tuple(values) for name, values in PC_PARAMETER_SOURCES.items()}

    @property
    def a1(self) -> str:
        return self.profile.cookie_map['a1']

    @property
    def sign_cookie(self) -> str:
        return self.profile.document_cookie

    def cookies_for_url(self, url: str, cookies: Any = None) -> dict:
        return self._cookie_store.cookies_for_url(
            url,
            self.profile.cookie_map if cookies is None else cookies,
        )

    def host_cookies_snapshot(self) -> dict:
        return self._cookie_store.snapshot()

    def current_b1(self, timestamp_ms: Optional[int] = None) -> str:
        return self.profile.current_b1(timestamp_ms)

    def next_sign_context(
        self,
        api: str,
        tier: Optional[str] = None,
        mns_profile: Optional[str] = None,
        timestamp_ms: Optional[int] = None,
    ) -> dict:
        context = self.profile.next_sign_context(
            api,
            tier=tier,
            mns_profile=mns_profile,
            timestamp_ms=timestamp_ms,
        )
        self._sync_storage_from_profile()
        return context

    def update_cookies(self, cookies: Any, *, source_url: str = '') -> None:
        values = self.profile.cookie_map
        updates = parse_cookie_kv(cookies)
        self._cookie_store.extract_host_only(
            updates,
            source_url or self.origin('api'),
        )
        values.update(updates)
        self.profile.update_cookies(values)
        self.cookies = cookie_header(self.profile.cookie_map)
        self.host_cookies = self._cookie_store.snapshot()
        self._sync_storage_from_profile()

    def update_runtime_state(
        self,
        *,
        b1: Optional[str] = None,
        dsl: Optional[str] = None,
        user_id: Optional[str] = None,
        local_storage: Optional[Mapping[str, Any]] = None,
        session_storage: Optional[Mapping[str, Any]] = None,
        web_profile_fields: Optional[Mapping[str, Any]] = None,
        web_profile_i12_seed: Optional[int] = None,
        web_profile_fi: Optional[int] = None,
    ) -> 'XHSPcAuth':
        """Merge optional runtime/alignment state without rebuilding Auth."""
        if b1 is not None:
            self.b1 = str(b1)
            self.profile.fixed_b1 = self.b1
        if dsl is not None:
            self._set_dsl(dsl)
        if user_id is not None:
            self.set_user_id(user_id)
        if web_profile_fields is not None:
            self.web_profile_fields = dict(web_profile_fields)
            self.profile.web_profile_fields.update(self.web_profile_fields)
        if web_profile_i12_seed is not None:
            self.web_profile_i12_seed = int(web_profile_i12_seed)
            self.profile.web_profile_i12_seed = self.web_profile_i12_seed
        if web_profile_fi is not None:
            self.web_profile_fi = int(web_profile_fi)
            self.profile.web_profile_fi = self.web_profile_fi
        if local_storage is not None:
            merged_local = dict(self.local_storage or {})
            merged_local.update(dict(local_storage))
            self.local_storage = merged_local
        if session_storage is not None:
            merged_session = dict(self.session_storage or {})
            merged_session.update(dict(session_storage))
            self.session_storage = merged_session
        self.profile.update_storage(local_storage, session_storage)
        self._sync_storage_from_profile()
        return self

    def update_browser_state(
        self,
        **kwargs,
    ) -> 'XHSPcAuth':
        """Backward-compatible alias for :meth:`update_runtime_state`."""
        return self.update_runtime_state(**kwargs)

    @property
    def dsl_pair(self) -> str:
        if self.dsl:
            value = self.dsl
        else:
            from .dsl import get_dsl
            value = get_dsl(
                proxies=self.proxies,
                http_client=self.http_client,
            )
        pair = self.profile.dsl_pair(value)
        self._sync_storage_from_profile()
        return pair

    def refresh_dsl(self) -> str:
        from .dsl import get_dsl
        from .state import now_ms

        self.dsl = get_dsl(
            proxies=self.proxies,
            force=True,
            http_client=self.http_client,
        )
        self.profile.session.dsllt = now_ms()
        return self.dsl_pair

    def needs_tiga_refresh(self, timestamp_ms: Optional[int] = None) -> bool:
        return self.profile.needs_tiga_refresh(timestamp_ms)

    def state_snapshot(self, include_tokens: bool = False) -> dict:
        state = self.profile.state_snapshot()
        state['loginSource'] = self.login_source
        state['transport'] = self.http_client.state_snapshot()
        state['hostCookieKeys'] = {
            host: list(values)
            for host, values in self._cookie_store.snapshot().items()
        }
        if not include_tokens:
            state['RWP_LOGIN_TOKEN'] = {}
        return state

    def close(self) -> None:
        self.http_client.close()

    def set_user_id(self, user_id: str) -> 'XHSPcAuth':
        if not user_id:
            raise ValueError('user_id is empty')
        self.user_id = str(user_id)
        self._user_id_ready = True
        return self

    @classmethod
    def from_cookie(cls, cookies: Any, **auth_kwargs) -> 'XHSPcAuth':
        """Create Auth from a complete user-supplied authenticated Cookie.

        The Cookie must contain at least ``a1`` and the server-issued
        ``web_session``. Copy the complete request Cookie header because
        ``web_session`` is HttpOnly and is not available through
        ``document.cookie``.
        """
        auth_kwargs['login_source'] = 'cookie'
        auth = cls(
            cookies=cookies,
            _factory_token=_AUTH_FACTORY_TOKEN,
            **auth_kwargs,
        )
        # Resolve the authenticated user id immediately so every business
        # API can be used without a second manual bootstrap step.
        from apis.xhs_pc_apis import XHS_Apis
        XHS_Apis(auth).bootstrap()
        return auth

    @classmethod
    def from_qrcode_login(
        cls,
        *,
        show_in_terminal: bool = True,
        proxies: Optional[dict] = None,
        http_client: Optional[PcHttpClient] = None,
    ) -> 'XHSPcAuth':
        """Login through the local QR API flow and return a ready Auth object.

        The QR is rendered locally and scanned with the XHS mobile app. No web
        browser, browser Cookie export, or browser JavaScript execution is used.
        """
        from apis.xhs_pc_login_apis import XHSLoginApi

        http_client = http_client or PcHttpClient(proxies=proxies)
        login = XHSLoginApi(
            proxies=proxies,
            http_client=http_client,
        )
        cookies = login.qrcode_login(
            show_in_terminal=show_in_terminal
        )
        if not cookies:
            http_client.close()
            raise RuntimeError('XHS QR login did not return an authenticated Cookie')
        auth = cls(
            cookies=cookies,
            login_source='qrcode',
            proxies=proxies,
            http_client=http_client,
            host_cookies=login.host_cookies_snapshot(),
            host_cookie_state=login.host_cookie_state(),
            cookie_source_url=PC_PLATFORM_CONFIG.origin('api'),
            profile=login.profile,
            _factory_token=_AUTH_FACTORY_TOKEN,
        )
        from apis.xhs_pc_apis import XHS_Apis
        XHS_Apis(auth).bootstrap()
        return auth

    @classmethod
    def from_phone_login(
        cls,
        *,
        proxies: Optional[dict] = None,
        http_client: Optional[PcHttpClient] = None,
    ) -> 'XHSPcAuth':
        """Login through the local SMS API flow without using a browser."""
        from apis.xhs_pc_login_apis import XHSLoginApi

        http_client = http_client or PcHttpClient(proxies=proxies)
        login = XHSLoginApi(
            proxies=proxies,
            http_client=http_client,
        )
        cookies = login.phone_login()
        if not cookies:
            http_client.close()
            raise RuntimeError('XHS phone login did not return an authenticated Cookie')
        auth = cls(
            cookies=cookies,
            login_source='phone',
            proxies=proxies,
            http_client=http_client,
            host_cookies=login.host_cookies_snapshot(),
            host_cookie_state=login.host_cookie_state(),
            cookie_source_url=PC_PLATFORM_CONFIG.origin('api'),
            profile=login.profile,
            _factory_token=_AUTH_FACTORY_TOKEN,
        )
        from apis.xhs_pc_apis import XHS_Apis
        XHS_Apis(auth).bootstrap()
        return auth

    def _set_dsl(self, value: str) -> None:
        text = str(value or '')
        if ';' in text:
            dsllt, text = text.split(';', 1)
            if dsllt.isdigit():
                self.profile.session.dsllt = int(dsllt)
        self.dsl = text

__all__ = ['PC_PARAMETER_SOURCES', 'XHSAuth', 'XHSPcAuth']
