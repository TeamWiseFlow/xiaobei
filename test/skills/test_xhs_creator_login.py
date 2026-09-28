"""QR handoff and session preservation for XHS Creator login."""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "crews/main/skills/expert-xhs/tools/xhs-publish/scripts/creator_local_cli.py"
spec = importlib.util.spec_from_file_location("xhs_creator_login_cli_test", SCRIPT)
assert spec and spec.loader
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CreatorLoginFlowTests(unittest.TestCase):
    def test_login_returns_image_before_login_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qr = root / "qr.png"
            output = io.StringIO()

            def spawn(*_args, **_kwargs):
                qr.write_bytes(b"PNG")
                return mock.Mock(pid=12345)

            with (
                mock.patch.object(cli, "LOGIN_DIR", root),
                mock.patch.object(cli, "STATUS_FILE", root / "status.json"),
                mock.patch.object(cli, "LOCK_FILE", root / "login.lock"),
                mock.patch.object(cli, "WORKER_LOG", root / "worker.log"),
                mock.patch.object(cli, "QR_FILE", qr),
                mock.patch.object(cli.subprocess, "Popen", side_effect=spawn) as popen,
                mock.patch.object(cli, "login_local") as complete_login,
                mock.patch.object(sys, "stdout", output),
            ):
                self.assertEqual(cli.login(), 0)
            self.assertEqual(json.loads(output.getvalue())["qr_path"], str(qr))
            self.assertEqual(json.loads((root / "status.json").read_text())["state"], "pending")
            popen.assert_called_once()
            complete_login.assert_not_called()

    def test_failed_login_keeps_previous_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_session = root / "session.json"
            old_session.write_text('{"cookies":{"a1":"old"}}')
            with (
                mock.patch.object(cli, "LOGIN_DIR", root),
                mock.patch.object(cli, "STATUS_FILE", root / "status.json"),
                mock.patch.object(cli, "LOCK_FILE", root / "login.lock"),
                mock.patch.object(cli, "login_local", side_effect=RuntimeError("二维码过期")),
            ):
                cli.save_status({"state": "pending", "run_id": "run1"})
                self.assertEqual(cli.worker("run1"), 1)
                self.assertEqual(cli.status()["state"], "failed")
            self.assertEqual(old_session.read_text(), '{"cookies":{"a1":"old"}}')

    def test_confirmation_checks_only_completed_login(self):
        with (
            mock.patch.object(cli, "status", return_value={"state": "pending"}),
            mock.patch.object(cli, "LOGIN_CONFIRM_SETTLE_SECONDS", 0),
            mock.patch.object(cli, "check") as check,
            mock.patch.object(sys, "stdout", io.StringIO()),
        ):
            self.assertEqual(cli.login_confirm(), 2)
            check.assert_not_called()
        with (
            mock.patch.object(cli, "status", return_value={"state": "success"}),
            mock.patch.object(cli, "check", return_value=0) as check,
        ):
            self.assertEqual(cli.login_confirm(), 0)
            check.assert_called_once()


if __name__ == "__main__":
    unittest.main()
