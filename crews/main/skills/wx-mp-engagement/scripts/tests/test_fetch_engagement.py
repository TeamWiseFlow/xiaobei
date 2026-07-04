#!/usr/bin/env python3
"""Unit tests for fetch_engagement.py (Phase 4.6 wx-mp engagement skill).

Covers:
- CLI subcommand routing (fetch, fetch-all)
- Argument validation (--row-id / --source-folder required, --days bounds)
- published-track row lookup (mocked sqlite3)
- engagement payload assembly (stats + top_comment + updated_at)
- DB write to pub_wx_mp via update-metrics.sh (subprocess mocked)
- Session lifecycle (cookie-import + open + cleanup)

All camoufox-cli + http + sqlite3 + subprocess calls are mocked — these are
unit tests, integration tests are deferred to the post-deployment phase.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import fetch_engagement  # noqa: E402


class TestPlatformConstants(unittest.TestCase):
    def test_platform_constant(self):
        # 微信平台 key 与 published-track 表名 pub_wx_mp 解耦
        self.assertEqual(fetch_engagement.PLATFORM, "wx_mp")
        # login-manager 中央存储 key
        self.assertEqual(fetch_engagement.LOGIN_MANAGER_PLATFORM, "wx-mp")

    def test_creator_center_url(self):
        # 创作者中心入口（spike 验证后可能微调）
        self.assertTrue(fetch_engagement.CREATOR_CENTER_URL.startswith("https://mp.weixin.qq.com/"))


class TestCliValidation(unittest.TestCase):
    def test_fetch_requires_row_id_or_source_folder(self):
        with self.assertRaises(SystemExit) as ctx:
            fetch_engagement.cmd_fetch(args=mock.Mock(row_id=None, source_folder=None))
        self.assertEqual(ctx.exception.code, 1)

    def test_fetch_all_days_must_be_positive(self):
        with self.assertRaises(SystemExit) as ctx:
            fetch_engagement.cmd_fetch_all(days=0)
        self.assertEqual(ctx.exception.code, 1)
        with self.assertRaises(SystemExit) as ctx:
            fetch_engagement.cmd_fetch_all(days=-1)
        self.assertEqual(ctx.exception.code, 1)


class TestEngagementPayload(unittest.TestCase):
    """Verify the JSON shape written to pub_wx_mp via update-metrics.sh."""

    def test_payload_shape(self):
        raw = {
            "read_count": 1234,
            "like_count": 56,
            "comment_count": 7,
            "share_count": 8,
            "favorite_count": 9,
            "top_comment": {"user": "用户A", "text": "好文", "like": 12},
        }
        out = fetch_engagement.build_metrics_payload(raw)
        self.assertEqual(out["reads"], 1234)
        self.assertEqual(out["likes"], 56)
        self.assertEqual(out["comments"], 7)
        self.assertEqual(out["shares"], 8)
        self.assertEqual(out["favorites"], 9)
        self.assertIn("用户A", out["top_comment"])
        self.assertIn("好文", out["top_comment"])

    def test_payload_handles_missing_fields(self):
        out = fetch_engagement.build_metrics_payload({})
        self.assertEqual(out["reads"], 0)
        self.assertEqual(out["likes"], 0)
        self.assertEqual(out["comments"], 0)
        self.assertEqual(out["shares"], 0)
        self.assertEqual(out["favorites"], 0)
        self.assertEqual(out["top_comment"], "")


class TestParseCreatorCenterDom(unittest.TestCase):
    """DOM 解析层（mock 后用 HTML fixture）"""

    def test_parse_read_count_from_dom(self):
        # 创作者中心单篇分析页 DOM 结构（推测，spike 验证后调整）
        html = """
        <div class="read-count">1,234</div>
        <div class="like-count">56</div>
        <div class="comment-count">7</div>
        """
        out = fetch_engagement.parse_dom_metrics(html)
        self.assertEqual(out["reads"], 1234)
        self.assertEqual(out["likes"], 56)
        self.assertEqual(out["comments"], 7)

    def test_parse_handles_missing_selectors(self):
        # 缺字段时不抛错，记 0
        out = fetch_engagement.parse_dom_metrics("<div>other</div>")
        self.assertEqual(out["reads"], 0)
        self.assertEqual(out["likes"], 0)
        self.assertEqual(out["comments"], 0)


class TestFetchCommandFlow(unittest.TestCase):
    """fetch --row-id <id> 端到端流程（全部 IO mock）"""

    def setUp(self):
        self.row = {
            "id": 42,
            "title": "测试文章",
            "publish_url": "https://mp.weixin.qq.com/s?__biz=xxx&mid=123",
            "publish_date": "2026-07-01",
            "source_folder": "output_articles/test/",
        }

    @mock.patch("fetch_engagement.update_metrics_row")
    @mock.patch("fetch_engagement.parse_dom_metrics")
    @mock.patch("fetch_engagement.camoufox_fetch_dom")
    @mock.patch("fetch_engagement.camoufox_open_session")
    @mock.patch("fetch_engagement.login_manager_session_cleanup")
    @mock.patch("fetch_engagement.login_manager_cookie_import")
    @mock.patch("fetch_engagement.login_manager_check")
    @mock.patch("fetch_engagement.lookup_published_row")
    def test_fetch_happy_path(
        self, mock_lookup, mock_check, mock_import, mock_cleanup, mock_open,
        mock_camoufox, mock_parse, mock_update
    ):
        mock_check.return_value = True
        mock_lookup.return_value = self.row
        mock_camoufox.return_value = "<div class='read-count'>100</div>"
        mock_parse.return_value = {"reads": 100, "likes": 5, "comments": 2, "shares": 0, "favorites": 0}
        mock_update.return_value = {"ok": True, "action": "updated"}

        out = StringIO()
        with mock.patch("sys.stdout", out):
            fetch_engagement.cmd_fetch(args=mock.Mock(row_id=42, source_folder=None))
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["row_id"], 42)
        self.assertEqual(result["metrics"]["reads"], 100)
        mock_update.assert_called_once()
        mock_import.assert_called_once()
        mock_cleanup.assert_called_once()

    @mock.patch("fetch_engagement.login_manager_check")
    def test_fetch_aborts_on_expired_cookie(self, mock_check):
        mock_check.return_value = False
        with self.assertRaises(SystemExit) as ctx:
            fetch_engagement.cmd_fetch(args=mock.Mock(row_id=42, source_folder=None))
        # exit 2 = cookie 失效，与 login-manager / fetch-and-update-metrics 契约一致
        self.assertEqual(ctx.exception.code, 2)

    @mock.patch("fetch_engagement.login_manager_check")
    @mock.patch("fetch_engagement.lookup_published_row")
    def test_fetch_aborts_on_missing_row(self, mock_lookup, mock_check):
        mock_check.return_value = True
        mock_lookup.return_value = None
        with self.assertRaises(SystemExit) as ctx:
            fetch_engagement.cmd_fetch(args=mock.Mock(row_id=999, source_folder=None))
        self.assertEqual(ctx.exception.code, 1)


class TestSessionLifecycle(unittest.TestCase):
    """Session 创建/清理"""

    @mock.patch("fetch_engagement.subprocess.run")
    def test_open_session_runs_camoufox_open(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
        fetch_engagement.camoufox_open_session("wx-mp-engagement-abc12345")
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertIn("camoufox-cli", cmd[0])
        self.assertIn("--session", cmd)
        self.assertIn("wx-mp-engagement-abc12345", cmd)
        self.assertIn("--persistent", cmd)
        self.assertIn("--headless", cmd)

    @mock.patch("fetch_engagement.subprocess.run")
    def test_fetch_dom_runs_eval(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "data": json.dumps({"html": "<div class='read-count'>99</div>"}),
            }),
        )
        out = fetch_engagement.camoufox_fetch_dom("session-x", "https://mp.weixin.qq.com/foo")
        self.assertIn("read-count", out)
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertIn("eval", cmd)


class TestFetchAllCommand(unittest.TestCase):
    @mock.patch("fetch_engagement.cmd_fetch")
    @mock.patch("fetch_engagement.list_pending_wx_mp_rows")
    def test_fetch_all_iterates_rows(self, mock_list, mock_fetch):
        mock_list.return_value = [42, 43, 44]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            fetch_engagement.cmd_fetch_all(days=7)
        self.assertEqual(mock_fetch.call_count, 3)
        result = json.loads(out.getvalue())
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["results"]), 3)

    @mock.patch("fetch_engagement.list_pending_wx_mp_rows")
    def test_fetch_all_handles_empty(self, mock_list):
        mock_list.return_value = []
        out = StringIO()
        with mock.patch("sys.stdout", out):
            fetch_engagement.cmd_fetch_all(days=7)
        result = json.loads(out.getvalue())
        self.assertEqual(result["total"], 0)


if __name__ == "__main__":
    unittest.main()
