"""Shared OFB Relay adapter for platform-supplied security programs."""
from __future__ import annotations

from typing import Any, Mapping

from xhs_utils.relay import compute


def generate_websectiga(scripting_code: str, *,
                         profile: Mapping[str, Any] | None = None) -> str:
    return str(compute('creator', 'websectiga', {
        'scripting_code': scripting_code,
        'profile': dict(profile or {}),
    })['websectiga'])


__all__ = ['generate_websectiga']
