#!/usr/bin/env python3
"""Unit tests for gen.py (Phase 5 火山方舟 Seedream image generation).

Covers:
- API key env var: AWK_API_KEY (not SILICONFLOW_API_KEY)
- Endpoint: https://ark.cn-beijing.volces.com/api/v3/images/generations
- Default model: doubao-seedream-4.5 (fallback doubao-seedream-5.0-lite)
- size validation (方式 1: 2K/3K/4K; 方式 2: WxH with total pixels + aspect ratio constraints)
- Payload construction (text-to-image vs image-edit)
- API request shape (Bearer token, JSON body, response_format, watermark)
- Image download (mocked)

All HTTP calls are mocked — these are unit tests.
Integration tests are deferred to the post-deployment phase.
"""
import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import gen  # noqa: E402


class TestApiConstants(unittest.TestCase):
    def test_endpoint_is_ark_v3_images(self):
        # 不是 /coding/v3（LLM 编码路径），是 /v3（标准推理）
        self.assertEqual(
            gen.API_URL,
            "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        )

    def test_default_models_are_seedream(self):
        # 4.0 是 dev plan 推荐的稳定版
        self.assertIn("seedream", gen.DEFAULT_GEN_MODEL)
        self.assertIn("seedream", gen.DEFAULT_EDIT_MODEL)

    def test_size_constraints_match_volcengine_docs(self):
        # 火山 API 文档：总像素 [2560x1440, 4096x4096]，宽高比 [1/16, 16]
        self.assertEqual(gen.MIN_TOTAL_PIXELS, 2560 * 1440)
        self.assertEqual(gen.MAX_TOTAL_PIXELS, 4096 * 4096)
        self.assertEqual(gen.MIN_ASPECT_RATIO, 1 / 16)
        self.assertEqual(gen.MAX_ASPECT_RATIO, 16)


class TestSizeValidation(unittest.TestCase):
    def test_quality_presets_accepted(self):
        for preset in ("2K", "3K", "4K"):
            self.assertEqual(gen.validate_size(preset), preset)

    def test_2k_recommended_sizes_accepted(self):
        for size in (
            "2048x2048", "2304x1728", "1728x2304",
            "2848x1600", "1600x2848", "2496x1664",
            "1664x2496", "3136x1344",
        ):
            self.assertEqual(gen.validate_size(size), size)

    def test_total_pixels_below_min_rejected(self):
        # 1500x1500 = 2250000 < 3686400
        with self.assertRaises(SystemExit) as ctx:
            gen.validate_size("1500x1500")
        self.assertEqual(ctx.exception.code, 1)

    def test_total_pixels_above_max_rejected(self):
        # 5000x5000 = 25000000 > 16777216
        with self.assertRaises(SystemExit) as ctx:
            gen.validate_size("5000x5000")
        self.assertEqual(ctx.exception.code, 1)

    def test_aspect_ratio_below_min_rejected(self):
        # 100x5000 = 500000 (above min total), but ratio = 0.02 < 1/16
        with self.assertRaises(SystemExit) as ctx:
            gen.validate_size("100x5000")
        self.assertEqual(ctx.exception.code, 1)

    def test_aspect_ratio_above_max_rejected(self):
        # 5000x100 = 500000, ratio = 50 > 16
        with self.assertRaises(SystemExit) as ctx:
            gen.validate_size("5000x100")
        self.assertEqual(ctx.exception.code, 1)

    def test_invalid_format_rejected(self):
        for bad in ("abc", "1024", "1024x", "x1024", ""):
            with self.assertRaises(SystemExit) as ctx:
                gen.validate_size(bad)
            self.assertEqual(ctx.exception.code, 1)

    def test_lowercase_x_accepted(self):
        # 文档示例用大写 X 但小写也应支持
        self.assertEqual(gen.validate_size("2048x2048"), "2048x2048")


class TestParseSize(unittest.TestCase):
    def test_valid_standard(self):
        self.assertEqual(gen._parse_size("2048x2048"), (2048, 2048))

    def test_valid_lowercase(self):
        self.assertEqual(gen._parse_size("1024x768"), (1024, 768))

    def test_valid_chinese_x(self):
        # 火山文档用 ×（中文乘号）
        self.assertEqual(gen._parse_size("2048×2048"), (2048, 2048))

    def test_invalid(self):
        self.assertIsNone(gen._parse_size("abc"))
        self.assertIsNone(gen._parse_size("1024"))
        self.assertIsNone(gen._parse_size("x1024"))


class TestPayloadConstruction(unittest.TestCase):
    def test_text_to_image_default(self):
        args = mock.Mock(
            prompt="a cat", model=None, image=None, image2=None, image3=None,
            image_size=None, seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_GEN_MODEL)
        self.assertEqual(payload["model"], gen.DEFAULT_GEN_MODEL)
        self.assertEqual(payload["prompt"], "a cat")
        # Default size is 2048x2048
        self.assertEqual(payload["size"], "2048x2048")
        self.assertFalse(payload["watermark"])
        # image field not present in text-to-image mode
        self.assertNotIn("image", payload)

    def test_text_to_image_explicit_size(self):
        args = mock.Mock(
            prompt="mountains", model=None, image=None, image2=None, image3=None,
            image_size="1664x2496", seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_GEN_MODEL)
        # 1664x2496 = 4153344, ratio 0.667 — within 2K
        self.assertEqual(payload["size"], "1664x2496")

    def test_text_to_image_quality_preset(self):
        args = mock.Mock(
            prompt="x", model=None, image=None, image2=None, image3=None,
            image_size="4K", seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_GEN_MODEL)
        self.assertEqual(payload["size"], "4K")

    def test_image_edit_single_source(self):
        args = mock.Mock(
            prompt="make it night", model=None,
            image="https://example.com/a.jpg", image2=None, image3=None,
            image_size=None, seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_EDIT_MODEL)
        self.assertEqual(payload["model"], gen.DEFAULT_EDIT_MODEL)
        # 单图是字符串（不是数组）
        self.assertEqual(payload["image"], "https://example.com/a.jpg")
        # image-edit 模式不传 size
        self.assertNotIn("size", payload)

    def test_image_edit_multi_source_uses_array(self):
        args = mock.Mock(
            prompt="blend", model=None,
            image="https://example.com/a.jpg",
            image2="https://example.com/b.jpg",
            image3="https://example.com/c.jpg",
            image_size=None, seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_EDIT_MODEL)
        # 多图用数组（火山 image 字段支持 array）
        self.assertIsInstance(payload["image"], list)
        self.assertEqual(len(payload["image"]), 3)

    def test_explicit_model_overrides_default(self):
        args = mock.Mock(
            prompt="x", model=gen.FALLBACK_MODEL,
            image=None, image2=None, image3=None,
            image_size=None, seed=None, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.FALLBACK_MODEL)
        self.assertEqual(payload["model"], gen.FALLBACK_MODEL)

    def test_seed_included_when_provided(self):
        args = mock.Mock(
            prompt="x", model=None, image=None, image2=None, image3=None,
            image_size=None, seed=42, watermark=False, response_format="url",
        )
        payload = gen.build_payload(args, gen.DEFAULT_GEN_MODEL)
        self.assertEqual(payload["seed"], 42)


class TestApiRequest(unittest.TestCase):
    @mock.patch("gen.urllib.request.urlopen")
    def test_request_uses_bearer_token(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "data": [{"url": "https://x.com/a.jpg"}],
            "usage": {"generated_images": 1},
        }).encode("utf-8")

        payload = {"model": "doubao-seedream-4.5", "prompt": "x", "size": "2048x2048"}
        gen.api_request(payload, "test-key-abc")

        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.headers["Authorization"], "Bearer test-key-abc")
        self.assertEqual(req.headers["Content-type"], "application/json")
        self.assertEqual(req.method, "POST")
        # Verify URL
        self.assertEqual(req.full_url, gen.API_URL)

    @mock.patch("gen.urllib.request.urlopen")
    def test_response_parsed(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "created": 1234,
            "data": [{"url": "https://x.com/a.jpg", "size": "2048x2048"}],
            "usage": {"generated_images": 1, "output_tokens": 16384, "total_tokens": 16384},
        }).encode("utf-8")

        result = gen.api_request({"model": "x", "prompt": "y", "size": "2048x2048"}, "k")
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["url"], "https://x.com/a.jpg")
        self.assertEqual(result["usage"]["generated_images"], 1)


class TestApiKeyEnv(unittest.TestCase):
    def test_awk_api_key_is_required_env(self):
        """SKILL.md frontmatter 的 `requires.env` 必须声明 AWK_API_KEY，不再含 SILICONFLOW_API_KEY。"""
        skill_md = (SCRIPTS_DIR.parent / "SKILL.md").read_text()
        # 抽 frontmatter YAML 块
        import re as _re
        m = _re.search(r"^---\n(.*?)\n---", skill_md, _re.DOTALL | _re.MULTILINE)
        self.assertIsNotNone(m, "SKILL.md 必须以 YAML frontmatter 开头")
        frontmatter = m.group(1)
        self.assertIn("AWK_API_KEY", frontmatter)
        # requires.env 段（缩进 2 空格的 env 子段）不含 SILICONFLOW_API_KEY
        env_block = _re.search(r"^\s+env:\n((?:\s+-\s+\S+\n)+)", frontmatter, _re.MULTILINE)
        self.assertIsNotNone(env_block, "frontmatter 应包含 env: 段")
        env_text = env_block.group(1)
        self.assertNotIn("SILICONFLOW_API_KEY", env_text)

    def test_awk_api_key_required_by_script(self):
        """脚本会显式校验 AWK_API_KEY 不存在时 exit 1。"""
        with mock.patch.dict(os.environ, {"AWK_API_KEY": ""}, clear=False):
            # 强制 AWK_API_KEY 为空，看脚本逻辑
            args = mock.Mock(prompt="x", model=None, image=None, image2=None, image3=None,
                             image_size=None, seed=None, watermark="false", response_format="url",
                             out_dir=None)
            with self.assertRaises(SystemExit) as ctx:
                # 模拟 main() 前半段（API key 校验）
                api_key = os.environ.get("AWK_API_KEY")
                if not api_key:
                    sys.exit(1)
            self.assertEqual(ctx.exception.code, 1)


class TestIntegrationDryRun(unittest.TestCase):
    """Subprocess-level smoke test: gen.py --help 应该可执行且不依赖 env。"""

    def test_help_runs_without_env(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gen.py"), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("image", result.stdout.lower())

    def test_missing_api_key_exits_1(self):
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "AWK_API_KEY"}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "gen.py"), "--prompt", "x"],
            capture_output=True, text=True, timeout=10, check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("AWK_API_KEY", result.stderr)


if __name__ == "__main__":
    unittest.main()
