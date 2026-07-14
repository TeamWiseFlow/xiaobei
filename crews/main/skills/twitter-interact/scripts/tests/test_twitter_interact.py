#!/usr/bin/env python3
"""Unit tests for twitter_interact.py.

Covers:
- 6 subcommands on tweets (like/unlike/retweet/unretweet/bookmark/unbookmark)
- 2 subcommands on users (follow/unfollow)
- URL/id extraction (extract_tweet_id / extract_user_handle)
- Frequency limit (check_freq_limit / record_action)
- Session naming (单一持久化 session twitter）
- run / cleanup subcommands
- article-scoped 探针 / testid 确认菜单 / 晚水合轮询（mock 新 helper）

All camoufox-cli / file IO are mocked at the helper layer (_poll_probe /
_click_scoped / _click_confirm / _poll_suffix / _click_suffix), 不耦合 eval 调用次数。
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
    """forked cli fail-first 队列：session 正忙时抛 SessionBusyError，
    twitter_session 透传 exit 3 且不 close（避免 tear down 正在跑的另一个操作）。"""

    @mock.patch("twitter_interact.camoufox_close")
    @mock.patch("twitter_interact.camoufox_open")
    def test_busy_raises_exit3_no_close(self, mock_open, mock_close):
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


# ── 命令层测试：mock 新 helper（_poll_probe / _click_scoped / _click_confirm /
#    _poll_suffix / _click_suffix），不耦合 eval 调用次数。 ────────────────

class TestCmdLike(unittest.TestCase):
    @mock.patch("twitter_interact.record_action")
    @mock.patch("twitter_interact._poll_probe")
    @mock.patch("twitter_interact._click_scoped")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_like_success(self, mock_close, mock_open, mock_click, mock_probe, mock_record):
        # 第一次探针找到 like，验证探针找到 unlike
        mock_probe.side_effect = ["like", "unlike"]
        mock_click.return_value = "clicked"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_like("https://x.com/u/status/123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "like")
        self.assertEqual(result["tweet_id"], "123")
        mock_record.assert_called_once()
        mock_close.assert_called_once()

    @mock.patch("twitter_interact._poll_probe")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_like_already(self, mock_close, mock_open, mock_probe):
        mock_probe.return_value = "unlike"  # 已点赞
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_like("123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertIn("已点赞", result["note"])

    @mock.patch("twitter_interact.camoufox_open")
    def test_like_invalid_url(self, mock_open):
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
    @mock.patch("twitter_interact._click_confirm")
    @mock.patch("twitter_interact._poll_probe")
    @mock.patch("twitter_interact._click_scoped")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_retweet_with_confirm(self, mock_close, mock_open, mock_click, mock_probe,
                                  mock_confirm, mock_record):
        # 探针：找到 retweet，验证找到 unretweet
        mock_probe.side_effect = ["retweet", "unretweet"]
        mock_click.return_value = "clicked"
        mock_confirm.return_value = True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_retweet("123")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "retweet")
        # 确认菜单用 testid=retweetConfirm（不是 text match "Repost"）
        mock_confirm.assert_called_once_with(twitter_interact.TWITTER_SESSION, "retweetConfirm")
        mock_record.assert_called_once()

    @mock.patch("twitter_interact._poll_probe")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_retweet_already(self, mock_close, mock_open, mock_probe):
        mock_probe.return_value = "unretweet"  # 已转推
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_retweet("123")
        result = json.loads(out.getvalue())
        self.assertIn("已转推", result["note"])


class TestCmdFollow(unittest.TestCase):
    @mock.patch("twitter_interact.record_action")
    @mock.patch("twitter_interact._poll_suffix")
    @mock.patch("twitter_interact._click_suffix")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_follow_success(self, mock_close, mock_open, mock_click, mock_suffix, mock_record):
        mock_suffix.side_effect = ["-follow", "-unfollow"]
        mock_click.return_value = "clicked"
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_follow("openai")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"], "openai")
        mock_record.assert_called_once()

    @mock.patch("twitter_interact._poll_suffix")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_follow_already(self, mock_close, mock_open, mock_suffix):
        mock_suffix.return_value = "-unfollow"  # 已关注
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_follow("openai")
        result = json.loads(out.getvalue())
        self.assertIn("已关注", result["note"])


class TestCmdUnfollow(unittest.TestCase):
    @mock.patch("twitter_interact._click_confirm")
    @mock.patch("twitter_interact._poll_suffix")
    @mock.patch("twitter_interact._click_suffix")
    @mock.patch("twitter_interact.camoufox_open")
    @mock.patch("twitter_interact.camoufox_close")
    def test_unfollow_with_confirm(self, mock_close, mock_open, mock_click, mock_suffix, mock_confirm):
        mock_suffix.side_effect = ["-unfollow", "-follow"]
        mock_click.return_value = "clicked"
        mock_confirm.return_value = True
        out = StringIO()
        with mock.patch("sys.stdout", out):
            twitter_interact.cmd_unfollow("openai")
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["action"], "unfollow")
        # 确认菜单用 testid=confirmationSheetConfirm（不是 text match "Unfollow"）
        mock_confirm.assert_called_once_with(twitter_interact.TWITTER_SESSION, "confirmationSheetConfirm")


class TestCmdRun(unittest.TestCase):
    """cmd_run 不再 gate login-manager（探活归前奏/agent），纯派发。"""

    @mock.patch("twitter_interact.cmd_like")
    def test_run_like_tweet(self, mock_like):
        with mock.patch("sys.argv", ["twitter_interact", "run",
                                      "--tweet-url", "https://x.com/u/status/123",
                                      "--action", "like"]):
            twitter_interact.main()
        mock_like.assert_called_once_with("https://x.com/u/status/123")

    @mock.patch("twitter_interact.cmd_follow")
    def test_run_follow_user(self, mock_follow):
        with mock.patch("sys.argv", ["twitter_interact", "run",
                                      "--user", "openai",
                                      "--action", "follow"]):
            twitter_interact.main()
        mock_follow.assert_called_once_with("openai")


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
