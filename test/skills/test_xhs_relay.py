"""XHS Relay boundary: credentials, v2 envelope and fail-closed behavior."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / 'crews/main/skills/_shared/xhs_utils/relay.py'


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f'relay_{path.stem}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class XhsRelayTests(unittest.TestCase):
    def test_shared_relay_uses_v2_contract(self):
        module = load(ADAPTER)
        response = mock.Mock(ok=True, status_code=200)
        response.json.return_value = {
            'success': True, 'data': {'xs': 'signed'}, 'error': None,
        }
        with (mock.patch.dict(os.environ, {'OFB_KEY': 'test-key'}),
              mock.patch.object(module.requests, 'post', return_value=response) as post):
            self.assertEqual(module.compute('pc', 'sign', {'api': '/test'}), {'xs': 'signed'})
        self.assertEqual(post.call_args.args[0], module.RELAY_BASE_URL + '/api/v1/sign/xhs/v2')
        self.assertEqual(post.call_args.kwargs['json'], {
            'version': 2, 'profile': 'pc', 'operation': 'sign',
            'inputs': {'api': '/test'},
        })
        self.assertEqual(post.call_args.kwargs['headers']['X-OFB-Key'], 'test-key')

    def test_missing_key_stops_before_network(self):
        module = load(ADAPTER)
        with (mock.patch.dict(os.environ, {'OFB_KEY': ''}),
              mock.patch.object(module.requests, 'post') as post):
            with self.assertRaisesRegex(module.XhsRelayError, 'SIGN_UNAVAILABLE'):
                module.compute('creator', 'sign', {})
            post.assert_not_called()

    def test_bad_envelope_fails_closed(self):
        module = load(ADAPTER)
        response = mock.Mock(ok=True, status_code=200)
        response.json.return_value = {'success': True, 'data': None}
        with (mock.patch.dict(os.environ, {'OFB_KEY': 'test-key'}),
              mock.patch.object(module.requests, 'post', return_value=response)):
            with self.assertRaisesRegex(module.XhsRelayError, 'SIGN_UNAVAILABLE'):
                module.compute('pc', 'sign', {})

    def test_security_script_refresh_does_not_reuse_stale_value(self):
        script = ADAPTER.parent / 'xhs_core/dsl.py'
        relay = SimpleNamespace(compute=mock.Mock(return_value={'value': 'fresh'}))
        with mock.patch.dict(sys.modules, {'xhs_utils.relay': relay}):
            module = load(script)
        fetcher = module.DsFetcher('xhs-pc-web', referer='https://example.test')
        response = SimpleNamespace(text='platform-script', raise_for_status=mock.Mock())
        http = SimpleNamespace(get=mock.Mock(return_value=response))
        fetcher.get_bundle(http_client=http)
        relay.compute.side_effect = RuntimeError('Relay unavailable')
        with self.assertRaisesRegex(RuntimeError, 'Relay unavailable'):
            fetcher.get_bundle(force=True, http_client=http)


if __name__ == '__main__':
    unittest.main()
