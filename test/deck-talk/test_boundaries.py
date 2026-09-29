"""Run: python3 -m unittest discover -s test/deck-talk -p 'test_*.py'."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT/'crews/content-producer/skills/expert-video/tools/video-producer/video-producer.sh'


class BoundaryTests(unittest.TestCase):
    def test_asr_word_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            timing = folder/'segments.json'
            report = folder/'boundaries.json'
            timing.write_text(json.dumps({'segments': [
                {'text': '讲清楚，', 'end': 1.25}, {'text': '再翻页。', 'end': 2.5}
            ]}, ensure_ascii=False))
            result = subprocess.run([str(WRAPPER), 'deck-boundaries', '--subtitle', str(timing),
                                     '--output', str(report)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([mark['time'] for mark in json.loads(report.read_text())['candidates']], [1.25, 2.5])

    def test_word_punctuation_and_sentence_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            subtitle = folder/'narration.subtitle.json'
            spec = folder/'deck-spec.json'
            report = folder/'review/page-boundaries.json'
            subtitle.write_text(json.dumps({'sentences': [
                {'text': '先讲结论。', 'words': [
                    {'word': '先讲', 'endTime': 1.0}, {'word': '结论', 'endTime': 2.0}]},
                {'text': '再讲原因，继续。', 'words': [
                    {'word': '再讲原因，', 'endTime': 4.0}, {'word': '继续。', 'endTime': 6.0}]}
            ]}, ensure_ascii=False))
            spec.write_text(json.dumps({'scenes': [
                {'duration': 2.05}, {'duration': 1.95}, {'duration': 2.0}]}))
            cmd = [str(WRAPPER), 'deck-boundaries', '--subtitle', str(subtitle),
                   '--spec', str(spec), '--output', str(report)]
            result = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(report.read_text())
            self.assertEqual(payload['verdict'], 'pass')
            self.assertEqual([mark['time'] for mark in payload['candidates']], [2.0, 4.0, 6.0])
            spec.write_text(json.dumps({'scenes': [
                {'duration': 2.5}, {'duration': 1.5}, {'duration': 2.0}]}))
            failed = subprocess.run(cmd, text=True, capture_output=True)
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(report.read_text())['verdict'], 'fail')


if __name__ == '__main__':
    unittest.main()
