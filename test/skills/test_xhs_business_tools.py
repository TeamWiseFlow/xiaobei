"""Offline contracts for live/IM and partnership wrappers."""

from __future__ import annotations

from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'crews/main/skills/expert-xhs/tools'
SCRIPTS = TOOLS / 'scripts'


def run_wrapper(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['bash', str(TOOLS / name / f'{name}.sh'), *args],
        text=True, capture_output=True, timeout=10,
    )


def load_partnership_cli():
    spec = importlib.util.spec_from_file_location(
        'xhs_partnership_cli_test', SCRIPTS / 'xhs_partnership_cli.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS))
    return module


class BusinessToolTests(unittest.TestCase):
    def test_wrapper_method_surfaces(self):
        expected = {'xhs-live': 15, 'xhs-im': 33,
                    'xhs-pugongying': 10, 'xhs-qianfan': 8}
        for name, count in expected.items():
            with self.subTest(name=name):
                result = run_wrapper(name, 'methods')
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertGreaterEqual(len(data['methods']), count)

    def test_missing_pc_session_stops_before_network_action(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, 'XHS_PC_SESSION_FILE': str(Path(directory) / 'missing.json')}
            result = subprocess.run(
                ['bash', str(TOOLS / 'xhs-live/xhs-live.sh'), 'call', 'list_categories'],
                text=True, capture_output=True, timeout=10, env=env,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['error'], 'SESSION_MISSING')

    def test_invite_preview_does_not_attempt_send(self):
        with tempfile.TemporaryDirectory() as directory:
            proposal = Path(directory) / 'proposal.json'
            proposal.write_text(json.dumps({
                'user_id': 'u1', 'product_name': '测试产品',
                'publish_start': '2026-10-01', 'publish_end': '2026-10-10',
                'content': '合作方案', 'contact_info': '平台内联系',
            }), encoding='utf-8')
            result = run_wrapper('xhs-pugongying', 'invite', '--proposal', str(proposal))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['state'], 'preview')

    def test_invite_preflight_and_duplicate_guard(self):
        module = load_partnership_cli()
        with tempfile.TemporaryDirectory() as directory:
            proposal = Path(directory) / 'proposal.json'
            proposal.write_text(json.dumps({
                'user_id': 'u1', 'product_name': '测试产品',
                'publish_start': '2026-10-01', 'publish_end': '2026-10-10',
                'content': '合作方案', 'contact_info': '平台内联系',
            }), encoding='utf-8')
            auth = Mock()
            auth.profile.cookie_map = {'a1': 'test', 'web_session': 'test'}
            api = Mock()
            api.get_self_info.return_value = {
                'success': True, 'data': {'userId': 'brand', 'nickName': '品牌'}}
            api.send_invite.return_value = {'success': True, 'data': {'inviteId': 'i1'}}
            with patch.object(module, 'ATTEMPTS_FILE', Path(directory) / 'attempts.jsonl'), \
                 patch.object(module, 'session_lock', return_value=nullcontext()), \
                 patch.object(module, 'load_auth', return_value=auth), \
                 patch.object(module, 'save_auth'), \
                 patch.object(module, '_api', return_value=api):
                first = module.invite(str(proposal), True)
                self.assertEqual(first['state'], 'submitted')
                self.assertEqual(api.send_invite.call_count, 1)
                with self.assertRaisesRegex(ValueError, '避免重复发送'):
                    module.invite(str(proposal), True)
                self.assertEqual(api.send_invite.call_count, 1)

    def test_qianfan_has_no_invite_endpoint(self):
        result = run_wrapper('xhs-qianfan', 'invite', '--proposal', '/no/such/file', '--send')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('没有发起合作邀约能力', result.stdout)

    def test_qianfan_profile_reports_partial_platform_rejection(self):
        module = load_partnership_cli()
        auth = Mock()
        auth.profile.cookie_map = {'a1': 'test', 'web_session': 'test'}
        api = Mock()
        for method in ('get_user_detail', 'get_user_cooperation', 'get_user_shop',
                       'get_user_item'):
            getattr(api, method).return_value = {'success': True, 'data': {}}
        api.get_user_fans.return_value = {
            'success': False, 'code': 401, 'msg': '无登录信息'}
        with patch.object(module, 'session_lock', return_value=nullcontext()), \
             patch.object(module, 'load_auth', return_value=auth), \
             patch.object(module, 'save_auth'), \
             patch.object(module, '_api', return_value=api):
            result = module.profile('qianfan', 'buyer')
        self.assertTrue(result['ok'])
        self.assertEqual(result['errors']['fans'], '无登录信息')

    def test_pgy_search_reuses_verified_brand_identity(self):
        module = load_partnership_cli()
        auth = Mock()
        auth.profile.cookie_map = {'a1': 'test', 'web_session': 'test'}
        api = Mock()
        api.get_all_categories.return_value = []
        api.get_self_info.return_value = {
            'success': True, 'data': {'userId': 'brand'}}
        api.get_user_by_page.return_value = ([{'user_id': str(i)} for i in range(20)], 20)
        util = types.ModuleType('xhs_utils.xhs_pugongying_util')
        util.generate_pugongying_data = lambda choice, categories: None
        with patch.object(module, 'session_lock', return_value=nullcontext()), \
             patch.object(module, 'load_auth', return_value=auth), \
             patch.object(module, 'save_auth'), \
             patch.object(module, '_api', return_value=api), \
             patch.dict(sys.modules, {'xhs_utils.xhs_pugongying_util': util}):
            result = module.search('pgy', '-1', 20)
        self.assertEqual(len(result['users']), 20)
        api.get_self_info.assert_called_once()
        self.assertEqual(api.get_user_by_page.call_args.kwargs['brand_user_id'], 'brand')

    def test_pgy_invite_signs_the_actual_post_body(self):
        script = '''
import json
from unittest.mock import Mock, patch
from apis.xhs_pugongying_apis import PuGongYingAPI
api = PuGongYingAPI()
signed = []
api._signed_headers = lambda cookies, path, data='': signed.append(data) or {}
response = Mock()
response.json.return_value = {'success': True}
brand = {'data': {'userId': 'brand', 'nickName': '品牌'}}
with patch('apis.xhs_pugongying_apis.requests.post', return_value=response) as post:
    api.send_invite('u1', {'a1': 'a'}, '产品', ['start', 'end'], '正文', '平台内联系', brand_info=brand)
    assert signed == [post.call_args.kwargs['data']]
    assert json.loads(signed[0])['kolId'] == 'u1'
'''
        result = subprocess.run([sys.executable, '-c', script], text=True,
                                capture_output=True, timeout=10,
                                env={**os.environ, 'PYTHONPATH': str(SCRIPTS)})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_live_listener_releases_session_lock_and_keeps_unknown_frames(self):
        script = '''
import asyncio
from contextlib import contextmanager, redirect_stdout
from io import StringIO
import json
from unittest.mock import Mock, patch
import xhs_live_cli as cli
import apis.xhs_live as live_module

held = [False]
@contextmanager
def lock():
    held[0] = True
    try:
        yield
    finally:
        held[0] = False

class WebSocket:
    def events(self):
        async def read():
            assert not held[0], 'listener holds the PC session lock while waiting'
            yield {'type': 'TEXT', 'data': 'future-protocol-frame'}
        return read()
    async def close(self):
        pass

class API:
    def __init__(self, auth):
        pass
    async def connect_push_from_storage(self, *, room_id=None):
        return WebSocket()

auth = Mock()
output = StringIO()
with patch.object(cli, 'session_lock', lock), patch.object(cli, 'load_auth', return_value=auth), \\
     patch.object(cli, 'save_auth'), patch.object(live_module, 'XHSLiveAPI', API), \\
     redirect_stdout(output):
    result = asyncio.run(cli._listen('live', 'room-1', 5, 2))
events = [json.loads(line) for line in output.getvalue().splitlines()]
assert result['events'] == 1
assert events[1]['event']['data'] == 'future-protocol-frame'
assert not held[0]
auth.close.assert_called_once()
'''
        result = subprocess.run([sys.executable, '-c', script], text=True,
                                capture_output=True, timeout=10,
                                env={**os.environ, 'PYTHONPATH': str(SCRIPTS)})
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
