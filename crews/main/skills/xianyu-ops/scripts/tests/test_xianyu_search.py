#!/usr/bin/env python3
"""Unit tests for xianyu_search.py.

Covers:
- filter 编码（priceRange / extraFilterValue / fromFilter）
- eval 表达式构造（值用 JSON 注入，无字符串拼接注入）
- 分页（limit 跨页、空结果早停）
- camoufox 信封解析（data.result）
- fail-first busy → exit 3
- 登录墙 → exit 2
- 参数校验
"""
import json
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import xianyu_search  # noqa: E402


class TestFilterEncoding(unittest.TestCase):
    def test_no_filter(self):
        self.assertEqual(xianyu_search.build_search_filter(None, None), "")
        self.assertEqual(xianyu_search.build_extra_filter(None, None), "{}")

    def test_price_range_both(self):
        self.assertEqual(xianyu_search.build_search_filter(100, 500), "priceRange:100,500;")

    def test_price_range_min_only(self):
        self.assertEqual(xianyu_search.build_search_filter(100, None), "priceRange:100,99999999;")

    def test_price_range_max_only(self):
        self.assertEqual(xianyu_search.build_search_filter(None, 500), "priceRange:0,500;")

    def test_extra_filter_province_only(self):
        s = xianyu_search.build_extra_filter("广东", None)
        d = json.loads(s)
        self.assertEqual(d["divisionList"], [{"province": "广东", "city": ""}])
        self.assertEqual(d["excludeMultiPlacesSellers"], "0")

    def test_extra_filter_city_only(self):
        s = xianyu_search.build_extra_filter(None, "深圳")
        d = json.loads(s)
        self.assertEqual(d["divisionList"], [{"province": "", "city": "深圳"}])

    def test_extra_filter_both(self):
        d = json.loads(xianyu_search.build_extra_filter("广东", "深圳"))
        self.assertEqual(d["divisionList"], [{"province": "广东", "city": "深圳"}])


class TestEvalExpression(unittest.TestCase):
    def test_expression_is_single_iife(self):
        expr = xianyu_search.build_eval_expression("手机", "", "{}", 1, False)
        # 单一表达式：以 (async () => { 开头，以 })() 结尾
        self.assertTrue(expr.startswith("(async () => {"))
        self.assertTrue(expr.endswith("})()"))

    def test_values_json_injected_no_string_concat(self):
        # 关键词含引号 / 反斜杠，必须 JSON 注入而非裸拼（避免注入 / 语法错）
        evil = 'a"b\\c'
        expr = xianyu_search.build_eval_expression(evil, "", "{}", 1, False)
        # 表达式里不应出现裸的关键词（应被 JSON 转义成 "a\"b\\c"）
        self.assertNotIn(f'keyword: "{evil}"', expr)
        # 但 JSON 注入的转义形式应在
        self.assertIn(json.dumps(evil), expr)

    def test_filter_injected(self):
        expr = xianyu_search.build_eval_expression("车", "priceRange:100,500;", "{}", 2, True)
        self.assertIn("priceRange:100,500;", expr)
        self.assertIn('"fromFilter": true', expr)
        self.assertIn('"pageNumber": 2', expr)

    def test_extra_filter_injected(self):
        ef = json.dumps({"divisionList": [{"province": "广东", "city": ""}]}, ensure_ascii=False)
        expr = xianyu_search.build_eval_expression("车", "", ef, 1, True)
        self.assertIn("广东", expr)


class TestSearchParsing(unittest.TestCase):
    """mock camoufox() 验证分页 + 解析。"""

    def _make_env(self, iife_result: dict) -> dict:
        return {"id": "x", "success": True, "data": {"result": iife_result}}

    @mock.patch("xianyu_search.camoufox")
    def test_single_page(self, mock_camoufox):
        items = [{"item_id": "1", "title": "A", "price": "¥10", "url": "https://www.goofish.com/item?id=1"}]
        mock_camoufox.return_value = self._make_env({"items": items, "page_count": 1})
        out = xianyu_search.search("test", None, None, None, None, 5)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["item_id"], "1")

    @mock.patch("xianyu_search.camoufox")
    def test_pagination_collects_across_pages(self, mock_camoufox):
        page1 = [{"item_id": str(i), "title": f"T{i}", "url": f"https://www.goofish.com/item?id={i}"} for i in range(30)]
        page2 = [{"item_id": str(i), "title": f"T{i}", "url": f"https://www.goofish.com/item?id={i}"} for i in range(30, 45)]
        mock_camoufox.side_effect = [
            self._make_env({"items": page1, "page_count": 30}),
            self._make_env({"items": page2, "page_count": 15}),
        ]
        out = xianyu_search.search("test", None, None, None, None, 45)
        self.assertEqual(len(out), 45)
        self.assertEqual(out[0]["item_id"], "0")
        self.assertEqual(out[44]["item_id"], "44")

    @mock.patch("xianyu_search.camoufox")
    def test_empty_page_stops_early(self, mock_camoufox):
        mock_camoufox.return_value = self._make_env({"items": [], "page_count": 0})
        out = xianyu_search.search("test", None, None, None, None, 30)
        self.assertEqual(out, [])
        self.assertEqual(mock_camoufox.call_count, 1)

    @mock.patch("xianyu_search.camoufox")
    def test_limit_caps_collection(self, mock_camoufox):
        page1 = [{"item_id": str(i), "title": f"T{i}", "url": f"u{i}"} for i in range(30)]
        mock_camoufox.return_value = self._make_env({"items": page1, "page_count": 30})
        out = xianyu_search.search("test", None, None, None, None, 10)
        self.assertEqual(len(out), 10)

    @mock.patch("xianyu_search.camoufox")
    def test_mtop_error_raises(self, mock_camoufox):
        mock_camoufox.return_value = self._make_env({"error": "mtop-response-error", "detail": "FAIL_BIZxxx"})
        with self.assertRaises(RuntimeError) as ctx:
            xianyu_search.search("test", None, None, None, None, 10)
        self.assertIn("mtop-response-error", str(ctx.exception))

    @mock.patch("xianyu_search.camoufox")
    def test_session_expired_raises_loginwall(self, mock_camoufox):
        mock_camoufox.return_value = self._make_env({"error": "mtop-response-error", "detail": "FAIL_SYS_SESSION_EXPIRED"})
        with self.assertRaises(xianyu_search.LoginWallError):
            xianyu_search.search("test", None, None, None, None, 10)

    @mock.patch("xianyu_search.camoufox")
    def test_mtop_not_ready_raises(self, mock_camoufox):
        mock_camoufox.return_value = self._make_env({"error": "mtop-not-ready"})
        with self.assertRaises(RuntimeError) as ctx:
            xianyu_search.search("test", None, None, None, None, 10)
        self.assertIn("mtop 未就绪", str(ctx.exception))


class TestCamoufoxCliEnvelope(unittest.TestCase):
    @mock.patch("xianyu_search.subprocess.run")
    def test_busy_exit3(self, mock_run):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.stdout = ""
        r.stderr = "session xianyu 正忙，请等待当前操作完成后再试"
        mock_run.return_value = r
        with self.assertRaises(xianyu_search.SessionBusyError):
            xianyu_search.camoufox(["eval", "1+1"])

    @mock.patch("xianyu_search.subprocess.run")
    def test_parses_data_result(self, mock_run):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.stdout = json.dumps({"id": "1", "success": True, "data": {"result": {"items": [], "page_count": 0}}})
        r.stderr = ""
        mock_run.return_value = r
        env = xianyu_search.camoufox(["eval", "1+1"])
        self.assertEqual(env["data"]["result"], {"items": [], "page_count": 0})

    @mock.patch("xianyu_search.subprocess.run")
    def test_non_json_output_raises(self, mock_run):
        from unittest.mock import MagicMock
        r = MagicMock()
        r.stdout = "not json"
        r.stderr = ""
        mock_run.return_value = r
        with self.assertRaises(RuntimeError):
            xianyu_search.camoufox(["eval", "1+1"])


class TestArgValidation(unittest.TestCase):
    def _run_main(self, argv):
        with mock.patch("sys.argv", ["xianyu_search", *argv]):
            with self.assertRaises(SystemExit) as ctx:
                xianyu_search.main()
        return ctx.exception.code

    def test_limit_out_of_range(self):
        self.assertEqual(self._run_main(["--query", "x", "--limit", "0"]), 1)
        self.assertEqual(self._run_main(["--query", "x", "--limit", "999"]), 1)

    def test_negative_price(self):
        self.assertEqual(self._run_main(["--query", "x", "--min-price", "-1"]), 1)

    def test_min_gt_max(self):
        self.assertEqual(self._run_main(["--query", "x", "--min-price", "100", "--max-price", "50"]), 1)


class TestIntegrationDryRun(unittest.TestCase):
    def test_help(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "xianyu_search.py"), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--min-price", result.stdout)
        self.assertIn("--province", result.stdout)


if __name__ == "__main__":
    unittest.main()
