"""Platform-neutral request identifiers used by XHS Web clients."""

from __future__ import annotations

from urllib.parse import urlencode

from xhs_utils.relay import compute


def generate_x_b3_traceid(length: int = 16, profile: str = 'pc') -> str:
    return str(compute(profile, 'trace-id', {'kind': 'b3', 'length': length})['value'])


def generate_xray_traceid(profile: str = 'pc') -> str:
    return str(compute(profile, 'trace-id', {'kind': 'xray'})['value'])


def splice_str(api: str, params: dict) -> str:
    return api + '?' + urlencode(
        {key: '' if value is None else value for key, value in params.items()},
        doseq=True,
    )


__all__ = ['generate_x_b3_traceid', 'generate_xray_traceid', 'splice_str']
