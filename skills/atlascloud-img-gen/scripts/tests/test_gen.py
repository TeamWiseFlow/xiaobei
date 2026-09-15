import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import gen  # noqa: E402


class AtlasCloudImageTests(unittest.TestCase):
    def test_submit_uses_media_endpoint_and_bearer_token(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"data": {"id": "p1"}}).encode()
        with mock.patch("gen.urllib.request.urlopen", return_value=response) as urlopen:
            result = gen.request_json(gen.GENERATE_URL, "secret", method="POST", payload={"model": "m"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.atlascloud.ai/api/v1/model/generateImage")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")
        self.assertEqual(request.headers["User-agent"], "xiaobei-atlascloud-img-gen/1.0")
        self.assertEqual(gen.prediction_id(result), "p1")

    def test_local_image_is_uploaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.png"
            path.write_bytes(b"png")
            with mock.patch("gen.upload_file", return_value="https://cdn.example/source.png") as upload:
                self.assertEqual(gen.resolve_image(str(path), "key"), "https://cdn.example/source.png")
            upload.assert_called_once_with(path, "key")

    def test_remote_image_skips_upload(self):
        with mock.patch("gen.upload_file") as upload:
            value = gen.resolve_image("https://example.com/source.png", "key")
        self.assertEqual(value, "https://example.com/source.png")
        upload.assert_not_called()

    def test_poll_returns_completed_prediction(self):
        responses = [
            {"data": {"status": "processing"}},
            {"data": {"status": "completed", "outputs": ["https://cdn.example/out.png"]}},
        ]
        with mock.patch("gen.request_json", side_effect=responses), mock.patch("gen.time.sleep"):
            result = gen.poll_prediction("p1", "key", 0, 10)
        self.assertEqual(gen.output_urls(result), ["https://cdn.example/out.png"])

    def test_failed_prediction_raises(self):
        with mock.patch("gen.request_json", return_value={"data": {"status": "failed"}}):
            with self.assertRaises(RuntimeError):
                gen.poll_prediction("p1", "key", 0, 10)


if __name__ == "__main__":
    unittest.main()
