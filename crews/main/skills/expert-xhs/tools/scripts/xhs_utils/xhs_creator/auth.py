"""Creator authentication object and complete parameter ownership boundary."""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import uuid
from typing import Any, ClassVar, Mapping, Optional

from xhs_utils.xhs_core.auth import CREATOR_PLATFORM_CONFIG, XHSAuth, XHSPlatformConfig
from xhs_utils.xhs_core.cookies import HostCookieStore
from xhs_utils.relay import compute

from .state import (
    DS_REFRESH_INTERVAL_MS,
    CreatorB1RuntimeState,
    CreatorDeviceProfile,
    cookie_header,
    now_ms,
    parse_cookie_kv,
)
from .http import CreatorHttpClient


CREATOR_PARAMETER_SOURCES = {'computed_values': 'OFB Relay', 'cookies': 'platform session'}


_AUTH_FACTORY_TOKEN = object()
_AUTH_COOKIE_KEYS = (
    'customer-sso-sid',
    'access-token-creator.xiaohongshu.com',
    'galaxy_creator_session_id',
    'web_session',
)


@dataclass
class XHSCreatorAuth(XHSAuth):
    """CREATOR HTTP authentication and persisted session state; computed values use OFB Relay."""

    PLATFORM_CONFIG: ClassVar[XHSPlatformConfig] = CREATOR_PLATFORM_CONFIG

    platform: str = 'creator'
    login_source: str = 'cookie'
    cookies: Any = field(default='', repr=False)
    b1: str = field(default='', repr=False)
    dsl: str = field(default='', repr=False)
    local_storage: Mapping[str, Any] = field(default_factory=dict, repr=False)
    session_storage: Mapping[str, Any] = field(default_factory=dict, repr=False)
    b1_state: Optional[CreatorB1RuntimeState] = field(default=None, repr=False)
    mns_env: Mapping[str, Mapping[str, Any]] = field(default_factory=dict, repr=False)
    web_profile_fields: Mapping[str, Any] = field(default_factory=dict, repr=False)
    host_cookies: Mapping[str, Any] = field(default_factory=dict, repr=False)
    host_cookie_state: Mapping[str, Any] = field(default_factory=dict, repr=False)
    cookie_source_url: str = field(default='', repr=False)
    profile: Optional[CreatorDeviceProfile] = field(default=None, repr=False)
    http_client: Optional[CreatorHttpClient] = field(default=None, repr=False)
    _cookie_store: HostCookieStore = field(init=False, repr=False)
    _factory_token: InitVar[object] = None

    def __post_init__(self, _factory_token: object) -> None:
        if _factory_token is not _AUTH_FACTORY_TOKEN:
            raise TypeError(
                'XHSCreatorAuth cannot be constructed directly; use '
                'from_cookie(), from_qrcode_login(), from_phone_login(), '
                'or from_pc_auth()'
            )
        self.login_source = self._bind_platform(self.login_source)
        if self.http_client is None:
            self.http_client = CreatorHttpClient(proxies=self.proxies)
        values = parse_cookie_kv(self.cookies)
        self._cookie_store = (
            HostCookieStore.from_state(self.host_cookie_state)
            if self.host_cookie_state
            else HostCookieStore(self.host_cookies)
        )
        self._cookie_store.extract_host_only(
            values,
            self.cookie_source_url or self.origin('api'),
        )
        self.host_cookies = self._cookie_store.snapshot()
        self.cookies = cookie_header(values)

        if self.profile is None:
            self.profile = CreatorDeviceProfile(
                cookies=values,
                local_storage=self.local_storage,
                session_storage=self.session_storage,
                fixed_b1=self.b1,
                dsl=self.dsl,
                b1_state=self.b1_state,
                web_profile_fields=dict(self.web_profile_fields or {}),
                source=f'auth:{self.login_source}',
            )
        else:
            self.profile.update_cookies(values)
            if self.b1:
                self.profile.fixed_b1 = str(self.b1)
            if self.b1_state is not None:
                self.profile.b1_state = self.b1_state
            if self.web_profile_fields:
                self.profile.web_profile_fields.update(
                    {str(key): value for key, value in self.web_profile_fields.items()}
                )

        for stage, material in dict(self.mns_env or {}).items():
            self.profile.set_mns_stage(
                str(stage),
                env_const=int(material['envConst']),
                env_fp_tail=material.get('envFpTailHex', material.get('envFpTail')),
                device_tag=material.get('deviceTag'),
                evidence=str(material.get('evidence') or 'XHSCreatorAuth override'),
            )
        self.local_storage = dict(self.profile.local_storage or {})
        self.session_storage = dict(self.profile.session_storage or {})
        self._set_dsl(self.dsl or self.profile.dsl)
        self.validate(require_authenticated=True)

    @staticmethod
    def parameter_sources() -> dict:
        return {
            name: tuple(values)
            for name, values in CREATOR_PARAMETER_SOURCES.items()
        }

    @property
    def cookie_map(self) -> dict:
        return self.profile.cookie_map

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

    @property
    def a1(self) -> str:
        return self.profile.cookie_map['a1']

    def validate(self, require_authenticated: bool = True) -> None:
        cookies = self.profile.cookie_map
        if not cookies.get('a1'):
            raise ValueError('Creator Cookie must contain a1')
        if require_authenticated and not any(cookies.get(key) for key in _AUTH_COOKIE_KEYS):
            raise ValueError(
                'Creator Cookie is not authenticated; pass the complete Cookie '
                'or use QR/phone login'
            )

    def current_b1(
        self,
        timestamp_ms: Optional[int] = None,
        profile_name: Optional[str] = None,
    ) -> str:
        return self.profile.current_b1(timestamp_ms, profile_name=profile_name)

    def next_sign_context(
        self,
        api: str,
        *,
        tier: Optional[str] = None,
        mns_profile: Optional[str] = None,
        timestamp_ms: Optional[int] = None,
        version: Optional[int] = None,
    ) -> dict:
        del api
        return self.profile.next_sign_context(
            tier=tier,
            mns_profile=mns_profile,
            timestamp_ms=timestamp_ms,
            version=version,
        )

    def dsl_pair(self, timestamp_ms: Optional[int] = None) -> str:
        self.ensure_ds_material()
        return self.profile.dsl_pair(timestamp_ms)

    def ensure_ds_material(self, force: bool = False) -> None:
        """Refresh the platform security configuration used by OFB Relay."""
        if not self.profile.session.security_ready:
            return
        stale = (
            now_ms() - int(self.profile.session.dsllt)
            >= DS_REFRESH_INTERVAL_MS
        )
        if not force and not stale and self.profile.dsl and self.profile.ds_program:
            return
        force = bool(force or stale)
        from .dsl import get_ds_bundle

        dsl, program = get_ds_bundle(
            proxies=self.proxies,
            force=force,
            http_client=self.http_client,
        )
        if force or not self.profile.dsl:
            self.profile.dsl = dsl
        self.profile.ds_program = program
        if force:
            self.profile.session.dsllt = now_ms()

    def refresh_dsl(self) -> str:
        self.ensure_ds_material(force=True)
        return self.profile.dsl_pair()

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

    def update_runtime_state(
        self,
        *,
        b1: Optional[str] = None,
        dsl: Optional[str] = None,
        b1_state: Optional[CreatorB1RuntimeState] = None,
        web_profile_fields: Optional[Mapping[str, Any]] = None,
    ) -> 'XHSCreatorAuth':
        if b1 is not None:
            self.b1 = str(b1)
            self.profile.fixed_b1 = self.b1
        if dsl is not None:
            self._set_dsl(dsl)
        if b1_state is not None:
            self.b1_state = b1_state
            self.profile.b1_state = b1_state
        if web_profile_fields is not None:
            self.web_profile_fields = dict(web_profile_fields)
            self.profile.web_profile_fields.update(self.web_profile_fields)
        return self

    def state_snapshot(self) -> dict:
        state = self.profile.state_snapshot()
        state['loginSource'] = self.login_source
        state['transport'] = self.http_client.state_snapshot()
        state['hostCookieKeys'] = {
            host: list(values)
            for host, values in self._cookie_store.snapshot().items()
        }
        return state

    def close(self) -> None:
        self.http_client.close()

    @classmethod
    def from_cookie(cls, cookies: Any, **auth_kwargs) -> 'XHSCreatorAuth':
        """Create from a complete user-supplied authenticated Creator Cookie."""
        auth_kwargs['login_source'] = 'cookie'
        return cls(
            cookies=cookies,
            _factory_token=_AUTH_FACTORY_TOKEN,
            **auth_kwargs,
        )

    @classmethod
    def from_pc_auth(
        cls,
        pc_auth,
        *,
        proxies: Optional[dict] = None,
        http_client: Optional[CreatorHttpClient] = None,
    ) -> 'XHSCreatorAuth':
        """Create the Creator signing view from an already logged-in PC Auth.

        The web and Creator sites share the server-issued login Cookie, but
        they do not share origin storage or signing state.  The browser's
        ``/publish/publish?source=official`` navigation therefore reuses the
        PC session and initializes a fresh Creator b1/MNS/security context;
        it does *not* perform another CAS QR/SMS login.  This bridge mirrors
        that behavior for the unified Auth entry point.
        """
        from xhs_utils.xhs_pc.auth import XHSPcAuth
        from apis.xhs_creator_login_apis import XHSCreatorLoginApi

        if not isinstance(pc_auth, XHSPcAuth):
            raise TypeError('pc_auth must be an authenticated XHSPcAuth instance')

        source = pc_auth.profile.cookie_map
        # Only carry cookies observed on the Creator publish navigation.  In
        # particular, PC's webBuild/xsecappid/loadts are origin-context
        # material and must be replaced by the Creator release values.
        shared_names = {
            'abRequestId', 'ets', 'a1', 'webId', 'unread', 'gid',
            'web_session', 'id_token', 'x-rednote-datactry',
            'x-rednote-holderctry', 'websectiga', 'sec_poison_id',
            '_gray_did',
            # When the source PC cookie was copied from an already-open
            # publish tab these Creator HttpOnly values are present too.
            # Preserve them so the navigation can reuse the exact session;
            # a fresh PC QR login simply omits them and lets navigation issue
            # the Creator set server-side.
            'customer-sso-sid', 'x-user-id-creator.xiaohongshu.com',
            'customerClientId', 'access-token-creator.xiaohongshu.com',
            'galaxy_creator_session_id', 'galaxy.creator.beaker.session.id',
        }
        creator_cookies = {
            name: value
            for name, value in source.items()
            if name in shared_names and value not in (None, '')
        }
        creator_cookies.setdefault('_gray_did', str(uuid.uuid4()))
        creator_cookies['webBuild'] = compute('creator', 'reference-profile', {})['release']['webBuild']
        creator_cookies['xsecappid'] = 'ugc'
        creator_cookies['loadts'] = str(now_ms())

        creator_profile = CreatorDeviceProfile(
            cookies=creator_cookies,
            source='auth:shared-pc-session',
        )
        # The shared PC Cookie includes the already-issued websectiga/gid, so
        # CreatorDeviceProfile would otherwise consider security initialized
        # and skip the DS program installation.  Creator's publish navigation
        # keeps those shared values for the first user/info call, but still
        # runs its own DS/redcaptcha/sbtsource bootstrap before later signed
        # requests.  Start the Creator runtime in that same intermediate state.
        creator_profile.session.security_ready = False
        creator_profile.dsl = ''
        creator_profile.ds_program = ''
        creator_http = http_client or CreatorHttpClient(
            proxies=proxies if proxies is not None else pc_auth.proxies,
        )
        login = XHSCreatorLoginApi(
            profile=creator_profile,
            proxies=proxies if proxies is not None else pc_auth.proxies,
            http_client=creator_http,
        )
        # Carry host-scoped edge cookies (notably edith's acw_tc) across the
        # same-site navigation.  The shared Cookie header alone cannot encode
        # this domain boundary, while Chrome's cookie jar preserves it.
        if getattr(pc_auth, 'host_cookies', None):
            login._cookie_store = HostCookieStore(pc_auth.host_cookies)
        try:
            # The browser first navigates to the publish document.  That
            # response exchanges the shared PC session for Creator's
            # host/session cookies (most are HttpOnly and never appear in
            # document.cookie).  Without this navigation the first permit
            # request is commonly rejected by the edge with HTTP 406.
            login.bootstrap_publish_navigation()
            # Existing web_session means the browser skips customer CAS.  On
            # the current publish page it also keeps the first user/info call
            # on the same 0201/nop batch as redcaptcha, scripting and
            # sbtsource; only after that response does it switch to 0101/a1.
            shared_session = bool(login.profile.cookie_map.get('web_session'))
            login._finish_security_bootstrap(activate=not shared_session)
            if shared_session:
                success, _, _ = login.get_user_info(
                    mns_profile=None,
                    b1_profile='login',
                    tier='0201',
                    dsl_pair_value=(
                        f'{login.profile.session.loadts};undefined'
                    ),
                    referer=(
                        login.creator_url
                        + '/publish/publish?source=official'
                    ),
                )
                if not success:
                    raise RuntimeError(
                        'Creator user/info rejected the shared PC login session'
                    )
                login._activate_security()
            else:
                # Defensive fallback for a PC auth object that did not carry
                # web_session: use the ordinary CAS probe after activation.
                try:
                    login.query_session()
                except Exception:
                    pass
                success, _, _ = login.get_user_info(
                    mns_profile='publish_user_info',
                    b1_profile='login',
                )
            if not success:
                raise RuntimeError(
                    'Creator user/info rejected the shared PC login session'
                )
            # Shared publish navigation already supplied the security Cookie
            # set.  Do not emit an extra webprofile/seccallback pair unless
            # the session is incomplete.
            try:
                login._require_security_cookies()
            except RuntimeError:
                login._complete_security()
            else:
                login._security_completed = True
            return cls(
                cookies=login.profile.cookie_map,
                login_source='cookie',
                proxies=proxies if proxies is not None else pc_auth.proxies,
                profile=login.profile,
                http_client=login.http,
                host_cookies=login.host_cookies_snapshot(),
                host_cookie_state=login.host_cookie_state(),
                cookie_source_url=CREATOR_PLATFORM_CONFIG.origin('api'),
                _factory_token=_AUTH_FACTORY_TOKEN,
            )
        except Exception:
            login.close()
            raise

    @classmethod
    def from_qrcode_login(
        cls,
        *,
        show_in_terminal: bool = True,
        proxies: Optional[dict] = None,
        http_client: Optional[CreatorHttpClient] = None,
    ) -> 'XHSCreatorAuth':
        """Run the pure-HTTP Creator QR flow and return ready Auth."""
        from apis.xhs_creator_login_apis import XHSCreatorLoginApi

        profile = CreatorDeviceProfile(cookies='', source='auth:qrcode')
        http_client = http_client or CreatorHttpClient(proxies=proxies)
        login = XHSCreatorLoginApi(
            profile=profile,
            proxies=proxies,
            http_client=http_client,
        )
        cookies = login.qrcode_login(show_in_terminal=show_in_terminal)
        if not cookies:
            login.close()
            raise RuntimeError('Creator QR login did not return an authenticated Cookie')
        return cls(
            cookies=cookies,
            login_source='qrcode',
            proxies=proxies,
            profile=login.profile,
            # 登录期间的会话级重试可能已重建传输实例，使用最终获胜会话。
            http_client=login.http,
            host_cookies=login.host_cookies_snapshot(),
            host_cookie_state=login.host_cookie_state(),
            cookie_source_url=CREATOR_PLATFORM_CONFIG.origin('api'),
            _factory_token=_AUTH_FACTORY_TOKEN,
        )

    @classmethod
    def from_phone_login(
        cls,
        *,
        proxies: Optional[dict] = None,
        http_client: Optional[CreatorHttpClient] = None,
    ) -> 'XHSCreatorAuth':
        """Run the pure-HTTP Creator SMS flow and return ready Auth."""
        from apis.xhs_creator_login_apis import XHSCreatorLoginApi

        profile = CreatorDeviceProfile(cookies='', source='auth:phone')
        http_client = http_client or CreatorHttpClient(proxies=proxies)
        login = XHSCreatorLoginApi(
            profile=profile,
            proxies=proxies,
            http_client=http_client,
        )
        cookies = login.phone_login()
        if not cookies:
            login.close()
            raise RuntimeError('Creator phone login did not return an authenticated Cookie')
        return cls(
            cookies=cookies,
            login_source='phone',
            proxies=proxies,
            profile=login.profile,
            http_client=login.http,
            host_cookies=login.host_cookies_snapshot(),
            host_cookie_state=login.host_cookie_state(),
            cookie_source_url=CREATOR_PLATFORM_CONFIG.origin('api'),
            _factory_token=_AUTH_FACTORY_TOKEN,
        )

    def _set_dsl(self, value: str) -> None:
        text = str(value or '')
        if ';' in text:
            dsllt, text = text.split(';', 1)
            if dsllt.isdigit():
                self.profile.session.dsllt = int(dsllt)
        self.dsl = text
        self.profile.dsl = text
        if text and text != 'undefined':
            self.profile.session.security_ready = True


__all__ = ['CREATOR_PARAMETER_SOURCES', 'XHSCreatorAuth']
