"""Safety boundaries for the local Creator route."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "crews/main/skills/expert-xhs/tools"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engagement = load("xhs_engagement_for_local_tests", SCRIPTS / "xhs-engagement/scripts/xhs_engagement.py")
publish_cli = load("publish_xhs_for_local_tests", SCRIPTS / "xhs-publish/scripts/publish_xhs.py")
publish = publish_cli
session_module = load("creator_session_for_local_tests", ROOT / "crews/main/skills/expert-xhs/tools/scripts/creator_session.py")


class CreatorMetricsTests(unittest.TestCase):
    def test_daily_writes_without_enable_step(self):
        args = type("Args", (), {"cmd": "daily"})()
        metrics = {"views": 12, "comments": 1, "likes": 2, "collects": 3, "shares": 0}
        entry = {"id": "abc", "title": "作品", "metrics": metrics, "missing": []}
        row = {"id": 42, "title": "作品", "publish_url": "https://www.xiaohongshu.com/explore/abc"}
        old_row = {"id": 5, "title": "旧作品", "publish_url": "https://www.xiaohongshu.com/explore/old"}
        output = io.StringIO()
        with (
            mock.patch.object(engagement, "claim_daily_run", return_value=True),
            mock.patch.object(engagement, "list_all_xhs_rows", return_value=[row, old_row]),
            mock.patch.object(engagement, "load_notes", return_value=([entry], {})) as load_notes,
            mock.patch.object(engagement, "load_analytics", return_value={}) as load_analytics,
            mock.patch.object(engagement, "load_note_detail", return_value={}),
            mock.patch.object(engagement, "previous_detail", return_value=({}, None)),
            mock.patch.object(engagement, "update_metrics_row", return_value={"ok": True}) as update,
            mock.patch.object(sys, "stdout", new=output),
        ):
            code = engagement.dispatch(args)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["matched"], 1)
        self.assertEqual(json.loads(output.getvalue())["total"], 1)
        self.assertEqual(json.loads(output.getvalue())["creator_notes_scanned"], 1)
        load_notes.assert_called_once_with(max_pages=3, allow_partial=True)
        load_analytics.assert_called_once_with(max_pages=3, allow_partial=True)
        update.assert_called_once_with(42, metrics, None, None)

    def test_fetch_all_writes_without_enable_step(self):
        args = type("Args", (), {"cmd": "fetch-all"})()
        metrics = {"views": 12, "comments": 1, "likes": 2, "collects": 3, "shares": 0}
        entry = {"id": "abc", "title": "作品", "metrics": metrics, "missing": []}
        row = {"id": 42, "title": "作品", "publish_url": "https://www.xiaohongshu.com/explore/abc"}
        with (
            mock.patch.object(engagement, "list_all_xhs_rows", return_value=[row]),
            mock.patch.object(engagement, "load_notes", return_value=([entry], {})) as load_notes,
            mock.patch.object(engagement, "load_analytics", return_value={}) as load_analytics,
            mock.patch.object(engagement, "load_note_detail", return_value={}),
            mock.patch.object(engagement, "previous_detail", return_value=({}, None)),
            mock.patch.object(engagement, "update_metrics_row", return_value={"ok": True}) as update,
            mock.patch.object(sys, "stdout", new=io.StringIO()),
        ):
            code = engagement.dispatch(args)
        self.assertEqual(code, 0)
        load_notes.assert_called_once_with()
        load_analytics.assert_called_once_with()
        update.assert_called_once_with(42, metrics, None, None)

    def test_daily_skips_analytics_when_recent_pages_have_no_recorded_note(self):
        args = type("Args", (), {"cmd": "daily"})()
        entry = {"id": "recent", "title": "近期作品", "metrics": {}, "missing": []}
        row = {"id": 5, "title": "旧作品", "publish_url": "https://www.xiaohongshu.com/explore/old"}
        output = io.StringIO()
        with (
            mock.patch.object(engagement, "claim_daily_run", return_value=True),
            mock.patch.object(engagement, "list_all_xhs_rows", return_value=[row]),
            mock.patch.object(engagement, "load_notes", return_value=([entry], {})),
            mock.patch.object(engagement, "load_analytics") as load_analytics,
            mock.patch.object(engagement, "update_metrics_row") as update,
            mock.patch.object(sys, "stdout", new=output),
        ):
            self.assertEqual(engagement.dispatch(args), 0)
        self.assertEqual(json.loads(output.getvalue())["creator_notes_scanned"], 1)
        load_analytics.assert_not_called()
        update.assert_not_called()

    def test_missing_share_count_is_not_a_zero(self):
        parsed = engagement.parse_note({
            "note_id": "abc", "title": "作品", "metrics": {
                "view_count": "1.2万", "comment_count": 3,
                "like_count": 8, "collect_count": 2,
            },
        })
        self.assertEqual(parsed["metrics"]["views"], 12000)
        self.assertEqual(parsed["missing"], ["shares"])

    def test_creator_posted_note_live_field_names(self):
        parsed = engagement.parse_note({
            "id": "abc", "display_title": "作品", "view_count": 101,
            "comments_count": 3, "likes": 8,
            "collected_count": 2, "shared_count": 1,
        })
        self.assertEqual(parsed, {
            "id": "abc", "title": "作品", "missing": [],
            "metrics": {"views": 101, "comments": 3, "likes": 8, "collects": 2, "shares": 1},
        })

    def test_published_id_mismatch_does_not_match_same_title(self):
        entries = [{"id": "other", "title": "作品", "metrics": {}, "missing": []}]
        self.assertIsNone(engagement.match(
            entries, title="作品",
            publish_url="https://www.xiaohongshu.com/explore/expected",
            normalize_title=engagement.normalize_title,
        ))

    def test_fetch_with_unknown_schema_never_writes_database(self):
        args = type("Args", (), {"cmd": "fetch", "row_id": 42, "title": None})()
        parsed = [{"id": "abc", "title": "作品", "metrics": {"views": 10}, "missing": ["shares"]}]
        with (
            mock.patch.object(engagement, "load_notes", return_value=(parsed, {})),
            mock.patch.object(engagement, "lookup_published_row", return_value={
                "id": 42, "title": "作品",
                "publish_url": "https://www.xiaohongshu.com/explore/abc",
            }),
            mock.patch.object(engagement, "update_metrics_row") as update,
            mock.patch.object(sys, "stdout", new=io.StringIO()),
        ):
            code = engagement.dispatch(args)
        self.assertEqual(code, 1)
        update.assert_not_called()


class CreatorPublishTests(unittest.TestCase):
    @staticmethod
    def args():
        return type("Args", (), {
            "title": "作品", "mode": "image", "private": False,
            "images": ["image.jpg"], "video": None, "cover": None,
            "ai_declaration": False,
        })()

    def test_success_without_note_id_is_unconfirmed(self):
        api = mock.Mock()
        api.post_note.return_value = (True, "成功", {"success": True, "data": {}})

        @contextmanager
        def client():
            yield api

        with (
            mock.patch.object(publish, "creator_api", client),
            mock.patch.object(publish, "observe"),
        ):
            result = publish.publish(self.args(), "正文", [])
        self.assertEqual(result["error"], "SUBMISSION_UNCONFIRMED")
        api.post_note.assert_called_once()

    def test_transport_error_is_ambiguous_and_never_retried(self):
        api = mock.Mock()
        api.post_note.side_effect = TimeoutError("request timed out")

        @contextmanager
        def client():
            yield api

        with (
            mock.patch.object(publish, "creator_api", client),
            mock.patch.object(publish, "observe"),
        ):
            result = publish.publish(self.args(), "正文", [])
        self.assertEqual(result["error"], "SUBMISSION_UNKNOWN")
        api.post_note.assert_called_once()

    def test_ai_declaration_is_forwarded_to_creator_api(self):
        args = self.args()
        args.ai_declaration = True
        api = mock.Mock()
        api.post_note.return_value = (True, "成功", {
            "success": True, "data": {"note_id": "abc"},
        })

        @contextmanager
        def client():
            yield api

        with (
            mock.patch.object(publish, "creator_api", client),
            mock.patch.object(publish, "observe"),
        ):
            result = publish.publish(args, "正文", [])
        self.assertTrue(result["ok"])
        self.assertTrue(api.post_note.call_args.args[0]["ai_declaration"])


class CreatorRouteTests(unittest.TestCase):
    def test_publish_uses_only_creator_route(self):
        argv = ["--mode", "image", "--title", "作品", "--body", "正文", "--images", "image.jpg"]
        with (
            mock.patch.object(publish_cli, "publish", return_value={"ok": True, "note_id": "abc"}) as submit,
            mock.patch.object(sys, "stdout", new=io.StringIO()),
        ):
            self.assertEqual(publish_cli.main(argv), 0)
        submit.assert_called_once()

    def test_engagement_main_calls_creator_dispatch(self):
        with mock.patch.object(engagement, "dispatch", return_value=0) as dispatch:
            self.assertEqual(engagement.main(["probe"]), 0)
        dispatch.assert_called_once()


class CreatorDeclarationTests(unittest.TestCase):
    def test_publish_payload_contains_creator_ai_declaration(self):
        _, api_type = session_module._imports()
        api = object.__new__(api_type)
        api.auth = SimpleNamespace(proxies=None)
        api.base_url = "https://creator.xiaohongshu.com"
        api.edith_url = "https://edith.xiaohongshu.com"
        api.http = mock.Mock()
        api.http.post.return_value.json.return_value = {"success": True}
        api.upload_media = mock.Mock(return_value=(True, "ok", {
            "fileIds": "image-file", "width": 100, "height": 100,
        }))
        api._request_params = mock.Mock(return_value=({}, {}, "{}"))
        module = sys.modules[api_type.__module__]

        with mock.patch.object(module, "generate_x_rap_param", return_value="rap"):
            success, _, _ = api.post_note({
                "title": "标题", "desc": "正文", "images": [b"image"],
                "media_type": "image", "ai_declaration": True,
            })

        self.assertTrue(success)
        signed_payload = api._request_params.call_args.args[1]
        binds = json.loads(signed_payload["common"]["business_binds"])
        self.assertEqual(binds["userDeclarationBind"], {"origin": 2})
        self.assertEqual(binds["noteCopyBind"], {"copyable": True})
        api.http.post.assert_called_once()

        with mock.patch.object(module, "generate_x_rap_param", return_value="rap"):
            api.post_note({
                "title": "标题", "desc": "正文", "images": [b"image"],
                "media_type": "image", "ai_declaration": False,
            })
        default_binds = json.loads(
            api._request_params.call_args.args[1]["common"]["business_binds"]
        )
        self.assertNotIn("userDeclarationBind", default_binds)

    def test_upload_signatures_use_relay(self):
        scripts = ROOT / "crews/main/skills/expert-xhs/tools/scripts"
        sys.path.insert(0, str(scripts))
        try:
            from xhs_utils import xhs_creator_util
            with mock.patch.object(xhs_creator_util, "compute", return_value={"value": "signed"}) as compute:
                self.assertEqual(
                    xhs_creator_util.signature_js.call("getSignature", "window", "file-id", 4, "host"),
                    "signed",
                )
                compute.assert_called_with(
                    "creator", "upload-signature",
                    {"method": "getSignature", "args": ["window", "file-id", 4, "host"]},
                )
                self.assertEqual(xhs_creator_util.sign_js.call("urlSing", "file-id"), "signed")
                compute.assert_called_with(
                    "creator", "url-signature",
                    {"method": "urlSing", "args": ["file-id"]},
                )
        finally:
            sys.path.remove(str(scripts))


class CreatorSessionTests(unittest.TestCase):
    def test_daily_claim_limits_requests_to_one_per_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session_file = root / "session.json"
            session_file.write_text(json.dumps({
                "cookies": {"a1": "device", "galaxy_creator_session_id": "session"},
            }), encoding="utf-8")
            with (
                mock.patch.object(session_module, "SESSION_FILE", session_file),
                mock.patch.object(session_module, "DAILY_STATE_DIR", root / "daily"),
            ):
                self.assertTrue(session_module.claim_daily_run())
                self.assertFalse(session_module.claim_daily_run())

    def test_reopening_session_restores_counters_without_security_script(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(json.dumps({
                "cookies": {"a1": "device", "galaxy_creator_session_id": "session"},
                "host_cookie_state": {},
                "local_storage": {"p1": 2},
                "session_storage": {"sc": 4},
                "dsl": "dsl-value",
                "ds_program": "program-value",
                "session_state": {"dsllt": 11, "mnsSeq": 12, "p1": 13, "sc": 14},
            }), encoding="utf-8")
            session = SimpleNamespace(dsllt=0, mns_seq=0, profile_count=0, sign_count=0)
            profile = SimpleNamespace(ds_program="", session=session)
            auth = SimpleNamespace(profile=profile, close=mock.Mock())
            auth_class = SimpleNamespace(from_cookie=mock.Mock(return_value=auth))
            with (
                mock.patch.object(session_module, "SESSION_FILE", path),
                mock.patch.object(session_module, "_imports", return_value=(auth_class, lambda _: object())),
                mock.patch.object(session_module, "_write_session"),
            ):
                with session_module.creator_api():
                    self.assertEqual(profile.ds_program, "")
                    self.assertEqual((session.dsllt, session.mns_seq, session.profile_count, session.sign_count), (11, 12, 13, 14))
            self.assertEqual(auth_class.from_cookie.call_args.kwargs["dsl"], "dsl-value")
            auth.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
