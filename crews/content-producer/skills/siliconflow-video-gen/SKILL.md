---
name: siliconflow-video-gen
description: Generate videos via SiliconFlow Video API. Supports text-to-video (T2V) and image-to-video (I2V) using Wan2.2 models. Async: submit job → poll until done → download.
metadata:
  openclaw:
    emoji: "🎬"
    requires:
      bins:
      - python3
      env:
      - SILICONFLOW_API_KEY
    primaryEnv: SILICONFLOW_API_KEY
    homepage: https://docs.siliconflow.cn/cn/userguide/capabilities/video
---

# SiliconFlow Video Gen

Generate videos using the SiliconFlow Video API (Wan2.2 models).

Video generation is **asynchronous**: the API returns a `requestId` immediately, then the script polls the status endpoint until the job completes (status: `Succeed`).

> The generated video URL is valid for **1 hour**. The script downloads the video locally automatically.

## Run

Note: Video generation typically takes **1–5 minutes**. Set exec timeout accordingly (e.g., `exec timeout=600`).

```bash
# Text-to-video
python3 ./skills/siliconflow-video-gen/scripts/gen.py --prompt "a dolphin leaping over ocean waves at sunset"

# Image-to-video (provide a public URL or local base64 image)
python3 ./skills/siliconflow-video-gen/scripts/gen.py \
  --model "Wan-AI/Wan2.2-I2V-A14B" \
  --prompt "the camera slowly zooms out" \
  --image "https://example.com/my-photo.jpg"

# Custom resolution and output directory
python3 ./skills/siliconflow-video-gen/scripts/gen.py \
  --prompt "time-lapse of a blooming flower" \
  --image-size 720x1280 \
  --out-dir ./out/videos

# Reproducible generation with a fixed seed
python3 ./skills/siliconflow-video-gen/scripts/gen.py --prompt "rocket launch" --seed 42
```

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt` | required | Text description of the video |
| `--model` | `Wan-AI/Wan2.2-T2V-A14B` | Model ID: `Wan-AI/Wan2.2-T2V-A14B` (T2V) or `Wan-AI/Wan2.2-I2V-A14B` (I2V) |
| `--image` | — | Image URL or `data:image/...;base64,...` (required for I2V model) |
| `--image-size` | `1280x720` | Resolution: `1280x720` (16:9), `720x1280` (9:16), `960x960` (1:1) |
| `--negative-prompt` | — | What to avoid in the video |
| `--seed` | — | Random seed for reproducibility |
| `--poll-interval` | `10` | Seconds between status polls |
| `--timeout` | `600` | Max seconds to wait for generation |
| `--out-dir` | `./tmp/sf-video-<ts>` | Output directory |

## Models

| Model | Type | Notes |
|-------|------|-------|
| `Wan-AI/Wan2.2-T2V-A14B` | Text → Video | Default model |
| `Wan-AI/Wan2.2-I2V-A14B` | Image → Video | Requires `--image` parameter |

## Output

- `video_<requestId>.mp4` downloaded locally
- `result.json` with full API response

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SILICONFLOW_API_KEY` | Your SiliconFlow API key (required) |
