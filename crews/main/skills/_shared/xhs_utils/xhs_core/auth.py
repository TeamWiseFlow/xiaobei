"""Shared authentication contracts and platform endpoint metadata."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Mapping, Optional
from urllib.parse import urlparse


AUTH_LOGIN_SOURCES = frozenset({'cookie', 'qrcode', 'phone'})


@dataclass(frozen=True)
class XHSPlatformConfig:
    """Immutable platform identity and named service origins.

    The signing/profile state stays platform-specific.  This shared object only
    removes duplicated domain strings and gives API/login clients a stable role
    lookup such as ``api``, ``login`` or ``security``.
    """

    name: str
    app_id: str
    cookie_domain: str
    origins: Mapping[str, str]

    def __post_init__(self) -> None:
        normalized = {
            str(role): str(origin).rstrip('/')
            for role, origin in dict(self.origins).items()
        }
        if 'web' not in normalized or 'api' not in normalized:
            raise ValueError('platform origins must contain web and api roles')
        for role, origin in normalized.items():
            parsed = urlparse(origin)
            if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
                raise ValueError(f'invalid {self.name} origin for {role}: {origin}')
        object.__setattr__(self, 'origins', MappingProxyType(normalized))

    def origin(self, role: str = 'api') -> str:
        try:
            return self.origins[str(role)]
        except KeyError as exc:
            raise KeyError(
                f'{self.name} platform has no origin role {role!r}; '
                f'available: {", ".join(sorted(self.origins))}'
            ) from exc

    def host(self, role: str = 'api') -> str:
        return urlparse(self.origin(role)).netloc


PC_PLATFORM_CONFIG = XHSPlatformConfig(
    name='pc',
    app_id='xhs-pc-web',
    cookie_domain='.xiaohongshu.com',
    origins={
        'web': 'https://www.xiaohongshu.com',
        'api': 'https://edith.xiaohongshu.com',
        'search': 'https://so.xiaohongshu.com',
        'live': 'https://live-room.xiaohongshu.com',
        'login': 'https://www.xiaohongshu.com',
        'security': 'https://as.xiaohongshu.com',
        'captcha': 'https://edith.xiaohongshu.com',
        'sem': 'https://pages.xiaohongshu.com',
    },
)


CREATOR_PLATFORM_CONFIG = XHSPlatformConfig(
    name='creator',
    app_id='ugc',
    cookie_domain='.xiaohongshu.com',
    origins={
        'web': 'https://creator.xiaohongshu.com',
        'api': 'https://creator.xiaohongshu.com',
        'login': 'https://customer.xiaohongshu.com',
        'security': 'https://as.xiaohongshu.com',
        'captcha': 'https://edith.xiaohongshu.com',
        'edith': 'https://edith.xiaohongshu.com',
        'upload': 'https://ros-upload.xiaohongshu.com',
        'public_web': 'https://www.xiaohongshu.com',
    },
)


@dataclass
class XHSAuth:
    """Small shared protocol; platform factories own actual authentication."""

    PLATFORM_CONFIG: ClassVar[Optional[XHSPlatformConfig]] = None

    platform: str = ''
    proxies: Optional[dict] = None

    @property
    def config(self) -> XHSPlatformConfig:
        config = self.PLATFORM_CONFIG
        if config is None:
            raise NotImplementedError(
                f'{type(self).__name__} must define PLATFORM_CONFIG'
            )
        return config

    @property
    def domains(self) -> Mapping[str, str]:
        """Read-only named origins for the concrete platform."""
        return self.config.origins

    def origin(self, role: str = 'api') -> str:
        return self.config.origin(role)

    def _bind_platform(self, login_source: str) -> str:
        """Bind the subclass identity and validate the three public sources."""
        self.platform = self.config.name
        source = str(login_source or 'cookie')
        if source not in AUTH_LOGIN_SOURCES:
            raise ValueError(
                'login_source must be cookie, qrcode, or phone'
            )
        return source


__all__ = [
    'AUTH_LOGIN_SOURCES',
    'XHSPlatformConfig',
    'PC_PLATFORM_CONFIG',
    'CREATOR_PLATFORM_CONFIG',
    'XHSAuth',
]
