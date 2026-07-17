#!/usr/bin/env python3
"""Unit tests for publish_douyin.py (纯浏览器模拟方案，形态仿 wechat-channels-publish).

 Covers:
- 4 个子命令路由（upload / fill / publish / get-link）+ run 一键全流程
- 纯浏览器操作：本 skill 不自管探活/登录，交 login-manager；脚本只复用持久化 session `douyin` 做发布
- camoufox-cli 调用模式（open / eval / click / type / set_file / wait）
- 持久化 session 复用（用完即 close，登录态在磁盘 profile，下次重起无头即恢复）
- file 不存在 / 按钮找不到等失败模式

All camoufox-cli / subprocess calls are mocked.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import publish_douyin  # noqa: E402


class TestConstants(unittest.TestCase):
    def test_upload_url_uses_douyin_creator(self):
        self.assertIn("creator.douyin.com", publish_douyin.UPLOAD_URL)
        self.assertIn("/creator-micro/content/upload", publish_douyin.UPLOAD_URL)
        self.assertIn("enter_from=dou_web", publish_douyin.UPLOAD_URL)

    def test_platform_key(self):
        # 持久化 session 名 = 平台 key（探活/登录/导出 cookie+UA 交 login-manager）
        self.assertEqual(publish_douyin.PERSISTENT_SESSION, "douyin")

    def test_no_douyin_open_platform_credentials(self):
        # Phase 3.2 浏览器模拟方案：不依赖开放平台凭据
        import inspect
        src = inspect.getsource(publish_douyin)
        # 不应再有 H5 schema / open platform 相关
        self.assertNotIn("open_platform", src.lower().replace(" ", ""))
        self.assertNotIn("client_key", src)
        self.assertNotIn("client_secret", src)
        self.assertNotIn("access_token", src)
        # 应该有 browser / camoufox 关键字
        self.assertIn("camoufox", src.lower())


class TestSessionNaming(unittest.TestCase):
    def test_session_name_format(self):
        name = publish_douyin.session_name("publish")
        # douyin-publish-{nonce} / douyin-upload-{nonce} / douyin-run-{nonce}
        self.assertTrue(name.startswith("douyin-publish-"))
        suffix = name[len("douyin-publish-"):]
        self.assertGreater(len(suffix), 0)


class TestCmdUpload(unittest.TestCase):
    def test_video_not_found_exits_1(self):
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_upload(video="/nonexistent.mp4", session="s1")
        self.assertEqual(ctx.exception.code, 1)

    @mock.patch("publish_douyin._check_logged_in")
    @mock.patch("publish_douyin.camoufox_wait_for_selector")
    @mock.patch("publish_douyin.camoufox_upload")
    @mock.patch("publish_douyin.camoufox_open")
    def test_successful_upload(self, mock_open, mock_upload, mock_wait, mock_login):
        mock_upload.return_value = True
        mock_wait.return_value = True

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"video")
            out = StringIO()
            with mock.patch("sys.stdout", out):
                publish_douyin.cmd_upload(video=str(video), session="douyin-upload-abc")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["session"], "douyin-upload-abc")
        mock_open.assert_called_once()
        mock_login.assert_called_once()  # 登录态守卫在 open 后被调用

    @mock.patch("publish_douyin._check_logged_in")
    @mock.patch("publish_douyin.camoufox_upload")
    @mock.patch("publish_douyin.camoufox_open")
    def test_upload_setfile_fail_exits_1(self, mock_open, mock_upload, mock_login):
        mock_upload.return_value = False
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"video")
            with self.assertRaises(SystemExit) as ctx:
                publish_douyin.cmd_upload(video=str(video), session="s1")
        self.assertEqual(ctx.exception.code, 1)


class TestCheckLoggedIn(unittest.TestCase):
    """登录态守卫：open 完上传页后立即验，未登录 exit 2（SESSION_EXPIRED）。"""

    @mock.patch("publish_douyin.subprocess.run")
    @mock.patch("publish_douyin.camoufox_eval")
    @mock.patch("publish_douyin.Path")
    def test_logged_in_passes(self, mock_path, mock_eval, mock_run):
        # URL 停在上传页 + cookies 三字段齐全 → 不 exit
        mock_eval.return_value = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
        mock_path.return_value.read_text.return_value = json.dumps(
            [{"name": "sessionid", "value": "x"}, {"name": "sid_tt", "value": "y"}, {"name": "uid_tt", "value": "z"}]
        )
        publish_douyin._check_logged_in("douyin")  # 不抛即通过

    @mock.patch("publish_douyin.subprocess.run")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_login_page_redirect_exits_2(self, mock_eval, mock_run):
        mock_eval.return_value = "https://creator.douyin.com/login?from=upload"
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin._check_logged_in("douyin")
        self.assertEqual(ctx.exception.code, 2)

    @mock.patch("publish_douyin.subprocess.run")
    @mock.patch("publish_douyin.camoufox_eval")
    @mock.patch("publish_douyin.Path")
    def test_missing_login_cookies_exits_2(self, mock_path, mock_eval, mock_run):
        # URL 停在上传页但 cookies 缺 sessionid → exit 2（兜住「页面渲染但无真 session」）
        mock_eval.return_value = "https://creator.douyin.com/creator-micro/content/upload"
        mock_path.return_value.read_text.return_value = json.dumps([{"name": "sid_tt", "value": "y"}, {"name": "uid_tt", "value": "z"}])
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin._check_logged_in("douyin")
        self.assertEqual(ctx.exception.code, 2)


class TestCmdFill(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_eval")
    @mock.patch("publish_douyin.camoufox_type_contenteditable")
    @mock.patch("publish_douyin.camoufox_type")
    def test_fill_title_and_caption(self, mock_type, mock_ce, mock_eval):
        mock_type.return_value = True
        mock_ce.return_value = True
        mock_eval.return_value = "no-select"  # 无自主声明区,_select_ai_declaration 直接 True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_fill(session="s1", title="测试标题", caption="描述 #话题")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])

    @mock.patch("publish_douyin.camoufox_type")
    def test_fill_title_missing_input_exits_1(self, mock_type):
        mock_type.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_fill(session="s1", title="x", caption="")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdPublish(unittest.TestCase):
    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.Path")
    @mock.patch("publish_douyin.camoufox_wait_for_url_contains")
    @mock.patch("publish_douyin.camoufox_click_button_by_text")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_publish_success_returns_aweme_id(self, mock_eval, mock_click, mock_wait, mock_path, mock_fetch):
        mock_click.return_value = True
        mock_wait.return_value = True
        # 拦截器命中 localStorage → 不走 work_list
        mock_eval.side_effect = ["intercepted", "123456", "[]"]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_publish(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["aweme_id"], "123456")
        mock_fetch.assert_not_called()

    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.Path")
    @mock.patch("publish_douyin.camoufox_wait_for_url_contains")
    @mock.patch("publish_douyin.camoufox_click_button_by_text")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_publish_interceptor_miss_falls_back_to_work_list(self, mock_eval, mock_click, mock_wait, mock_path, mock_fetch):
        # 拦截器 miss(发布走 form/导航)→ work_list API 兜底取最新作品
        mock_click.return_value = True
        mock_wait.return_value = True
        mock_eval.side_effect = ["intercepted", None, "[]", "ok"]  # 拦截注入 + 读captured(miss) + 读debug + 落localStorage
        mock_fetch.return_value = ("7663480620206542131", "测试标题")
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_publish(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["aweme_id"], "7663480620206542131")
        mock_fetch.assert_called_once()

    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.Path")
    @mock.patch("publish_douyin.camoufox_wait_for_url_contains")
    @mock.patch("publish_douyin.camoufox_click_button_by_text")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_publish_aweme_id_none_exits_3_no_false_success(self, mock_eval, mock_click, mock_wait, mock_path, mock_fetch):
        # 拦截器 + work_list 都 miss → exit 3，不再误报 ok（2026-07-17 xiaobei 事故根因之二）
        mock_click.return_value = True
        mock_wait.return_value = True
        mock_eval.side_effect = ["intercepted", None, "[]"]
        mock_fetch.return_value = (None, None)
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_publish(session="s1")
        self.assertEqual(ctx.exception.code, 3)

    @mock.patch("publish_douyin.camoufox_click_button_by_text")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_publish_button_not_found_exits_1(self, mock_eval, mock_click):
        mock_click.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_publish(session="s1")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdGetLink(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_from_localStorage(self, mock_eval, mock_open):
        # 策略1: _read_captured_aweme_id 命中 localStorage → 不重开页面
        mock_eval.return_value = "123456"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_get_link(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://www.douyin.com/video/123456")
        self.assertEqual(result["aweme_id"], "123456")
        mock_open.assert_not_called()

    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_fallback_manage_dom(self, mock_eval, mock_open, mock_fetch):
        # 策略1(localStorage) miss → 策略2(work_list) miss → 策略3 管理页 DOM 命中
        mock_fetch.return_value = (None, None)
        mock_eval.side_effect = [None, "https://creator.douyin.com/creator-micro/content/manage", "https://www.douyin.com/video/789"]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_get_link(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://www.douyin.com/video/789")
        mock_open.assert_not_called()  # 已在 manage 页,不重开

    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_work_list_strategy(self, mock_eval, mock_open, mock_fetch):
        # 策略1 miss → 策略2 work_list 命中
        mock_eval.return_value = None  # _read_captured_aweme_id miss
        mock_fetch.return_value = ("999", "标题")
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_get_link(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://www.douyin.com/video/999")
        self.assertEqual(result["aweme_id"], "999")
        mock_open.assert_not_called()

    @mock.patch("publish_douyin._fetch_newest_aweme_id")
    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_no_result_returns_ok_url_none(self, mock_eval, mock_open, mock_fetch):
        # 三条策略都 miss → 不 exit,返回 ok=True url=None(发布已成功)
        mock_fetch.return_value = (None, None)
        mock_eval.side_effect = [None, "https://creator.douyin.com/creator-micro/content/manage", "null"]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_get_link(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertIsNone(result["url"])


class TestCmdRun(unittest.TestCase):
    """run 命令不再自管探活——假设 login-manager 已就位，直接走 upload → fill → publish → get-link。"""

    @mock.patch("publish_douyin.cmd_get_link")
    @mock.patch("publish_douyin.cmd_publish")
    @mock.patch("publish_douyin.cmd_fill")
    @mock.patch("publish_douyin.cmd_upload")
    def test_run_invokes_chain_in_order(self, mock_upload, mock_fill, mock_publish, mock_get_link):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            publish_douyin.cmd_run(video=str(video), title="t", caption="c")
        mock_upload.assert_called_once()
        mock_fill.assert_called_once()
        mock_publish.assert_called_once()
        mock_get_link.assert_called_once()


class TestIntegrationDryRun(unittest.TestCase):
    """CLI smoke test: --help 应该可执行。"""

    def test_help_runs(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "publish_douyin.py"), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("upload", result.stdout)


if __name__ == "__main__":
    unittest.main()
