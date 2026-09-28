"""Regression tests for xhs_engagement metric normalization."""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "crews/main/skills/expert-xhs/tools/xhs-engagement/scripts/xhs_engagement.py"
SPEC = importlib.util.spec_from_file_location("xhs_engagement", SCRIPT_PATH)
assert SPEC and SPEC.loader
xhs_engagement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xhs_engagement)


class CreatorEngagementTests(unittest.TestCase):
    def test_fetch_writes_complete_creator_metrics(self) -> None:
        metrics = {"views": 101, "comments": 7, "likes": 23, "collects": 5, "shares": 2}
        entry = {"id": "abc", "title": "测试笔记", "metrics": metrics, "missing": []}
        output = io.StringIO()
        with (
            mock.patch.object(xhs_engagement, "lookup_published_row", return_value={
                "id": 42, "title": "测试笔记", "publish_url": "https://www.xiaohongshu.com/explore/abc",
            }),
            mock.patch.object(xhs_engagement, "load_notes", return_value=([entry], {})),
            mock.patch.object(xhs_engagement, "load_analytics", return_value={}),
            mock.patch.object(xhs_engagement, "load_note_detail", return_value={}),
            mock.patch.object(xhs_engagement, "load_note_portrait", return_value=None),
            mock.patch.object(xhs_engagement, "previous_detail", return_value=({}, None)),
            mock.patch.object(xhs_engagement.time, "sleep"),
            mock.patch.object(xhs_engagement, "update_metrics_row", return_value={"ok": True}) as update,
            mock.patch("sys.stdout", output),
        ):
            self.assertEqual(xhs_engagement.main(["fetch", "--row-id", "42"]), 0)
        update.assert_called_once_with(42, metrics, None, None)

    def test_fetch_writes_deep_summary_and_video_completion_for_matching_id(self) -> None:
        metrics = {"views": 14, "comments": 0, "likes": 2, "collects": 0, "shares": 0}
        entry = {"id": "video-123", "title": "视频", "metrics": metrics, "missing": []}
        summary = {"imp_count": 178, "coverClickRate": 0.073}
        detail = {"impl_count": 178, "cover_click_rate": 7.3, "full_view_rate": 25}
        with (
            mock.patch.object(xhs_engagement, "lookup_published_row", return_value={
                "id": 42, "title": "视频", "publish_url": "https://www.xiaohongshu.com/explore/video-123",
            }),
            mock.patch.object(xhs_engagement, "load_notes", return_value=([entry], {})),
            mock.patch.object(xhs_engagement, "load_analytics", return_value={"video-123": summary}),
            mock.patch.object(xhs_engagement, "load_note_detail", return_value=detail),
            mock.patch.object(xhs_engagement, "update_metrics_row", return_value={"ok": True}) as update,
            mock.patch("sys.stdout", io.StringIO()),
        ):
            self.assertEqual(xhs_engagement.main(["fetch", "--row-id", "42"]), 0)
        args = update.call_args.args
        self.assertEqual(args[:2], (42, metrics))
        self.assertEqual(args[2]["summary"], summary)
        self.assertEqual(args[2]["detail"], detail)
        self.assertIn("detail_captured_at", args[2])
        self.assertIsNone(args[3])

    def test_high_view_note_writes_complete_portrait_data(self) -> None:
        metrics = {"views": 120, "comments": 1, "likes": 3, "collects": 0, "shares": 0}
        entry = {"id": "abc", "title": "高阅读", "metrics": metrics, "missing": []}
        portrait = {
            "no_data": False,
            "gender": [{"name": "女", "value": 62}],
            "age": [{"name": "25-34", "value": 50}],
            "city": [], "interest": [],
        }
        with (
            mock.patch.object(xhs_engagement, "lookup_published_row", return_value={
                "id": 9, "title": "高阅读", "publish_url": "https://www.xiaohongshu.com/explore/abc",
            }),
            mock.patch.object(xhs_engagement, "load_notes", return_value=([entry], {})),
            mock.patch.object(xhs_engagement, "load_analytics", return_value={"abc": {"read_count": 120}}),
            mock.patch.object(xhs_engagement, "load_note_detail", return_value={}),
            mock.patch.object(xhs_engagement, "load_note_portrait", return_value=portrait) as load_portrait,
            mock.patch.object(xhs_engagement, "previous_detail", return_value=({}, None)),
            mock.patch.object(xhs_engagement.time, "sleep"),
            mock.patch.object(xhs_engagement, "update_metrics_row", return_value={"ok": True}) as update,
            mock.patch("sys.stdout", io.StringIO()),
        ):
            self.assertEqual(xhs_engagement.main(["fetch", "--row-id", "9"]), 0)
        load_portrait.assert_called_once_with("abc")
        self.assertEqual(update.call_args.args[3], portrait)

    def test_no_data_portrait_is_not_saved(self) -> None:
        api = mock.Mock()
        api.get_note_audience_portrait.return_value = (
            True, "成功", {"data": {"no_data": True, "gender": [], "age": [], "city": [], "interest": []}},
        )
        with mock.patch.object(xhs_engagement, "creator_api") as creator_api:
            creator_api.return_value.__enter__.return_value = api
            self.assertIsNone(xhs_engagement.load_note_portrait("abc"))

    def test_update_writes_metrics_to_the_correct_named_columns(self) -> None:
        metrics = {
            "views": 101,
            "comments": 7,
            "likes": 23,
            "collects": 5,
            "shares": 2,
        }
        completed = xhs_engagement.subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true}', stderr=""
        )

        with (
            mock.patch.object(xhs_engagement, "UPDATE_METRICS_SH", SCRIPT_PATH),
            mock.patch.object(xhs_engagement.subprocess, "run", return_value=completed) as run,
        ):
            result = xhs_engagement.update_metrics_row(42, metrics)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            run.call_args.args[0],
            [
                str(SCRIPT_PATH),
                "--platform", "xhs",
                "--id", "42",
                "--views", "101",
                "--comments", "7",
                "--likes", "23",
                "--favorites", "5",
                "--shares", "2",
            ],
        )

    def test_deep_json_is_passed_to_published_track_and_removed(self) -> None:
        captured = {}

        def capture(cmd, **_kwargs):
            path = Path(cmd[cmd.index("--deep-file") + 1])
            captured["path"] = path
            captured["deep"] = json.loads(path.read_text(encoding="utf-8"))
            captured["source"] = cmd[cmd.index("--deep-source") + 1]
            return xhs_engagement.subprocess.CompletedProcess([], 0, '{"ok":true}', "")

        with (
            mock.patch.object(xhs_engagement, "UPDATE_METRICS_SH", SCRIPT_PATH),
            mock.patch.object(xhs_engagement.subprocess, "run", side_effect=capture),
        ):
            self.assertTrue(xhs_engagement.update_metrics_row(4, {"views": 1}, {"detail": {"full_view_rate": 25}})["ok"])
        self.assertEqual(captured["deep"], {"detail": {"full_view_rate": 25}})
        self.assertEqual(captured["source"], "xhs:creator_datacenter")
        self.assertFalse(captured["path"].exists())

    def test_posted_notes_follow_cursor_beyond_two_pages(self) -> None:
        api = mock.Mock()
        api.get_posted_notes_page.side_effect = [
            (True, "成功", {"data": {"notes": [{"id": "a"}], "page": 11}}),
            (True, "成功", {"data": {"notes": [{"id": "b"}], "page": 22}}),
            (True, "成功", {"data": {"notes": [{"id": "c"}], "page": -1}}),
        ]
        with (
            mock.patch.object(xhs_engagement, "creator_api") as creator_api,
            mock.patch.object(xhs_engagement.time, "sleep"),
            mock.patch.object(xhs_engagement, "observe"),
        ):
            creator_api.return_value.__enter__.return_value = api
            notes, _ = xhs_engagement.load_notes(max_pages=10)
        self.assertEqual([note["id"] for note in notes], ["a", "b", "c"])
        self.assertEqual(
            [call.kwargs["page"] for call in api.get_posted_notes_page.call_args_list],
            [0, 11, 22],
        )

    def test_posted_notes_reject_truncated_page_limit(self) -> None:
        api = mock.Mock()
        api.get_posted_notes_page.side_effect = [
            (True, "成功", {"data": {"notes": [{"id": "a"}], "page": 11}}),
            (True, "成功", {"data": {"notes": [{"id": "b"}], "page": 22}}),
        ]
        with (
            mock.patch.object(xhs_engagement, "creator_api") as creator_api,
            mock.patch.object(xhs_engagement.time, "sleep"),
        ):
            creator_api.return_value.__enter__.return_value = api
            with self.assertRaises(xhs_engagement.CreatorApiFailure):
                xhs_engagement.load_notes(max_pages=2)

    def test_daily_posted_notes_stop_after_three_pages_without_error(self) -> None:
        api = mock.Mock()
        api.get_posted_notes_page.side_effect = [
            (True, "成功", {"data": {"notes": [{"id": str(index)}], "page": index + 1}})
            for index in range(3)
        ]
        with (
            mock.patch.object(xhs_engagement, "creator_api") as creator_api,
            mock.patch.object(xhs_engagement.time, "sleep"),
            mock.patch.object(xhs_engagement, "observe"),
        ):
            creator_api.return_value.__enter__.return_value = api
            notes, _ = xhs_engagement.load_notes(max_pages=3, allow_partial=True)
        self.assertEqual([note["id"] for note in notes], ["0", "1", "2"])
        self.assertEqual(api.get_posted_notes_page.call_count, 3)

    def test_daily_analytics_stop_after_three_pages_without_error(self) -> None:
        api = mock.Mock()
        api.get_note_analyze_page.side_effect = [
            (True, "成功", {"data": {
                "note_infos": [{"id": f"{page}-{index}"} for index in range(10)],
                "total": 50,
            }})
            for page in range(3)
        ]
        with (
            mock.patch.object(xhs_engagement, "creator_api") as creator_api,
            mock.patch.object(xhs_engagement.time, "sleep"),
            mock.patch.object(xhs_engagement, "observe"),
        ):
            creator_api.return_value.__enter__.return_value = api
            analytics = xhs_engagement.load_analytics(max_pages=3, allow_partial=True)
        self.assertEqual(len(analytics), 30)
        self.assertEqual(api.get_note_analyze_page.call_count, 3)

    def test_portrait_json_is_passed_whole_to_published_track(self) -> None:
        portrait = {"no_data": False, "gender": [{"name": "女", "value": 62}], "age": [], "city": [], "interest": []}
        captured = {}

        def capture(cmd, **_kwargs):
            path = Path(cmd[cmd.index("--fan-portrait-file") + 1])
            captured["path"] = path
            captured["portrait"] = json.loads(path.read_text(encoding="utf-8"))
            return xhs_engagement.subprocess.CompletedProcess([], 0, '{"ok":true}', "")

        with (
            mock.patch.object(xhs_engagement, "UPDATE_METRICS_SH", SCRIPT_PATH),
            mock.patch.object(xhs_engagement.subprocess, "run", side_effect=capture),
        ):
            self.assertTrue(xhs_engagement.update_metrics_row(4, {"views": 120}, None, portrait)["ok"])
        self.assertEqual(captured["portrait"], portrait)
        self.assertFalse(captured["path"].exists())

if __name__ == "__main__":
    unittest.main()
