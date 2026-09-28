"""Shared Chrome-impersonating HTTP transport for XHS web platforms.

The platform Auth objects own signing, Cookie state and request payloads. This
module only supplies a reusable curl_cffi Session with browser-like TLS/HTTP2
transport while keeping ordinary Headers and body bytes explicit.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from curl_cffi import requests as curl_requests


DEFAULT_IMPERSONATE = 'chrome146'
DEFAULT_ACCEPT_ENCODING = 'gzip, deflate, br, zstd'
DEFAULT_HTTP_VERSION = 'v2tls'


def _cookie_header(cookies: Any) -> str:
    if not cookies:
        return ''
    if isinstance(cookies, str):
        return cookies
    if isinstance(cookies, Mapping):
        return '; '.join(f'{key}={value}' for key, value in cookies.items())
    try:
        return '; '.join(f'{key}={value}' for key, value in cookies.items())
    except AttributeError as exc:
        raise TypeError('transport cookies must be a string or mapping') from exc


def ordered_wire_headers(
    headers: Optional[Mapping[str, Any]],
    *,
    order: tuple[str, ...] | list[str],
    cookies: Any = None,
    accept_encoding: str = DEFAULT_ACCEPT_ENCODING,
    strict: bool = True,
    optional: tuple[str, ...] | list[str] = (),
) -> dict[str, str]:
    """Inject Cookie/Accept-Encoding and enforce an observed Header contract.

    HTTP/2 pseudo headers and ``content-length`` remain libcurl's job.  The
    returned mapping owns the order of all ordinary browser-visible headers.
    """
    values = {
        str(key).lower(): str(value)
        for key, value in dict(headers or {}).items()
        if str(key).lower() != 'authority'
    }
    values.setdefault('accept-encoding', str(accept_encoding))
    cookie = _cookie_header(cookies)
    if cookie:
        values['cookie'] = cookie
    else:
        values.pop('cookie', None)

    normalized_order = tuple(str(key).lower() for key in order)
    optional_names = {str(key).lower() for key in optional}
    missing = [
        key for key in normalized_order
        if key not in values and key not in optional_names
    ]
    # Optional captured headers may be present in a route-specific request
    # without belonging to the shared canonical order.  Keep them after the
    # ordered fields rather than rejecting a valid Chrome capture.
    unexpected = sorted(set(values) - set(normalized_order) - optional_names)
    if missing or (strict and unexpected):
        raise RuntimeError(
            'wire header contract drifted: '
            f'missing={missing}, unexpected={unexpected}'
        )
    result = {
        key: values[key]
        for key in normalized_order
        if key in values
    }
    for key in values:
        if key in optional_names and key not in result:
            result[key] = values[key]
    return result


class BrowserHttpClient:
    """Reusable browser-impersonating Session with an isolated CookieJar."""

    def __init__(
        self,
        *,
        proxies: Optional[dict] = None,
        impersonate: str = DEFAULT_IMPERSONATE,
        accept_encoding: str = DEFAULT_ACCEPT_ENCODING,
        http_version: str = DEFAULT_HTTP_VERSION,
    ) -> None:
        self.proxies = proxies
        self.impersonate = str(impersonate)
        self.accept_encoding = str(accept_encoding)
        self.http_version = str(http_version)
        self.session = curl_requests.Session(
            proxies=proxies,
            impersonate=self.impersonate,
            default_headers=False,
            discard_cookies=True,
            http_version=self.http_version,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Mapping[str, Any]] = None,
        cookies: Any = None,
        proxies: Optional[dict] = None,
        **kwargs,
    ):
        wire_headers: dict[str, Any] = {}
        for key, value in dict(headers or {}).items():
            name = str(key)
            # Browser captures expose HTTP/2 :authority as "authority". It is
            # a pseudo-header, so libcurl must derive it from the request URL.
            if name.lower() == 'authority':
                continue
            wire_headers[name] = None if value is None else str(value)

        lowered = {key.lower() for key in wire_headers}
        cookie = _cookie_header(cookies)
        if cookie and 'cookie' not in lowered:
            wire_headers['cookie'] = cookie
            lowered.add('cookie')
        if 'accept-encoding' not in lowered:
            wire_headers['accept-encoding'] = self.accept_encoding

        upper_method = str(method).upper()
        body = kwargs.get('data')
        has_json = kwargs.get('json') is not None
        has_multipart = kwargs.get('multipart') is not None
        if (
            upper_method == 'POST'
            and not has_json
            and not has_multipart
            and body in (None, '', b'')
            and 'content-type' not in lowered
        ):
            # libcurl otherwise synthesizes
            # ``Content-Type: application/x-www-form-urlencoded`` for an
            # empty POST.  curl_cffi maps a None Header value to
            # ``Content-Type:`` in CURLOPT_HTTPHEADER, which suppresses the
            # synthesized field without putting an empty Header on the wire.
            # Chrome's XHS empty POST contract is Content-Length: 0 with no
            # Content-Type field at all.
            wire_headers['content-type'] = None

        request_proxies = self.proxies if proxies is None else proxies
        return self.session.request(
            str(method).upper(),
            str(url),
            headers=wire_headers,
            proxies=request_proxies,
            impersonate=self.impersonate,
            default_headers=False,
            discard_cookies=True,
            http_version=self.http_version,
            accept_encoding=self.accept_encoding,
            **kwargs,
        )

    def get(self, url: str, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request('POST', url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request('PUT', url, **kwargs)

    def close(self) -> None:
        self.session.close()

    def state_snapshot(self) -> dict:
        return {
            'backend': 'curl_cffi',
            'impersonate': self.impersonate,
            'httpVersion': self.http_version,
            'defaultHeaders': False,
            'cookieJarPersistence': False,
        }


__all__ = [
    'DEFAULT_IMPERSONATE',
    'DEFAULT_ACCEPT_ENCODING',
    'DEFAULT_HTTP_VERSION',
    'ordered_wire_headers',
    'BrowserHttpClient',
]
