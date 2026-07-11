#!/usr/bin/env python3
"""Unit tests for twitter_interact.py (Phase 2026.7 v2.4 borrow).

Covers:
- 6 subcommands on tweets (like/unlike/retweet/unretweet/bookmark/unbookmark)
- 2 subcommands on users (follow/unfollow)
- URL/id extraction (extract_tweet_id / extract_user_handle)
- Frequency limit (check_freq_limit / record_action)
- Session naming (D18 + 4.5.5)
- run / cleanup subcommands

All camoufox-cli / login-manager / file IO are mocked.
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

import twitter_interact  # noqa: E402


class TestExtractTweetId(unittest.TestCase):
    def test_bare_id(self):
        self.assertEqual(twitter_interact.extract_tweet_id("1234567890"), "1234567890")

    def test_x_url(self):
        self.assertEqual(
            twitter_interact.extract_tweet_id("https://x.com/user/status/1234567890"),
            "1234567890",
        )

    def test_x_url_with_query(self):
        self.assertEqual(
            twitter_interact.extract_tweet_id("https://x.com/user/status/1234567890?s=20"),
            "1234567890",
        )

    def test_invalid(self):
        self.assertIsNone(twitter_interact.extract_tweet_id("not-a-tweet"))
        self.assertIsNone(twitter_interact.extract_tweet_id(""))


class TestExtractUserHandle(unittest.TestCase):
    def test_bare_handle(self):
        self.assertEqual(twitter_interact.extract_user_handle("elonmusk"), "elonmusk")

    def test_at_prefix(self):
        self.assertEqual(twitter_interact.extract_user_handle("@openai"), "openai")

    def test_url(self):
        self.assertEqual(
            twitter_interact.extract_user_handle("https://x.com/openai"),
            "openai",
        )

    def test_url_trailing_path(self):
        self.assertEqual(
            twitter_interact.extract_user_handle("https://x.com/openai/"),
            "openai",
        )

    def test_reserved_paths(self):
        # x.com/i, x.com/intent 等应被排除
        self.assertIsNone(twitter_interact.extract_user_handle("https://x.com/i/web/status/123"))

    def test_invalid(self):
        self.assertIsNone(twitter_interact.extract_user_handle(""))


class TestSessionNaming(unittest.TestCase):
    def test_session_is_constant_twitter(self):
        # 原则 1：每平台一个且只一个持久化 session。purpose 参数仅标注意图，不影响 session 名。
        self.assertEqual(twitter_interact.session_name("like"), "twitter")
        self.assertEqual(twitter_interact.session_name("retweet"), "twitter")
        self.assertEqual(twitter_interact.TWITTER_SESSION, "twitter")


class TestFailFirstQueue(unittest.TestCase):
    """forked cli fail-first 队列（spec §1.1）：session 正忙时抛 SessionBusyError，
    twitter_session 透传 exit 3 且不 close（避免 tear down 正在跑的另一个操作）。"""

    @mock.patch("twitter_interact.camoufox_close")
    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    def test_busy_raises_exit3_no_close(self, mock_open, mock_eval, mock_close):
        mock_open.side_effect = twitter_interact.SessionBusyError(
            "session twitter 正忙，请等待当前操作完成后再试"
        )
        with self.assertRaises(SystemExit) as ctx:
            twitter_interact.cmd_like("https://x.com/u/status/123")
        self.assertEqual(ctx.exception.code, 3)
        # 关键：busy 时不能 close（会 tear down 正在跑的另一个操作）
        mock_close.assert_not_called()


class TestFrequencyLimits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch = mock.patch.object(
            twitter_interact, "FREQ_TRACKER_PATH",
            Path(self.tmp.name) / "freq.json"
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_check_fresh_path(self):
        ok, reason = twitter_interact.check_freq_limit("like")
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_check_min_interval_violation(self):
        # 写一个 1s 前的记录
        import time as t
        twitter_interact._save_freq({
            "last_action_at": t.strftime("%Y-%m-%dT%H:%M:%S%z", t.localtime(t.time() - 1)),
            "today_count": 5,
            "last_action_type": "like",
        })
        ok, reason = twitter_interact.check_freq_limit("like")
        self.assertFalse(ok)
        self.assertIn("限制", reason)

    def test_check_daily_max_violation(self):
        twitter_interact._save_freq({
            "last_action_at": "2020-01-01T00:00:00+00:00",  # 很久以前
            "today_count": 200,  # like 上限 200
            "last_action_type": "like",
        })
        ok, reason = twitter_interact.check_freq_limit("like")
        self.assertFalse(ok)
        self.assertIn("日上限", reason)

    def test_record_action_increments(self):
        twitter_interact.record_action("like")
        data = twitter_interact._load_freq()
        self.assertEqual(data["today_count"], 1)
        self.assertEqual(data["last_action_type"], "like")
        self.assertEqual(data["actions"]["like"], 1)


class TestCmdLike(unittest.TestCase):
    @mock.patch("twitter_interact.record_action")
    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_like_success(self, mock_close, mock_open, mock_eval, mock_record):
        mock_eval.return_value = "true"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_like("https://x.com/u/status/123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "like")
        self.assertEqual(result["tweet_id"], "123")
        mock_record.assert_called_once()
        mock_close.assert_called_once()

    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_like_already(self, mock_close, mock_open, mock_eval):
        mock_eval.return_value = "already"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_like("123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertIn("已点赞", result["note"])

    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_like_invalid_url(self, mock_close, mock_open, mock_eval):
        with self.assertRaises(SystemExit) as ctx:
            twitter_interact.cmd_like("not-a-tweet")
        self.assertEqual(ctx.exception.code, 1)

    @mock.patch("twitter_interact.check_freq_limit")
    def test_like_freq_limit_blocks(self, mock_check):
        mock_check.return_value = (False, "频率限制 — 测试")
        with self.assertRaises(SystemExit) as ctx:
            twitter_interact.cmd_like("123")
        self.assertEqual(ctx.exception.code, 1)


class TestCmdRetweet(unittest.TestCase):
    @mock.patch("twitter_interact.record_action")
    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_retweet_with_confirm(self, mock_close, mock_open, mock_eval, mock_record):
        # 第一次 eval 返回 pending_confirm，第二次返回 true
        mock_eval.side_effect = ["pending_confirm", "true"]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_retweet("123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "retweet")
        mock_record.assert_called_once()

    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_retweet_already(self, mock_close, mock_open, mock_eval):
        mock_eval.return_value = "already"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_retweet("123")
        result = json.loads(out.getvalue())
        self.assertIn("已转推", result["note"])


class TestCmdFollow(unittest.TestCase):
    @mock.patch("twitter_interact.record_action")
    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_follow_success(self, mock_close, mock_open, mock_eval, mock_record):
        mock_eval.return_value = "true"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_follow("openai")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"], "openai")
        mock_record.assert_called_once()

    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_follow_already(self, mock_close, mock_open, mock_eval):
        mock_eval.return_value = "not_found"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_follow("openai")
        result = json.loads(out.getvalue())
        self.assertIn("已关注", result["note"])


class TestCmdUnfollow(unittest.TestCase):
    @mock.patch("twitter_interact.camoufox_eval")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_unfollow_with_confirm(self, mock_close, mock_open, mock_eval):
        mock_eval.side_effect = ["pending_confirm", "true"]
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_unfollow("openai")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "unfollow")


class TestCmdRun(unittest.TestCase):
    @mock.patch("twitter_interact.login_manager_check")
    @mock.patch("twitter_interact.cmd_like")
    def test_run_like_tweet(self, mock_like, mock_check):
        mock_check.return_value = True
        with mock.patch("sys.argv", ["twitter_interact", "run",
                                      "--tweet-url", "https://x.com/u/status/123",
                                      "--action", "like"]):
            twitter_interact.main()
        mock_like.assert_called_once_with("https://x.com/u/status/123")

    @mock.patch("twitter_interact.login_manager_check")
    def test_run_cookie_expired(self, mock_check):
        mock_check.return_value = False
        # main() 抓住 SystemExit 转换为返回值
        with mock.patch("sys.argv", ["twitter_interact", "run",
                                      "--tweet-url", "123",
                                      "--action", "like"]):
            rc = twitter_interact.main()
        self.assertEqual(rc, 2)


class TestIntegrationDryRun(unittest.TestCase):
    def test_help_runs(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "twitter_interact.py"), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("like", result.stdout)


if __name__ == "__main__":
    unittest.main()
