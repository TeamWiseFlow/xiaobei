"""Local contract tests for the standalone XHS PC hunter."""

from __future__ import annotations

import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[2] / 'crews/main/skills/xhs-hunter/scripts'
sys.path.insert(0, str(SCRIPTS))
from xhs_utils import pc_session  # noqa: E402
import xhs_hunter  # noqa: E402
sys.path.remove(str(SCRIPTS))


class HunterTests(unittest.TestCase):
    def test_count_strings_have_numeric_companions(self):
        self.assertEqual(xhs_hunter._count_number('2.7万'), 27000)
        self.assertEqual(xhs_hunter._count_number('3,268'), 3268)
        self.assertIsNone(xhs_hunter._count_number('未知'))
        enriched = xhs_hunter._with_numeric_counts({
            'liked_count': '3268', 'note_card': {
                'interact_info': {'comment_count': '2.7万'}}})
        self.assertEqual(enriched['liked_count_num'], 3268)
        self.assertEqual(enriched['note_card']['interact_info']['comment_count_num'], 27000)

    def test_search_filters_non_notes_and_empty_titles(self):
        cards = [
            {'model_type': 'note', 'note_card': {'display_title': '有效'}},
            {'model_type': 'note', 'note_card': {'display_title': ''}},
            {'model_type': 'ads', 'note_card': {'display_title': '广告'}},
        ]
        self.assertEqual(xhs_hunter._search_note_cards(cards), cards[:1])

    def test_fetch_rejects_empty_detail_before_saving(self):
        url = 'https://www.xiaohongshu.com/explore/abc?xsec_token=wrong'
        with patch.object(xhs_hunter, 'call_method', return_value={
            'ok': True, 'data': {'data': {'items': [{'id': 'abc', 'note_card': {}}]}}}), \
             patch.object(xhs_hunter, 'save_note') as save:
            result = xhs_hunter.fetch_note(url)
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'NOTE_UNAVAILABLE')
        save.assert_not_called()

    def test_comment_rate_limit_message_and_bounded_collection(self):
        script = '''
from unittest.mock import Mock
from apis.xhs_pc_apis import XHS_Apis
api = object.__new__(XHS_Apis)
api.base_url = 'https://www.xiaohongshu.com'
api.http = Mock()
api._request_params = Mock(return_value=({}, {}, ''))
api._proxies = Mock(return_value=None)
api.http.get.return_value.json.return_value = {
    'code': 300013, 'success': True, 'msg': '访问频繁，请稍后再试', 'data': {}}
success, message, data = api.get_note_all_out_comment('note', 'token')
assert success is False and message == '访问频繁，请稍后再试'
assert data == []
api.http.post.return_value.json.return_value = {
    'code': 300013, 'success': True, 'msg': '访问频繁，请稍后再试', 'data': {}}
success, message, data = api.get_note_info(
    'https://www.xiaohongshu.com/explore/note?xsec_token=token')
assert success is False and message == '访问频繁，请稍后再试'
api.get_note_out_comment = Mock(return_value=(True, 'ok', {'data': {
    'comments': [{'id': '1'}, {'id': '2'}], 'has_more': True, 'cursor': 'next'}}))
api.get_note_all_inner_comment = Mock()
success, message, data = api.get_note_all_comment(
    'https://www.xiaohongshu.com/explore/note?xsec_token=token',
    limit=1, include_inner=False)
assert success is True and len(data) == 1
assert api.get_note_out_comment.call_count == 1
api.get_note_all_inner_comment.assert_not_called()
'''
        result = subprocess.run([sys.executable, '-c', script], text=True,
                                capture_output=True, timeout=10,
                                env={**os.environ, 'PYTHONPATH': str(SCRIPTS)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_comment_cli_rejects_unbounded_limit_without_network(self):
        result = subprocess.run(
            ['bash', str(SCRIPTS.parent / 'xhs-hunter.sh'), 'comments',
             'https://www.xiaohongshu.com/explore/abc', '--limit', '0'],
            text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['error'], 'ValueError')

    def test_all_pc_methods_are_exposed(self):
        result = subprocess.run(
            ['bash', str(SCRIPTS.parent / 'xhs-hunter.sh'), 'methods'],
            text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        methods = __import__('json').loads(result.stdout)['methods']
        self.assertGreaterEqual(len(methods), 45)
        for name in ('search_note', 'search_user', 'get_note_info',
                     'get_note_all_comment', 'get_unread_message',
                     'get_note_no_water_video', 'get_note_no_water_img'):
            self.assertIn(name, methods)

    def test_qr_code_is_private_png(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'qr.png'
            result = subprocess.run(
                [sys.executable, '-c',
                 'from apis.xhs_pc_login_apis import XHSLoginApi; '
                 'XHSLoginApi.show_qrcode_image("https://www.xiaohongshu.com/test")'],
                text=True, capture_output=True, timeout=10,
                env={**os.environ, 'PYTHONPATH': str(SCRIPTS), 'XHS_PC_QR_IMAGE': str(path)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_note_normalization_includes_text_metrics_and_media(self):
        raw = {'data': {'items': [{'id': 'abc', 'note_card': {
            'type': 'video', 'title': '标题', 'desc': '正文',
            'user': {'user_id': 'u1', 'nickname': '作者'},
            'interact_info': {'liked_count': '12', 'comment_count': '3'},
            'image_list': [{'info_list': [{'url': 'a'}, {'url': 'b'}]}],
            'video': {'media': {'stream': {'h264': [{'master_url': 'video'}]}}},
            'tag_list': [{'name': '话题'}],
        }}]}}
        note = xhs_hunter.normalize_note(raw, 'https://www.xiaohongshu.com/explore/abc')
        self.assertEqual(note['content'], '正文')
        self.assertEqual(note['metrics']['liked_count'], '12')
        self.assertEqual(note['images'], ['b'])
        self.assertEqual(note['video_url'], 'video')

    def test_note_normalization_accepts_non_h264_video_stream(self):
        raw = {'data': {'items': [{'id': 'abc', 'note_card': {
            'type': 'video', 'video': {'media': {'stream': {
                'h264': [], 'h265': [{'master_url': 'https://sns-video-bd.xhscdn.com/example'}],
            }}},
        }}]}}
        note = xhs_hunter.normalize_note(raw, 'https://www.xiaohongshu.com/explore/abc')
        self.assertEqual(note['video_url'], 'https://sns-video-bd.xhscdn.com/example')

    def test_note_normalization_upgrades_platform_media_to_https(self):
        raw = {'data': {'items': [{'id': 'abc', 'note_card': {
            'type': 'video',
            'image_list': [{'info_list': [{'url': 'http://sns-webpic-qc.xhscdn.com/cover'}]}],
            'video': {'media': {'stream': {
                'h264': [{'master_url': 'http://sns-video-v3.xhscdn.com/video'}],
            }}},
        }}]}}
        note = xhs_hunter.normalize_note(raw, 'https://www.xiaohongshu.com/explore/abc')
        self.assertEqual(note['images'], ['https://sns-webpic-qc.xhscdn.com/cover'])
        self.assertEqual(note['video_url'], 'https://sns-video-v3.xhscdn.com/video')

    def test_note_url_normalizes_discovery_and_short_links(self):
        canonical = 'https://www.xiaohongshu.com/explore/abc?xsec_token=token'
        self.assertEqual(xhs_hunter._note_url(
            'https://www.xiaohongshu.com/discovery/item/abc?xsec_token=token'), canonical)
        response = type('Response', (), {'url': canonical,
                                          'raise_for_status': lambda self: None,
                                          '__enter__': lambda self: self,
                                          '__exit__': lambda self, *args: None})()
        with patch('requests.get', return_value=response):
            self.assertEqual(xhs_hunter._note_url('https://xhslink.com/a/b'), canonical)

    def test_session_file_is_private_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'session.json'
            with patch.object(pc_session, 'SESSION_FILE', target):
                profile = type('Profile', (), {
                    'cookie_map': {'a1': 'a', 'web_session': 's'},
                    'browser_storage_snapshot': lambda self: ({'sc': '1'}, {}),
                })()
                store = type('Store', (), {'export_state': lambda self: {}})()
                auth = type('Auth', (), {'profile': profile, '_cookie_store': store,
                                         'dsl': 'dsl', 'user_id': 'user'})()
                pc_session.save_auth(auth)
                state = pc_session.read_session()
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state['user_id'], 'user')
            self.assertEqual(state['local_storage']['sc'], '1')

    def test_collect_export_uses_limited_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            urls = Path(directory) / 'urls.txt'
            urls.write_text('https://www.xiaohongshu.com/explore/a\n'
                            'https://www.xiaohongshu.com/explore/b\n', encoding='utf-8')
            auth = Mock()
            api = Mock()
            api.get_note_info.return_value = (True, 'ok', {'data': {'items': []}})
            api_module = types.ModuleType('apis.xhs_pc_apis')
            api_module.XHS_Apis = Mock(return_value=api)
            with patch.object(xhs_hunter, 'session_lock', return_value=nullcontext()), \
                 patch.object(xhs_hunter, 'load_auth', return_value=auth), \
                 patch.dict(sys.modules, {'apis.xhs_pc_apis': api_module}), \
                 patch.object(xhs_hunter, 'normalize_note', return_value={
                     'note_id': 'a', 'title': '=SUM(1,2)'}), \
                 patch.object(xhs_hunter, 'save_note'), \
                 patch.object(xhs_hunter, 'save_auth'):
                result = xhs_hunter.collect('urls', str(urls), count=1,
                                            output_dir=str(Path(directory) / 'out'),
                                            download_media=False, xlsx=True)
            self.assertEqual(api.get_note_info.call_count, 1)
            self.assertEqual(result['count'], 1)
            self.assertTrue(Path(result['excel_path']).is_file())


if __name__ == '__main__':
    unittest.main()
