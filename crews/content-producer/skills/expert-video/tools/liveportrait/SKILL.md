---
name: liveportrait
description: expert-video 内部数字人工具。用百炼 LivePortrait 将肖像和一条确定的人声音频合成为口型视频，支持检测、临时素材上传、任务续查与同源校验。
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - ffprobe
---

# LivePortrait

仅作 expert-video 包内工具，按 deck-talk 的 Brief 与闸门调用。使用百炼业务空间 `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`），不使用 `AWK_API_KEY`。

先确定声音，再生成人物视频：用户录音优先；明确要求合成声音时用 awk-tts 的音色档案。肖像及声音须来自本人或有使用授权。合成声音仍是合成声音，不标为真人原录音。

```bash
liveportrait generate --image /absolute/portrait.png --audio /absolute/narration.wav --output /absolute/project/render/presenter.mp4
liveportrait resume --job /absolute/project/render/presenter.liveportrait.json
```

- `generate` 自动校验媒体、调用 liveportrait-detect、提交 liveportrait、保存 task_id、轮询并下载。默认 calm、30fps、头动强度 0.3；可传 `--template normal|calm|active`、`--fps 15..30`、`--head-move 0..1`、`--timeout 1..3600`。
- 支持本地文件和 HTTP(S) URL。远程媒体会先下载校验；本地文件使用百炼临时存储上传，检测和生成分别上传，不能跨模型复用临时 URL。临时存储用于开发/小规模验证，48 小时过期，不用于高并发生产批量。勿记录上传凭据。
- 图像 <10MB，JPEG/PNG/BMP/WebP，最大边 ≤4096，宽/高 ≤2。音频 WAV/MP3、<15MB、1秒 < 时长 <180秒；应为清晰单人人声，无 BGM/环境噪声。超长讲解先按句边界分段，生成对应片段再用 video-producer assemble 合成。
- 已存在输出/任务记录时不再次提交。超时用 `resume`；提交结果不确定且没有 task_id 时先查百炼控制台，勿盲目重试扣费。
- 产出 MP4 和 `.liveportrait.json`，记录原音频路径、音视频 SHA-256、时长和任务状态。时长偏差 >0.12秒时停止合成，不能变速声音迁就人物视频。
- `video-producer deck-compose --mode avatar --avatar-job ... --base ... --output ...` 自动使用任务的原音频，丢弃小窗视频自带音轨。BGM 在口型驱动之后处理，不能混入送往 LivePortrait 的音频。
- 先用 5–10 秒样片核验人脸、嘴型、声音，再按 Brief 的 GATE B 批准范围生成全量。工具返回成功不替代人工审片。

参考：[人像检测](https://help.aliyun.com/zh/model-studio/liveportrait-detect-api)、[视频生成](https://help.aliyun.com/zh/model-studio/liveportrait-api)、[临时媒体上传](https://help.aliyun.com/en/model-studio/get-temporary-file-url)。
