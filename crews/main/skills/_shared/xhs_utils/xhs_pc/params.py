from xhs_utils.relay import compute
import json
import math
import os
import random
import time
import uuid
from urllib.parse import urlencode

from xhs_utils.cookie_util import trans_cookies
from xhs_utils.xhs_core.http import ordered_wire_headers


PC_LOGIN_ACCEPT_LANGUAGE = 'zh-CN,zh;q=0.9'
PC_BUSINESS_ACCEPT_LANGUAGE = 'zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7,ja;q=0.6'
PC_SEC_CH_UA = (
    '"Not;A=Brand";v="8", "Chromium";v="152", '
    '"Google Chrome";v="152"'
)

PC_CURRENT_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
)

PC_NAVIGATION_HEADER_ORDER = (
    'upgrade-insecure-requests', 'user-agent', 'sec-ch-ua',
    'sec-ch-ua-mobile', 'sec-ch-ua-platform', 'accept', 'accept-encoding',
    'accept-language', 'cookie', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-user',
)
PC_HONEYPOT_HEADER_ORDER = (
    'sec-ch-ua-platform', 'referer', 'user-agent', 'accept', 'sec-ch-ua',
    'content-type', 'sec-ch-ua-mobile', 'accept-encoding', 'accept-language',
    'cookie', 'origin', 'priority', 'sec-fetch-dest', 'sec-fetch-mode',
    'sec-fetch-site',
)
PC_SECURITY_HEADER_ORDER = (
    'sec-ch-ua-platform', 'referer', 'sec-ch-ua', 'sec-ch-ua-mobile',
    'x-t', 'x-s-common', 'user-agent', 'accept', 'content-type', 'x-s',
    'accept-encoding', 'accept-language', 'cookie', 'origin', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
PC_SEM_HEADER_ORDER = (
    'sec-ch-ua-platform', 'referer', 'sec-ch-ua', 'sec-ch-ua-mobile',
    'x-t', 'x-s-common', 'user-agent', 'accept', 'x-s', 'accept-encoding',
    'accept-language', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
PC_SIGNED_POST_HEADER_ORDER = (
    'sec-ch-ua-platform', 'referer', 'sec-ch-ua', 'x-xray-traceid',
    'sec-ch-ua-mobile', 'x-t', 'x-b3-traceid', 'x-s-common',
    'user-agent', 'accept', 'content-type', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
PC_SIGNED_GET_HEADER_ORDER = (
    'sec-ch-ua-platform', 'referer', 'sec-ch-ua', 'x-xray-traceid',
    'sec-ch-ua-mobile', 'x-t', 'x-b3-traceid', 'x-s-common',
    'user-agent', 'accept', 'x-s', 'accept-encoding', 'accept-language',
    'cookie', 'origin', 'priority', 'sec-fetch-dest', 'sec-fetch-mode',
    'sec-fetch-site',
)
PC_BUSINESS_SIGNED_POST_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid', 'x-s-common',
    'user-agent', 'accept', 'content-type', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
PC_BUSINESS_SIGNED_GET_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid', 'x-s-common',
    'user-agent', 'accept', 'x-s', 'accept-encoding', 'accept-language',
    'cookie', 'origin', 'priority', 'sec-fetch-dest', 'sec-fetch-mode',
    'sec-fetch-site',
)
PC_BUSINESS_CDEVICE_GET_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'c_device_id', 'x-t', 'x-b3-traceid',
    'x-s-common', 'user-agent', 'accept', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
PC_LIVE_POST_HEADER_ORDER = (
    'referer', 'xy-common-params', 'x-t', 'x-s-common',
    'x-ratelimit-meta', 'accept', 'content-type', 'x-s', 'user-agent',
    'accept-encoding', 'accept-language', 'cookie', 'origin', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
PC_LIVE_GET_HEADER_ORDER = (
    'referer', 'xy-common-params', 'x-t', 'x-s-common',
    'x-ratelimit-meta', 'accept', 'x-s', 'user-agent', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
PC_RAP_POST_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid', 'x-s-common',
    'x-rap-param', 'accept', 'content-type', 'x-s', 'user-agent',
    'accept-encoding', 'accept-language', 'cookie', 'origin', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
PC_XY_RAP_POST_HEADER_ORDER = (
    # Chrome's homefeed/feed requests place the sharding header first.
    'xy-direction', 'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid',
    'x-s-common', 'x-rap-param', 'accept', 'content-type', 'x-s',
    'user-agent', 'accept-encoding', 'accept-language', 'cookie', 'origin',
    'priority', 'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
PC_RAP_GET_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid', 'x-s-common',
    'x-rap-param', 'user-agent', 'accept', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)


def resolve_mns_tier(api: str, fingerprint_ready: bool = True) -> str:
    return str(compute('pc', 'resolve-tier', {
        'api': api, 'fingerprint_ready': fingerprint_ready,
    })['tier'])


def generate_x_b3_traceid(len=16):
    return str(compute('pc', 'trace-id', {'kind': 'b3', 'length': len})['value'])

_BASE36_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"

def _int_to_base36(value):
    if value == 0:
        return "0"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = _BASE36_CHARS[remainder] + result
    return result

def generate_search_id(root_search_id=None):
    if root_search_id:
        return root_search_id
    timestamp_ms = int(time.time() * 1000)
    random_part = math.ceil(0x7ffffffe * random.random())
    return _int_to_base36((timestamp_ms << 64) + random_part)

def generate_search_request_id():
    timestamp_ms = int(time.time() * 1000)
    random_part = math.ceil(0x7ffffffe * random.random())
    return f"{random_part}-{timestamp_ms}"


def generate_search_session_id():
    """Current `/v2/search/notes` session_id is a UUIDv4.

    This is distinct from the legacy numeric `request_id` used by user search.
    """
    return str(uuid.uuid4())


def generate_xs(
    a1, api, data='', method='POST', *, cookie='', tier=None,
    sign_context=None,
):
    """Generate X-s/X-t for endpoints that do not send X-S-Common.

    蒲公英等接口只携带 X-s/X-t，因此不应伪造 b1 或 dsl_pair。MNS 环境和
    会话计数仍必须由 PcDeviceProfile.next_sign_context() 显式提供。
    """
    del method  # method does not participate in the current browser signer
    if not cookie or 'a1=' not in cookie:
        raise ValueError('generate_xs: cookie 须含 a1')
    if not sign_context:
        raise ValueError('generate_xs: sign_context 必传')
    from .runtime import run_signer

    resolved_tier = tier or sign_context.get('tier') or resolve_mns_tier(api)
    result = run_signer(
        api,
        data,
        a1=a1,
        cookie=cookie,
        b1='',
        dsl_pair='',
        tier=resolved_tier,
        sign_context=sign_context,
    )
    if not result or not result.get('xs') or not result.get('xt'):
        raise RuntimeError('OFB Relay PC 签名响应不完整')
    return result['xs'], result['xt']

def generate_xs_xs_common(
    a1, api, data='', method='POST', b1=None, dsl_pair=None, cookie='', tier=None,
    sign_context=None,
):
    """Request signed headers from OFB Relay."""
    if not cookie or 'a1=' not in cookie:
        raise ValueError('generate_xs_xs_common: cookie(document.cookie 含 a1) 必传')
    if b1 is None:
        raise ValueError('generate_xs_xs_common: b1 必须显式传入（允许空字符串）')
    if not dsl_pair or ';' not in str(dsl_pair):
        raise ValueError('generate_xs_xs_common: dsl_pair 必传，格式 dsllt;_dsl')

    from .runtime import run_signer
    if not sign_context:
        raise ValueError('generate_xs_xs_common: sign_context 必传（PcDeviceProfile 会话状态）')
    tier = tier or sign_context.get('tier') or resolve_mns_tier(api)
    relay_result = run_signer(
        api, data, a1=a1, cookie=cookie, b1=b1, dsl_pair=dsl_pair, tier=tier,
        sign_context=sign_context,
    )
    if not relay_result or not relay_result.get('xs') or not relay_result.get('xt'):
        raise RuntimeError('OFB Relay PC 签名响应不完整')
    xs = relay_result['xs']
    xt = relay_result['xt']
    xs_common = relay_result.get('xs_common')
    if not xs_common:
        raise RuntimeError('OFB Relay PC 签名响应缺少 x-s-common')
    return xs, xt, xs_common

def generate_xray_traceid():
    return str(compute('pc', 'trace-id', {'kind': 'xray'})['value'])

def generate_x_rap_param(api, data, app_id=None, fingerprint_hex: str = '', profile: str = 'pc'):
    body = data if isinstance(data, str) else json.dumps(data or {}, ensure_ascii=False)
    result = compute(profile, 'rap', {
        'api': api, 'body': body, 'app_id': app_id,
        'fingerprint_hex': fingerprint_hex,
    })
    return str(result['x_rap_param'])

def get_common_headers():
    return {
        'upgrade-insecure-requests': '1',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/152.0.0.0 Safari/537.36'
        ),
        'sec-ch-ua': PC_SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,'
            'image/avif,image/webp,image/apng,*/*;q=0.8,'
            'application/signed-exchange;v=b3;q=0.7'
        ),
        'accept-language': PC_LOGIN_ACCEPT_LANGUAGE,
        'priority': 'u=0, i',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
    }
def generate_xy_direction(user_id: str) -> int:
    if not user_id:
        return 0
    return int(compute('pc', 'xy-direction', {'user_id': user_id})['value'])


def get_request_headers_template(
    sign_context=None,
    *,
    method='POST',
    accept_language=PC_BUSINESS_ACCEPT_LANGUAGE,
    has_body=None,
    include_client_hints=True,
    include_trace_headers=True,
):
    context = sign_context or {}
    user_agent = context.get(
        'userAgent',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36',
    )
    headers = {
        'referer': 'https://www.xiaohongshu.com/',
        'x-t': '',
        'x-s-common': '',
        'user-agent': user_agent,
        'accept': 'application/json, text/plain, */*',
        'x-s': '',
        'accept-language': str(accept_language),
        'origin': 'https://www.xiaohongshu.com',
        'priority': 'u=1, i',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
    }
    if include_trace_headers:
        headers['x-xray-traceid'] = context.get('xXrayTraceId') or generate_xray_traceid()
        headers['x-b3-traceid'] = ''
    if include_client_hints:
        headers['sec-ch-ua-platform'] = '"Windows"'
        headers['sec-ch-ua'] = context.get('secChUa', PC_SEC_CH_UA)
        headers['sec-ch-ua-mobile'] = '?0'
    if has_body is None:
        has_body = str(method).upper() != 'GET'
    if has_body:
        headers['content-type'] = 'application/json;charset=UTF-8'
    return headers


def build_pc_navigation_headers(headers, cookies=None):
    return ordered_wire_headers(
        headers,
        order=PC_NAVIGATION_HEADER_ORDER,
        cookies=cookies,
        optional=('cookie',),
    )


def build_pc_login_headers(headers, cookies=None, *, kind='post'):
    if kind == 'honeypot':
        order = PC_HONEYPOT_HEADER_ORDER
    elif kind == 'security':
        order = PC_SECURITY_HEADER_ORDER
    elif kind == 'sem':
        order = PC_SEM_HEADER_ORDER
    elif kind == 'get':
        order = PC_SIGNED_GET_HEADER_ORDER
    elif kind == 'get-login-mode':
        order = (
            'sec-ch-ua-platform', 'x-login-mode',
        ) + PC_SIGNED_GET_HEADER_ORDER[1:]
    else:
        order = PC_SIGNED_POST_HEADER_ORDER
    if 'content-type' not in {str(key).lower() for key in headers}:
        order = tuple(key for key in order if key != 'content-type')
    return ordered_wire_headers(headers, order=order, cookies=cookies)


def build_pc_business_headers(headers, cookies, *, api, method='POST'):
    upper_method = str(method).upper()
    has_rap = 'x-rap-param' in {str(key).lower() for key in headers}
    has_xy = 'xy-direction' in {str(key).lower() for key in headers}
    has_client_hints = 'sec-ch-ua-platform' in {str(key).lower() for key in headers}
    has_device_header = 'c_device_id' in {str(key).lower() for key in headers}
    if not has_client_hints and has_device_header:
        order = PC_BUSINESS_CDEVICE_GET_HEADER_ORDER
    elif not has_client_hints and has_xy:
        order = PC_XY_RAP_POST_HEADER_ORDER
    elif not has_client_hints and has_rap and upper_method == 'GET':
        order = PC_RAP_GET_HEADER_ORDER
    elif not has_client_hints and has_rap:
        order = PC_RAP_POST_HEADER_ORDER
    elif not has_client_hints and not has_rap and not has_xy:
        order = (
            PC_BUSINESS_SIGNED_GET_HEADER_ORDER
            if upper_method == 'GET'
            else PC_BUSINESS_SIGNED_POST_HEADER_ORDER
        )
    elif has_xy:
        order = PC_XY_RAP_POST_HEADER_ORDER
    elif has_rap and upper_method == 'GET':
        order = PC_RAP_GET_HEADER_ORDER
    elif has_rap:
        order = PC_RAP_POST_HEADER_ORDER
    elif upper_method == 'GET':
        order = PC_SIGNED_GET_HEADER_ORDER
    else:
        order = PC_SIGNED_POST_HEADER_ORDER
    if 'content-type' not in {str(key).lower() for key in headers}:
        order = tuple(key for key in order if key != 'content-type')
    # Message-page bootstrap captures include these cache controls in this
    # exact relative position.
    lower_keys = {str(key).lower() for key in headers}
    order = list(order)
    if 'cache-control' in lower_keys and 'cache-control' not in order:
        anchor = order.index('cookie') if 'cookie' in order else order.index('origin')
        order.insert(anchor, 'cache-control')
    if 'pragma' in lower_keys and 'pragma' not in order:
        anchor = order.index('priority') if 'priority' in order else len(order)
        order.insert(anchor, 'pragma')
    return ordered_wire_headers(
        headers,
        order=tuple(order),
        cookies=cookies,
    )


def build_pc_live_headers(headers, cookies, *, method='POST'):
    """Build the separate live-room header contract captured in Chrome.

    Live-room requests currently omit client-hint and trace headers.  The
    live page places ``xy-common-params`` immediately after the referer and
    ``x-ratelimit-meta`` before ``accept``.
    """
    order = PC_LIVE_GET_HEADER_ORDER if str(method).upper() == 'GET' else PC_LIVE_POST_HEADER_ORDER
    if 'content-type' not in {str(key).lower() for key in headers}:
        order = tuple(key for key in order if key != 'content-type')
    return ordered_wire_headers(
        headers,
        order=order,
        cookies=cookies,
        optional=('xy-common-params', 'x-ratelimit-meta'),
    )

def generate_headers(
    a1, api, data='', method='POST', user_id: str = '', cookie: str = '',
    b1=None, dsl_pair=None, with_xy_direction: bool = False,
    tier=None, sign_context=None,
    include_client_hints=True, include_trace_headers=True,
):
    # user_id 用于可选 xy-direction；签名材料仍强制在 generate_xs_xs_common / generate_request_params 校验
    xs, xt, xs_common = generate_xs_xs_common(
        a1, api, data, method, b1=b1, dsl_pair=dsl_pair, cookie=cookie, tier=tier,
        sign_context=sign_context,
    )
    x_b3_traceid = (sign_context or {}).get('xB3TraceId') or generate_x_b3_traceid()
    headers = get_request_headers_template(
        sign_context,
        method=method,
        has_body=data not in ('', None),
        include_client_hints=include_client_hints,
        include_trace_headers=include_trace_headers,
    )
    headers['x-s'] = xs
    headers['x-t'] = str(xt)
    headers['x-s-common'] = xs_common
    headers['x-b3-traceid'] = x_b3_traceid
    # 浏览器实抓：仅 homefeed / feed 带 xy-direction
    if with_xy_direction:
        if not user_id:
            raise ValueError('generate_headers: 该接口需要 xy-direction，user_id 必传')
        headers['xy-direction'] = str(generate_xy_direction(user_id))
    if data == '' or data is None:
        data = ''
    elif isinstance(data, str):
        data = data
    else:
        data = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return headers, data

def generate_request_params(
    cookies_str, api, data='', method='POST', user_id: str = '', b1=None,
    dsl_pair=None, doc_cookie: str = '', with_xy_direction: bool = False,
    tier=None, sign_context=None,
    include_client_hints=True, include_trace_headers=True,
):
    # Network Cookie 已含 a1 时可直接复用，不必再传一份 document.cookie
    sign_cookie = doc_cookie or cookies_str
    if not sign_cookie or 'a1=' not in sign_cookie:
        raise ValueError('generate_request_params: cookies 须含 a1（Network Cookie 或 document.cookie）')
    if b1 is None:
        raise ValueError('generate_request_params: b1 必须显式传入（允许空字符串）')
    if not dsl_pair or ';' not in str(dsl_pair):
        raise ValueError('generate_request_params: dsl_pair 必传')
    # user_id 仅在需要 xy-direction 时强制；其余接口可后置 bootstrap
    if with_xy_direction and not user_id:
        raise ValueError('generate_request_params: 该接口需要 xy-direction，user_id 必传')
    cookies = trans_cookies(cookies_str)
    if 'a1' not in cookies:
        raise ValueError('generate_request_params: cookies_str 须含 a1')
    a1 = cookies['a1']
    headers, data = generate_headers(
        a1, api, data, method, user_id=user_id,
        cookie=sign_cookie, b1=b1, dsl_pair=dsl_pair,
        with_xy_direction=with_xy_direction, tier=tier, sign_context=sign_context,
        include_client_hints=include_client_hints,
        include_trace_headers=include_trace_headers,
    )
    return headers, cookies, data

def splice_str(api, params):
    return api + '?' + urlencode(
        {key: '' if value is None else value for key, value in params.items()},
        doseq=True
    )


__all__ = [
    'resolve_mns_tier',
    'generate_x_b3_traceid',
    'generate_search_id',
    'generate_search_request_id',
    'generate_search_session_id',
    'generate_xs',
    'generate_xs_xs_common',
    'generate_xray_traceid',
    'generate_x_rap_param',
    'get_common_headers',
    'PC_LOGIN_ACCEPT_LANGUAGE',
    'PC_BUSINESS_ACCEPT_LANGUAGE',
    'PC_SEC_CH_UA',
    'PC_CURRENT_BROWSER_UA',
    'build_pc_navigation_headers',
    'build_pc_login_headers',
    'build_pc_business_headers',
    'build_pc_live_headers',
    'generate_xy_direction',
    'get_request_headers_template',
    'generate_headers',
    'generate_request_params',
    'splice_str',
]
