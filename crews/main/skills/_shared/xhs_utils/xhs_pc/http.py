"""PC Web Chrome-impersonating transport defaults."""

from __future__ import annotations

from typing import Optional

from xhs_utils.xhs_core.http import BrowserHttpClient


PC_IMPERSONATE = 'chrome146'
PC_ACCEPT_ENCODING = 'gzip, deflate, br, zstd'
PC_HTTP_VERSION = 'v2tls'


class PcHttpClient(BrowserHttpClient):
    """One reusable Chrome-impersonating Session per PC Auth lifecycle."""

    def __init__(
        self,
        *,
        proxies: Optional[dict] = None,
        impersonate: str = PC_IMPERSONATE,
    ) -> None:
        super().__init__(
            proxies=proxies,
            impersonate=impersonate,
            accept_encoding=PC_ACCEPT_ENCODING,
            http_version=PC_HTTP_VERSION,
        )


__all__ = [
    'PC_IMPERSONATE',
    'PC_ACCEPT_ENCODING',
    'PC_HTTP_VERSION',
    'PcHttpClient',
]
