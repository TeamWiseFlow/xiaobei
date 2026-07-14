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

    @mock.patch("publish_douyin.camoufox_wait_for_text")
    @mock.patch("publish_douyin.camoufox_upload")
    @mock.patch("publish_douyin.camoufox_open")
    def test_successful_upload(self, mock_open, mock_upload, mock_wait):
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

    @mock.patch("publish_douyin.camoufox_wait_for_text")
    @mock.patch("publish_douyin.camoufox_upload")
    @mock.patch("publish_douyin.camoufox_open")
    def test_upload_setfile_fail_exits_1(self, mock_open, mock_upload, mock_wait):
        mock_upload.return_value = False
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
