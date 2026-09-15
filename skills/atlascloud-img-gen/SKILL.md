---
name: atlascloud-img-gen
description: Generate or edit images with Atlas Cloud's asynchronous Media API. Supports text prompts, remote reference images, local image upload, polling, and downloading results.
metadata:
  openclaw:
    emoji: 🎨
    requires:
      bins:
      - python3
      env:
      - ATLASCLOUD_API_KEY
    primaryEnv: ATLASCLOUD_API_KEY
    homepage: https://www.atlascloud.ai/console
---

# Atlas Cloud Image Generation

Use `atlascloud-img-gen` for text-to-image and image-edit jobs. The wrapper submits an asynchronous Atlas Cloud task, polls it to completion, and downloads every output.

```bash
atlascloud-img-gen --prompt "a cinematic mountain village at sunrise"
atlascloud-img-gen --prompt "turn this into a watercolor" --image https://example.com/source.jpg
atlascloud-img-gen --prompt "remove the background" --image ./source.png --out-dir ./output
```

The default model is `bytedance/seedream-v5.0-lite`. Override it with `--model`. Model-specific options can be supplied as JSON with `--params`, for example:

```bash
atlascloud-img-gen --prompt "editorial product photo" \
  --params '{"image_size":"2048x2048"}'
```

Local files passed to `--image` are uploaded first. Remote `http` or `https` URLs are sent directly. Credentials come only from `ATLASCLOUD_API_KEY`; do not place keys in arguments or files.

Outputs are written below `./tmp/atlascloud-img-<timestamp>` unless `--out-dir` is set. The directory contains downloaded images and `result.json` with the prediction metadata.
