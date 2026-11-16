---
name: avatar
description: expert-video 内部数字人口型视频工具。用百炼 Wan S2V 检测肖像、按原声生成、恢复任务、登记口型审查和合并同源分段。
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - ffmpeg
        - ffprobe
---

# Avatar

按 expert-video 的 deck-talk Brief 与闸门执行。使用 `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`），不使用 Token Plan Key。声音优先用用户原录音；合成声音须获明确批准并沿用 awk-tts 音色档案。

```bash
avatar generate --image /absolute/portrait.png --audio /absolute/narration.wav --output /absolute/render/presenter.mp4
avatar resume --job /absolute/render/presenter.avatar.json
avatar review --job /absolute/render/presenter.avatar.json --verdict pass --reviewer main --notes '已审看全段口型、人像和尾部'
video-producer deck-compose --mode avatar --avatar-job /absolute/render/presenter.avatar.json --base /absolute/base.mp4 --output /absolute/composed.mp4
```

- `generate` 校验图片，调用 `wan2.2-s2v-detect` 的 `check_pass`，再用 `wan2.2-s2v` 创建异步任务。`--resolution 480P|720P` 默认480P；`--timeout 1..3600` 默认900秒。输出新视频及 `.avatar.json`，内部记录真实 provider/model。
- 图片 JPEG/PNG/BMP/WebP，宽高均400–7000像素。音频 WAV/MP3，应为清晰人声，无BGM或环境噪声。脚本解码原声、提取指定时间窗，末尾默认追加0.75秒精确静音作为驱动余量；`--tail 0..2` 可调整。驱动音频含静音必须严格小于20秒、文件小于15MB。模型视频不足以覆盖完整原声时停止，不定帧、不循环、不变速、不自动重提。
- 本地和 HTTP(S) 媒体均支持；临时上传按检测与生成模型分别执行，勿跨模型复用 URL。只在独立派生目录保存驱动 WAV，不修改原声。合成时丢弃模型自带音轨。
- `api_succeeded` 仅表示服务端成功；`timing_pass` 表示视频覆盖原声音频且量化误差≤0.12秒；`lip_sync_review_pass` 必须由实际审片后通过 `review` 登记，并绑定当前音视频哈希。不得因时长通过自动填写口型通过。`deck-compose` 在人工审查前阻断新任务合成。
- 先生成5–10秒样片，核验人物、嘴型、尾部和小窗裁切；按 GATE B 已批准范围再做全量。`review` 不代替 GATE B，也不等于批准新一轮模型调用。
- 已有 job 用 `resume`，不再 generate。无 task_id 的 SUBMITTING 表示提交不确定，先查控制台；已确认失败也不自动重提。已下载且通过哈希校验的本地产物可恢复，不因远端任务过期而重复付费。旧 `.liveportrait.json` 仍由 `avatar resume` 兼容续查。

## 长音频分段与合并

每段均从同一条完整原声取窗口，避免累计 MP3 容器时长。`--start`、`--duration` 按解码 PCM 计时；按句边界选择窗口，原始说话时间不得裁掉。每段都要审片，再写一个有序 job 路径数组到工作区 manifest：

```json
["segments/01.avatar.json", "segments/02.avatar.json"]
```

```bash
avatar generate --image /absolute/portrait.png --audio /absolute/locked.mp3 --start 0 --duration 5 --output /absolute/render/segments/01.mp4
avatar assemble --manifest /absolute/render/jobs.json --audio /absolute/locked.mp3 --output /absolute/render/presenter-all.mp4
```

`assemble` 校验每段API状态、时长、口型审查、原声哈希和逐窗PCM，要求从0开始无缝覆盖完整原声。仅重叠的驱动静音会被舍弃；不冻结或补造视频帧。输出汇总 `.avatar.json`，使用完整原声作最终音轨。对汇总视频审看全段及接缝后再 `avatar review`，之后交 `deck-compose`。

参考：[检测](https://help.aliyun.com/zh/model-studio/wan-s2v-detect-api)、[生成](https://help.aliyun.com/zh/model-studio/wan-s2v-api)。
