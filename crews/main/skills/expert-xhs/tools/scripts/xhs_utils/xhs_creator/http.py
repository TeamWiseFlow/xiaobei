"""Creator-specific Chrome transport defaults."""

from __future__ import annotations

from typing import Optional

from xhs_utils.xhs_core.http import BrowserHttpClient


# The currently captured Creator publish page is Chrome 152.  curl_cffi 0.16.2
# does not ship a Chrome 152 profile yet; chrome150 is its newest supported
# profile and is materially closer to the browser than the old chrome146 one.
CREATOR_IMPERSONATE = 'chrome150'
CREATOR_ACCEPT_ENCODING = 'gzip, deflate, br, zstd'
CREATOR_HTTP_VERSION = 'v2tls'


class CreatorHttpClient(BrowserHttpClient):
    """One reusable Chrome-impersonating Session per Creator Auth lifecycle."""

    def __init__(
        self,
        *,
        proxies: Optional[dict] = None,
        impersonate: str = CREATOR_IMPERSONATE,
    ) -> None:
        super().__init__(
            proxies=proxies,
            impersonate=impersonate,
            accept_encoding=CREATOR_ACCEPT_ENCODING,
            http_version=CREATOR_HTTP_VERSION,
        )


__all__ = [
    'CREATOR_IMPERSONATE',
    'CREATOR_ACCEPT_ENCODING',
    'CREATOR_HTTP_VERSION',
    'CreatorHttpClient',
]
