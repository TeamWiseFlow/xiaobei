"""Creator request signing and browser-shaped headers."""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING
from urllib.parse import urlencode

from xhs_utils.xhs_core.params import (
    generate_x_b3_traceid,
    generate_xray_traceid,
)
from xhs_utils.xhs_core.http import ordered_wire_headers

from .runtime import run_signer

if TYPE_CHECKING:
    from .auth import XHSCreatorAuth
    from .state import CreatorDeviceProfile


CREATOR_SEC_CH_UA = (
    '"Not;A=Brand";v="8", "Chromium";v="152", '
    '"Google Chrome";v="152"'
)
CREATOR_CURRENT_BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
)
# Chrome 152's XHR/fetch requests on the Creator publish page use the short
# language list.  The longer list is only observed on the cross-origin media
# PUT upload and must not be reused for signed Creator API requests.
CREATOR_ACCEPT_LANGUAGE = 'zh-CN,zh;q=0.9'
CREATOR_NAVIGATION_HEADER_ORDER = (
    'upgrade-insecure-requests', 'user-agent', 'sec-ch-ua',
    'sec-ch-ua-mobile', 'sec-ch-ua-platform', 'accept', 'accept-encoding',
    'accept-language', 'cookie', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-user',
)
CREATOR_HONEYPOT_HEADER_ORDER = (
    'referer', 'user-agent', 'accept', 'content-type', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_REDCAPTCHA_HEADER_ORDER = (
    'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid', 'x-s-common',
    'user-agent', 'accept', 'content-type', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_SECURITY_HEADER_ORDER = (
    'authorization', 'referer', 'x-t', 'x-s-common', 'user-agent', 'accept',
    'content-type', 'x-s', 'accept-encoding', 'accept-language', 'cookie',
    'origin', 'priority', 'sec-fetch-dest', 'sec-fetch-mode',
    'sec-fetch-site',
)
CREATOR_SIGNED_GET_HEADER_ORDER = (
    'authorization', 'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid',
    'x-s-common', 'user-agent', 'accept', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_SIGNED_POST_HEADER_ORDER = (
    'authorization', 'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid',
    'x-s-common', 'user-agent', 'accept', 'content-type', 'x-s',
    'accept-encoding', 'accept-language', 'cookie', 'origin', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_CAS_GET_HEADER_ORDER = (
    'authorization', 'referer', 'x-t', 'x-s-common', 'user-agent', 'accept',
    'x-ratelimit-meta', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_CAS_POST_HEADER_ORDER = (
    'authorization', 'referer', 'x-t', 'x-s-common', 'user-agent', 'accept',
    'x-ratelimit-meta', 'content-type', 'x-s', 'accept-encoding',
    'accept-language', 'cookie', 'origin', 'priority', 'sec-fetch-dest',
    'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_CAS_GET_NO_RATE_HEADER_ORDER = (
    'authorization', 'referer', 'x-t', 'x-s-common', 'user-agent', 'accept',
    'x-s', 'accept-encoding', 'accept-language', 'cookie', 'origin', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)
CREATOR_CAS_POST_NO_RATE_HEADER_ORDER = (
    'authorization', 'referer', 'x-t', 'x-s-common', 'user-agent', 'accept',
    'content-type', 'x-s', 'accept-encoding', 'accept-language', 'cookie',
    'origin', 'priority', 'sec-fetch-dest', 'sec-fetch-mode',
    'sec-fetch-site',
)
CREATOR_LOGIN_USER_INFO_HEADER_ORDER = (
    'authorization', 'referer', 'x-xray-traceid', 'x-t', 'x-b3-traceid',
    'x-s-common', 'user-agent', 'accept', 'content-type', 'x-s',
    'accept-encoding', 'accept-language', 'cookie', 'priority',
    'sec-fetch-dest', 'sec-fetch-mode', 'sec-fetch-site',
)


def build_creator_navigation_headers(headers, cookies=None):
    return ordered_wire_headers(
        headers,
        order=CREATOR_NAVIGATION_HEADER_ORDER,
        cookies=cookies,
        optional=('cookie',),
    )


def build_creator_login_headers(headers, cookies=None, *, kind='security'):
    if kind == 'honeypot':
        order = CREATOR_HONEYPOT_HEADER_ORDER
    elif kind == 'redcaptcha':
        order = CREATOR_REDCAPTCHA_HEADER_ORDER
    elif kind == 'get':
        order = CREATOR_SIGNED_GET_HEADER_ORDER
    elif kind == 'cas-get':
        order = CREATOR_CAS_GET_HEADER_ORDER
    elif kind == 'cas-post':
        order = CREATOR_CAS_POST_HEADER_ORDER
    elif kind == 'cas-get-no-rate':
        order = CREATOR_CAS_GET_NO_RATE_HEADER_ORDER
    elif kind == 'cas-post-no-rate':
        order = CREATOR_CAS_POST_NO_RATE_HEADER_ORDER
    elif kind == 'login-user-info':
        order = CREATOR_LOGIN_USER_INFO_HEADER_ORDER
    else:
        order = CREATOR_SECURITY_HEADER_ORDER
    return ordered_wire_headers(headers, order=order, cookies=cookies)


def build_creator_business_headers(headers, cookies=None, *, method='GET'):
    """Apply the observed ordinary Header order for signed Creator APIs.

    Creator RAP publish requests are intentionally excluded because their
    complete current Header order has not been recaptured in this audit.
    """
    if 'x-rap-param' in {str(key).lower() for key in headers}:
        raise RuntimeError(
            'Creator RAP Header order is not verified by this builder'
        )
    order = (
        CREATOR_SIGNED_GET_HEADER_ORDER
        if str(method).upper() == 'GET'
        else CREATOR_SIGNED_POST_HEADER_ORDER
    )
    return ordered_wire_headers(headers, order=order, cookies=cookies)


def splice_str(api, params):
    """Creator CAS keeps the URL scheme colon unescaped in query values."""
    return api + '?' + urlencode(
        {key: '' if value is None else value for key, value in params.items()},
        doseq=True,
        safe=':',
    )


def get_request_headers_template(
    sign_context: dict | None = None,
    *,
    method: str = 'POST',
    origin: str = 'https://creator.xiaohongshu.com',
    referer: str = 'https://creator.xiaohongshu.com/',
    sec_fetch_site: str = 'same-site',
    include_client_hints: bool = True,
    include_trace_headers: bool = True,
    include_authorization: bool = True,
    include_origin: bool | None = None,
) -> dict:
    context = sign_context or {}
    headers = {
        'user-agent': context.get(
            'userAgent',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/152.0.0.0 Safari/537.36',
        ),
        'accept': 'application/json, text/plain, */*',
        'accept-language': CREATOR_ACCEPT_LANGUAGE,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': sec_fetch_site,
        'referer': referer,
        'priority': 'u=1, i',
    }
    if include_authorization:
        headers['authorization'] = ''
    if include_trace_headers:
        headers.update({
            'x-b3-traceid': context.get('xB3TraceId') or generate_x_b3_traceid(profile='creator'),
            'x-xray-traceid': context.get('xXrayTraceId') or generate_xray_traceid(profile='creator'),
        })
    if include_origin is None:
        include_origin = str(method).upper() != 'GET'
    if include_origin:
        headers['origin'] = origin
    if str(method).upper() != 'GET':
        headers['content-type'] = 'application/json'
    if include_client_hints:
        headers.update({
            'sec-ch-ua': context.get(
                'secChUa',
                CREATOR_SEC_CH_UA,
            ),
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        })
    return headers


def generate_request_params(
    auth: 'XHSCreatorAuth',
    api: str,
    data: Any = '',
    method: str = 'POST',
    *,
    tier: str | None = None,
    b1_profile: str | None = None,
    mns_profile: str | None = None,
    origin: str = 'https://creator.xiaohongshu.com',
    referer: str = 'https://creator.xiaohongshu.com/',
    sec_fetch_site: str = 'same-site',
    include_client_hints: bool = True,
    include_trace_headers: bool = True,
    include_authorization: bool = True,
    include_origin: bool | None = None,
    b1_value: str | None = None,
    dsl_pair_value: str | None = None,
) -> tuple[dict, dict, str]:
    """Return signed headers, Cookie mapping and compact wire body.

    ``method`` is passed through for request construction.
    """
    auth.validate(require_authenticated=True)
    auth.ensure_ds_material()
    return generate_profile_request_params(
        auth.profile,
        api,
        data,
        method,
        tier=tier,
        b1_profile=b1_profile,
        mns_profile=mns_profile,
        origin=origin,
        referer=referer,
        sec_fetch_site=sec_fetch_site,
        include_client_hints=include_client_hints,
        include_trace_headers=include_trace_headers,
        include_authorization=include_authorization,
        include_origin=include_origin,
        b1_value=b1_value,
        dsl_pair_value=dsl_pair_value,
    )


def generate_profile_request_params(
    profile: 'CreatorDeviceProfile',
    api: str,
    data: Any = '',
    method: str = 'POST',
    *,
    tier: str | None = None,
    b1_profile: str | None = None,
    mns_profile: str | None = None,
    origin: str = 'https://creator.xiaohongshu.com',
    referer: str = 'https://creator.xiaohongshu.com/',
    sec_fetch_site: str = 'same-site',
    include_client_hints: bool = True,
    include_trace_headers: bool = True,
    include_authorization: bool = True,
    include_origin: bool | None = None,
    b1_value: str | None = None,
    dsl_pair_value: str | None = None,
) -> tuple[dict, dict, str]:
    """Lower-level signer used during anonymous QR/SMS initialization."""
    cookies = profile.cookie_map
    if not cookies.get('a1'):
        raise ValueError('Creator profile Cookie must contain a1')
    context = profile.next_sign_context(tier=tier, mns_profile=mns_profile)
    b1 = (
        profile.current_b1(context['now'], profile_name=b1_profile)
        if b1_value is None
        else str(b1_value)
    )
    dsl_pair = (
        profile.dsl_pair(context['now'])
        if dsl_pair_value is None
        else str(dsl_pair_value)
    )
    result = run_signer(
        api,
        data,
        cookie='; '.join(f'{key}={value}' for key, value in cookies.items()),
        b1=b1,
        dsl_pair=dsl_pair,
        tier=context['tier'],
        sign_context=context,
    )
    headers = get_request_headers_template(
        context,
        method=method,
        origin=origin,
        referer=referer,
        sec_fetch_site=sec_fetch_site,
        include_client_hints=include_client_hints,
        include_trace_headers=include_trace_headers,
        include_authorization=include_authorization,
        include_origin=include_origin,
    )
    headers.update({
        'x-s': result['xs'],
        'x-t': str(result['xt']),
        'x-s-common': result['xs_common'],
    })
    if data == '' or data is None:
        body = ''
    elif isinstance(data, str):
        body = data
    else:
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return headers, cookies, body


def generate_xsc(
    auth: 'XHSCreatorAuth',
    api: str,
    data: Any = '',
    method: str = 'POST',
    **kwargs,
) -> dict:
    headers, _, _ = generate_request_params(auth, api, data, method, **kwargs)
    return {
        key: headers[key]
        for key in ('x-s', 'x-t', 'x-s-common', 'x-b3-traceid', 'x-xray-traceid')
    }


__all__ = [
    'generate_x_b3_traceid',
    'generate_xray_traceid',
    'splice_str',
    'get_request_headers_template',
    'CREATOR_SEC_CH_UA',
    'CREATOR_ACCEPT_LANGUAGE',
    'build_creator_navigation_headers',
    'build_creator_login_headers',
    'build_creator_business_headers',
    'generate_request_params',
    'generate_profile_request_params',
    'generate_xsc',
]
