import json
import os
import random
import time
import tempfile
from typing import Optional

from loguru import logger

from xhs_utils.common_util import generate_a1, generate_web_id
from xhs_utils.relay import compute
from xhs_utils.http_util import REQUEST_TIMEOUT
from xhs_utils.xhs_core.auth import CREATOR_PLATFORM_CONFIG
from xhs_utils.xhs_core.cookies import HostCookieStore, url_host
from xhs_utils.xhs_creator.dsl import get_ds_bundle
from xhs_utils.xhs_creator.http import CreatorHttpClient
from xhs_utils.xhs_creator.params import (
    CREATOR_SEC_CH_UA,
    build_creator_login_headers,
    build_creator_navigation_headers,
    generate_profile_request_params,
    get_request_headers_template,
    splice_str,
)
from xhs_utils.xhs_creator.runtime import (
    generate_profile_data,
    generate_websectiga,
)
from xhs_utils.xhs_creator.state import (
    CreatorDeviceProfile,
    cookie_header,
)


CREATOR_LOGIN_ACCEPT_LANGUAGE = 'zh-CN,zh;q=0.9'
CREATOR_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/152.0.0.0 Safari/537.36'
)
_SECURITY_COOKIE_LENGTHS = {
    'websectiga': 64,
    'sec_poison_id': 36,
    'gid': 72,
}

# 安全初始化完成后，浏览器把 `loadts` Cookie 重建到**末尾**，其余字段保持各自的
# 创建/响应到达顺序（CDP 抓包实证）。两份真实样本：
#   verify-code: ets, webBuild, xsecappid, a1, webId, acw_tc, websectiga, sec_poison_id, gid, loadts
#   qr-code    : ets, webBuild, xsecappid, a1, webId, acw_tc, gid, websectiga, sec_poison_id, loadts
# 中段 gid 与 websectiga/sec_poison_id 的相对次序随会话响应竞速而变（非固定协议）；
# 唯一稳定不变的是「匿名前缀 + loadts 置于末尾」。因此这里只做最小变换：保持传入
# 顺序、仅把 loadts 移到最后。我们本地的到达顺序（seccallback 先、webprofile 后）
# 与浏览器 verify-code 样本逐字节一致。
# 2026-07-25 补充证据：1.19.3 浏览器两次抓包的 Cookie 顺序本身不稳定
# （loadts 一次在第 4 位、一次在倒数第 2 位），说明服务端并不校验字段次序；
# 保留此变换仅因为它是 2026-07-25 01:27 端到端登录成功时的已验证形态。


def _order_creator_login_cookies(cookies: dict) -> dict:
    """保持字段到达顺序，仅把 loadts 移到末尾，对齐浏览器 CAS 请求 Cookie。"""
    ordered = {name: value for name, value in cookies.items() if name != 'loadts'}
    if 'loadts' in cookies:
        ordered['loadts'] = cookies['loadts']
    return ordered

QR_STATUS_ERROR = 0
QR_STATUS_SUCCESS = 1
QR_STATUS_WAIT_SCAN = 2
QR_STATUS_WAIT_CONFIRM = 3
QR_STATUS_EXPIRED = 4
QR_STATUS_MESSAGES = {
    QR_STATUS_ERROR: '二维码状态异常',
    QR_STATUS_SUCCESS: '验证成功',
    QR_STATUS_WAIT_SCAN: '请扫描二维码',
    QR_STATUS_WAIT_CONFIRM: '请在手机上确认登录',
    QR_STATUS_EXPIRED: '二维码已过期',
}

# customer 域登录动作（qr-code / verify-code）的 HTTP 406 是按设备会话标记的
# 概率闸门（2026-07-25 实证）：被标记的会话重发全部 406，通过的会话持续稳定；
# 同请求重发无效，必须整包重建匿名设备会话。通过率随时间波动（实测 ~0%-50%），
# 16 次尝试在中等通过率（≥0.2）下累计成功率 >97%。
LOGIN_SESSION_MAX_ATTEMPTS = 16


class XHSCreatorLoginApi:
    """Creator QR/SMS HTTP login; computed security values come from OFB Relay."""

    def __init__(
        self,
        *,
        profile: Optional[CreatorDeviceProfile] = None,
        proxies: Optional[dict] = None,
        http_client: Optional[CreatorHttpClient] = None,
    ):
        self.platform_config = CREATOR_PLATFORM_CONFIG
        self.customer_url = self.platform_config.origin('login')
        self.creator_url = self.platform_config.origin('web')
        self.as_url = self.platform_config.origin('security')
        self.edith_url = self.platform_config.origin('captcha')
        self.profile = profile or CreatorDeviceProfile()
        self.proxies = proxies
        self.http = http_client or CreatorHttpClient(proxies=proxies)
        self._security_started = False
        self._security_bootstrapped = False
        self._security_completed = False
        self._pending_dsl = ''
        self._pending_ds_program = ''
        self._cookie_store = HostCookieStore()

    def close(self):
        self.http.close()

    def _reset_anonymous_session(self) -> None:
        """Rebuild the anonymous device session after a 406-flagged attempt.

        The 406 gate marks the whole device session, so the retry must start
        over with a fresh device profile (new a1/webId) and a fresh transport
        connection, not just resend the request.  Storage overrides from the
        original profile are carried over; the old http client is closed.
        """
        self.profile = CreatorDeviceProfile(
            cookies='',
            local_storage=dict(self.profile.local_storage),
            session_storage=dict(self.profile.session_storage),
            source=f'{self.profile.source}:retry',
        )
        self._cookie_store = HostCookieStore()
        self._security_started = False
        self._security_bootstrapped = False
        self._security_completed = False
        self._pending_dsl = ''
        self._pending_ds_program = ''
        self.http.close()
        self.http = CreatorHttpClient(proxies=self.proxies)

    def host_cookies_snapshot(self) -> dict:
        return self._cookie_store.snapshot()

    def host_cookie_state(self) -> dict:
        return self._cookie_store.export_state()

    def _cookies_for_url(self, url: str, cookies=None) -> dict:
        ordered = self._cookie_store.cookies_for_url(
            url,
            cookies if cookies is not None else self.profile.cookie_map,
        )
        # 仅 customer 域、且安全 Cookie 已就绪的 CAS 请求需要浏览器字段顺序；
        # 匿名早期请求（无 gid/websectiga）保持原顺序以匹配浏览器早期状态。
        if (
            url_host(url) == self.platform_config.host('login')
            and 'gid' in ordered
            and 'websectiga' in ordered
        ):
            return _order_creator_login_cookies(ordered)
        return ordered

    def _merge_response_cookies(self, response) -> dict:
        values = self.profile.cookie_map
        self._cookie_store.merge_response(values, response)
        self.profile.update_cookies(values)
        return self.profile.cookie_map

    def _signed(
        self,
        api: str,
        data='',
        method: str = 'POST',
        *,
        origin: Optional[str] = None,
        referer: Optional[str] = None,
        sec_fetch_site: str = 'same-site',
        include_trace_headers: bool = False,
        include_authorization: bool = True,
        include_origin: bool | None = None,
        tier: str | None = None,
        mns_profile: str | None = None,
        b1_profile: str | None = None,
        b1_value: str | None = None,
        dsl_pair_value: str | None = None,
    ) -> tuple[dict, dict, str]:
        headers, cookies, body = generate_profile_request_params(
            self.profile,
            api,
            data,
            method,
            origin=origin or self.creator_url,
            referer=referer or f'{self.creator_url}/',
            sec_fetch_site=sec_fetch_site,
            # 浏览器实证（2026-07-25 全量 XHR 抓包）：Chrome 只在导航请求里发
            # sec-ch-ua* 客户端提示头，任何 fetch/XHR 都不带。此前每条签名
            # 请求都带上了它们，是系统性的每请求指纹差异。
            include_client_hints=False,
            include_trace_headers=include_trace_headers,
            include_authorization=include_authorization,
            include_origin=include_origin,
            tier=tier,
            mns_profile=mns_profile,
            b1_profile=b1_profile,
            b1_value=b1_value,
            dsl_pair_value=dsl_pair_value,
        )
        # Fresh Creator login contexts advertise the short zh-CN language
        # profile. Logged-in note-manager pages use a longer preference list.
        headers['accept-language'] = CREATOR_LOGIN_ACCEPT_LANGUAGE
        return headers, cookies, body

    def _add_service_ratelimit_header(self, headers):
        headers['x-ratelimit-meta'] = f'host={self.platform_config.host("web")}'

    def _debug_dump(
        self,
        label,
        *,
        request_headers=None,
        request_body=None,
        response=None,
    ) -> None:
        """诊断用：设置环境变量 XHS_CREATOR_DEBUG=1 时打印请求/响应实况。

        默认关闭，不影响正常流程。用于抓取失败的 CAS 请求（Cookie 头、签名头、
        服务端返回码与原始 body），以便逐字节对比浏览器抓包。
        """
        if not os.environ.get('XHS_CREATOR_DEBUG'):
            return
        lines = [f'==== DEBUG {label} ====']
        if request_headers is not None:
            for key in (
                'x-ratelimit-meta', 'x-t', 'x-s', 'x-s-common',
                'origin', 'referer', 'cookie',
            ):
                if key in request_headers:
                    lines.append(f'  req {key}: {request_headers[key]}')
        if request_body is not None:
            lines.append(f'  req body: {request_body}')
        if response is not None:
            lines.append(f'  status: {response.status_code}')
            try:
                resp_cookies = dict(response.cookies)
            except Exception:
                resp_cookies = {}
            if resp_cookies:
                lines.append(f'  set-cookie keys: {list(resp_cookies)}')
            text = getattr(response, 'text', '') or ''
            lines.append(f'  resp body: {text[:800]}')
        logger.debug('\n'.join(lines))

    @staticmethod
    def _response_message(response, result: dict, default: str) -> str:
        message = result.get('msg') or result.get('message')
        if message:
            return str(message)
        code = result.get('code')
        if code is not None:
            return f'{default} (HTTP {response.status_code}, code={code})'
        return f'{default} (HTTP {response.status_code})'

    def generate_init_cookies(self, *, complete_security: bool = True) -> dict:
        # The browser loads the document before the login JS creates its
        # cross-subdomain Cookie fields. Host-only navigation Cookies such as
        # acw_tc must not be flattened into the shared Creator Cookie map.
        navigation_headers = build_creator_navigation_headers({
            'upgrade-insecure-requests': '1',
            'user-agent': CREATOR_USER_AGENT,
            'sec-ch-ua': CREATOR_SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'accept-language': CREATOR_LOGIN_ACCEPT_LANGUAGE,
            'priority': 'u=0, i',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
        })
        response = self.http.get(
            self.creator_url + '/login',
            headers=navigation_headers,
            proxies=self.proxies,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response)
        ts = int(time.time() * 1000)
        a1 = generate_a1('creator')
        web_id = generate_web_id('creator', a1)
        cookies = {
            'ets': str(ts),
            'webBuild': self.profile.release['webBuild'],
            'xsecappid': 'ugc',
            'loadts': str(ts + random.randint(50, 200)),
            'a1': a1,
            'webId': web_id,
        }
        self.profile.update_cookies(cookies)
        self._bootstrap_security()
        if complete_security:
            self._complete_security()
        return self.profile.cookie_map

    def bootstrap_publish_navigation(self, *, path: str = '/publish/publish?source=official'):
        """Load the authenticated Creator publish document once.

        A PC QR/SMS session carries the shared ``web_session``/``id_token``
        values, but Creator's publish document exchanges those values for a
        second set of HttpOnly cookies (``customer-sso-sid``,
        ``access-token-creator.xiaohongshu.com``, ``galaxy_creator_session_id``
        and related fields).  Browsers receive them during the cross-site
        navigation before the first Creator XHR; a pure API bridge must do the
        same request explicitly or the later permit endpoint is rejected with
        HTTP 406.

        The response body is intentionally ignored.  Only response cookies
        and host-scoped edge cookies are merged into the login profile.
        """
        navigation_headers = build_creator_navigation_headers({
            'upgrade-insecure-requests': '1',
            'user-agent': CREATOR_USER_AGENT,
            'sec-ch-ua': CREATOR_SEC_CH_UA,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'accept-language': CREATOR_LOGIN_ACCEPT_LANGUAGE,
            'priority': 'u=0, i',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'same-site',
            'sec-fetch-user': '?1',
        }, self._cookies_for_url(self.creator_url, self.profile.cookie_map))
        before_keys = set(self.profile.cookie_map)
        response = self.http.get(
            self.creator_url + str(path),
            headers=navigation_headers,
            proxies=self.proxies,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response)
        if os.environ.get('XHS_CREATOR_DEBUG'):
            after_keys = set(self.profile.cookie_map)
            logger.debug(
                'Creator publish navigation: http={} cookie_keys={} new_keys={}',
                getattr(response, 'status_code', None),
                sorted(after_keys),
                sorted(after_keys - before_keys),
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f'Creator publish navigation failed (HTTP {response.status_code})'
            )
        return self.profile.cookie_map

    def _fetch_honeypot(self) -> None:
        """Request the launcher's unsigned, best-effort honeypot program.

        The launcher evaluates the returned program and ignores evaluation
        errors, but does not consume an evaluation result.  Browser captures,
        byte-exact signer fixtures and server acceptance show no downstream
        signing dependency, so the pure client reproduces the request without
        executing the opaque program.
        """
        headers = get_request_headers_template(
            None,
            method='POST',
            include_client_hints=False,
            include_trace_headers=False,
            include_authorization=False,
            include_origin=True,
        )
        headers['accept-language'] = CREATOR_LOGIN_ACCEPT_LANGUAGE
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.as_url),
            kind='honeypot',
        )
        response = self.http.post(
            self.as_url + '/api/p/pj',
            headers=headers,
            data=b'{"callFrom":"ugc"}',
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response)

    def _bootstrap_security(self) -> None:
        """Start the browser's MNS0201/nop bootstrap.

        Chrome 152 keeps the first security batch on ``mns0201/nop``.  The
        batch is deliberately split across :meth:`_finish_security_bootstrap`
        so the request order remains redcaptcha -> scripting -> sbtsource;
        only after that batch does the page switch to ``mns0101/a1``.
        """
        if self._security_started:
            return

        self._fetch_honeypot()

        self._security_started = True

    def _bootstrap_dsl_program(self) -> None:
        """Fetch the server DS program while still on the 0201/nop tier."""
        if self._pending_dsl and self._pending_ds_program:
            return

        ds_body = {
            'callFrom': 'creator-platform',
            'callback': '',
            'type': 'ds',
            'appId': 'ugc',
        }
        headers, cookies, body = self._signed(
            '/api/sec/v1/scripting', ds_body, 'POST',
            tier='0201',
            mns_profile=None,
            b1_profile='login',
            dsl_pair_value=(
                f'{self.profile.session.loadts};undefined'
            ),
        )
        headers['content-type'] = 'application/json'
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='security',
        )
        ds_response = self.http.post(
            self.as_url + '/api/sec/v1/scripting',
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(ds_response)

        dsl = ''
        ds_code = ''
        try:
            ds_json = ds_response.json()
            ds_code = str(((ds_json.get('data') or {}).get('data')) or '')
            if ds_code:
                dsl = str(compute('creator', 'ds-anchor', {'script': ds_code})['value'])
        except (ValueError, AttributeError):
            pass
        if not dsl or not ds_code:
            fallback_dsl, fallback_program = get_ds_bundle(
                proxies=self.proxies,
                http_client=self.http,
            )
            if not dsl:
                dsl = fallback_dsl
            if not ds_code:
                ds_code = fallback_program
        self._pending_dsl = dsl
        self._pending_ds_program = ds_code

    def _activate_security(self) -> None:
        """在进入 mns0101/a1 阶段前安装服务端 DS 程序（对齐浏览器时序）。"""
        # A PC -> Creator bridge can start with shared ``gid``/``websectiga``
        # cookies.  ``CreatorDeviceProfile.update_cookies`` quite correctly
        # marks that session as authenticated, but those cookies do not mean
        # that Creator's own server-issued DS program has been installed.
        # Only skip activation when both the ready flag and the actual DS
        # material are present; otherwise the first 0101 request would omit
        # ``dsProgram`` and fail the exact ``_dsf`` signer gate.
        if (
            self.profile.session.security_ready
            and self.profile.dsl
            and self.profile.ds_program
        ):
            return
        if not self._pending_dsl or not self._pending_ds_program:
            dsl, program = get_ds_bundle(
                proxies=self.proxies,
                http_client=self.http,
            )
            self._pending_dsl = self._pending_dsl or dsl
            self._pending_ds_program = self._pending_ds_program or program
        self.profile.activate_security(
            self._pending_dsl,
            ds_program=self._pending_ds_program,
            timestamp_ms=int(time.time() * 1000),
        )

    def _finish_security_bootstrap(self, *, activate: bool = True) -> None:
        """Run the browser's 0201 security batch, then install DS material."""
        if self._security_bootstrapped:
            return
        if not self._security_started:
            self._bootstrap_security()

        # On Chrome 152 redcaptcha is the first signed request and still uses
        # mns0201/nop.  Its X-S-Common already contains the generated page b1;
        # only the DSL half is unavailable at this point.
        headers, cookies, body = self._signed(
            '/api/redcaptcha/v2/getconfig', {}, 'POST',
            include_trace_headers=True,
            include_authorization=False,
            tier='0201',
            mns_profile=None,
            b1_profile='login',
            dsl_pair_value=(
                f'{self.profile.session.loadts};undefined'
            ),
        )
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.edith_url, cookies),
            kind='redcaptcha',
        )
        response = self._send_with_gate_retry(
            lambda: self.http.post(
                self.edith_url + '/api/redcaptcha/v2/getconfig',
                headers=headers,
                data=body.encode('utf-8'),
                proxies=self.proxies,
                timeout=REQUEST_TIMEOUT,
            ),
            label='redcaptcha',
        )
        self._merge_response_cookies(response)

        # The platform script is fetched after redcaptcha and held in memory
        # for the Relay calculation used by the next request.
        self._bootstrap_dsl_program()

        sbt_body = {'callFrom': 'creator-platform', 'appId': 'ugc'}
        headers, cookies, body = self._signed(
            '/api/sec/v1/sbtsource', sbt_body, 'POST',
            tier='0201',
            mns_profile=None,
            b1_profile='login',
            dsl_pair_value=(
                f'{self.profile.session.loadts};undefined'
            ),
        )
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='security',
        )
        sbt_response = self._send_with_gate_retry(
            lambda: self.http.post(
                self.as_url + '/api/sec/v1/sbtsource',
                headers=headers,
                data=body.encode('utf-8'),
                proxies=self.proxies,
                timeout=REQUEST_TIMEOUT,
            ),
            label='sbtsource',
        )
        self._merge_response_cookies(sbt_response)
        self._security_bootstrapped = True
        # A logged-in publish navigation emits one final user/info request on
        # 0201/nop before switching to 0101/a1.  QR/phone flows have no such
        # shared-session request and can activate immediately.
        if activate:
            self._activate_security()

    def _complete_security(self) -> None:
        """Run the DS-ready seccallback and webprofile phase once."""
        if self._security_completed:
            return
        if not self._security_started:
            self._bootstrap_security()
        if not self._security_bootstrapped:
            self._finish_security_bootstrap()
        # DS 已在 bootstrap 响应后安装；seccallback/webprofile 分别使用
        # login_callback 与 login_ready 的 0101/a1 档位。
        self._activate_security()
        if not self.profile.session.security_ready:
            raise RuntimeError('Creator DS program was not activated after bootstrap')
        self._fetch_websectiga()
        self._require_security_cookies(('websectiga', 'sec_poison_id'))
        self._fetch_gid()
        self._require_security_cookies()
        self._security_completed = True

    def _require_security_cookies(self, names=None) -> None:
        """Reject an incomplete security bootstrap before any CAS login call."""
        values = self.profile.cookie_map
        required = tuple(names or _SECURITY_COOKIE_LENGTHS)
        invalid = []
        for name in required:
            value = str(values.get(name) or '')
            expected = _SECURITY_COOKIE_LENGTHS[name]
            if len(value) != expected:
                invalid.append(f'{name}(length={len(value)}, expected={expected})')
        if invalid:
            raise RuntimeError(
                'Creator security bootstrap incomplete: ' + ', '.join(invalid)
            )

    def _fetch_websectiga(self) -> str:
        api = '/api/sec/v1/scripting'
        data = {'callFrom': 'creator-platform', 'callback': 'seccallback'}
        headers, cookies, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_callback',
            b1_profile='login',
        )
        headers['content-type'] = 'application/json'
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='security',
        )
        response = self.http.post(
            self.as_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        values = self._merge_response_cookies(response)
        try:
            result = response.json()
        except ValueError as error:
            raise RuntimeError(
                f'Creator scripting response is not JSON (HTTP {response.status_code})'
            ) from error
        data_obj = result.get('data') or {}
        sec_poison_id = data_obj.get('secPoisonId') or data_obj.get('sec_poison_id')
        if not sec_poison_id:
            raise RuntimeError('Creator scripting response missing sec_poison_id')
        code = str(data_obj.get('data') or '')
        if not code:
            raise RuntimeError('Creator scripting response missing JSVMP program')
        try:
            websectiga = generate_websectiga(
                code,
                profile={
                    'userAgent': CREATOR_USER_AGENT,
                    'platform': 'Win32',
                    'pageUrl': self.creator_url + '/login',
                },
            )
        except Exception as error:
            raise RuntimeError(
                f'Creator security calculation failed: {error}'
            ) from error
        self.profile.update_cookies({
            'websectiga': websectiga,
            'sec_poison_id': str(sec_poison_id),
        })
        return websectiga

    def _fetch_gid(self) -> Optional[str]:
        # A same-site navigation from the already logged-in PC page carries a
        # valid shared gid.  Chrome skips the webprofile POST in that case;
        # preserve that behavior instead of issuing a redundant profile
        # report from the Creator bridge.
        existing = str(self.profile.cookie_map.get('gid') or '')
        if len(existing) == _SECURITY_COOKIE_LENGTHS['gid']:
            return existing
        api = '/api/sec/v1/shield/webprofile'
        profile_data = generate_profile_data(
            self.profile.profile_data_options(
                location=self.creator_url + '/login',
                referer=self.creator_url + '/login',
            )
        )
        data = {
            'platform': 'Windows',
            'sdkVersion': self.profile.release['webProfileSdkVersion'],
            'svn': '2',
            'profileData': profile_data,
        }
        headers, cookies, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_ready',
            b1_profile='login',
        )
        headers['content-type'] = 'application/json'
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='security',
        )
        response = self.http.post(
            self.as_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        values = self._merge_response_cookies(response)
        gid = values.get('gid')
        if gid:
            self.profile.session.profile_count += 1
        return gid

    def generate_qrcode(self, cookies=None, old_qr_id=None):
        if cookies:
            self.profile.update_cookies(cookies)
        self._require_security_cookies()
        api = '/api/cas/customer/web/qr-code'
        data = {'service': self.creator_url}
        if old_qr_id:
            data['old_qr_id'] = str(old_qr_id)
        headers, cookie_map, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_ready',
            b1_profile='login',
        )
        headers['content-type'] = 'application/json'
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-post-no-rate',
        )
        response = self.http.post(
            self.customer_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._debug_dump(
            'qr-code (POST, 0101/a1)',
            request_headers=headers,
            request_body=body,
            response=response,
        )
        values = self._merge_response_cookies(response)
        result = response.json()
        if not result.get('success'):
            return False, self._response_message(response, result, '获取二维码失败'), None
        data_obj = result.get('data') or {}
        if not all(key in data_obj for key in ('id', 'url')):
            return False, result.get('msg', '二维码响应缺少必要字段'), {
                'cookies': values,
                'res_json': result,
            }
        return True, '成功', {
            'cookies': values,
            'qr_id': data_obj['id'],
            'qr_url': data_obj['url'],
            'support_channels': data_obj.get('support_qr_code_channel_infos', []),
        }

    def _build_zone_request(self, cookies=None):
        if cookies:
            self.profile.update_cookies(cookies)
        api = splice_str('/api/cas/customer/web/zones', {
            'service': self.creator_url,
        })
        headers, cookie_map, _ = self._signed(
            api,
            '',
            'GET',
            include_origin=True,
            tier='0101',
            mns_profile='login_early',
            b1_profile='login',
        )
        self._add_service_ratelimit_header(headers)
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-get',
        )
        return api, headers

    def _send_with_gate_retry(self, send_once, *, attempts=5, label=''):
        """406 概率闸门的请求级重试：同会话换新签名重发。

        2026-07-25 实证：customer 域对 0101 档的 406 是按请求概率的
        （tgt@0101 同会话第 4 发即 200），不是会话级标记——因此同会话
        重发有效，无需重建设备。
        """
        response = None
        for attempt in range(1, attempts + 1):
            response = send_once()
            if response.status_code != 406:
                return response
            logger.debug(f'{label} 406 概率拒绝，同会话重发 ({attempt}/{attempts})')
        return response

    def _send_zone_request(self, prepared):
        api, headers = prepared
        response = self._send_with_gate_retry(
            lambda: self.http.get(
                self.customer_url + api,
                headers=headers,
                proxies=self.proxies,
                timeout=REQUEST_TIMEOUT,
            ),
            label='zones',
        )
        self._debug_dump('zones (GET, 0101/a1)', request_headers=headers, response=response)
        values = self._merge_response_cookies(response)
        result = response.json()
        return result.get('success', False), result.get('data') or [], values

    def get_zone_list(self, cookies=None):
        """Load the domestic SMS zone list, as the login component does."""
        return self._send_zone_request(self._build_zone_request(cookies))

    def _build_session_request(self, cookies=None):
        if cookies:
            self.profile.update_cookies(cookies)
        api = '/api/cas/customer/web/service-ticket'
        data = {'service': self.creator_url, 'source': '', 'type': 'tgt'}
        headers, cookie_map, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_early',
            b1_profile='login',
        )
        self._add_service_ratelimit_header(headers)
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-post',
        )
        return api, headers, body

    def _send_session_request(self, prepared) -> dict:
        api, headers, body = prepared
        response = self._send_with_gate_retry(
            lambda: self.http.post(
                self.customer_url + api,
                headers=headers,
                data=body.encode('utf-8'),
                proxies=self.proxies,
                timeout=REQUEST_TIMEOUT,
            ),
            label='service-ticket',
        )
        self._debug_dump(
            'service-ticket type=tgt (POST, 0101/a1)',
            request_headers=headers,
            request_body=body,
            response=response,
        )
        values = self._merge_response_cookies(response)
        result = response.json()
        data_obj = result.get('data') or {}
        ticket = str(data_obj.get('ticket') or '')
        login_type = str(data_obj.get('type') or '')
        return {
            'active': bool(ticket or login_type == 'at'),
            'ticket': ticket,
            'type': login_type,
            'cookies': values,
            'res_json': result,
        }

    def query_session(self, cookies=None) -> dict:
        """Run the browser's automatic ``type=tgt`` session probe."""
        return self._send_session_request(
            self._build_session_request(cookies)
        )

    def check_session(self, cookies=None):
        detail = self.query_session(cookies)
        return detail['active'], detail['cookies']

    def query_qrcode_status(self, qr_id, cookies=None) -> dict:
        """Return the complete CAS QR state without discarding ticket metadata."""
        if cookies:
            self.profile.update_cookies(cookies)
        api = '/api/cas/customer/web/qr-code'
        signed_api = splice_str(api, {
            'service': self.creator_url,
            'qr_code_id': qr_id,
            'source': '',
        })
        headers, cookie_map, _ = self._signed(
            signed_api,
            '',
            'GET',
            include_origin=True,
            tier='0101',
            mns_profile='login_ready',
            b1_profile='login',
        )
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-get-no-rate',
        )
        response = self.http.get(
            self.customer_url + signed_api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        values = self._merge_response_cookies(response)
        result = response.json()
        data_obj = result.get('data') or {}
        status = data_obj.get('status')
        message = QR_STATUS_MESSAGES.get(status, f'未知状态: {status}')
        if status is None:
            message = self._response_message(
                response,
                result,
                '二维码状态响应缺少 status',
            )
        return {
            'success': bool(result.get('success') and status == QR_STATUS_SUCCESS),
            'message': message,
            'status': status,
            'ticket': str(data_obj.get('ticket') or ''),
            'type': str(data_obj.get('type') or ''),
            'avatar': str(data_obj.get('avatar') or ''),
            'cookies': values,
            'res_json': result,
        }

    def check_qrcode_status(self, qr_id, cookies=None):
        detail = self.query_qrcode_status(qr_id, cookies)
        return detail['success'], detail['message'], detail['cookies']

    def get_user_info(
        self,
        cookies=None,
        *,
        mns_profile='login_ready',
        b1_profile='login',
        b1_value=None,
        tier='0101',
        dsl_pair_value=None,
        referer=None,
    ):
        if cookies:
            self.profile.update_cookies(cookies)
        api = '/api/galaxy/user/info'
        headers, cookie_map, _ = self._signed(
            api,
            '',
            'GET',
            referer=referer or (self.creator_url + '/login'),
            sec_fetch_site='same-origin',
            include_trace_headers=True,
            include_origin=False,
            tier=tier,
            mns_profile=mns_profile,
            b1_profile=b1_profile,
            b1_value=b1_value,
            dsl_pair_value=dsl_pair_value,
        )
        headers['content-type'] = 'application/json;charset=UTF-8'
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.creator_url, cookie_map),
            kind='login-user-info',
        )
        response = self.http.get(
            self.creator_url + api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        values = self._merge_response_cookies(response)
        result = response.json()
        return result.get('success', False), result.get('data') or {}, values

    def send_phone_code(self, phone, cookies=None, zone='86'):
        if cookies:
            self.profile.update_cookies(cookies)
        self._require_security_cookies()
        api = '/api/cas/customer/web/verify-code'
        # BeerLogin serializes this object in insertion order. The compact body
        # is also the signer input, so retain the browser's service/phone/zone
        # order instead of treating JSON object order as cosmetic.
        data = {'service': self.creator_url, 'phone': phone, 'zone': zone}
        headers, cookie_map, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_ready',
            b1_profile='login',
        )
        headers['content-type'] = 'application/json'
        self._add_service_ratelimit_header(headers)
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-post',
        )
        response = self.http.post(
            self.customer_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._debug_dump(
            'verify-code (POST, 0101/a1)',
            request_headers=headers,
            request_body=body,
            response=response,
        )
        self._merge_response_cookies(response)
        result = response.json()
        success = bool(result.get('success'))
        message = result.get('msg') or result.get('message')
        if not message:
            message = (
                '成功'
                if success
                else self._response_message(response, result, '发送验证码失败')
            )
        return (
            success,
            str(message),
            result,
        )

    def login_by_phone(self, phone, code, cookies=None, zone='86'):
        if cookies:
            self.profile.update_cookies(cookies)
        self._require_security_cookies()
        api = '/api/cas/customer/web/service-ticket'
        data = {
            'zone': zone,
            'phone': phone,
            'verify_code': code,
            'service': self.creator_url,
            'source': '',
            'type': 'phoneVerifyCode',
        }
        headers, cookie_map, body = self._signed(
            api,
            data,
            'POST',
            tier='0101',
            mns_profile='login_ready',
            b1_profile='login',
        )
        headers['content-type'] = 'application/json'
        self._add_service_ratelimit_header(headers)
        headers = build_creator_login_headers(
            headers,
            self._cookies_for_url(self.customer_url, cookie_map),
            kind='cas-post',
        )
        response = self.http.post(
            self.customer_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        values = self._merge_response_cookies(response)
        result = response.json()
        success = bool(result.get('success'))
        message = result.get('msg') or result.get('message')
        if not message:
            message = (
                '成功'
                if success
                else self._response_message(response, result, '手机号登录失败')
            )
        return success, str(message), {
            'cookies': values,
            'res_json': result,
        }

    @staticmethod
    def cookies_to_str(cookies):
        return cookie_header(cookies)

    def _prepare_login_session(self) -> tuple[dict, dict]:
        """Initialize the Creator HTTP login session."""

        cookies = self.generate_init_cookies(complete_security=False)
        # Chrome 152 在 CAS 请求前先完成 redcaptcha + sbtsource。
        self._finish_security_bootstrap()
        # 随后做 zones + type=tgt（同为 0101/a1 login_early）。
        # 先并发构建两条请求再发送，复现浏览器并发启动，并避免 zones 的边缘
        # acw_tc 泄漏进紧随其后的 type=tgt。
        zone_request = self._build_zone_request(cookies)
        session_request = self._build_session_request(cookies)
        try:
            self._send_zone_request(zone_request)
        except Exception as error:
            # The browser falls back to its built-in zone list.
            logger.debug(f'Creator 区号列表加载失败，继续使用默认区号: {error}')
        session = self._send_session_request(session_request)
        return self.profile.cookie_map, session

    def _accept_session(self, cookies=None):
        """Require the same Creator user-info acceptance used by the page."""
        success, user_info, values = self.get_user_info(cookies)
        if not success:
            logger.error('Creator 用户信息验收失败，不能判定为登录成功')
            return None
        logger.info(
            f'用户: {user_info.get("userName", "未知")} '
            f'(RedID: {user_info.get("redId", "未知")})'
        )
        logger.success('Creator 登录成功，Cookie 已通过返回值交给调用方')
        return self.cookies_to_str(
            self._cookies_for_url(self.creator_url, values)
        )

    @staticmethod
    def show_qrcode_terminal(url):
        import qrcode

        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        image_path = os.environ.get('XHS_CREATOR_QR_IMAGE')
        if image_path:
            image_path = os.path.expanduser(image_path)
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            image_qr = qrcode.QRCode(box_size=10, border=4)
            image_qr.add_data(url)
            image_qr.make(fit=True)
            handle = tempfile.NamedTemporaryFile(
                'wb', dir=os.path.dirname(image_path),
                prefix='.xhs-creator-qr-', delete=False,
            )
            try:
                os.chmod(handle.name, 0o600)
                with handle:
                    image_qr.make_image(fill_color='black', back_color='white').save(handle, format='PNG')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(handle.name, image_path)
            finally:
                if os.path.exists(handle.name):
                    os.unlink(handle.name)
            print(f'Creator 二维码图片：{image_path}', flush=True)
        qr.print_ascii(invert=True)

    @staticmethod
    def show_qrcode_image(url):
        import qrcode

        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        qr.make_image(fill_color='black', back_color='white').show()

    def qrcode_login(self, show_in_terminal=True):
        qr_data = None
        cookies = None
        for attempt in range(1, LOGIN_SESSION_MAX_ATTEMPTS + 1):
            logger.info('[1/5] 正在初始化 Creator 匿名设备...')
            cookies, session = self._prepare_login_session()
            logger.debug(f'初始 Cookie 字段: {list(cookies)}')

            logger.info('[2/5] 正在检查已有 Creator 会话...')
            if session['active']:
                logger.info('检测到可复用的 Creator 会话，跳过二维码')
                accepted = self._accept_session(cookies)
                self._complete_security()
                if not accepted:
                    return None
                return self.cookies_to_str(
                    self._cookies_for_url(self.creator_url)
                )

            self._complete_security()
            cookies = self.profile.cookie_map
            logger.info('[3/5] 正在获取二维码...')
            success, message, qr_data = self.generate_qrcode(cookies)
            if success:
                break
            # 406 是按设备会话标记的概率闸门：同会话重发无效，整包重建后再试
            logger.warning(
                f'当前设备会话被边缘拒绝（{message}），'
                f'重建匿名设备重试 ({attempt}/{LOGIN_SESSION_MAX_ATTEMPTS})'
            )
            self._reset_anonymous_session()
        else:
            logger.error(f'获取二维码失败: {message}')
            return None
        logger.info('请使用小红书APP扫描以下二维码:')
        if show_in_terminal:
            self.show_qrcode_terminal(qr_data['qr_url'])
        else:
            self.show_qrcode_image(qr_data['qr_url'])

        logger.info('[4/5] 等待扫码和手机确认...')
        last_status = None
        while True:
            # Production BeerLogin schedules the first and subsequent polls
            # one second after the previous poll completes.
            time.sleep(1)
            detail = self.query_qrcode_status(qr_data['qr_id'])
            status = detail['status']
            if status != last_status:
                logger.info(detail['message'])
                last_status = status
            if detail['success']:
                break
            if status in {QR_STATUS_ERROR, QR_STATUS_EXPIRED, None}:
                logger.error(detail['message'])
                return None
            if status not in {QR_STATUS_WAIT_SCAN, QR_STATUS_WAIT_CONFIRM}:
                logger.error(detail['message'])
                return None

        logger.info('[5/5] 验证正式 Creator 会话...')
        return self._accept_session(detail['cookies'])

    def phone_login(self):
        result = None
        for attempt in range(1, LOGIN_SESSION_MAX_ATTEMPTS + 1):
            logger.info('[1/5] 正在初始化 Creator 匿名设备...')
            cookies, session = self._prepare_login_session()
            logger.debug(f'初始 Cookie 字段: {list(cookies)}')

            logger.info('[2/5] 正在检查已有 Creator 会话...')
            if session['active']:
                logger.info('检测到可复用的 Creator 会话，跳过短信验证')
                accepted = self._accept_session(cookies)
                self._complete_security()
                if not accepted:
                    return None
                return self.cookies_to_str(
                    self._cookies_for_url(self.creator_url)
                )

            self._complete_security()
            cookies = self.profile.cookie_map
            if attempt == 1:
                phone = input('请输入手机号: ')
            logger.info('[3/5] 正在发送验证码...')
            success, message, result = self.send_phone_code(phone, cookies)
            if success:
                break
            # 与 qr-code 相同的按会话概率闸门：整包重建后再发
            logger.warning(
                f'当前设备会话被边缘拒绝（{message}），'
                f'重建匿名设备重试 ({attempt}/{LOGIN_SESSION_MAX_ATTEMPTS})'
            )
            self._reset_anonymous_session()
        else:
            logger.error(f'发送失败: {message}')
            return None
        logger.info('验证码已发送')

        code = input('请输入验证码: ')
        logger.info('[4/5] 正在验证...')
        success, message, result = self.login_by_phone(phone, code)
        if not success:
            logger.error(f'验证失败: {message}')
            return None

        logger.info('[5/5] 验证正式 Creator 会话...')
        return self._accept_session(result['cookies'])


__all__ = ['XHSCreatorLoginApi']
