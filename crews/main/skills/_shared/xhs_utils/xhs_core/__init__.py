"""Shared runtime and platform metadata used by XHS Web adapters."""

from .auth import (
    AUTH_LOGIN_SOURCES,
    CREATOR_PLATFORM_CONFIG,
    PC_PLATFORM_CONFIG,
    XHSAuth,
    XHSPlatformConfig,
)
from .http import BrowserHttpClient

__all__ = [
    'AUTH_LOGIN_SOURCES',
    'XHSPlatformConfig',
    'PC_PLATFORM_CONFIG',
    'CREATOR_PLATFORM_CONFIG',
    'XHSAuth',
    'BrowserHttpClient',
]
