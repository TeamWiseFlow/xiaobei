"""Ordered shared/host Cookie handling for XHS web requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable
from urllib.parse import urlparse


HOST_ONLY_COOKIE_NAMES = frozenset({'acw_tc'})


def parse_cookie_kv(value: Any) -> dict[str, str]:
    """Parse a Cookie header without losing its key order."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {
            str(key): str(item)
            for key, item in value.items()
            if key is not None and item is not None
        }
    result: dict[str, str] = {}
    for part in str(value).split(';'):
        item = part.strip()
        if not item:
            continue
        key, separator, content = item.partition('=')
        if key:
            result[key.strip()] = content if separator else ''
    return result


def cookie_header(value: Any) -> str:
    return '; '.join(
        f'{key}={item}' for key, item in parse_cookie_kv(value).items()
    )


def url_host(url: str) -> str:
    return (urlparse(str(url or '')).hostname or '').lower()


class HostCookieStore:
    """Keep edge Cookies scoped to the host that issued them.

    Chrome does not send an ``acw_tc`` issued by ``edith`` to ``as``, ``so``
    or ``customer``.  A flat ``dict`` loses that boundary and changes both the
    Cookie key set and order seen by XHS gateways.
    """

    def __init__(self, host_cookies: Mapping[str, Any] | None = None) -> None:
        self._values: dict[str, dict[str, str]] = {}
        self._order: dict[tuple[str, str, str], int] = {}
        self._next_order = 0
        for host, values in dict(host_cookies or {}).items():
            normalized = url_host(str(host)) or str(host).lower().strip()
            if normalized:
                parsed = parse_cookie_kv(values)
                self._values[normalized] = parsed
                for name in parsed:
                    self._remember('host', normalized, name)

    @classmethod
    def from_state(cls, state: Mapping[str, Any] | None) -> 'HostCookieStore':
        data = dict(state or {})
        store = cls(data.get('values') or {})
        order = data.get('order') or []
        if order:
            store._order = {}
            store._next_order = 0
            for item in order:
                try:
                    scope, host, name = item
                except (TypeError, ValueError):
                    continue
                store._remember(str(scope), str(host), str(name))
        return store

    def _remember(self, scope: str, host: str, name: str, *, move=False) -> None:
        key = (scope, host, name)
        if move:
            self._order.pop(key, None)
        if key not in self._order:
            self._order[key] = self._next_order
            self._next_order += 1

    def _sync_shared(self, shared: Mapping[str, Any]) -> None:
        for name in shared:
            self._remember('shared', '', str(name))

    def snapshot(self) -> dict[str, dict[str, str]]:
        return {
            host: dict(values)
            for host, values in self._values.items()
        }

    def export_state(self) -> dict[str, Any]:
        ordered = sorted(self._order, key=self._order.get)
        return {
            'values': self.snapshot(),
            'order': [list(item) for item in ordered],
        }

    def update(self, host_or_url: str, cookies: Any) -> None:
        host = url_host(host_or_url) or str(host_or_url).lower().strip()
        if not host:
            raise ValueError('host Cookie update requires a host or URL')
        updates = parse_cookie_kv(cookies)
        target = self._values.setdefault(host, {})
        for name, value in updates.items():
            target[name] = value
            self._remember('host', host, name)

    def extract_host_only(
        self,
        shared: dict[str, str],
        source_url: str,
        names: Iterable[str] = HOST_ONLY_COOKIE_NAMES,
    ) -> dict[str, str]:
        host = url_host(source_url)
        host_only = set(names)
        for name in list(shared):
            if name in host_only:
                value = shared.pop(name)
                if host:
                    self._values.setdefault(host, {})[name] = value
                    self._remember('host', host, name)
            else:
                self._remember('shared', '', name)
        return shared

    def cookies_for_url(self, url: str, shared: Any) -> dict[str, str]:
        values = parse_cookie_kv(shared)
        self._sync_shared(values)
        host = url_host(url)
        combined = [
            (self._order[('shared', '', name)], name, value)
            for name, value in values.items()
        ]
        for name, value in self._values.get(host, {}).items():
            self._remember('host', host, name)
            combined.append((self._order[('host', host, name)], name, value))
        combined.sort(key=lambda item: item[0])
        return {name: value for _, name, value in combined}

    def merge_response(
        self,
        shared: dict[str, str],
        response: Any,
        *,
        append_shared: Iterable[str] = (),
    ) -> dict[str, str]:
        host = url_host(str(getattr(response, 'url', '') or ''))
        append_names = set(append_shared)
        self._sync_shared(shared)
        for key, value in getattr(response, 'cookies', {}).items():
            name = str(key)
            content = str(value)
            if name in HOST_ONLY_COOKIE_NAMES:
                if host:
                    self._values.setdefault(host, {})[name] = content
                    self._remember('host', host, name)
                continue
            if name in append_names and name in shared:
                shared.pop(name)
                self._remember('shared', '', name, move=True)
            else:
                self._remember('shared', '', name)
            shared[name] = content
        return shared


__all__ = [
    'HOST_ONLY_COOKIE_NAMES',
    'HostCookieStore',
    'cookie_header',
    'parse_cookie_kv',
    'url_host',
]
