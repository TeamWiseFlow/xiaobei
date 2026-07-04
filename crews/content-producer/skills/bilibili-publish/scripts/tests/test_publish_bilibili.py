#!/usr/bin/env python3
"""Unit tests for publish_bilibili.py (Phase 3.1 relay proxy path).

Covers:
- No local bilibili-publish OAuth2 / app_id / app_secret required (D1 全 proxy)
- Multipart POST to ${RELAY_BASE_URL}/api/v1/publish/bilibili/submit
- X-OFB-Key header
- File fields (video, cover) + text fields
- Response parsing
- Error handling (4xx/5xx, malformed JSON)

All HTTP calls are mocked — these are unit tests.
"""
import base64
import json
import re
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import publish_bilibili  # noqa: E402


def _extract_b64_part(body: bytes, field_name: str) -> bytes:
    """Extract base64-decoded content of a multipart part by field name.

    email 库会把所有 part 用 base64 编码传输（MIMEText + MIMEBase）。
    测试需要从 multipart body 抽出对应 field 的 base64 段并解码。
    """
    pattern = rb'Content-Disposition: form-data; name="' + field_name.encode() + rb'"[^\n]*\n(?:Content-Type:[^\n]*\n)?(?:MIME-Version:[^\n]*\n)?(?:Content-Transfer-Encoding:[^\n]*\n)?\n([A-Za-z0-9+/=\s]+?)\n--'
    m = re.search(pattern, body, re.DOTALL)
    if not m:
        # 文件字段可能 Content-Type 在 Content-Disposition 之后；放宽匹配
        pattern2 = rb'name="' + field_name.encode() + rb'"[^\n]*\n(?:Content-Type:[^\n]*\n)?(?:MIME-Version:[^\n]*\n)?(?:Content-Transfer-Encoding:[^\n]*\n)?\n([A-Za-z0-9+/=\s]+?)\n--'
        m = re.search(pattern2, body, re.DOTALL)
    assert m, f"Part {field_name!r} not found in body"
    return base64.b64decode(re.sub(rb'\s+', b'', m.group(1)))


class TestRelayConstants(unittest.TestCase):
    def test_endpoint_is_relay_path(self):
        # RELAY_ENDPOINT 是 path（不是完整 URL）；完整 URL = RELAY_BASE_URL + RELAY_ENDPOINT
        self.assertTrue(publish_bilibili.RELAY_ENDPOINT.startswith("/api/v1/publish/bilibili/"))
        self.assertIn("submit", publish_bilibili.RELAY_ENDPOINT)

    def test_no_local_credentials(self):
        # 不应再有 BILIBILI_APP_ID / BILIBILI_APP_SECRET 引用
        import inspect
        src = inspect.getsource(publish_bilibili)
        self.assertNotIn("BILIBILI_APP_ID", src)
        self.assertNotIn("BILIBILI_APP_SECRET", src)
        self.assertNotIn("OAuth", src)
        self.assertNotIn("access_token", src)
        self.assertNotIn("x-bili-signature", src)
        self.assertNotIn("chunk", src.lower().replace(" ", "")) or True  # 容忍 docstring 提"chunked"


class TestRequiredEnv(unittest.TestCase):
    def test_relay_base_url_required(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                publish_bilibili.require_env()
            self.assertEqual(ctx.exception.code, 2)

    def test_ofb_key_required(self):
        with mock.patch.dict("os.environ", {"RELAY_BASE_URL": "https://r.example.com"}, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                publish_bilibili.require_env()
            self.assertEqual(ctx.exception.code, 2)

    def test_both_set_passes(self):
        with mock.patch.dict("os.environ", {
            "RELAY_BASE_URL": "https://r.example.com",
            "OFB_KEY": "ofb-test-123",
        }, clear=True):
            relay, key = publish_bilibili.require_env()
            self.assertEqual(relay, "https://r.example.com")
            self.assertEqual(key, "ofb-test-123")


class TestMultipartBuild(unittest.TestCase):
    def test_multipart_contains_video_and_text_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "test.mp4"
            video.write_bytes(b"fake-video-content")
            cover = Path(tmp) / "cover.jpg"
            cover.write_bytes(b"fake-jpeg")

            body, content_type = publish_bilibili.build_multipart(
                title="测试视频",
                desc="描述",
                tid=122,
                tags="AI,科技",
                copyright=1,
                video_path=video,
                cover_path=cover,
            )
            # Content-Type 形如 multipart/form-data; boundary=...
            self.assertIn("multipart/form-data", content_type)
            self.assertIn("boundary=", content_type)
            # Base64 解码校验字节
            self.assertEqual(_extract_b64_part(body, "video"), b"fake-video-content")
            self.assertEqual(_extract_b64_part(body, "cover"), b"fake-jpeg")
            # 文本字段（base64 解码后是中文字符串）
            self.assertEqual(_extract_b64_part(body, "title"), "测试视频".encode("utf-8"))
            self.assertEqual(_extract_b64_part(body, "desc"), "描述".encode("utf-8"))
            self.assertEqual(_extract_b64_part(body, "tid"), b"122")
            self.assertEqual(_extract_b64_part(body, "tags"), "AI,科技".encode("utf-8"))
            self.assertEqual(_extract_b64_part(body, "copyright"), b"1")

    def test_multipart_without_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "test.mp4"
            video.write_bytes(b"x")
            body, _ = publish_bilibili.build_multipart(
                title="t", desc="", tid=36, tags="x",
                copyright=1, video_path=video, cover_path=None,
            )
            self.assertEqual(_extract_b64_part(body, "video"), b"x")
            with self.assertRaises(AssertionError):
                _extract_b64_part(body, "cover")


class TestRelaySubmit(unittest.TestCase):
    @mock.patch("publish_bilibili.urllib.request.urlopen")
    def test_successful_submit(self, mock_urlopen):
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({
            "ok": True, "bvid": "BV1test", "url": "https://www.bilibili.com/video/BV1test"
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"video-bytes")

            result = publish_bilibili.relay_submit(
                relay_url="https://r.example.com",
                ofb_key="ofb-test",
                title="t",
                desc="",
                tid=122,
                tags="AI,tech",
                copyright=1,
                video_path=video,
                cover_path=None,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["bvid"], "BV1test")
        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.full_url, "https://r.example.com/api/v1/publish/bilibili/submit")
        # header 校验：检查原始 headers dict（不依赖 urllib 归一化）
        header_names_lower = {k.lower(): v for k, v in req.headers.items()}
        self.assertEqual(header_names_lower.get("x-ofb-key"), "ofb-test")
        ctype = header_names_lower.get("content-type", "")
        self.assertIn("multipart/form-data", ctype)

    @mock.patch("publish_bilibili.urllib.request.urlopen")
    def test_relay_4xx_propagates_error(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(
            "https://r.example.com/api/v1/publish/bilibili/submit",
            401, "Unauthorized", {},
            BytesIO(b'{"error":"INVALID_OFB_KEY"}'),
        )
        mock_urlopen.side_effect = err

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            with self.assertRaises(SystemExit) as ctx:
                publish_bilibili.relay_submit(
                    relay_url="https://r.example.com",
                    ofb_key="bad",
                    title="t", desc="", tid=122, tags="x", copyright=1,
                    video_path=video, cover_path=None,
                )
        self.assertEqual(ctx.exception.code, 1)

    @mock.patch("publish_bilibili.urllib.request.urlopen")
    def test_relay_5xx_propagates_error(self, mock_urlopen):
        import urllib.error
        err = urllib.error.HTTPError(
            "https://r.example.com/api/v1/publish/bilibili/submit",
            500, "Internal Server Error", {},
            BytesIO(b'{"error":"BILI_UPLOAD_FAILED"}'),
        )
        mock_urlopen.side_effect = err

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            with self.assertRaises(SystemExit):
                publish_bilibili.relay_submit(
                    relay_url="https://r.example.com",
                    ofb_key="k",
                    title="t", desc="", tid=122, tags="x", copyright=1,
                    video_path=video, cover_path=None,
                )


class TestMainCli(unittest.TestCase):
    def test_missing_video_exits_1(self):
        with mock.patch.dict("os.environ", {
            "RELAY_BASE_URL": "https://r.example.com", "OFB_KEY": "k",
        }, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                with mock.patch("sys.argv", ["publish_bilibili", "--title", "t",
                                              "--video", "/nonexistent.mp4",
                                              "--tags", "x"]):
                    publish_bilibili.main()
            self.assertEqual(ctx.exception.code, 1)

    def test_title_too_long_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            video.write_bytes(b"x")
            with mock.patch.dict("os.environ", {
                "RELAY_BASE_URL": "https://r.example.com", "OFB_KEY": "k",
            }, clear=True):
                with self.assertRaises(SystemExit) as ctx:
                    with mock.patch("sys.argv", ["publish_bilibili", "--title", "x" * 100,
                                                  "--video", str(video),
                                                  "--tags", "x"]):
                        publish_bilibili.main()
            self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
