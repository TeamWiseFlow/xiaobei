"""Bounded Relay-only HTTP recovery and one shared budget for Python and Node."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

BUDGET = Path(__file__).with_name('relay_budget.mjs')
HEADERS = ('x-ofb-ratelimit-limit', 'x-ofb-ratelimit-remaining', 'x-ofb-ratelimit-reset-ms',
           'retry-after', 'x-ofb-retry-after-ms')


class RelayBudgetError(RuntimeError):
    def __init__(self, retry_after_seconds=None):
        super().__init__('RELAY_RATE_LIMITED')
        self.retry_after_seconds = retry_after_seconds


def budget(action, base, key, **extra):
    data = {'action': action, 'base': base, 'digest': hashlib.sha256(key.encode()).hexdigest(), **extra}
    try:
        result = subprocess.run(['node', str(BUDGET)], input=json.dumps(data), text=True,
                                capture_output=True, timeout=40, check=False)
        value = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise RuntimeError('RELAY_BUDGET_UNAVAILABLE') from exc
    if not value.get('ok'):
        if value.get('error') == 'RELAY_RATE_LIMITED':
            raise RelayBudgetError(value.get('retry_after_seconds'))
        raise RuntimeError('RELAY_BUDGET_UNAVAILABLE')


def post(url, *, key, request, **kwargs):
    for attempt in range(2):
        budget('acquire', url, key)
        response = request(url, **kwargs)
        headers = getattr(response, 'headers', {})
        status = getattr(response, 'status_code', None)
        feedback = {name: headers[name] for name in HEADERS if isinstance(headers.get(name), str)}
        if feedback or status == 429:
            budget('observe', url, key, headers=feedback, status=status)
        if status != 429 or attempt:
            return response
    raise AssertionError('unreachable')
