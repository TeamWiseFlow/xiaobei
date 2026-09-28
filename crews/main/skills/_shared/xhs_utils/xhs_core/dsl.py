"""Fetch platform security configuration and ask OFB Relay to interpret it."""

from __future__ import annotations

import threading
import time
from typing import Optional

from xhs_utils.relay import compute


class DsFetcher:
    def __init__(self, app_id: str, *, referer: str, ttl: int = 300) -> None:
        self.app_id = str(app_id)
        self.referer = referer
        self.ttl = ttl
        self._value: Optional[str] = None
        self._program: Optional[str] = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return f'https://as.xiaohongshu.com/api/sec/v1/ds?appId={self.app_id}'

    def get(self, proxies: Optional[dict] = None, force: bool = False,
            http_client=None) -> str:
        return self.get_bundle(proxies=proxies, force=force,
                               http_client=http_client)[0]

    def get_bundle(self, proxies: Optional[dict] = None, force: bool = False,
                   http_client=None) -> tuple[str, str]:
        with self._lock:
            if not force and self._value and time.time() - self._fetched_at < self.ttl:
                return self._value, self._program or ''
            headers = {'Referer': self.referer, 'Accept': '*/*'}
            if http_client is None:
                import requests
                response = requests.get(self.url, headers=headers,
                                        proxies=proxies, timeout=8)
            else:
                response = http_client.get(self.url, headers=headers,
                                           proxies=proxies, timeout=8)
            response.raise_for_status()
            result = compute('creator' if self.app_id == 'ugc' else 'pc',
                             'ds-anchor', {'script': response.text})
            self._value = str(result['value'])
            self._program = response.text
            self._fetched_at = time.time()
            return self._value, self._program or ''

    def peek(self) -> Optional[str]:
        return self._value

    def peek_program(self) -> Optional[str]:
        return self._program


__all__ = ['DsFetcher']
