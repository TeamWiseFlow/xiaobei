---
name: siliconflow-tts
description: Generate speech audio via SiliconFlow Text-to-Speech API. Converts text to MP3/WAV/Opus/PCM using fnlp/MOSS-TTSD-v0.5 voices and SILICONFLOW_API_KEY.
metadata:
  openclaw:
    emoji: 🔊
    requires:
      bins:
      - python3
      env:
      - SILICONFLOW_API_KEY
    primaryEnv: SILICONFLOW_API_KEY
    homepage: https://docs.siliconflow.cn/cn/api-reference/audio/create-speech
---

# SiliconFlow TTS

Generate narration audio from text using SiliconFlow Text-to-Speech API.

Use this skill when:
- You need voiceover or narration audio for a video
- You need standalone TTS assets before composing with Remotion/MoviePy
- You want to convert a script into reusable `.mp3`, `.wav`, `.opus`, or `.pcm`

## Run

**Do NOT set env vars inline** (for example, `SILICONFLOW_API_KEY=... python3 ...`). The env var is already in the system environment; inline assignments break the exec permission check.

```bash
# Basic Chinese narration, saved under ./tmp/sf-tts-<ts>/speech.mp3
python3 ./skills/siliconflow-tts/scripts/tts.py --text "大家好，欢迎来到今天的视频。"

# Read text from a file
python3 ./skills/siliconflow-tts/scripts/tts.py \
  --text-file ./scripts/script.txt \
  --out-dir ./assets/audio

# Fragment workflow: read tts_requirement.md, extract voiceover/voice/speed,
# and output speech.mp3 + speech.json to ./fragments/01-hook/artifacts/
python3 ./skills/siliconflow-tts/scripts/tts.py ./fragments/01-hook/ --overwrite

# Select voice, format, and exact output path
python3 ./skills/siliconflow-tts/scripts/tts.py \
  --text "This is a demo voiceover." \
  --voice "fnlp/MOSS-TTSD-v0.5:benjamin" \
  --format wav \
  --sample-rate 44100 \
  --output ./assets/audio/demo.wav
```

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `fragment_dir` | — | Optional fragment directory under `fragments/`; when set, reads `tts_requirement.md` and defaults output to `artifacts/speech.<format>` |
| `--text` | — | Text to synthesize. Required unless `--text-file` or `fragment_dir` is set |
| `--text-file` | — | UTF-8 text file to synthesize. Must be relative and under `scripts`, `assets`, `tmp`, `output_videos`, or `fragments` |
| `--model` | `fnlp/MOSS-TTSD-v0.5` | SiliconFlow TTS model |
| `--voice` | `fnlp/MOSS-TTSD-v0.5:benjamin` | Voice ID |
| `--format` | `mp3` | Audio format: `mp3`, `opus`, `wav`, `pcm` |
| `--max-tokens` | — | Optional maximum output tokens |
| `--sample-rate` | — | Optional sample rate. `mp3`: 32000/44100; `opus`: 48000; `wav`/`pcm`: 8000/16000/24000/32000/44100 |
| `--stream` / `--no-stream` | `--no-stream` | Request streaming or non-streaming response |
| `--speed` | — | Optional speech speed, range `0.25`–`4.0` |
| `--gain` | — | Optional audio gain, range `-10`–`10` |
| `--output` | — | Exact output file path under `assets/audio`, `tmp`, `output_videos`, or `fragments` |
| `--out-dir` | `./tmp/sf-tts-<ts>` | Output directory under `assets/audio`, `tmp`, `output_videos`, or `fragments` when `--output` is not set |
| `--overwrite` | off | Overwrite existing output audio/metadata files |
| `--no-asr-check` | off | Skip ASR self-check after TTS generation |

## Recommended voices

| Voice ID | Notes |
|----------|-------|
| `fnlp/MOSS-TTSD-v0.5:benjamin` | 幽默男声，语速较慢，推荐 |
| `fnlp/MOSS-TTSD-v0.5:charles` | 激昂男声，适合广告 |
| `fnlp/MOSS-TTSD-v0.5:claire` | 清澈女声，推荐 |
| `fnlp/MOSS-TTSD-v0.5:david` | 清脆男声 |
| `fnlp/MOSS-TTSD-v0.5:diana` | 可爱女声，娃娃音 |

## Dialogue format

`fnlp/MOSS-TTSD-v0.5` supports spoken dialogue scripts. Use speaker tags when writing multi-speaker dialogue:

```text
[S1]Hello, how are you today?[S2]I'm doing great, thanks for asking!
```

## Output

- Audio file: `speech.<format>` or the path set by `--output`
- Metadata file: `speech.json` beside the audio file, containing:
  - `duration`: audio duration in seconds (via ffprobe)
  - `model`, `voice`, `format`, `text_chars`, `audio_bytes`, `file` etc.

When used in the content-producer fragment workflow, pass the fragment directory directly. The script reads `tts_requirement.md`, extracts the `## 配音文案` / `## Voiceover Text` section, reads voice/speed settings, and writes directly to the fragment's `artifacts/` directory.

For `tts_requirement.md`, the script skips markdown headings, comments, and voice settings when synthesizing audio.

## ASR Self-Check

After generating audio, the script automatically runs an ASR self-check (unless `--no-asr-check` is set):

1. Transcribes the generated audio via SiliconFlow ASR (`TeleAI/TeleSpeechASR` by default)
2. Compares transcription with the input text using Jaccard similarity
3. Threshold: **0.5** (50%) — based on testing, 50% Jaccard is sufficient for practical quality; higher thresholds caused excessive false negatives
4. Result printed as `PASS` or `WARN`; does not abort on failure

The ASR check calls `/audio/transcriptions` with multipart form fields `file` and `model`, matching SiliconFlow's transcription API. It requires `SILICONFLOW_API_KEY`; if not set, the check is silently skipped.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SILICONFLOW_API_KEY` | Your SiliconFlow API key (required) |
| `SILICONFLOW_API_BASE` | Optional API base override, default `https://api.siliconflow.cn/v1` |
| `SILICONFLOW_ASR_MODEL` | Optional ASR model override, default `TeleAI/TeleSpeechASR` |
