import json
import os
import tempfile
import time

from loguru import logger

from xhs_utils.http_util import REQUEST_TIMEOUT
from xhs_utils.xhs_core.http import ordered_wire_headers
from xhs_utils.xhs_creator import XHSCreatorAuth
from xhs_utils.xhs_creator.http import CREATOR_ACCEPT_ENCODING
from xhs_utils.xhs_creator.params import (
    build_creator_business_headers,
    CREATOR_CURRENT_BROWSER_UA,
    generate_request_params,
    splice_str,
)
from xhs_utils.xhs_creator_util import (
    get_fileIds_params,
    get_loc_data,
    get_post_note_image_data,
    get_post_note_video_data,
    get_upload_media_headers,
    sign_js,
    signature_js,
)
from xhs_utils.xhs_pc.params import generate_x_rap_param


TRANSCODE_MAX_RETRIES = 20
TRANSCODE_RETRY_DELAY = 3


def _load_media_bytes(path_or_file):
    """媒体入参统一为字节：bytes 原样返回，str/PathLike 按本地文件读取。"""
    if isinstance(path_or_file, (bytes, bytearray, memoryview)):
        return bytes(path_or_file)
    if isinstance(path_or_file, (str, os.PathLike)):
        with open(path_or_file, 'rb') as handle:
            return handle.read()
    raise TypeError(
        f'media must be bytes or a local file path, got {type(path_or_file).__name__}'
    )

CREATOR_HOME_REFERER = "https://creator.xiaohongshu.com/new/home"
CREATOR_NOTE_MANAGER_REFERER = "https://creator.xiaohongshu.com/new/note-manager"
CREATOR_ANALYTICS_REFERER = "https://creator.xiaohongshu.com/statistics/data-analysis?source=official"
CREATOR_PUBLISH_REFERER = (
    "https://creator.xiaohongshu.com/publish/publish"
    "?source=official&from=tab_switch"
)

CREATOR_PUBLISH_COOKIE_ORDER = (
    'abRequestId', 'ets', 'a1', 'webId', 'gid',
    'x-rednote-datactry', 'x-rednote-holderctry', '_gray_did', 'id_token',
    'customer-sso-sid', 'x-user-id-creator.xiaohongshu.com',
    'customerClientId', 'access-token-creator.xiaohongshu.com',
    'galaxy_creator_session_id', 'galaxy.creator.beaker.session.id',
    'web_session', 'unread', 'webBuild', 'xsecappid', 'acw_tc',
    'websectiga', 'sec_poison_id', 'loadts',
)

CREATOR_NOTE_MANAGER_HEADER_ORDER = (
    "authorization",
    "referer",
    "x-xray-traceid",
    "x-t",
    "x-b3-traceid",
    "x-s-common",
    "user-agent",
    "accept",
    "x-s",
    "accept-encoding",
    "accept-language",
    "cookie",
    "priority",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
)
CREATOR_NOTE_MANAGER_USER_INFO_HEADER_ORDER = (
    "authorization",
    "referer",
    "x-xray-traceid",
    "x-t",
    "x-b3-traceid",
    "x-s-common",
    "user-agent",
    "accept",
    "x-s",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "cookie",
    "pragma",
    "priority",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
)


def _load_opencv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            '图片/视频上传需要 opencv-python 和 numpy；'
            '请先执行 pip install -r requirements.txt'
        ) from exc
    return cv2, np


def _log_api_error(error):
    logger.exception(f'XHS Creator API request failed: {error}')
    return str(error)


def _creator_note_manager_headers(headers, cookies, *, user_info=False):
    """Build the note-manager GET with an explicit browser wire contract.

    curl_cffi supplies Chrome TLS/HTTP2 fingerprints but its default browser
    Headers stay disabled. This function therefore remains the sole owner of
    ordinary Header order and the exact Cookie string.
    """
    order = (
        CREATOR_NOTE_MANAGER_USER_INFO_HEADER_ORDER
        if user_info
        else CREATOR_NOTE_MANAGER_HEADER_ORDER
    )
    return ordered_wire_headers(
        headers,
        order=order,
        cookies=cookies,
        accept_encoding=CREATOR_ACCEPT_ENCODING,
    )


class XHS_Creator_Apis:
    """创作者中心 API；鉴权和动态签名材料只从 ``XHSCreatorAuth`` 获取。

    ``auth`` 只能由以下三个入口创建：

    - ``XHSCreatorAuth.from_cookie(完整 Creator Cookie)``
    - ``XHSCreatorAuth.from_qrcode_login()``
    - ``XHSCreatorAuth.from_phone_login()``
    - ``XHSCreatorAuth.from_pc_auth(pc_auth)``（统一登录后的 Creator 视图）

    业务方法不再散传 Cookie、a1、b1、dsl。b1、MNS、X-s、X-t、
    X-S-Common、trace id 和 Cookie 生命周期均由 Auth 内部维护。
    """

    def __init__(self, auth: XHSCreatorAuth):
        if not isinstance(auth, XHSCreatorAuth):
            raise TypeError(
                'XHS_Creator_Apis 仅支持 XHSCreatorAuth；请使用 '
                'from_cookie()、from_qrcode_login() 或 from_phone_login() 创建'
            )
        auth.validate(require_authenticated=True)
        self.auth = auth
        self.http = auth.http_client
        self.base_url = auth.origin('api')
        self.upload_url = auth.origin('upload')
        self.edith_url = auth.origin('edith')
        self.xhs_web_url = auth.origin('public_web')
        self._note_manager_signed = False

    def _proxies(self, proxies=None):
        return proxies if proxies is not None else self.auth.proxies

    def _request_params(
        self,
        api,
        data='',
        method='POST',
        *,
        referer=None,
        sec_fetch_site='same-site',
        b1_profile=None,
        b1_value=None,
        mns_profile=None,
        target_origin=None,
        order_wire_headers=True,
    ):
        """为 Creator 请求获取 Relay 签名并组装线上请求头、Cookie 与紧凑 body。"""
        # The publish document keeps one page-level b1 snapshot across all
        # XHRs.  Reusing the named login snapshot prevents each API call from
        # emitting a subtly different x8/x9 pair in X-S-Common.
        if b1_profile is None:
            b1_profile = 'login'
        web_origin = self.auth.origin('web')
        headers, cookies, body = generate_request_params(
            self.auth,
            api,
            data,
            method,
            b1_profile=b1_profile,
            b1_value=b1_value,
            mns_profile=mns_profile,
            origin=web_origin,
            referer=referer or f'{web_origin}/',
            sec_fetch_site=sec_fetch_site,
            # 浏览器 XHR 一律不带 sec-ch-ua*（2026-07-25 实证），仅导航请求保留。
            include_client_hints=False,
        )
        target = (target_origin or self.base_url) + api
        wire_cookies = self.auth.cookies_for_url(target, cookies)
        if target.startswith(self.base_url):
            # Current publish-tab Cookie order (Chrome 152).  In particular,
            # creator.xiaohongshu.com's host-only acw_tc sits between the
            # page release fields and websectiga/sec_poison_id; flattening it
            # at the end produces a different edge fingerprint.
            wire_cookies = {
                **{
                    name: wire_cookies[name]
                    for name in CREATOR_PUBLISH_COOKIE_ORDER
                    if name in wire_cookies
                },
                **{
                    name: value
                    for name, value in wire_cookies.items()
                    if name not in CREATOR_PUBLISH_COOKIE_ORDER
                },
            }
        if order_wire_headers:
            headers = build_creator_business_headers(
                headers,
                wire_cookies,
                method=method,
            )
        headers['user-agent'] = CREATOR_CURRENT_BROWSER_UA
        return headers, wire_cookies, body

    def bootstrap(self, proxies=None):
        """调用浏览器同款 ``user/info`` 验收 Creator 登录态。"""
        success, msg, _ = self.get_user_info(proxies=proxies)
        if not success:
            raise RuntimeError(f'Creator bootstrap user/info failed: {msg}')
        return self

    def get_user_info(self, proxies=None):
        res_json = None
        try:
            api = '/api/galaxy/user/info'
            headers, cookies, _ = self._request_params(
                api,
                '',
                'GET',
                referer=CREATOR_NOTE_MANAGER_REFERER,
                sec_fetch_site='same-origin',
                b1_profile='login',
                mns_profile='publish_user_info',
            )
            headers['cache-control'] = 'no-cache'
            headers['pragma'] = 'no-cache'
            wire_headers = _creator_note_manager_headers(
                headers,
                cookies,
                user_info=True,
            )
            response = self.http.get(
                self.base_url + api,
                headers=wire_headers,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            # The publish navigation receives creator.xiaohongshu.com's
            # host-scoped acw_tc from this response.  Keep it in Auth's
            # HostCookieStore so the immediately following permit/upload
            # requests match the browser Cookie scope.
            self.auth.update_cookies(
                getattr(response, 'cookies', {}),
                source_url=self.base_url + api,
            )
            res_json = response.json()
            success = bool(res_json.get('success'))
            msg = res_json.get('msg') or ('成功' if success else '登录态无效')
        except Exception as error:
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def get_topic(self, keyword, proxies=None):
        try:
            api = "/web_api/sns/v1/search/topic"
            data = {
                "keyword": keyword,
                "suggest_topic_request": {
                    "title": "",
                    "desc": f"#{keyword}",
                },
                "page": {
                    "page_size": 20,
                    "page": 1,
                },
            }
            headers, cookies, body = self._request_params(
                api,
                data,
                'POST',
                target_origin=self.edith_url,
            )
            response = self.http.post(
                self.edith_url + api,
                headers=headers,
                cookies=cookies,
                data=body.encode('utf-8'),
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as error:
            res_json = None
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def get_location_info(self, keyword, proxies=None):
        try:
            data = get_loc_data(keyword)
            api = "/web_api/sns/v1/local/poi/creator/search"
            headers, cookies, body = self._request_params(
                api,
                data,
                'POST',
                target_origin=self.edith_url,
            )
            response = self.http.post(
                self.edith_url + api,
                headers=headers,
                cookies=cookies,
                data=body.encode('utf-8'),
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as error:
            res_json = None
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    # media_type: image or video
    def get_fileIds(self, media_type, proxies=None):
        api = "/api/media/v1/upload/creator/permit"
        params = get_fileIds_params(media_type)
        splice_api = splice_str(api, params)
        last_response = None
        last_json = None
        last_xt = None

        # The publish page occasionally receives the same edge rejection as
        # the post endpoint (HTTP 406 or JSON code=-1).  Rebuild the signed
        # headers on every attempt so x-t/x-s/MNS sequence are not replayed.
        for attempt in range(3):
            try:
                # Use the media permit request profile selected by Relay.
                permit_profile = (
                    'publish_permit_video'
                    if str(media_type).lower() == 'video'
                    else 'publish_permit_image'
                )
                headers, cookies, _ = self._request_params(
                    splice_api,
                    '',
                    'GET',
                    referer=CREATOR_PUBLISH_REFERER,
                    sec_fetch_site='same-origin',
                    mns_profile=permit_profile,
                    b1_profile='login',
                )
                last_xt = headers.get('x-t')
                response = self.http.get(
                    self.base_url + splice_api,
                    headers=headers,
                    cookies=cookies,
                    proxies=self._proxies(proxies),
                    timeout=REQUEST_TIMEOUT,
                )
                last_response = response
                # Keep any refreshed host-scoped acw_tc in the Auth jar.
                self.auth.update_cookies(
                    getattr(response, 'cookies', {}),
                    source_url=self.base_url + splice_api,
                )
                res_json = response.json()
                last_json = res_json
                if os.environ.get('XHS_CREATOR_DEBUG'):
                    logger.debug(
                        'Creator permit response: attempt={} http={} code={} '
                        'success={} permit_count={}',
                        attempt + 1,
                        getattr(response, 'status_code', None),
                        res_json.get('code'),
                        bool(res_json.get('success')),
                        len((res_json.get('data') or {}).get('uploadTempPermits') or []),
                    )
            except Exception as error:
                return False, _log_api_error(error), (last_json, last_xt)

            data = res_json.get('data') or {}
            result = data.get('result') or {}
            permits = data.get('uploadTempPermits') or []
            # Current responses expose success at the top level, while a few
            # gateway variants additionally mirror it under data.result.
            success = bool(res_json.get('success') or result.get('success'))
            if success and permits:
                return True, '获取fileIds成功', (res_json, last_xt)

            code = res_json.get('code', result.get('code'))
            status = getattr(last_response, 'status_code', None)
            retryable = status == 406 or code == -1
            message = (
                res_json.get('msg')
                or res_json.get('message')
                or result.get('msg')
                or result.get('message')
            )
            if retryable and attempt < 2:
                logger.warning(
                    f'发布许可被边缘拒绝（HTTP {status}, code={code}），'
                    f'重发 ({attempt + 1}/3)'
                )
                continue
            if not message:
                message = f'获取上传许可失败 (HTTP {status}, code={code})'
            return False, str(message), (res_json, last_xt)

        return False, '获取上传许可失败', (last_json, last_xt)

    def get_file_ids(self, media_type, proxies=None):
        """``get_fileIds`` 的 PEP 8 别名。"""
        return self.get_fileIds(media_type, proxies=proxies)

    def upload_media(self, path_or_file, media_type, proxies=None):
        res = {
            "fileIds": '',
            "width": '',
            "height": '',
            "video_id": '',
        }
        try:
            # 先读文件再申请上传许可，路径错误时不浪费许可额度。
            path_or_file = _load_media_bytes(path_or_file)
            success, msg, (data, xt) = self.get_fileIds(media_type, proxies=proxies)
            if not success:
                raise RuntimeError(msg)
            data = data['data']['uploadTempPermits'][0]
            upload_host = data.get('uploadAddr') or self.upload_url.replace('https://', '')
            upload_url = upload_host if upload_host.startswith('http') else f"https://{upload_host}"
            file_ids = data['fileIds'][0].split('/')[-1]
            expire_time = data['expireTime']
            token = data['token']
            res['fileIds'] = file_ids
            xt, expire_time = str(xt)[:10], str(expire_time)[:10]
            message = f"{xt};{expire_time}"
            if media_type == "image":
                width, height, file, file_size = self.get_file_info(
                    path_or_file,
                    media_type="image",
                )
                res['width'] = width
                res['height'] = height
                res['file_size'] = file_size
                res['mime_type'] = "image/png"
            else:
                file, file_size = self.get_file_info(path_or_file, media_type="video")
                res['file_size'] = file_size
            signature = signature_js.call(
                'getSignature',
                message,
                file_ids,
                file_size,
                upload_host,
            )
            headers = get_upload_media_headers(
                message,
                signature,
                token,
                user_agent=self.auth.profile.release['userAgent'],
                upload_host=upload_host,
            )
            api = f"/spectrum/{file_ids}"
            # ROS 上传域名不会收到 creator.xiaohongshu.com 的登录 Cookie。
            response = self.http.put(
                upload_url + api,
                headers=headers,
                data=file,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            if media_type == "video":
                res['video_id'] = response.headers.get('X-Ros-Video-Id')
                if not res['video_id']:
                    raise ValueError('upload response missing X-Ros-Video-Id')
        except Exception as error:
            return False, _log_api_error(error), None
        return True, "上传成功", res

    def query_transcode(self, video_id, proxies=None):
        res_json = None
        success, msg = False, ''
        try:
            api = "/web_api/sns/capa/postgw/query_transcode"
            params = {
                "video_id": str(video_id),
                "need_transcode": "false",
                "resource_type": "0",
            }
            splice_api = splice_str(api, params)
            # 当前转码查询沿用发布许可页的 0101/a1 签名档位。
            # 另需 www 侧 web_session（PC 登录签发），否则 401 无登录信息。
            headers, cookies, _ = self._request_params(
                splice_api,
                '',
                'GET',
                target_origin=self.edith_url,
                b1_profile='login',
                mns_profile='publish_permit',
            )
            response = self.http.get(
                self.edith_url + splice_api,
                headers=headers,
                cookies=cookies,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success = res_json["success"]
            if 'msg' in res_json:
                msg = res_json['msg']
        except Exception as error:
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def encryption(self, file_id, proxies=None):
        res_json = None
        success, msg = False, ''
        try:
            api = "/web_api/sns/v5/creator/file/encryption"
            params = {
                "file_id": file_id,
                "type": "image",
                "ts": str(int(time.time() * 1000)),
                "sign": sign_js.call('urlSing', file_id),
            }
            splice_api = splice_str(api, params)
            headers, cookies, _ = self._request_params(
                splice_api,
                '',
                'GET',
                target_origin=self.xhs_web_url,
            )
            response = self.http.get(
                self.xhs_web_url + splice_api,
                headers=headers,
                cookies=cookies,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success, msg = res_json["success"], res_json["msg"]
        except Exception as error:
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def post_note(self, noteInfo, proxies=None):
        """发布图文或视频笔记；登录和签名参数由 ``self.auth`` 自动提供。"""
        post_api = "/web_api/sns/v2/note"
        title = noteInfo.get('title', '')
        desc = noteInfo.get('desc', '')
        postTime = noteInfo.get('postTime')
        location = noteInfo.get('location')
        privacy_type = noteInfo.get('type', 1)
        media_type = noteInfo.get('media_type', 'image')

        if location is not None:
            success, msg, location_info = self.get_location_info(
                location,
                proxies=proxies,
            )
            if not success:
                raise RuntimeError(msg)
            poi_list = (location_info.get('data') or {}).get('poi_list') or []
            if len(poi_list) == 0:
                raise RuntimeError('未找到该地点')
            location = poi_list[0]
            post_loc = {
                "name": location['name'],
                "subname": location['full_address'],
                "poi_id": location['poi_id'],
                "poi_type": location['poi_type'],
            }
        else:
            post_loc = {}

        if media_type == 'video':
            video = noteInfo.get('video')
            if not video:
                raise ValueError('video media requires noteInfo["video"]')
            video = _load_media_bytes(video)
            cover, metadata = self.extract_video_cover_and_metadata(video)
            # Xiaobei's public CLI accepts an explicitly selected video cover.
            if noteInfo.get('cover'):
                cover = _load_media_bytes(noteInfo['cover'])
            success, msg, fileInfo = self.upload_media(video, media_type, proxies=proxies)
            if not success:
                raise RuntimeError(msg)
            success, msg, coverInfo = self.upload_media(cover, 'image', proxies=proxies)
            if not success:
                raise RuntimeError(msg)
            transcode_ready = False
            for _ in range(TRANSCODE_MAX_RETRIES):
                success, msg, res = self.query_transcode(
                    fileInfo['video_id'],
                    proxies=proxies,
                )
                if not success:
                    # query_transcode 需要 PC 侧 web_session（Creator 登录只发
                    # creator 系 Cookie，401 无登录信息）。2026-07-25 实证跳过
                    # 轮询直接发布可成功——服务端异步转码，等待仅为封面建议。
                    logger.warning(
                        f'转码查询不可用（{msg}），跳过等待直接发布'
                    )
                    transcode_ready = True
                    break
                data_info = res.get('data') or {}
                if (
                    data_info.get('hasFirstFrame') is True
                    or data_info.get('has_first_frame') is True
                    or data_info.get('firstFrameFileId')
                    or data_info.get('first_frame_file_id')
                    or data_info.get('status') in (2, 'success', 'SUCCESS')
                    or not data_info
                ):
                    transcode_ready = True
                    break
                time.sleep(TRANSCODE_RETRY_DELAY)
            if not transcode_ready:
                raise TimeoutError('video transcode not ready after polling')
            data = get_post_note_video_data(
                title,
                desc,
                postTime,
                post_loc,
                privacy_type,
                fileInfo,
                coverInfo,
                metadata,
            )
        else:
            fileInfos = []
            images = noteInfo.get('images') or []
            if not images:
                raise ValueError('image media requires noteInfo["images"]')
            for image in images:
                success, msg, fileInfo = self.upload_media(
                    image,
                    media_type,
                    proxies=proxies,
                )
                if not success:
                    raise RuntimeError(msg)
                fileInfos.append(fileInfo)
            data = get_post_note_image_data(
                title,
                desc,
                postTime,
                post_loc,
                privacy_type,
                fileInfos,
            )

        # 浏览器实抓（2026-07-25 reqid=5609）：未选地点时 common 里**不带**
        # post_loc 键；发空对象 {} 会被服务端以 参数错误(result=-9059) 打回。
        if not post_loc:
            data['common'].pop('post_loc', None)

        # Creator publish UI stores the selected declaration inside the JSON
        # string business_binds. "笔记含AI合成内容" is userDeclarationBind.origin=2.
        if noteInfo.get('ai_declaration'):
            business_binds = json.loads(data['common']['business_binds'])
            business_binds['userDeclarationBind'] = {'origin': 2}
            data['common']['business_binds'] = json.dumps(
                business_binds, ensure_ascii=False, separators=(',', ':'),
            )

        topics = noteInfo.get('topics') or []
        for topic in topics:
            success, msg, res_json = self.get_topic(topic, proxies=proxies)
            if not success:
                raise RuntimeError(msg)
            if len(res_json['data']['topic_info_dtos']) == 0:
                raise RuntimeError(f'未找到话题{topic}')
            topic_info = res_json['data']['topic_info_dtos'][0]
            insert_topic = {
                "id": topic_info['id'],
                "link": topic_info['link'],
                "name": topic_info['name'],
                "type": 'topic',
            }
            data['common']['hash_tag'].append(insert_topic)
            marker = f"#{insert_topic['name']}[话题]#"
            if marker not in data['common']['desc']:
                data['common']['desc'] += f" {marker} "

        # 浏览器实抓（2026-07-25 reqid=5609）：post_note 的 referer 是站点根路径
        # "https://creator.xiaohongshu.com/"，不是发布页完整 URL（fetch 封装层
        # 默认行为）；permit 请求才带发布页 URL。
        headers, cookies, body = self._request_params(
            post_api,
            data,
            'POST',
            referer=f'{self.base_url}/',
            target_origin=self.edith_url,
            order_wire_headers=False,
        )
        # Creator 发布请求需要独立的 Relay 签名配置。
        headers['x-rap-param'] = generate_x_rap_param(
            post_api,
            body,
            profile='creator',
        )
        # 本地接入只提交一次。code=-1 或响应丢失时，调用方先人工核对后台，
        # 避免在平台已经收单但回包异常时创建重复笔记。
        response = self.http.post(
            self.edith_url + post_api,
            headers=headers,
            data=body.encode('utf-8'),
            cookies=cookies,
            proxies=self._proxies(proxies),
            timeout=REQUEST_TIMEOUT,
        )
        res_json = response.json()
        # 成功响应为 {"result":0,"success":true,"msg":"",...}，部分响应缺 msg 字段
        success = bool(res_json.get("success"))
        msg = res_json.get("msg") or res_json.get("message") or (
            "成功" if success else "发布失败"
        )
        return success, msg, res_json

    def get_file_info(self, file, media_type="image"):
        file_size = len(file)
        if media_type == "image":
            cv2, np = _load_opencv()
            image = cv2.imdecode(np.frombuffer(file, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError('image decode failed')
            size = image.shape
            width, height = size[1], size[0]
            if width > 2 * height:
                height = int(width / 2)
            return width, height, file, file_size
        return file, file_size

    def extract_video_cover_and_metadata(self, video):
        cv2, _ = _load_opencv()
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as handle:
                handle.write(video)
                temp_path = handle.name

            cap = cv2.VideoCapture(temp_path)
            if not cap.isOpened():
                raise ValueError("video decode failed")

            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            duration_ms = int(frame_count / fps * 1000) if fps else 0
            success, frame = cap.read()
            cap.release()
            if not success:
                raise ValueError("video cover frame decode failed")

            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise ValueError("video cover encode failed")

            metadata = {
                "video": {
                    "bitrate": None,
                    "colour_primaries": "BT.709",
                    "duration": duration_ms,
                    "format": "AVC",
                    "frame_rate": round(fps, 3) if fps else 0,
                    "height": height,
                    "matrix_coefficients": "BT.709",
                    "rotation": 0,
                    "transfer_characteristics": "BT.709",
                    "width": width,
                },
                "audio": {
                    "bitrate": None,
                    "channels": 2,
                    "duration": duration_ms,
                    "format": "AAC",
                    "sampling_rate": 48000,
                },
            }
            return encoded.tobytes(), metadata
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    # # page: 页数
    # # time: 最近几天的时间
    # def get_publish_note_info(self, page: int, time: int, proxies=None):
    #     success = False
    #     msg = '成功'
    #     res_json = None
    #     try:
    #         api = "/api/galaxy/creator/data/note_stats/new"
    #         params = {
    #             "page": str(page),
    #             "page_size": "12",
    #             "sort_by": "time",
    #             "note_type": "0",
    #             "time": str(time),
    #             "is_recent": "false",
    #         }
    #         splice_api = splice_str(api, params)
    #         headers, cookies, _ = self._request_params(
    #             splice_api, '', 'GET',
    #             referer=CREATOR_HOME_REFERER,
    #             sec_fetch_site='same-origin',
    #         )
    #         response = self.http.get(
    #             self.base_url + splice_api,
    #             headers=headers,
    #             cookies=cookies,
    #             proxies=self._proxies(proxies),
    #             timeout=REQUEST_TIMEOUT,
    #         )
    #         res_json = response.json()
    #         success = res_json["success"]
    #     except Exception as error:
    #         success, msg = False, _log_api_error(error)
    #     return success, msg, res_json
    #
    #
    # # 获取全部的发布信息
    # def get_all_publish_note_info(self, proxies=None):
    #     page = 1
    #     time = 7
    #     success, msg, res_json = self.get_publish_note_info(page, time, proxies)
    #     if not success:
    #         return False, msg, None
    #     notes = res_json['data']['note_infos']
    #     total = res_json['data']['total']
    #     while len(notes) < total:
    #         page += 1
    #         success, msg, res_json = self.get_publish_note_info(page, time, proxies)
    #         if not success:
    #             return False, msg, None
    #         notes += res_json['data']['note_infos']
    #     return True, '成功', notes

    def get_posted_notes_page(self, page=0, tab=0, proxies=None):
        """获取 Creator 笔记管理页的一页已发布作品。

        当前页面首请求固定传 ``page=0``；响应 ``data.page`` 是下一页游标，
        ``-1`` 表示结束。签名使用作品管理页对应的 Relay 配置。
        """
        res_json = None
        try:
            api = "/api/galaxy/v2/creator/note/user/posted"
            params = {
                "tab": str(int(tab)),
                "page": str(int(page if page is not None else 0)),
            }
            splice_api = splice_str(api, params)
            mns_profile = (
                'note_manager_steady'
                if self._note_manager_signed
                else 'note_manager'
            )
            headers, cookies, _ = self._request_params(
                splice_api,
                '',
                'GET',
                referer=CREATOR_NOTE_MANAGER_REFERER,
                sec_fetch_site='same-origin',
                b1_profile='note_manager',
                mns_profile=mns_profile,
            )
            self._note_manager_signed = True
            wire_headers = _creator_note_manager_headers(
                headers,
                self.auth.cookies_for_url(self.base_url + splice_api, cookies),
            )
            response = self.http.get(
                self.base_url + splice_api,
                headers=wire_headers,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success = bool(res_json.get('success'))
            if success:
                msg = res_json.get('msg') or '成功'
            else:
                code = res_json.get('code', 'unknown')
                status = getattr(response, 'status_code', 'unknown')
                msg = res_json.get('msg') or res_json.get('message') or (
                    f'获取作品列表失败 (HTTP {status}, code={code})'
                )
        except Exception as error:
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def _get_analytics(self, path, referer, proxies=None):
        """签名读取创作者数据分析页；返回与作品管理页相同的三元组。"""
        res_json = None
        try:
            headers, cookies, _ = self._request_params(
                path, '', 'GET', referer=referer,
                sec_fetch_site='same-origin',
                b1_profile='note_manager', mns_profile='note_manager',
            )
            wire_headers = _creator_note_manager_headers(
                headers,
                self.auth.cookies_for_url(self.base_url + path, cookies),
            )
            response = self.http.get(
                self.base_url + path,
                headers=wire_headers,
                proxies=self._proxies(proxies),
                timeout=REQUEST_TIMEOUT,
            )
            res_json = response.json()
            success = bool(res_json.get('success'))
            msg = res_json.get('msg') or res_json.get('message') or (
                '成功' if success else f'数据分析读取失败 (HTTP {response.status_code})'
            )
        except Exception as error:
            success, msg = False, _log_api_error(error)
        return success, msg, res_json

    def get_note_analyze_page(self, page_num=1, page_size=10, proxies=None):
        path = (
            '/api/galaxy/creator/datacenter/note/analyze/list'
            f'?type=0&page_size={int(page_size)}&page_num={int(page_num)}'
        )
        return self._get_analytics(path, CREATOR_ANALYTICS_REFERER, proxies)

    def get_note_analytics_base(self, note_id, proxies=None):
        from urllib.parse import quote

        encoded_id = quote(str(note_id), safe='')
        path = f'/api/galaxy/creator/datacenter/note/base?note_id={encoded_id}'
        referer = f'https://creator.xiaohongshu.com/statistics/note-detail?noteId={encoded_id}'
        return self._get_analytics(path, referer, proxies)

    def get_note_audience_portrait(self, note_id, proxies=None):
        from urllib.parse import quote

        encoded_id = quote(str(note_id), safe='')
        path = (
            '/api/galaxy/creator/datacenter/note/audience/source/detail'
            f'?note_id={encoded_id}'
        )
        referer = f'https://creator.xiaohongshu.com/statistics/note-detail?noteId={encoded_id}'
        return self._get_analytics(path, referer, proxies)

    def get_publish_note_info(self, page=0, proxies=None):
        """兼容旧方法名；等价于 :meth:`get_posted_notes_page`."""
        return self.get_posted_notes_page(page=page, proxies=proxies)

    def get_all_posted_notes(self, tab=0, proxies=None):
        """按服务端游标获取全部已发布作品，返回扁平 notes 列表。"""
        page = 0
        notes = []
        seen_pages = set()
        while True:
            if page in seen_pages:
                return False, f'作品列表返回重复分页游标: {page}', notes
            seen_pages.add(page)
            success, msg, res_json = self.get_posted_notes_page(
                page=page,
                tab=tab,
                proxies=proxies,
            )
            if not success:
                return False, msg, notes
            data = (res_json or {}).get('data') or {}
            page_notes = data.get('notes') or []
            if not isinstance(page_notes, list):
                return False, '作品列表 data.notes 不是数组', notes
            notes.extend(page_notes)
            next_page = data.get('page', -1)
            try:
                page = int(next_page)
            except (TypeError, ValueError):
                return False, f'作品列表分页游标无效: {next_page!r}', notes
            if page == -1:
                break
        return True, '成功', notes

    def get_all_publish_note_info(self, proxies=None):
        """兼容旧方法名；等价于 :meth:`get_all_posted_notes`."""
        return self.get_all_posted_notes(proxies=proxies)


XHSCreatorApis = XHS_Creator_Apis


__all__ = ['XHS_Creator_Apis', 'XHSCreatorApis']
