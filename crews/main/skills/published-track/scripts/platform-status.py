#!/usr/bin/env python3
"""Read the existing calibration enabled flag without initializing state."""
import argparse
import json
import os
from pathlib import Path


def platform_status(workspace, platform):
    directory = workspace / platform / 'calibration'
    path = directory / 'platform-state.json'
    if not path.exists():
        path = directory / '.platform-state.json'
    if not path.exists():
        return {'ok': True, 'platform': platform, 'enabled': False, 'reason': 'NOT_INITIALIZED'}
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict) or not isinstance(state.get('enabled'), bool):
            raise ValueError('enabled must be a boolean')
        return {'ok': True, 'platform': platform, 'enabled': state['enabled']}
    except (OSError, ValueError) as exc:
        return {'ok': False, 'platform': platform, 'enabled': False, 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True, choices=['douyin', 'xhs', 'wx_channel', 'wx_mp', 'tiktok', 'kuaishou', 'twitter', 'weibo'])
    args = parser.parse_args()
    workspace = Path(os.path.abspath(Path(__file__).parent / '../../..'))
    result = platform_status(workspace, args.platform)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
