"""Request PC or Creator device identifiers from OFB Relay."""

from xhs_utils.relay import compute


def generate_a1(profile: str) -> str:
    return str(compute(profile, 'a1', {})['value'])


def generate_web_id(profile: str, a1: str) -> str:
    return str(compute(profile, 'web-id', {'a1': a1})['value'])
