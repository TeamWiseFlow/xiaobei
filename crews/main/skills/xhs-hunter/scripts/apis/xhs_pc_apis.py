# encoding: utf-8
import json
import re
import time
import urllib
from xhs_utils.xhs_pc import XHSAuth, XHSPcAuth
from xhs_utils.xhs_pc.http import PcHttpClient
from xhs_utils.xhs_pc.params import (
    build_pc_business_headers,
    build_pc_navigation_headers,
    generate_request_params,
    generate_search_id,
    generate_search_request_id,
    generate_search_session_id,
    generate_x_rap_param,
    PC_CURRENT_BROWSER_UA,
    get_common_headers,
    splice_str,
)
from xhs_utils.http_util import REQUEST_TIMEOUT
from xhs_utils.relay import compute

"""
    获小红书的api
"""
def _log_api_error(error):
    # The CLI reports this message as JSON. Avoid a second, unstructured
    # traceback on stderr, which also breaks callers that merge both streams.
    return f'{type(error).__name__}: {error}'


def _get_query_params(parsed_url):
    return {
        key: values[-1] if values else ''
        for key, values in urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True).items()
    }


def _insert_header_after(headers, key, value, after):
    """Insert a captured header at its observed wire position."""
    out = {}
    inserted = False
    for name, current in headers.items():
        if name.lower() == key.lower():
            continue
        out[name] = current
        if name.lower() == after.lower():
            out[key] = value
            inserted = True
    if not inserted:
        out[key] = value
    return out


class XHS_Apis():
    """
    PC 端 API。鉴权材料全部走 XHSPcAuth，接口不再散传 cookies/b1/dsl/user_id。

      auth = XHSPcAuth.from_cookie(xhr_cookie, b1=..., dsl=...)
      apis = XHS_Apis(auth)
      apis.bootstrap()              # 自动填 auth.user_id
      apis.get_unread_message()

    取参说明见 xhs_utils/xhs_pc/auth.py（XHSPcAuth 类注释）。
    """

    def __init__(self, auth: XHSAuth):
        if not isinstance(auth, XHSPcAuth):
            raise TypeError('XHS_Apis 当前仅支持 XHSPcAuth，其它平台鉴权类后续扩展')
        self.auth: XHSPcAuth = auth
        self.http = auth.http_client
        self.base_url = auth.origin('api')
        self.so_base_url = auth.origin('search')

    def bootstrap(self, proxies: dict = None):
        """调 user/me 写入 auth.user_id（算 xy-direction 用）。"""
        success, msg, res = self.get_user_me(proxies)
        if not success:
            raise RuntimeError(f'bootstrap user/me failed: {msg}')
        uid = ((res or {}).get('data') or {}).get('user_id') or ''
        if not uid:
            raise RuntimeError('bootstrap: user/me 未返回 user_id')
        self.auth.set_user_id(uid)
        return self

    def _proxies(self, proxies: dict = None):
        return proxies if proxies is not None else self.auth.proxies

    def _request_params(
        self,
        api: str,
        data='',
        method='POST',
        tier=None,
        *,
        target_origin=None,
    ):
        """
        按浏览器实抓组装头：
        必有: x-s / x-t / x-s-common / x-b3-traceid / x-xray-traceid
        条件: x-rap-param（RAP 白名单）、xy-direction（仅 homefeed/feed）
        无 x-mns（浏览器 edith 业务请求未带）
        tier: None → 按 resolve_mns_tier(api) 自动选档（爬虫内容接口=mns0301，与真机稳态一致、服务端接受）；
              个别接口如需强制档位可显式传 '0201'/'0101'。
        """
        self.auth.validate(require_user_id=False)
        route_policy = compute('pc', 'route-policy', {'api': api})
        if route_policy.get('xy') and not self.auth.user_id:
            self.bootstrap()
        sign_context = self.auth.next_sign_context(api, tier=tier)
        b1 = self.auth.current_b1(sign_context['now'])
        headers, cookies, body = generate_request_params(
            self.auth.cookies, api, data, method,
            user_id=self.auth.user_id,
            b1=b1,
            dsl_pair=self.auth.dsl_pair,
            doc_cookie=self.auth.sign_cookie,
            with_xy_direction=bool(route_policy.get('xy')),
            tier=sign_context['tier'],
            sign_context=sign_context,
            include_client_hints=False,
        )
        headers.pop("x-mns", None)
        # Chrome's message-page bootstrap marks these cacheable GET/empty-POST
        # endpoints explicitly.  They are conditional: ordinary feed and
        # notification calls do not carry the two fields.
        if api.split('?', 1)[0] in {
            '/api/sns/web/v1/config',
            '/api/sns/web/v1/system/config',
            '/api/sns/web/v2/user/me',
        }:
            headers['cache-control'] = 'no-cache'
            headers['pragma'] = 'no-cache'
        if route_policy.get('rap'):
            headers["x-rap-param"] = generate_x_rap_param(
                api,
                body or "",
                app_id=self.auth.profile.release['appId'],
                fingerprint_hex=self.auth.profile.rap_fingerprint_hex,
            )
        elif "x-rap-param" in headers:
            headers.pop("x-rap-param", None)
        target = (target_origin or self.base_url) + api
        wire_cookies = self.auth.cookies_for_url(target, cookies)
        headers = build_pc_business_headers(
            headers,
            wire_cookies,
            api=api,
            method=method,
        )
        # Preserve the UA tied to the captured release/session.  The current
        # default is Chrome 152, while explicit historical fixtures may carry
        # Chrome 150; never overwrite a captured context here.
        headers['user-agent'] = sign_context.get('userAgent', PC_CURRENT_BROWSER_UA)
        return headers, wire_cookies, body

    def get_homefeed_all_channel(self, proxies: dict = None):
        """
            获取主页的所有频道
            返回主页的所有频道
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/homefeed/category"
            headers, cookies, data = self._request_params(api, '', 'GET')
            response = self.http.get(self.base_url + api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_homefeed_recommend(
        self,
        category,
        cursor_score,
        refresh_type,
        note_index,
        proxies: dict = None,
        *,
        num: int = 20,
        need_num: int = 10,
    ):
        """
            获取主页推荐的笔记
            :param category: 你想要获取的频道
            :param cursor_score: 你想要获取的笔记的cursor
            :param refresh_type: 你想要获取的笔记的刷新类型
            :param note_index: 你想要获取的笔记的index
            :param num: 单次候选数量；页面会按视口/阶段动态调整
            :param need_num: 单次期望返回数量；页面会按视口/阶段动态调整
            返回主页推荐的笔记
        """
        res_json = None
        try:
            api = f"/api/sns/web/v1/homefeed"
            data = {
                "cursor_score": cursor_score,
                "num": int(num),
                "refresh_type": refresh_type,
                "note_index": note_index,
                "unread_begin_note_id": "",
                "unread_end_note_id": "",
                "unread_note_count": 0,
                "category": category,
                "search_key": "",
                "need_num": int(need_num),
                "image_formats": [
                    "jpg",
                    "webp",
                    "avif"
                ],
                "need_filter_image": False
            }
            headers, cookies, trans_data = self._request_params(api, data, 'POST')
            response = self.http.post(self.base_url + api, headers=headers, data=trans_data, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_homefeed_recommend_by_num(self, category, require_num, proxies: dict = None):
        """
            根据数量获取主页推荐的笔记
            :param category: 你想要获取的频道
            :param require_num: 你想要获取的笔记的数量
            根据数量返回主页推荐的笔记
        """
        cursor_score, refresh_type, note_index = "", 1, 0
        note_list = []
        try:
            while True:
                success, msg, res_json = self.get_homefeed_recommend(category, cursor_score, refresh_type, note_index, proxies)
                if not success:
                    raise Exception(msg)
                if "items" not in res_json["data"]:
                    break
                notes = res_json["data"]["items"]
                note_list.extend(notes)
                cursor_score = res_json["data"]["cursor_score"]
                refresh_type = 3
                note_index += 20
                if len(note_list) > require_num:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        if len(note_list) > require_num:
            note_list = note_list[:require_num]
        return success, msg, note_list

    def get_user_info(self, user_id: str, proxies: dict = None):
        """
            获取用户的信息
            :param user_id: 你想要获取的用户的id
            返回用户的信息
        """
        res_json = None
        try:
            api = f"/api/sns/web/v1/user/otherinfo"
            params = {
                "target_user_id": user_id
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json


    def get_user_me(self, proxies: dict = None):
        """
            获取用户自己的信息2
            返回用户自己的信息2
        """
        res_json = None
        try:
            api = f"/api/sns/web/v2/user/me"
            headers, cookies, data = self._request_params(api, '', 'GET')
            response = self.http.get(self.base_url + api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_user_note_info(self, user_id: str, cursor: str, xsec_token='', xsec_source='', proxies: dict = None):
        """
            获取用户指定位置的笔记
            :param user_id: 你想要获取的用户的id
            :param cursor: 你想要获取的笔记的cursor
            返回用户指定位置的笔记
        """
        res_json = None
        try:
            api = f"/api/sns/web/v1/user_posted"
            params = {
                "num": "30",
                "cursor": cursor,
                "user_id": user_id,
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
                "xsec_source": xsec_source,
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json


    def get_user_all_notes(self, user_url: str, proxies: dict = None):
        """
           获取用户所有笔记
           :param user_id: 你想要获取的用户的id
           返回用户的所有笔记
        """
        cursor = ''
        note_list = []
        try:
            urlParse = urllib.parse.urlparse(user_url)
            user_id = urlParse.path.split("/")[-1]
            kvDist = _get_query_params(urlParse)
            xsec_token = kvDist['xsec_token'] if 'xsec_token' in kvDist else ""
            xsec_source = kvDist['xsec_source'] if 'xsec_source' in kvDist else "pc_search"
            while True:
                success, msg, res_json = self.get_user_note_info(user_id, cursor, xsec_token, xsec_source, proxies)
                if not success:
                    raise Exception(msg)
                notes = res_json["data"]["notes"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                note_list.extend(notes)
                if len(notes) == 0 or not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, note_list

    def get_user_like_note_info(self, user_id: str, cursor: str, xsec_token='', xsec_source='', proxies: dict = None):
        """
            获取用户指定位置喜欢的笔记
            :param user_id: 你想要获取的用户的id
            :param cursor: 你想要获取的笔记的cursor
            返回用户指定位置喜欢的笔记
        """
        res_json = None
        try:
            api = f"/api/sns/web/v1/note/like/page"
            params = {
                "num": "30",
                "cursor": cursor,
                "user_id": user_id,
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
                "xsec_source": xsec_source,
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_user_all_like_note_info(self, user_url: str, proxies: dict = None):
        """
            获取用户所有喜欢笔记
            :param user_id: 你想要获取的用户的id
            返回用户的所有喜欢笔记
        """
        cursor = ''
        note_list = []
        try:
            urlParse = urllib.parse.urlparse(user_url)
            user_id = urlParse.path.split("/")[-1]
            kvDist = _get_query_params(urlParse)
            xsec_token = kvDist['xsec_token'] if 'xsec_token' in kvDist else ""
            xsec_source = kvDist['xsec_source'] if 'xsec_source' in kvDist else "pc_user"
            while True:
                success, msg, res_json = self.get_user_like_note_info(user_id, cursor, xsec_token, xsec_source, proxies)
                if not success:
                    raise Exception(msg)
                notes = res_json["data"]["notes"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                note_list.extend(notes)
                if len(notes) == 0 or not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, note_list

    def get_user_collect_note_info(self, user_id: str, cursor: str, xsec_token='', xsec_source='', proxies: dict = None):
        """
            获取用户指定位置收藏的笔记
            :param user_id: 你想要获取的用户的id
            :param cursor: 你想要获取的笔记的cursor
            返回用户指定位置收藏的笔记
        """
        res_json = None
        try:
            api = f"/api/sns/web/v2/note/collect/page"
            params = {
                "num": "30",
                "cursor": cursor,
                "user_id": user_id,
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token,
                "xsec_source": xsec_source,
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_user_all_collect_note_info(self, user_url: str, proxies: dict = None):
        """
            获取用户所有收藏笔记
            :param user_id: 你想要获取的用户的id
            返回用户的所有收藏笔记
        """
        cursor = ''
        note_list = []
        try:
            urlParse = urllib.parse.urlparse(user_url)
            user_id = urlParse.path.split("/")[-1]
            kvDist = _get_query_params(urlParse)
            xsec_token = kvDist['xsec_token'] if 'xsec_token' in kvDist else ""
            xsec_source = kvDist['xsec_source'] if 'xsec_source' in kvDist else "pc_search"
            while True:
                success, msg, res_json = self.get_user_collect_note_info(user_id, cursor, xsec_token, xsec_source, proxies)
                if not success:
                    raise Exception(msg)
                notes = res_json["data"]["notes"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                note_list.extend(notes)
                if len(notes) == 0 or not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, note_list

    def get_note_info(self, url: str, proxies: dict = None):
        """
            获取笔记的详细
            :param url: 你想要获取的笔记的url
            :param xsec_source: 你的xsec_source 默认为pc_search pc_user pc_feed
            返回笔记的详细
        """
        res_json = None
        try:
            urlParse = urllib.parse.urlparse(url)
            note_id = urlParse.path.split("/")[-1]
            kvDist = _get_query_params(urlParse)
            api = f"/api/sns/web/v1/feed"
            data = {
                "source_note_id": note_id,
                "image_formats": [
                    "jpg",
                    "webp",
                    "avif"
                ],
                "extra": {
                    "need_body_topic": "1"
                },
                "xsec_source": kvDist['xsec_source'] if 'xsec_source' in kvDist else "pc_search",
                "xsec_token": kvDist.get('xsec_token', '')
            }
            headers, cookies, data = self._request_params(api, data, 'POST')
            response = self.http.post(self.base_url + api, headers=headers, data=data, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
            code = res_json.get("code")
            if code is not None and code not in (0, "0", 200, "200"):
                success = False
                msg = msg or f"笔记详情接口返回 code={code}"
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    @staticmethod
    def _captured_json_body(data, required, *, operation):
        """Return a browser-captured JSON mapping with an exact field contract.

        Insertion order is retained because it is part of the signed wire
        body.  These helpers intentionally reject partial payloads instead of
        silently relying on server defaults, which can trigger risk control.
        """
        if not isinstance(data, dict):
            raise TypeError(f'{operation} requires a mapping body')
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError(
                f'{operation} missing captured fields: {", ".join(missing)}'
            )
        return {key: data[key] for key in data}

    def share_code(self, note_id: str, proxies: dict = None):
        """Generate a note share code using the captured one-field body."""
        if not note_id:
            raise ValueError('share_code requires captured note_id')
        data = self._captured_json_body(
            {'share_code': {'id': str(note_id)}},
            ('share_code',),
            operation='share_code',
        )
        api = '/api/sns/web/share/code'
        headers, cookies, body = self._request_params(api, data, 'POST')
        response = self.http.post(
            self.base_url + api, headers=headers, data=body,
            cookies=cookies, proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        return response.json()

    def get_widgets(self, note_id: str, *, source: str = 'web_feed',
                    mode: int = 1, exp_flags: dict | None = None,
                    proxies: dict = None):
        """Fetch note widgets with the complete captured request shape."""
        if not note_id:
            raise ValueError('get_widgets requires captured note_id')
        if exp_flags is None:
            exp_flags = {'web_support_related_search': True}
        data = self._captured_json_body(
            {'note_id': str(note_id), 'scene': 'web', 'mode': int(mode),
             'source': str(source), 'exp_flags': exp_flags},
            ('note_id', 'scene', 'mode', 'source', 'exp_flags'),
            operation='get_widgets',
        )
        api = '/api/sns/web/v2/widgets'
        headers, cookies, body = self._request_params(api, data, 'POST')
        response = self.http.post(
            self.base_url + api, headers=headers, data=body,
            cookies=cookies, proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        return response.json()

    def worldcup_note_seo(self, note_ids, proxies: dict = None):
        """Fetch SEO/indexability state using Chrome's ordered body.

        The browser sends ``{"note_ids":[...]}`` even for a single note;
        callers must provide a non-empty captured list so the signed body
        cannot silently fall back to a server default.
        """
        if not isinstance(note_ids, (list, tuple)) or not note_ids:
            raise ValueError('worldcup_note_seo requires captured note_ids')
        data = self._captured_json_body(
            {'note_ids': [str(value) for value in note_ids]},
            ('note_ids',), operation='worldcup_note_seo',
        )
        api = '/api/sns/web/worldcup/note/seo'
        headers, cookies, body = self._request_params(api, data, 'POST')
        response = self.http.post(
            self.base_url + api, headers=headers, data=body,
            cookies=cookies, proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        return response.json()

    def report_note_metrics(self, data: dict, proxies: dict = None):
        """Report note-view metrics using a complete captured body."""
        required = (
            'note_id', 'note_type', 'report_type', 'stress_test', 'trace',
            'viewer', 'author', 'interaction', 'note', 'other',
        )
        payload = self._captured_json_body(
            data, required, operation='report_note_metrics'
        )
        api = '/api/sns/web/v1/note/metrics_report'
        headers, cookies, body = self._request_params(api, payload, 'POST')
        response = self.http.post(
            self.base_url + api, headers=headers, data=body,
            cookies=cookies, proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        return response.json()

    def report_history_web(self, data: dict, proxies: dict = None):
        """Report web history events using the captured event envelope."""
        payload = self._captured_json_body(
            data, ('events', 'extra_map'), operation='report_history_web'
        )
        api = '/api/sns/v1/history/report_web'
        headers, cookies, body = self._request_params(api, payload, 'POST')
        # Chrome uses the generic JSON media type for this endpoint.
        headers['content-type'] = 'application/json'
        headers = build_pc_business_headers(
            headers, cookies, api=api, method='POST'
        )
        response = self.http.post(
            self.base_url + api, headers=headers, data=body,
            cookies=cookies, proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        return response.json()


    def get_search_keyword(self, word: str, proxies: dict = None):
        """
            获取搜索关键词
            :param word: 你的关键词
            返回搜索关键词
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/search/recommend"
            # 浏览器: keyword 由 urlencode 一次编码，勿预先 quote
            splice_api = splice_str(api, {"keyword": word})
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_web_config(self, proxies: dict = None):
        """Fetch the PC web config (POST with the browser's empty body)."""
        res_json = None
        try:
            api = "/api/sns/web/v1/config"
            headers, cookies, body = self._request_params(api, '', 'POST')
            # Chrome sends content-length: 0 here; do not serialize an empty
            # JSON object or add a synthetic field.
            response = self.http.post(
                self.base_url + api, headers=headers,
                data=body.encode("utf-8") if body else b"",
                cookies=cookies, proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            self._merge_response_cookies(response, self.base_url + api)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_system_config(self, proxies: dict = None):
        """Fetch the system config endpoint observed during PC bootstrap."""
        res_json = None
        try:
            api = "/api/sns/web/v1/system/config"
            headers, cookies, _ = self._request_params(api, '', 'GET')
            target = self.base_url + api
            response = self.http.get(
                target, headers=headers, cookies=cookies,
                proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
            )
            self._merge_response_cookies(response, target)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_trending_queries(
        self,
        *,
        source: str = "UserPage",
        search_type: str = "trend",
        last_query: str = "",
        last_query_time: int = 0,
        word_request_situation: str = "FIRST_ENTER",
        hint_word: str = "",
        hint_word_type: str = "",
        hint_word_request_id: str = "",
        proxies: dict = None,
    ):
        """Fetch trending queries with the captured query-field order."""
        params = {
            "source": source,
            "search_type": search_type,
            "last_query": last_query,
            "last_query_time": last_query_time,
            "word_request_situation": word_request_situation,
            "hint_word": hint_word,
            "hint_word_type": hint_word_type,
            "hint_word_request_id": hint_word_request_id,
        }
        api = splice_str("/api/sns/web/v1/search/trending/query", params)
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(
            target, headers=headers, cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def get_celestial_lt(self, *, device_id: str, proxies: dict = None):
        """Refresh the browser RWP token using the captured device header."""
        if not device_id:
            raise ValueError("device_id must come from browser session storage")
        api = "/api/sns/web/v1/celestial/lt"
        headers, cookies, _ = self._request_params(api, "", "GET")
        # Chrome places this device header between x-xray-traceid and x-t;
        # appending it would change the observable header order.
        headers = _insert_header_after(
            headers, "c_device_id", str(device_id), "x-xray-traceid"
        )
        target = self.base_url + api
        response = self.http.get(
            target, headers=headers, cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def get_user_board(self, user_id: str, *, num: int = 15, page: int = 1,
                       proxies: dict = None):
        """Fetch the user's public board list observed on the search page."""
        api = splice_str("/api/sns/web/v1/board/user", {
            "user_id": str(user_id), "num": num, "page": page,
        })
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(
            target, headers=headers, cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def get_dqa_recommend(self, *, source: str = "diandian",
                          proxies: dict = None):
        """Fetch the discovery-question recommendations shown on Explore.

        Chrome emits one required query member (``source``); keep it explicit
        so callers cannot accidentally send a different or incomplete shape.
        """
        if source is None or source == "":
            raise ValueError("source must match the captured browser query")
        api = splice_str("/api/sns/web/v1/dqa/recommend/query",
                         {"source": str(source)})
        headers, cookies, _ = self._request_params(api, "", "GET",
                                                   target_origin=self.so_base_url)
        target = self.so_base_url + api
        response = self.http.get(target, headers=headers, cookies=cookies,
                                 proxies=self._proxies(proxies),
                                 timeout=REQUEST_TIMEOUT)
        self._merge_response_cookies(response, target)
        return response.json()

    def get_global_config(self, proxies: dict = None):
        """Fetch the Explore global configuration route captured in Chrome."""
        api = "/api/sns/web/global/config"
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(target, headers=headers, cookies=cookies,
                                 proxies=self._proxies(proxies),
                                 timeout=REQUEST_TIMEOUT)
        self._merge_response_cookies(response, target)
        return response.json()

    def get_worldcup_display_period(self, proxies: dict = None):
        """Fetch the read-only World Cup display-period configuration."""
        api = "/api/sns/web/worldcup/dots/display_period"
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(target, headers=headers, cookies=cookies,
                                 proxies=self._proxies(proxies),
                                 timeout=REQUEST_TIMEOUT)
        self._merge_response_cookies(response, target)
        return response.json()

    def get_worldcup_live_bar(self, proxies: dict = None):
        """Fetch the read-only World Cup live-bar configuration."""
        api = "/api/sns/web/worldcup/live_bar"
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(target, headers=headers, cookies=cookies,
                                 proxies=self._proxies(proxies),
                                 timeout=REQUEST_TIMEOUT)
        self._merge_response_cookies(response, target)
        return response.json()

    def sync_search_history(self, query: str, *, client_time: int = None,
                            proxies: dict = None):
        """Sync one search operation using the browser's exact body shape."""
        timestamp = int(client_time if client_time is not None else time.time() * 1000)
        api = "/api/sns/web/search/history/sync"
        data = {
            "client_time": timestamp,
            "ops": [{"act": "search", "q": str(query), "ct": timestamp}],
        }
        headers, cookies, body = self._request_params(
            api, data, "POST", target_origin=self.so_base_url
        )
        target = self.so_base_url + api
        response = self.http.post(
            target, headers=headers, data=body.encode("utf-8"), cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def sync_search_history_captured(
        self,
        *,
        client_time: int,
        ops,
        proxies: dict = None,
    ):
        """Replay the complete search-history body captured from Chrome.

        ``ops`` is kept as an explicit list because the browser sometimes
        sends an empty list during bootstrap and uses a different operation
        object after a user search.  No operation members are inferred here.
        """
        if not isinstance(ops, list):
            raise ValueError('captured search-history ops must be a list')
        data = {"client_time": int(client_time), "ops": ops}
        api = "/api/sns/web/search/history/sync"
        headers, cookies, body = self._request_params(
            api, data, "POST", target_origin=self.so_base_url
        )
        target = self.so_base_url + api
        response = self.http.post(
            target, headers=headers, data=body.encode("utf-8"), cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def search_onebox(self, query: str, *, search_id: str = None,
                      biz_type: str = "web_search_user", request_id: str = None,
                      proxies: dict = None):
        """Fetch search suggestions with the captured four-field JSON body."""
        api = "/api/sns/web/v1/search/onebox"
        data = {
            "keyword": str(query),
            "search_id": search_id or generate_search_id(),
            "biz_type": str(biz_type),
            "request_id": request_id or generate_search_request_id(),
        }
        headers, cookies, body = self._request_params(api, data, "POST")
        target = self.base_url + api
        response = self.http.post(
            target, headers=headers, data=body.encode("utf-8"), cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def search_filter(self, keyword: str, search_id: str,
                      proxies: dict = None):
        """Fetch the filter groups for an existing browser search session."""
        api = splice_str("/api/sns/web/v1/search/filter", {
            "keyword": str(keyword), "search_id": str(search_id),
        })
        headers, cookies, _ = self._request_params(api, "", "GET")
        target = self.base_url + api
        response = self.http.get(
            target, headers=headers, cookies=cookies,
            proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT,
        )
        self._merge_response_cookies(response, target)
        return response.json()

    def _merge_response_cookies(self, response, source_url: str):
        values = getattr(response, "cookies", None)
        if values is not None and hasattr(values, "items"):
            updates = dict(values.items())
            if updates:
                self.auth.update_cookies(updates, source_url=source_url)

    def search_note(self, query: str, page=1, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo="", search_id=None, proxies: dict = None):
        """
            获取搜索笔记的结果（浏览器实抓：so.xiaohongshu.com /api/sns/web/v2/search/notes）
            :param query 搜索的关键词
            :param page 搜索的页数
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time / note_range / pos_distance 保留参数；当前 PC 默认搜索体与浏览器一致不带 filters
            返回搜索的结果
        """
        res_json = None
        sort_type = "general"
        if sort_type_choice == 1:
            sort_type = "time_descending"
        elif sort_type_choice == 2:
            sort_type = "popularity_descending"
        elif sort_type_choice == 3:
            sort_type = "comment_descending"
        elif sort_type_choice == 4:
            sort_type = "collect_descending"
        # note_type: 浏览器默认 0；1/2 时写入 body.note_type
        body_note_type = 0
        if note_type == 1:
            body_note_type = 1
        elif note_type == 2:
            body_note_type = 2
        if geo and not isinstance(geo, str):
            geo = json.dumps(geo, separators=(',', ':'))
        try:
            # 2026-07 浏览器实抓（非 edith v1）
            api = "/api/sns/web/v2/search/notes"
            data = {
                "keyword": query,
                "page": page,
                "page_size": 20,
                "search_id": search_id or generate_search_id(),
                "sort": sort_type,
                "note_type": body_note_type,
                "ext_flags": [],
                "geo": geo or "",
                "image_formats": ["jpg", "webp", "avif"],
                "session_id": generate_search_session_id(),
            }
            # 兼容旧筛选：仅当调用方显式要求非默认时附加 filters（浏览器默认搜索无此字段）
            if note_time or note_range or pos_distance:
                data["filters"] = [
                    {"tags": [sort_type], "type": "sort_type"},
                    {"tags": [["不限", "视频笔记", "普通笔记"][note_type] if note_type in (0, 1, 2) else "不限"], "type": "filter_note_type"},
                    {"tags": [["不限", "一天内", "一周内", "半年内"][note_time] if note_time in (0, 1, 2, 3) else "不限"], "type": "filter_note_time"},
                    {"tags": [["不限", "已看过", "未看过", "已关注"][note_range] if note_range in (0, 1, 2, 3) else "不限"], "type": "filter_note_range"},
                    {"tags": [["不限", "同城", "附近"][pos_distance] if pos_distance in (0, 1, 2) else "不限"], "type": "filter_pos_distance"},
                ]
            headers, cookies, data = self._request_params(
                api,
                data,
                'POST',
                target_origin=self.so_base_url,
            )
            response = self.http.post(
                self.so_base_url + api,
                headers=headers,
                data=data.encode('utf-8'),
                cookies=cookies,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def search_some_note(self, query: str, require_num: int, sort_type_choice=0, note_type=0, note_time=0, note_range=0, pos_distance=0, geo="", proxies: dict = None):
        """
            指定数量搜索笔记，设置排序方式和笔记类型和笔记数量
            :param query 搜索的关键词
            :param require_num 搜索的数量
            :param sort_type_choice 排序方式 0 综合排序, 1 最新, 2 最多点赞, 3 最多评论, 4 最多收藏
            :param note_type 笔记类型 0 不限, 1 视频笔记, 2 普通笔记
            :param note_time 笔记时间 0 不限, 1 一天内, 2 一周内天, 3 半年内
            :param note_range 笔记范围 0 不限, 1 已看过, 2 未看过, 3 已关注
            :param pos_distance 位置距离 0 不限, 1 同城, 2 附近 指定这个必须要指定 geo
            :param geo: 定位信息 经纬度
            返回搜索的结果
        """
        page = 1
        note_list = []
        root_search_id = generate_search_id()
        try:
            while True:
                search_id = generate_search_id(root_search_id)
                success, msg, res_json = self.search_note(query, page, sort_type_choice, note_type, note_time, note_range, pos_distance, geo, search_id, proxies)
                if not success:
                    raise Exception(msg)
                if "items" not in res_json["data"]:
                    break
                notes = res_json["data"]["items"]
                note_list.extend(notes)
                page += 1
                if len(note_list) >= require_num or not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        if len(note_list) > require_num:
            note_list = note_list[:require_num]
        return success, msg, note_list

    def search_user(self, query: str, page=1, proxies: dict = None):
        """
            获取搜索用户的结果
            :param query 搜索的关键词
            :param page 搜索的页数
            返回搜索的结果
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/search/usersearch"
            data = {
                "search_user_request": {
                    "keyword": query,
                    "search_id": generate_search_id(),
                    "page": page,
                    "page_size": 15,
                    "biz_type": "web_search_user",
                    "request_id": generate_search_request_id()
                }
            }
            headers, cookies, data = self._request_params(api, data, 'POST')
            response = self.http.post(self.base_url + api, headers=headers, data=data.encode('utf-8'), cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def search_some_user(self, query: str, require_num: int, proxies: dict = None):
        """
            指定数量搜索用户
            :param query 搜索的关键词
            :param require_num 搜索的数量
            返回搜索的结果
        """
        page = 1
        user_list = []
        try:
            while True:
                success, msg, res_json = self.search_user(query, page, proxies)
                if not success:
                    raise Exception(msg)
                if "users" not in res_json["data"]:
                    break
                users = res_json["data"]["users"]
                user_list.extend(users)
                page += 1
                if len(user_list) >= require_num or not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        if len(user_list) > require_num:
            user_list = user_list[:require_num]
        return success, msg, user_list

    def get_note_out_comment(self, note_id: str, cursor: str, xsec_token: str, proxies: dict = None):
        """
            获取指定位置的笔记一级评论
            :param note_id 笔记的id
            :param cursor 指定位置的评论的cursor
            返回指定位置的笔记一级评论
        """
        res_json = None
        try:
            api = "/api/sns/web/v2/comment/page"
            params = {
                "note_id": note_id,
                "cursor": cursor,
                "top_comment_id": "",
                "image_formats": "jpg,webp,avif",
                "xsec_token": xsec_token
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
            code = res_json.get("code")
            if code is not None and code not in (0, "0", 200, "200"):
                success = False
                msg = msg or f"评论接口返回 code={code}"
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_note_all_out_comment(self, note_id: str, xsec_token: str, proxies: dict = None,
                                 limit: int = None):
        """
            获取笔记的全部一级评论
            :param note_id 笔记的id
            返回笔记的全部一级评论
        """
        cursor = ''
        note_out_comment_list = []
        if limit is not None and limit < 1:
            return False, 'limit 必须大于 0', note_out_comment_list
        try:
            while True:
                success, msg, res_json = self.get_note_out_comment(note_id, cursor, xsec_token, proxies)
                if not success:
                    return False, msg, note_out_comment_list
                data = (res_json or {}).get('data') or {}
                comments = data.get('comments')
                if not isinstance(comments, list):
                    return False, msg or '评论接口未返回 comments', note_out_comment_list
                note_out_comment_list.extend(comments)
                if limit is not None and len(note_out_comment_list) >= limit:
                    break
                if not comments or not data.get('has_more'):
                    break
                next_cursor = data.get('cursor')
                if next_cursor is None or str(next_cursor) == cursor:
                    return False, '评论翻页游标缺失或未更新', note_out_comment_list
                cursor = str(next_cursor)
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, note_out_comment_list[:limit]

    def get_note_inner_comment(self, comment: dict, cursor: str, xsec_token: str, proxies: dict = None):
        """
            获取指定位置的笔记二级评论
            :param comment 笔记的一级评论
            :param cursor 指定位置的评论的cursor
            返回指定位置的笔记二级评论
        """
        res_json = None
        try:
            api = "/api/sns/web/v2/comment/sub/page"
            params = {
                "note_id": comment['note_id'],
                "root_comment_id": comment['id'],
                "num": "10",
                "cursor": cursor,
                "image_formats": "jpg,webp,avif",
                "top_comment_id": '',
                "xsec_token": xsec_token
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
            code = res_json.get("code")
            if code is not None and code not in (0, "0", 200, "200"):
                success = False
                msg = msg or f"二级评论接口返回 code={code}"
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_note_all_inner_comment(self, comment: dict, xsec_token: str, proxies: dict = None):
        """
            获取笔记的全部二级评论
            :param comment 笔记的一级评论
            返回笔记的全部二级评论
        """
        try:
            if not comment['sub_comment_has_more']:
                return True, 'success', comment
            cursor = comment['sub_comment_cursor']
            inner_comment_list = []
            while True:
                success, msg, res_json = self.get_note_inner_comment(comment, cursor, xsec_token, proxies)
                if not success:
                    return False, msg, comment
                data = (res_json or {}).get('data') or {}
                comments = data.get('comments')
                if not isinstance(comments, list):
                    return False, msg or '二级评论接口未返回 comments', comment
                inner_comment_list.extend(comments)
                if not comments or not data.get('has_more'):
                    break
                next_cursor = data.get('cursor')
                if next_cursor is None or str(next_cursor) == cursor:
                    return False, '二级评论翻页游标缺失或未更新', comment
                cursor = str(next_cursor)
            comment.setdefault('sub_comments', []).extend(inner_comment_list)
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, comment

    def get_note_all_comment(self, url: str, proxies: dict = None, limit: int = None,
                             include_inner: bool = True):
        """
            获取一篇文章的评论，可限制一级评论数或跳过二级评论
            :param note_id: 你想要获取的笔记的id
            :param limit: 最多返回的一级评论数；None 表示全量
            :param include_inner: 是否读取二级评论
        """
        out_comment_list = []
        try:
            urlParse = urllib.parse.urlparse(url)
            note_id = urlParse.path.split("/")[-1]
            kvDist = _get_query_params(urlParse)
            xsec_token = kvDist.get('xsec_token', '')
            success, msg, out_comment_list = self.get_note_all_out_comment(
                note_id, xsec_token, proxies, limit=limit)
            if not success:
                return False, msg, out_comment_list
            if include_inner:
                for comment in out_comment_list:
                    success, msg, new_comment = self.get_note_all_inner_comment(comment, xsec_token, proxies)
                    if not success:
                        return False, msg, out_comment_list
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, out_comment_list

    def get_unread_message(self, proxies: dict = None):
        """
            获取未读消息
            返回未读消息
        """
        res_json = None
        try:
            api = "/api/sns/web/unread_count"
            headers, cookies, data = self._request_params(api, '', 'GET')
            response = self.http.get(self.base_url + api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_metions(self, cursor: str, proxies: dict = None):
        """
            获取评论和@提醒
            :param cursor: 你想要获取的评论和@提醒的cursor
            返回评论和@提醒
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/you/mentions"
            params = {
                "num": "20",
                "cursor": cursor
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_all_metions(self, proxies: dict = None):
        """
            获取全部的评论和@提醒
            返回全部的评论和@提醒
        """
        cursor = ''
        metions_list = []
        try:
            while True:
                success, msg, res_json = self.get_metions(cursor, proxies)
                if not success:
                    raise Exception(msg)
                metions = res_json["data"]["message_list"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                metions_list.extend(metions)
                if not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, metions_list

    def get_likesAndcollects(self, cursor: str, proxies: dict = None):
        """
            获取赞和收藏
            :param cursor: 你想要获取的赞和收藏的cursor
            返回赞和收藏
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/you/likes"
            params = {
                "num": "20",
                "cursor": cursor
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_all_likesAndcollects(self, proxies: dict = None):
        """
            获取全部的赞和收藏
            返回全部的赞和收藏
        """
        cursor = ''
        likesAndcollects_list = []
        try:
            while True:
                success, msg, res_json = self.get_likesAndcollects(cursor, proxies)
                if not success:
                    raise Exception(msg)
                likesAndcollects = res_json["data"]["message_list"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                likesAndcollects_list.extend(likesAndcollects)
                if not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, likesAndcollects_list

    def get_new_connections(self, cursor: str, proxies: dict = None):
        """
            获取新增关注
            :param cursor: 你想要获取的新增关注的cursor
            返回新增关注
        """
        res_json = None
        try:
            api = "/api/sns/web/v1/you/connections"
            params = {
                "num": "20",
                "cursor": cursor
            }
            splice_api = splice_str(api, params)
            headers, cookies, data = self._request_params(splice_api, '', 'GET')
            response = self.http.get(self.base_url + splice_api, headers=headers, cookies=cookies, proxies=self._proxies(proxies), timeout=REQUEST_TIMEOUT)
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, res_json

    def get_all_new_connections(self, proxies: dict = None):
        """
            获取全部的新增关注
            返回全部的新增关注
        """
        cursor = ''
        connections_list = []
        try:
            while True:
                success, msg, res_json = self.get_new_connections(cursor, proxies)
                if not success:
                    raise Exception(msg)
                connections = res_json["data"]["message_list"]
                if 'cursor' in res_json["data"]:
                    cursor = str(res_json["data"]["cursor"])
                else:
                    break
                connections_list.extend(connections)
                if not res_json["data"]["has_more"]:
                    break
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, connections_list

    @staticmethod
    def get_note_no_water_video(note_id):
        """
            获取笔记无水印视频
            :param note_id: 你想要获取的笔记的id
            返回笔记无水印视频
        """
        success = True
        msg = '成功'
        video_addr = None
        try:
            # This is a non-login document request.  The current Chrome
            # capture for webBuild 6.47.2 uses Chrome/152; keep the legacy
            # 150 UA in get_common_headers() for the separate login cold
            # chain, but align this public navigation call with the capture.
            navigation_headers = get_common_headers()
            navigation_headers['user-agent'] = PC_CURRENT_BROWSER_UA
            headers = build_pc_navigation_headers(navigation_headers)
            url = f"https://www.xiaohongshu.com/explore/{note_id}"
            http = PcHttpClient()
            try:
                response = http.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            finally:
                http.close()
            res = response.text
            video_addr = re.findall(r'<meta name="og:video" content="(.*?)">', res)[0]
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, video_addr


    @staticmethod
    def get_note_no_water_img(img_url):
        """
            获取笔记无水印图片
            :param img_url: 你想要获取的图片的url
            返回笔记无水印图片
        """
        success = True
        msg = '成功'
        new_url = None
        try:
            # 新版图片资源优先保留 notes_pre_post token，使用 ci.xiaohongshu.com 输出 JPEG。
            # 例：
            # https://sns-webpic-qc.xhscdn.com/<time>/<hash>/notes_pre_post/<img_id>!nd_dft_wlteh_webp_3
            # -> https://ci.xiaohongshu.com/notes_pre_post/<img_id>?imageView2/format/jpeg
            if 'notes_pre_post/' in img_url:
                token = 'notes_pre_post/' + img_url.split('notes_pre_post/', 1)[1].split('!', 1)[0].split('?', 1)[0]
                new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
            elif 'spectrum' in img_url:
                token = '/'.join(img_url.split('/')[-2:]).split('!', 1)[0].split('?', 1)[0]
                new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
            elif '.jpg' in img_url:
                token = '/'.join([split for split in img_url.split('/')[-3:]]).split('!', 1)[0].split('?', 1)[0]
                new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
            else:
                token = img_url.split('/')[-1].split('!', 1)[0].split('?', 1)[0]
                new_url = f'https://ci.xiaohongshu.com/{token}?imageView2/format/jpeg'
        except Exception as e:
            success = False
            msg = _log_api_error(e)
        return success, msg, new_url
