"""Regression tests for publish_xhs body newline normalization."""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "crews/main/skills/expert-xhs/tools/xhs-publish/scripts/publish_xhs.py"
SPEC = importlib.util.spec_from_file_location("publish_xhs", SCRIPT_PATH)
assert SPEC and SPEC.loader
publish_xhs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_xhs)


class NormalizeBodyNewlinesTests(unittest.TestCase):
    def test_converts_literal_backslash_n_to_real_newline(self) -> None:
        # bash 双引号里 --body "第一行\n第二行" 收到的就是字面量反斜杠+n
        self.assertEqual(
            publish_xhs.normalize_body_newlines("第一行\\n第二行"),
            "第一行\n第二行",
        )

    def test_converts_literal_crlf_without_leaving_stray_cr(self) -> None:
        self.assertEqual(publish_xhs.normalize_body_newlines("a\\r\\nb"), "a\nb")

    def test_keeps_real_newlines_untouched(self) -> None:
        self.assertEqual(publish_xhs.normalize_body_newlines("a\nb"), "a\nb")

    def test_handles_mixed_literal_and_real_newlines(self) -> None:
        self.assertEqual(publish_xhs.normalize_body_newlines("a\nb\\nc"), "a\nb\nc")

    def test_normalizing_before_extraction_keeps_topic_names_clean(self) -> None:
        # 字面量 \n 是非空白字符：不先归一化，extract_topics 会把 "职场\n第二行" 整个当话题名
        raw = "#职场\\n第二行正文"
        topics = publish_xhs.extract_topics(
            publish_xhs.normalize_body_newlines(raw), None
        )
        self.assertEqual([t["name"] for t in topics], ["职场"])

    def test_formatted_topic_is_not_wrapped_twice(self) -> None:
        body = "\ufeff#职场[话题]#\ufeff"
        topics = publish_xhs.extract_topics(body)
        self.assertEqual(publish_xhs.rewrite_topics_in_body(body, topics), body)


class MainBodyNormalizationTests(unittest.TestCase):
    def test_main_publishes_body_with_real_newlines(self) -> None:
        # 端到端守住 main() 的接线：字面量 \n 的 --body 到达发布函数时已是真实换行
        argv = [
            "publish_xhs.py",
            "--mode", "image",
            "--title", "标题",
            "--body", "第一行\\n第二行",
            "--images", "img.jpg",
        ]
        captured: dict = {}

        def fake_publish(args, body, topics):
            captured["body"] = body
            return {"ok": True, "note_id": "x", "url": "u"}

        with (
            mock.patch.object(publish_xhs, "publish", side_effect=fake_publish),
            mock.patch.object(sys, "stdout", new=io.StringIO()),
        ):
            self.assertEqual(publish_xhs.main(argv[1:]), 0)

        self.assertEqual(captured["body"], "第一行\n第二行")

    def test_ai_declaration_flag_reaches_publish(self) -> None:
        captured = {}

        def fake_publish(args, body, topics):
            captured["ai_declaration"] = args.ai_declaration
            return {"ok": True, "note_id": "x", "url": "u"}

        with (
            mock.patch.object(publish_xhs, "publish", side_effect=fake_publish),
            mock.patch.object(sys, "stdout", new=io.StringIO()),
        ):
            self.assertEqual(publish_xhs.main([
                "--mode", "image", "--title", "标题", "--body", "正文",
                "--images", "img.jpg", "--ai-declaration",
            ]), 0)
        self.assertTrue(captured["ai_declaration"])


if __name__ == "__main__":
    unittest.main()
