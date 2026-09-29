"""公众号文章元数据提取回归测试。"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = (Path(__file__).resolve().parents[2] /
          "crews/main/skills/wx-mp-hunter/scripts/wx_mp_hunter.py")
spec = importlib.util.spec_from_file_location("wx_mp_hunter", SCRIPT)
hunter = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"httpx": types.ModuleType("httpx")}):
    spec.loader.exec_module(hunter)


class ArticleMetadataTests(unittest.TestCase):
    def test_og_fields_precede_dom_and_meta_date_is_read_in_any_attribute_order(self):
        html = """
        <html><head>
          <meta content='分享标题 &amp; 后缀' property='og:title'>
          <meta property="og:article:author" content="分享账号">
          <meta content="2026-09-26T12:30:00+08:00" property="article:published_time">
          <meta content="//mmbiz.qpic.cn/cover?x=1&amp;y=2" property="og:image">
        </head><body>
          <h1>页面标题</h1><a id="js_name">页面账号</a>
          <div id="js_content"><p>正文</p></div><div></div>
        </body></html>
        """
        fields = hunter._extract_article_fields(html)
        self.assertEqual(fields["title"], "分享标题 & 后缀")
        self.assertEqual(fields["author"], "分享账号")
        self.assertEqual(fields["publish_time"], "2026-09-26")
        self.assertEqual(fields["cover_url"], "https://mmbiz.qpic.cn/cover?x=1&y=2")
        self.assertIn("正文", fields["content_text"])
        self.assertFalse(fields["error_msg"])

    def test_empty_og_fields_fall_back_to_dom_and_dom_date_precedes_meta(self):
        html = """
        <meta property="og:title" content="  ">
        <meta content='' property='og:article:author'>
        <meta property='og:article:published_time' content='2026-09-25T10:00:00'>
        <h1>页面标题</h1><a id="js_name">页面账号</a>
        <em id="publish_time">2026年9月26日</em>
        <div id="js_content">正文</div><div></div>
        """
        fields = hunter._extract_article_fields(html)
        self.assertEqual(fields["title"], "页面标题")
        self.assertEqual(fields["author"], "页面账号")
        self.assertEqual(fields["publish_time"], "2026年9月26日")
        self.assertFalse(fields["error_msg"])

    def test_no_h1_text_page_uses_og_author_before_dom(self):
        html = """
        <meta property='og:title' content='分享标题'>
        <meta content='分享账号' property='og:article:author'>
        <a id="js_name">页面账号</a><p id="js_text_desc">正文</p>
        """
        fields = hunter._extract_article_fields(html)
        self.assertEqual(fields["title"], "分享标题")
        self.assertEqual(fields["author"], "分享账号")
        self.assertEqual(fields["content_text"], "正文")
        self.assertFalse(fields["error_msg"])

    def test_no_h1_share_page_keeps_description_fallback(self):
        html = """
        <meta content='分享标题' property='og:title'>
        <meta property='og:article:author' content='分享账号'>
        <meta content='摘要&amp;更多' property='og:description'>
        """
        fields = hunter._extract_article_fields(html)
        self.assertEqual(fields["title"], "分享标题")
        self.assertEqual(fields["author"], "分享账号")
        self.assertEqual(fields["content_text"], "摘要&更多")
        self.assertFalse(fields["error_msg"])


if __name__ == "__main__":
    unittest.main()
