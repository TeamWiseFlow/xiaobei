#!/usr/bin/env python3
"""Unit tests for publish_douyin.py (Phase 3.2 浏览器模拟方案).

Covers:
- 6 个子命令路由（login / upload / fill / publish / get-link / cleanup）
- login_manager 集成（check + session-cleanup）
- camoufox-cli 调用模式（open / eval / click / type / set_file / wait）
- Session 命名（每任务一 session，D18 + 4.5.5）
- file 不存在 / cookie 失效 / 按钮找不到等失败模式

All camoufox-cli / login-manager / subprocess calls are mocked.
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
        # login-manager 中央存储 key
        self.assertEqual(publish_douyin.LOGIN_MANAGER_PLATFORM, "douyin")

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


class TestCmdLogin(unittest.TestCase):
    @mock.patch("publish_douyin.login_manager_check")
    def test_login_active_exits_0(self, mock_check):
        mock_check.return_value = True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            with self.assertRaises(SystemExit) as ctx:
                publish_douyin.cmd_login()
            self.assertEqual(ctx.exception.code, 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["platform"], "douyin")

    @mock.patch("publish_douyin.login_manager_check")
    def test_login_expired_exits_2(self, mock_check):
        mock_check.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_login()
        self.assertEqual(ctx.exception.code, 2)


class TestCmdUpload(unittest.TestCase):
    def test_video_not_found_exits_1(self):
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_upload(video="/nonexistent.mp4", session="s1")
        self.assertEqual(ctx.exception.code, 1)

    @mock.patch("publish_douyin.camoufox_close")
    @mock.patch("publish_douyin.camoufox_wait_for_text")
    @mock.patch("publish_douyin.camoufox_set_file")
    @mock.patch("publish_douyin.camoufox_open")
    def test_successful_upload(self, mock_open, mock_set_file, mock_wait, mock_close):
        mock_set_file.return_value = True
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

    @mock.patch("publish_douyin.camoufox_wait_for_text")
    @mock.patch("publish_douyin.camoufox_set_file")
    @mock.patch("publish_douxin.camoufox_open" if False else "publish_douyin.camoufox_open")
    def test_upload_setfile_fail_exits_1(self, mock_open, mock_set_file, mock_wait):
        mock_set_file.return_value = False
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"video")
            with self.assertRaises(SystemExit) as ctx:
                publish_douyin.cmd_upload(video=str(video), session="s1")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdFill(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_type")
    def test_fill_title_and_caption(self, mock_type):
        mock_type.return_value = True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_fill(session="s1", title="测试标题", caption="描述 #话题")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(mock_type.call_count, 2)

    @mock.patch("publish_douyin.camoufox_type")
    def test_fill_title_missing_input_exits_1(self, mock_type):
        mock_type.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_fill(session="s1", title="x", caption="")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdPublish(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_wait_for_text")
    @mock.patch("publish_douyin.camoufox_click")
    def test_publish_success(self, mock_click, mock_wait):
        mock_click.return_value = True
        mock_wait.return_value = True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_publish(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])

    @mock.patch("publish_douyin.camoufox_click")
    def test_publish_button_not_found_exits_1(self, mock_click):
        mock_click.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_publish(session="s1")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdGetLink(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_success(self, mock_eval, mock_open):
        mock_eval.return_value = "https://www.douyin.com/video/12345"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_get_link(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], "https://www.douyin.com/video/12345")

    @mock.patch("publish_douyin.camoufox_open")
    @mock.patch("publish_douyin.camoufox_eval")
    def test_get_link_no_result_exits_1(self, mock_eval, mock_open):
        mock_eval.return_value = "null"
        with self.assertRaises(SystemExit) as ctx:
            publish_douyin.cmd_get_link(session="s1")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdRun(unittest.TestCase):
    @mock.patch("publish_douyin.login_manager_check")
    def test_run_cookie_expired_exits_2(self, mock_check):
        mock_check.return_value = False
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            with self.assertRaises(SystemExit) as ctx:
                publish_douyin.cmd_run(video=str(video), title="t")
        self.assertEqual(ctx.exception.code, 2)


class TestCleanup(unittest.TestCase):
    @mock.patch("publish_douyin.camoufox_close")
    def test_cleanup_invokes_close(self, mock_close):
        out = StringIO()
        with mock.patch("sys.stdout", out):
            publish_douyin.cmd_cleanup(session="s1")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        mock_close.assert_called_once_with("s1")


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
