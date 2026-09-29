#!/usr/bin/env python3
"""Unit tests for tts.py (多供应商 TTS 路由 + 百炼 payload 映射).

Covers:
- 供应商路由优先级：火山凭据 → 百炼业务空间 → 百炼 agent plan → die
- 百炼 payload：格式别名 ogg_opus→opus、语速/响度线性映射、instruction、火山音色换默认
- 相似度：清洗标点空白后序敏感比对（中文无空格不再归零）
- ASR 自检后端选择标记

All network calls avoided; peak guard cases use local FFmpeg fixtures.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / 'skills/awk-tts/scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

import tts  # noqa: E402

KEYS = (
    "VOLC_TTS_APP_ID", "VOLC_TTS_ACCESS_KEY", "VOLC_TTS_APP_KEY",
    "WORKSPACE_ID", "MODELSTUDIO_API_KEY", "DASHSCOPE_API_KEY", "AWK_API_KEY",
)


def _env(**overrides):
    base = {k: v for k, v in os.environ.items() if k not in KEYS}
    base.update({k: v for k, v in overrides.items() if v is not None})
    return base


class TestProviderRouting(unittest.TestCase):
    def test_volc_priority(self):
        with mock.patch.dict(os.environ, _env(
            VOLC_TTS_APP_ID="1", VOLC_TTS_ACCESS_KEY="t",
            WORKSPACE_ID="llm-x", MODELSTUDIO_API_KEY="sk-w", AWK_API_KEY="sk-sp",
        ), clear=True):
            self.assertEqual(tts.resolve_tts_provider(), "volc")

    def test_volc_single_header(self):
        with mock.patch.dict(os.environ, _env(VOLC_TTS_APP_KEY="k"), clear=True):
            self.assertEqual(tts.resolve_tts_provider(), "volc")

    def test_bailian_workspace(self):
        with mock.patch.dict(os.environ, _env(
            WORKSPACE_ID="llm-x", MODELSTUDIO_API_KEY="sk-w"
        ), clear=True):
            provider = tts.resolve_tts_provider()
        self.assertEqual(provider[0], "bailian")
        self.assertEqual(provider[3], "workspace")
        self.assertIn("llm-x.cn-beijing.maas.aliyuncs.com", provider[1])

    def test_bailian_agent_plan(self):
        with mock.patch.dict(os.environ, _env(AWK_API_KEY="sk-sp-x"), clear=True):
            provider = tts.resolve_tts_provider()
        self.assertEqual(provider[0], "bailian")
        self.assertEqual(provider[3], "agent-plan")
        self.assertIn("token-plan", provider[1])

    def test_no_credentials_dies(self):
        with mock.patch.dict(os.environ, _env(), clear=True):
            with self.assertRaises(SystemExit):
                tts.resolve_tts_provider()


class TestBailianPayload(unittest.TestCase):
    def _args(self, **overrides):
        defaults = dict(
            voice=None, format="mp3", sample_rate=None, speech_rate=None,
            loudness_rate=None, context_text=None, model=None, enable_subtitle=False,
        )
        defaults.update(overrides)
        return mock.Mock(**defaults)

    def test_defaults(self):
        payload = tts.build_bailian_payload(self._args(), "你好", "qwen-audio-3.0-tts-plus")
        self.assertEqual(payload["model"], "qwen-audio-3.0-tts-plus")
        inp = payload["input"]
        self.assertEqual(inp["text"], "你好")
        self.assertEqual(inp["voice"], tts.BAILIAN_DEFAULT_VOICE)
        self.assertEqual(inp["format"], "mp3")
        self.assertEqual(inp["sample_rate"], 24000)
        self.assertNotIn("rate", inp)
        self.assertNotIn("volume", inp)

    def test_format_alias_ogg_opus(self):
        payload = tts.build_bailian_payload(self._args(format="ogg_opus"), "x", "m")
        self.assertEqual(payload["input"]["format"], "opus")

    def test_speech_rate_mapping(self):
        # 100 → 2.0, -50 → 0.5, 0 → 1.0
        for rate, expected in ((100, 2.0), (-50, 0.5), (0, 1.0), (50, 1.5)):
            payload = tts.build_bailian_payload(self._args(speech_rate=rate), "x", "m")
            self.assertEqual(payload["input"]["rate"], expected)

    def test_loudness_mapping(self):
        # 0 → 50, 100 → 100, -50 → 25
        for loud, expected in ((0, 50), (100, 100), (-50, 25)):
            payload = tts.build_bailian_payload(self._args(loudness_rate=loud), "x", "m")
            self.assertEqual(payload["input"]["volume"], expected)

    def test_context_text_maps_to_instruction(self):
        payload = tts.build_bailian_payload(self._args(context_text="用撒娇的语气"), "x", "m")
        self.assertEqual(payload["input"]["instruction"], "用撒娇的语气")

    def test_volc_voice_swapped_to_bailian_default(self):
        payload = tts.build_bailian_payload(
            self._args(voice="zh_female_shuangkuaisisi_uranus_bigtts"), "x", "m"
        )
        self.assertEqual(payload["input"]["voice"], tts.BAILIAN_DEFAULT_VOICE)

    def test_bailian_voice_passthrough(self):
        payload = tts.build_bailian_payload(self._args(voice="my_cloned_voice"), "x", "m")
        self.assertEqual(payload["input"]["voice"], "my_cloned_voice")


class TestSimilarity(unittest.TestCase):
    def test_chinese_punctuation_difference_passes(self):
        # 旧 jaccard 按空白分词此处会归零
        sim = tts.similarity_ratio(
            "火山链路回归测试确认默认路径未变",
            "火山链路回归测试，确认默认路径未变。",
        )
        self.assertGreater(sim, 0.9)

    def test_identical(self):
        self.assertEqual(tts.similarity_ratio("abc def", "abc def"), 1.0)

    def test_empty(self):
        self.assertEqual(tts.similarity_ratio("", "abc"), 0.0)
        self.assertEqual(tts.similarity_ratio("", ""), 1.0)

    def test_asr_typo_still_passes_threshold(self):
        # 实测场景：ASR 把"字级"听成"字集"，单字差异仍应过 0.5 阈值
        sim = tts.similarity_ratio(
            "大家好这是百炼语音合成链路的实测包含字集时间戳",
            "大家好，这是百炼语音合成链路的实测，包含字级时间戳。",
        )
        self.assertGreater(sim, 0.5)


class TestSubtitleSchema(unittest.TestCase):
    def test_bailian_sentence_to_volc_schema(self):
        raw = {
            "text": "大家好",
            "words": [
                {"text": "大", "begin_time": 160, "end_time": 240},
                {"text": "家", "begin_time": 240, "end_time": 400},
            ],
        }
        converted = tts._bailian_stream_sentences(raw)
        self.assertEqual(converted["text"], "大家好")
        self.assertEqual(converted["words"][0], {"word": "大", "startTime": 0.16, "endTime": 0.24})
        self.assertEqual(converted["phonemes"], [])


class TestAudioPeakGuard(unittest.TestCase):
    def test_hot_tts_wav_gets_headroom(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'narration.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.5', '-af', 'volume=24dB',
                            '-c:a', 'pcm_s16le', str(path)], check=True)
            result = tts.protect_audio_peak(path, 'wav', 44100)
            self.assertGreater(result['input_true_peak_db'], -1)
            self.assertLessEqual(result['output_true_peak_db'], -1.5)
            self.assertLess(result['gain_db'], 0)

    def test_compressed_and_raw_formats_keep_supported_output(self):
        encodings = {
            'mp3': ['-c:a', 'libmp3lame', '-f', 'mp3'],
            'ogg_opus': ['-c:a', 'libopus', '-f', 'ogg'],
            'pcm': ['-c:a', 'pcm_s16le', '-f', 's16le'],
        }
        with tempfile.TemporaryDirectory() as tmp:
            for fmt, flags in encodings.items():
                with self.subTest(fmt=fmt):
                    path = Path(tmp)/f'narration.{fmt}'
                    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                    'sine=frequency=440:duration=0.5', '-af', 'volume=24dB',
                                    *flags, str(path)], check=True)
                    result = tts.protect_audio_peak(path, fmt, 44100)
                    self.assertLessEqual(result['output_true_peak_db'], -1.5)
                    self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
