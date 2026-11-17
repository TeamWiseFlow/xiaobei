"""Fetch platform security configuration and ask OFB Relay to interpret it."""

from __future__ import annotations

import threading
import time
import hashlib
import json
import os
import tempfile
from typing import Optional

from xhs_utils.relay import compute, _cache_path


def _material_hash(value, program):
    return hashlib.sha256(json.dumps([value, program], ensure_ascii=False).encode()).hexdigest()


class DsFetcher:
    def __init__(self, app_id: str, *, referer: str, ttl: int = 300) -> None:
        self.app_id = str(app_id)
        self.referer = referer
        self.ttl = ttl
        self._value: Optional[str] = None
        self._program: Optional[str] = None
        self._fetched_at = 0.0
        self._binding = None
        self._lock = threading.Lock()

    @property
    def url(self) -> str:
        return f'https://as.xiaohongshu.com/api/sec/v1/ds?appId={self.app_id}'

    def get(self, proxies: Optional[dict] = None, force: bool = False,
            http_client=None) -> str:
        return self.get_bundle(proxies=proxies, force=force,
                               http_client=http_client)[0]

    def get_bundle(self, proxies: Optional[dict] = None, force: bool = False,
                   http_client=None, cache_identity=None) -> tuple[str, str]:
        # Bind both memory and disk to the device, login, proxy and Relay key.
        inputs = {'app_id': self.app_id, 'referer': self.referer,
                  'proxies': proxies, 'identity': cache_identity}
        key = os.environ.get('OFB_KEY', '')
        profile = 'creator' if self.app_id == 'ugc' else 'pc'
        cache = _cache_path(profile, 'ds-material', inputs, key)
        persistent = cache_identity is not None and bool(key)
        with self._lock:
            if (not force and self._binding == str(cache) and self._value
                    and 0 <= time.time() - self._fetched_at < self.ttl):
                return self._value, self._program or ''
            if persistent and not force:
                try:
                    if cache.stat().st_size > 4_000_000:
                        raise ValueError('oversized material')
                    item = json.loads(cache.read_text())
                    program, value, at = item['program'], item['value'], item['at']
                    if (item.get('version') == 1 and isinstance(at, (int, float))
                            and 0 <= time.time() - at < self.ttl
                            and isinstance(value, str) and 1 <= len(value) <= 64
                            and isinstance(program, str) and 0 < len(program) <= 3_000_000
                            and _material_hash(value, program) == item['sha256']):
                        self._value, self._program, self._fetched_at, self._binding = value, program, at, str(cache)
                        return value, program
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            headers = {'Referer': self.referer, 'Accept': '*/*'}
            if http_client is None:
                import requests
                response = requests.get(self.url, headers=headers,
                                        proxies=proxies, timeout=8)
            else:
                response = http_client.get(self.url, headers=headers,
                                           proxies=proxies, timeout=8)
            response.raise_for_status()
            result = compute(profile, 'ds-anchor', {'script': response.text})
            self._value = str(result['value'])
            self._program = response.text
            self._fetched_at = time.time()
            self._binding = str(cache)
            if persistent:
                name = None
                try:
                    cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    fd, name = tempfile.mkstemp(dir=cache.parent, prefix='.ds-')
                    with os.fdopen(fd, 'w') as stream:
                        json.dump({'version': 1, 'at': self._fetched_at, 'value': self._value,
                                   'program': self._program,
                                   'sha256': _material_hash(self._value, self._program)}, stream)
                    os.replace(name, cache)
                except OSError:
                    pass
                finally:
                    if name and os.path.exists(name):
                        os.unlink(name)
            return self._value, self._program or ''

    def peek(self) -> Optional[str]:
        return self._value

    def peek_program(self) -> Optional[str]:
        return self._program


__all__ = ['DsFetcher']
