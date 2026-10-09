import json
import random
import time

from loguru import logger

from xhs_utils.http_util import REQUEST_TIMEOUT
from xhs_utils.relay import compute
from xhs_utils.xhs_core.auth import PC_PLATFORM_CONFIG
from xhs_utils.xhs_core.cookies import HostCookieStore
from xhs_utils.xhs_pc.dsl import get_dsl
from xhs_utils.xhs_pc.http import PcHttpClient
from xhs_utils.xhs_pc.params import (
    PC_LOGIN_ACCEPT_LANGUAGE,
    PC_SEC_CH_UA,
    build_pc_login_headers,
    build_pc_navigation_headers,
    generate_request_params,
    get_common_headers,
    splice_str,
)
from xhs_utils.xhs_pc.runtime import (
    accept_web_ssk,
    create_web_ssk_handshake,
    generate_profile_data,
    generate_websectiga,
)
from xhs_utils.xhs_pc.state import (
    PcDeviceProfile,
    REFERENCE_PROFILE,
    cookie_header,
    initial_pc_cookies,
)
from xhs_utils.common_util import generate_a1, generate_web_id


class XHSLoginApi:
    """Pure-HTTP PC login client.

    Platform requests stay in this process; computed security values come from
    OFB Relay. Login requires the user to scan the returned QR code or enter an
    SMS verification code. Network requests use a reusable curl_cffi session.
    """

    def __init__(
        self,
        proxies=None,
        *,
        b1='',
        dsl='',
        local_storage=None,
        session_storage=None,
        b1_state=None,
        web_build='',
        mns_env=None,
        rap_fingerprint_hex='',
        web_profile_fields=None,
        web_profile_i12_seed=None,
        web_profile_fi=None,
        http_client=None,
    ):
        self.platform_config = PC_PLATFORM_CONFIG
        self.base_url = self.platform_config.origin('api')
        self.as_url = self.platform_config.origin('security')
        self.web_url = self.platform_config.origin('web')
        self.sem_url = self.platform_config.origin('sem')
        self.home_url = self.platform_config.origin('web') + '/explore'
        self.profile = None
        self.proxies = proxies
        self.http = http_client or PcHttpClient(proxies=proxies)
        self.fixed_b1 = str(b1 or '')
        self.dsl = str(dsl or '')
        self.local_storage = dict(local_storage or {})
        self.session_storage = dict(session_storage or {})
        self.b1_state = b1_state
        self.web_build = str(web_build or '')
        self.mns_env = dict(mns_env or {})
        self.rap_fingerprint_hex = str(rap_fingerprint_hex or '')
        self.profile_data = ''
        self._webprofile_reported = False
        self._login_b1 = ''
        self.web_profile_fields = dict(web_profile_fields or {})
        self.web_profile_i12_seed = web_profile_i12_seed
        self.web_profile_fi = web_profile_fi
        self._cookie_store = HostCookieStore()

    def close(self):
        self.http.close()

    def _new_profile(self, cookies):
        profile = PcDeviceProfile(
            cookies=cookies,
            local_storage=self.local_storage,
            session_storage=self.session_storage,
            fixed_b1=self.fixed_b1,
            web_build=self.web_build,
            b1_state=self.b1_state,
            rap_fingerprint_hex=self.rap_fingerprint_hex,
            web_profile_fields=self.web_profile_fields,
            web_profile_i12_seed=self.web_profile_i12_seed,
            web_profile_fi=self.web_profile_fi,
            source='pc-login',
        )
        for tier, material in self.mns_env.items():
            profile.set_mns_stage(
                str(tier),
                env_const=int(material['envConst']),
                env_fp_tail=material.get('envFpTailHex', material.get('envFpTail')),
                evidence=str(material.get('evidence') or 'XHSLoginApi override'),
            )
        return profile

    @staticmethod
    def _get_sec_headers(sign_context=None, *, method='POST'):
        context = sign_context or {}
        headers = {
            'sec-ch-ua-platform': '"Windows"',
            'referer': 'https://www.xiaohongshu.com/',
            'sec-ch-ua': context.get('secChUa', PC_SEC_CH_UA),
            'sec-ch-ua-mobile': '?0',
            'user-agent': context.get('userAgent', REFERENCE_PROFILE['release']['userAgent']),
            'accept': 'application/json, text/plain, */*',
            'accept-language': PC_LOGIN_ACCEPT_LANGUAGE,
            'origin': 'https://www.xiaohongshu.com',
            'priority': 'u=1, i',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        }
        if str(method).upper() != 'GET':
            headers['content-type'] = 'application/json;charset=UTF-8'
        return headers

    def host_cookies_snapshot(self):
        return self._cookie_store.snapshot()

    def host_cookie_state(self):
        return self._cookie_store.export_state()

    def _cookies_for_url(self, url, cookies=None):
        return self._cookie_store.cookies_for_url(
            url,
            cookies if cookies is not None else self.profile.cookie_map,
        )

    def _ensure_profile(self, cookies):
        if self.profile is None:
            self.profile = self._new_profile(cookies)
        else:
            self.profile.update_cookies(cookies)
        return self.profile

    def _signed_request_params(
        self,
        cookies,
        api,
        data='',
        method='POST',
        sec_domain=False,
        tier=None,
        include_trace_headers=True,
        include_b1=None,
        mns_profile=None,
    ):
        """用同一 PcDeviceProfile 为登录全链生成 MNS/X-S-Common。

        当前浏览器在 webprofile collector 启动前仍发送 X-S-Common，但
        ``x8`` 是空字符串。webprofile 请求首次生成并缓存登录页 b1，后续
        验证码/二维码请求复用该值。
        """
        profile = self._ensure_profile(cookies)
        sign_context = profile.next_sign_context(
            api,
            tier=tier,
            mns_profile=mns_profile,
        )
        if include_b1 is None:
            include_b1 = bool(self._login_b1 or self._webprofile_reported)
        if include_b1 and not self._login_b1:
            self._login_b1 = profile.current_b1(
                sign_context['now'], profile_name='login'
            )
        b1 = self._login_b1 if include_b1 else ''
        if not self.dsl:
            self.dsl = get_dsl(
                proxies=self.proxies,
                http_client=self.http,
            )
        if profile.session.last_tiga_update_time:
            dsl_pair = profile.dsl_pair(
                self.dsl, timestamp_ms=sign_context['now']
            )
        else:
            # Browser cold chain: _dsl is available, while dsllt remains null
            # until seccallback has installed the current tiga program.
            dsl_pair = f'null;{self.dsl}'
        headers, _, body = generate_request_params(
            cookie_header(cookies), api, data, method,
            b1=b1,
            dsl_pair=dsl_pair,
            doc_cookie=profile.document_cookie,
            tier=sign_context['tier'],
            sign_context=sign_context,
        )
        headers['accept-language'] = PC_LOGIN_ACCEPT_LANGUAGE
        if sec_domain:
            names = ['x-s', 'x-t', 'x-s-common']
            if include_trace_headers:
                names.extend(['x-b3-traceid', 'x-xray-traceid'])
            signed_headers = {key: headers[key] for key in names}
            headers = self._get_sec_headers(sign_context, method=method)
            headers.update(signed_headers)
        return headers, body

    def _merge_response_cookies(self, cookies, response, *, append_shared=()):
        self._cookie_store.merge_response(
            cookies,
            response,
            append_shared=append_shared,
        )
        self._ensure_profile(cookies)

    def _post_scripting(self, cookies, payload, tier, *, mns_profile=None):
        api = '/api/sec/v1/scripting'
        headers, data_str = self._signed_request_params(
            cookies,
            api,
            payload,
            sec_domain=True,
            tier=tier,
            mns_profile=mns_profile,
            include_trace_headers=False,
        )
        wire_cookies = self._cookies_for_url(self.as_url, cookies)
        headers = build_pc_login_headers(
            headers,
            wire_cookies,
            kind='security',
        )
        resp = self.http.post(
            self.as_url + api,
            headers=headers,
            data=data_str.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, resp)
        res = resp.json()
        if not resp.ok or not res.get('success'):
            raise RuntimeError(res.get('msg') or f'scripting HTTP {resp.status_code}')
        return res

    def _fetch_honeypot(self, cookies):
        api = '/api/p/pj'
        headers = {
            'sec-ch-ua-platform': '"Windows"',
            'referer': self.web_url + '/',
            'user-agent': REFERENCE_PROFILE['release']['userAgent'],
            'accept': 'application/json, text/plain, */*',
            'sec-ch-ua': REFERENCE_PROFILE['release']['secChUa'],
            'content-type': 'application/json;charset=UTF-8',
            'sec-ch-ua-mobile': '?0',
            'accept-language': PC_LOGIN_ACCEPT_LANGUAGE,
            'origin': self.web_url,
            'priority': 'u=1, i',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        }
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='honeypot',
        )
        response = self.http.post(
            self.as_url + api,
            headers=headers,
            data=b'{"callFrom":"xhs-pc-web"}',
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, response)

    def _fetch_redcaptcha(self, cookies):
        api = '/api/redcaptcha/v2/getconfig'
        headers, body = self._signed_request_params(
            cookies,
            api,
            {},
            sec_domain=True,
            tier='0201',
            mns_profile='security_initial',
            include_trace_headers=True,
        )
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='post',
        )
        response = self.http.post(
            self.base_url + api,
            headers=headers,
            data=body.encode('utf-8'),
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, response)

    def _fetch_sem_sdk(self, cookies):
        api = '/data/sem_sdk'
        headers, _ = self._signed_request_params(
            cookies,
            api,
            '',
            method='GET',
            sec_domain=True,
            tier='0201',
            mns_profile='security_initial',
            include_trace_headers=False,
        )
        headers = build_pc_login_headers(headers, None, kind='sem')
        response = self.http.get(
            self.sem_url + api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, response)

    def _fetch_sbtsource(self, cookies):
        api = '/api/sec/v1/sbtsource'
        payload = {'callFrom': 'web', 'appId': 'xhs-pc-web'}
        headers, body = self._signed_request_params(
            cookies,
            api,
            payload,
            sec_domain=True,
            tier='0201',
            mns_profile='security_initial',
            include_trace_headers=False,
        )
        headers = build_pc_login_headers(
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
        self._merge_response_cookies(cookies, response)

    def _initialize_security(self, cookies):
        """Run the two cold-start security programs in browser order."""
        if not self.dsl:
            self.dsl = get_dsl(
                proxies=self.proxies,
                http_client=self.http,
            )

        self._fetch_honeypot(cookies)
        self._fetch_redcaptcha(cookies)
        self._fetch_sem_sdk(cookies)

        ds_res = self._post_scripting(
            cookies,
            {"callFrom": "web", "callback": "", "type": "ds", "appId": "xhs-pc-web"},
            tier='0201',
            mns_profile='security_initial',
        )
        ds_code = str(((ds_res.get('data') or {}).get('data')) or '')
        if not ds_code:
            raise RuntimeError('DS scripting response is empty')
        self.dsl = str(compute('pc', 'ds-anchor', {'script': ds_code})['value'])

        self._fetch_sbtsource(cookies)

        sec_res = self._post_scripting(
            cookies,
            {"callFrom": "web", "callback": "seccallback"},
            tier='0101',
            mns_profile='security_callback',
        )
        response_data = sec_res.get('data') or {}
        sec_poison_id = str(response_data.get('secPoisonId') or '')
        scripting_code = str(response_data.get('data') or '')
        if not sec_poison_id or len(scripting_code) < 1000:
            raise RuntimeError('seccallback response is missing secPoisonId or program data')

        websectiga = generate_websectiga(scripting_code, profile={
            'userAgent': REFERENCE_PROFILE['release']['userAgent'],
            'platform': 'Win32',
            'pageUrl': self.home_url,
        })
        cookies['websectiga'] = websectiga
        cookies['sec_poison_id'] = sec_poison_id
        self.profile.update_cookies(cookies)
        tiga_time = self.profile.mark_tiga_updated()
        self.profile.session.dsllt = tiga_time
        # The current browser stays on 0101 for login/activate.  The successful
        # SSK exchange below is the transition to the 0301 login stage.

    def _activate(self, cookies):
        """Create the anonymous visitor session required by both login flows."""
        api = '/api/sns/web/v1/login/activate'
        handshake = create_web_ssk_handshake()
        payload = {
            'client_public_key_base64': handshake['client_public_key_base64'],
        }
        headers, body = self._signed_request_params(
            cookies,
            api,
            payload,
            tier='0101',
            mns_profile='activate',
        )
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='post',
        )
        resp = self.http.post(
            self.base_url + api,
            headers=headers,
            data=body,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, resp)
        res = resp.json()
        data = res.get('data') or {}
        if not resp.ok or not res.get('success'):
            raise RuntimeError(res.get('msg') or f'login/activate HTTP {resp.status_code}')
        visitor_session = str(data.get('session') or '')
        if visitor_session:
            cookies['web_session'] = visitor_session
            self.profile.update_cookies(cookies)
        if not cookies.get('web_session'):
            raise RuntimeError('login/activate did not issue visitor web_session')
        encrypted_ssk = str(data.get('ssk') or '')
        if not encrypted_ssk:
            raise RuntimeError('login/activate did not issue encrypted SSK')
        ssk = accept_web_ssk(handshake['private_key_base64'], encrypted_ssk)
        web_ssk = json.dumps(
            {'xhs-pc-web': ssk},
            ensure_ascii=False,
            separators=(',', ':'),
        )
        self.local_storage['webSsk'] = web_ssk
        self.profile.update_storage(local_storage=self.local_storage)
        self.profile.mark_fingerprint_ready(True)
        return data

    def _fetch_gid(self, cookies):
        if self._webprofile_reported and cookies.get('gid'):
            return cookies['gid']
        api = '/api/sec/v1/shield/webprofile'
        if not self.profile_data:
            self.profile_data = generate_profile_data(
                **self.profile.profile_data_options()
            )
        data = {
            "platform": "Windows",
            "sdkVersion": REFERENCE_PROFILE['release']['webProfileSdkVersion'],
            "svn": "2",
            "profileData": self.profile_data,
        }

        headers, data_str = self._signed_request_params(
            cookies,
            api,
            data,
            sec_domain=True,
            tier='0301',
            mns_profile='webprofile',
            include_trace_headers=False,
            include_b1=True,
        )
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.as_url, cookies),
            kind='security',
        )
        try:
            resp = self.http.post(
                self.as_url + api,
                headers=headers,
                data=data_str.encode('utf-8'),
                proxies=self.proxies,
                timeout=REQUEST_TIMEOUT
            )
            self._merge_response_cookies(cookies, resp)
            res = resp.json()
            if resp.ok and (res.get('success') is True or res.get('code') == 0):
                gid = cookies.get('gid')
                if not gid:
                    return None
                self.profile.mark_profile_reported()
                self._webprofile_reported = True
                return gid
            return None
        except Exception as e:
            logger.debug(f'fetch gid failed: {e}')
            return None

    def _initialize_navigation(self, cookies):
        headers = build_pc_navigation_headers(get_common_headers())
        response = self.http.get(
            self.web_url + '/',
            headers=headers,
            proxies=self.proxies,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, response)
        headers = build_pc_navigation_headers(
            get_common_headers(),
            self._cookies_for_url(self.web_url, cookies),
        )
        response = self.http.get(
            self.home_url,
            headers=headers,
            proxies=self.proxies,
            allow_redirects=False,
            timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(cookies, response)
        if not cookies.get('abRequestId'):
            raise RuntimeError('initial www navigation did not issue abRequestId')

    def generate_init_cookies(self):
        navigation_cookies = {}
        self.profile = self._new_profile(navigation_cookies)
        self._initialize_navigation(navigation_cookies)
        ts = int(time.time() * 1000)
        a1 = generate_a1('pc')
        web_id = generate_web_id('pc', a1)
        cookies = initial_pc_cookies(
            a1,
            web_id,
            ab_request_id=navigation_cookies['abRequestId'],
            timestamp_ms=ts,
            loadts_ms=ts + random.randint(50, 200),
            web_build=self.web_build or None,
        )
        self.profile = self._new_profile(cookies)
        self.profile_data = ''
        self._webprofile_reported = False
        self._login_b1 = ''
        self._initialize_security(cookies)
        self._activate(cookies)
        return cookies

    def ensure_webprofile(self, cookies):
        """Generate/report anonymous profileData before the user authenticates."""
        gid = self._fetch_gid(cookies)
        if not gid:
            raise RuntimeError('webprofile succeeded without issuing gid')
        cookies['gid'] = gid
        self.profile.update_cookies(cookies)
        return gid

    def generate_qrcode(self, cookies):
        api = '/api/sns/web/v1/login/qrcode/create'
        data = {"qr_type": 1}

        headers, data = self._signed_request_params(
            cookies,
            api,
            data,
            tier='0301',
            mns_profile='qrcode_create',
        )
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='post',
        )
        resp = self.http.post(
            self.base_url + api,
            headers=headers, data=data,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)

        res = resp.json()
        if not res.get('success'):
            return False, res.get('msg', '未知错误'), None
        data = res.get('data') or {}
        if not all(key in data for key in ('qr_id', 'code', 'url')):
            return False, res.get('msg', '二维码响应缺少必要字段'), {'cookies': cookies, 'res_json': res}

        return True, '成功', {
            'cookies': cookies,
            'qr_id': data['qr_id'],
            'code': data['code'],
            'qr_url': data['url'],
        }

    def check_qrcode_status(self, qr_id, code, cookies):
        api = '/api/qrcode/userinfo'
        data = {"qrId": qr_id, "code": code}

        headers, data = self._signed_request_params(
            cookies,
            api,
            data,
            tier='0301',
            mns_profile='qrcode_poll',
        )
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='post',
        )
        resp = self.http.post(
            self.base_url + api,
            headers=headers, data=data,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)

        res = resp.json()
        status = (res.get('data') or {}).get('codeStatus')
        if status is None:
            return False, res.get('msg', '二维码状态响应缺少 codeStatus'), cookies

        if status == 2:
            cookies = self._login_by_qrcode_status(qr_id, code, cookies)

        status_map = {
            0: (False, '请扫描二维码'),
            1: (False, '请确认登录'),
            2: (True, '验证成功'),
            3: (False, '二维码已过期'),
        }
        success, msg = status_map.get(status, (False, f'未知状态: {status}'))
        return success, msg, cookies

    def _login_by_qrcode_status(self, qr_id, code, cookies):
        api = '/api/sns/web/v1/login/qrcode/status'
        params = {"qr_id": qr_id, "code": code}
        splice_api = splice_str(api, params)
        visitor_session = str(cookies.get('web_session') or '')

        headers, _ = self._signed_request_params(
            cookies,
            splice_api,
            method='GET',
            tier='0301',
            mns_profile='qrcode_poll',
        )
        headers['x-login-mode'] = ''
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='get-login-mode',
        )
        resp = self.http.get(
            self.base_url + splice_api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(
            cookies,
            resp,
            append_shared=(
                'web_session',
                'id_token',
                'x-rednote-datactry',
                'x-rednote-holderctry',
            ),
        )

        res = resp.json()
        data = res.get('data') or {}
        if not res.get('success') or data.get('code_status') != 2:
            raise RuntimeError(res.get('msg') or '二维码最终登录状态无效')
        login_info = data.get('login_info') or {}
        session = str(login_info.get('session') or '')
        if session:
            # Replace the anonymous session even when Set-Cookie parsing is
            # unavailable.  Keeping the visitor session would produce a false
            # login success.
            cookies.pop('web_session', None)
            cookies['web_session'] = session
            self.profile.update_cookies(cookies)
        elif not cookies.get('web_session') or cookies.get('web_session') == visitor_session:
            raise RuntimeError('二维码登录响应缺少正式 web_session')

        return cookies

    def get_user_info(self, cookies):
        api = '/api/sns/web/v2/user/me'

        headers, _ = self._signed_request_params(cookies, api, method='GET')
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='get',
        )
        resp = self.http.get(
            self.base_url + api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)

        res = resp.json()
        return res.get('success', False), res.get('data', {}), cookies

    def send_phone_code(self, phone, cookies, zone='86'):
        api = '/api/sns/web/v2/login/send_code'
        params = {"phone": phone, "zone": zone, "type": "login"}
        splice_api = splice_str(api, params)

        headers, _ = self._signed_request_params(cookies, splice_api, method='GET')
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='get',
        )
        resp = self.http.get(
            self.base_url + splice_api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)
        res = resp.json()
        return res.get('success', False), res.get('msg', ''), res

    def login_by_phone(self, phone, code, cookies, zone='86'):
        check_api = '/api/sns/web/v1/login/check_code'
        params = {"phone": phone, "zone": zone, "code": code}
        splice_api = splice_str(check_api, params)

        headers, _ = self._signed_request_params(cookies, splice_api, method='GET')
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='get',
        )
        resp = self.http.get(
            self.base_url + splice_api,
            headers=headers,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)
        res = resp.json()
        if not res.get('success'):
            return False, res.get('msg', '验证码验证失败'), {'cookies': cookies}
        mobile_token = (res.get('data') or {}).get('mobile_token')
        if not mobile_token:
            return False, res.get('msg', '验证码响应缺少 mobile_token'), {'cookies': cookies, 'res_json': res}

        login_api = '/api/sns/web/v2/login/code'
        data = {"mobile_token": mobile_token, "zone": zone, "phone": phone}
        headers, data = self._signed_request_params(cookies, login_api, data)
        headers = build_pc_login_headers(
            headers,
            self._cookies_for_url(self.base_url, cookies),
            kind='post',
        )
        resp = self.http.post(
            self.base_url + login_api,
            headers=headers, data=data,
            proxies=self.proxies,
            timeout=REQUEST_TIMEOUT
        )
        self._merge_response_cookies(cookies, resp)

        res = resp.json()
        if not res.get('success'):
            return False, res.get('msg', '登录失败'), {'cookies': cookies}
        session = (res.get('data') or {}).get('session')
        if not session:
            return False, res.get('msg', '登录响应缺少 session'), {'cookies': cookies, 'res_json': res}
        cookies.pop('web_session', None)
        cookies['web_session'] = session
        self.profile.update_cookies(cookies)
        return True, '成功', {
            'cookies': cookies,
            'res_json': res,
        }

    @staticmethod
    def cookies_to_str(cookies):
        return '; '.join(f'{k}={v}' for k, v in cookies.items())

    @staticmethod
    def show_qrcode_terminal(url):
        import qrcode
        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)

    @staticmethod
    def show_qrcode_image(url):
        import os
        import tempfile
        import qrcode
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        target = os.environ.get('XHS_PC_QR_IMAGE')
        if not target:
            img.show()
            return
        directory = os.path.dirname(os.path.abspath(target))
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.xhs-pc-qr-', suffix='.png', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                img.save(stream, format='PNG')
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp, 0o600)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def qrcode_login(
        self,
        show_in_terminal=True,
        timeout_seconds=180,
        poll_interval=2.0,
    ):
        logger.info('[1/5] 正在初始化匿名设备...')
        try:
            cookies = self.generate_init_cookies()
        except Exception as exc:
            logger.error(f'匿名设备初始化失败: {exc}')
            return None
        logger.debug(f'初始 Cookie 字段: {list(cookies)}')

        logger.info('[2/5] 正在获取二维码...')
        success, msg, qr_data = self.generate_qrcode(cookies)
        if not success:
            logger.error(f'获取二维码失败: {msg}')
            return None
        cookies = qr_data['cookies']

        logger.info('[3/5] 正在验证本地指纹环境...')
        try:
            # Browser order: create QR -> first anonymous poll -> webprofile.
            success, msg, cookies = self.check_qrcode_status(
                qr_data['qr_id'], qr_data['code'], cookies
            )
            if success:
                logger.error('二维码在展示前已被确认，拒绝复用异常登录状态')
                return None
            if msg != '请扫描二维码':
                logger.error(f'二维码预检查状态异常: {msg}')
                return None
            self.ensure_webprofile(cookies)
        except Exception as exc:
            logger.error(f'匿名指纹验收失败，未进入扫码阶段: {exc}')
            return None

        logger.info('请使用小红书APP扫描以下二维码:')
        if show_in_terminal:
            self.show_qrcode_terminal(qr_data['qr_url'])
        else:
            self.show_qrcode_image(qr_data['qr_url'])

        logger.info('[4/5] 等待扫码和手机确认...')
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while time.monotonic() < deadline:
            try:
                success, msg, cookies = self.check_qrcode_status(
                    qr_data['qr_id'], qr_data['code'], cookies
                )
            except Exception as exc:
                logger.error(f'二维码状态检查失败: {exc}')
                return None
            if success:
                logger.info(msg)
                break
            if msg == '二维码已过期':
                logger.error(msg)
                return None
            time.sleep(max(0.5, float(poll_interval)))
        else:
            logger.error('等待扫码超时，请重新生成二维码')
            return None

        logger.info('[5/5] 验证正式登录状态...')
        success, user_info, cookies = self.get_user_info(cookies)
        if not success or user_info.get('guest') is not False:
            logger.error('正式会话验证失败，拒绝返回访客 Cookie')
            return None
        logger.info(f'用户: {user_info.get("nickname", "未知")} (RedID: {user_info.get("red_id", "未知")})')

        cookies_str = self.cookies_to_str(cookies)
        logger.success('登录成功，Cookie 已通过返回值交给调用方')
        return cookies_str

    def phone_login(self):
        logger.info('[1/5] 正在初始化匿名设备...')
        try:
            # SMS uses the activated anonymous device; webprofile is a QR-flow step.
            cookies = self.generate_init_cookies()
        except Exception as exc:
            logger.error(f'匿名设备验收失败，未发送验证码: {exc}')
            return None
        logger.debug(f'初始 Cookie 字段: {list(cookies)}')

        phone = input('请输入手机号: ')
        logger.info('[2/5] 正在发送验证码...')
        success, msg, _ = self.send_phone_code(phone, cookies)
        if not success:
            logger.error(f'发送失败: {msg}')
            return None
        logger.info('验证码已发送')

        code = input('请输入验证码: ')
        logger.info('[3/5] 正在验证...')
        success, msg, result = self.login_by_phone(phone, code, cookies)
        if not success:
            logger.error(f'验证失败: {msg}')
            return None
        cookies = result['cookies']

        logger.info('[4/5] 正在合并正式会话...')
        success, user_info, cookies = self.get_user_info(cookies)
        if not success or user_info.get('guest') is not False:
            logger.error('正式会话验证失败，拒绝返回访客 Cookie')
            return None
        logger.info(f'用户: {user_info.get("nickname", "未知")} (RedID: {user_info.get("red_id", "未知")})')

        cookies_str = self.cookies_to_str(cookies)
        logger.success('[5/5] 登录成功，Cookie 已通过返回值交给调用方')
        return cookies_str
