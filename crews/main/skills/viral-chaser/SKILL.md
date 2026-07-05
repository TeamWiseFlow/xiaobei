---
name: viral-chaser
description: 下载分析抖音/B站/小红书爆款视频，生成追爆报告。仅产出报告，脚本另外使用 video-product 技能根据 追爆报告.md 生成。
metadata:
  openclaw:
    emoji: 🎯
    requires:
      bins:
      - node
      - ffmpeg
      env:
      - SILICONFLOW_API_KEY
---

# Viral Chaser（追爆分析 — 报告产出）

Use this skill when:
- 用户提供抖音 / B 站 / 小红书视频链接，希望分析并制作同类视频
- 需要分析爆款视频的结构和公式

**本技能仅产出追爆报告**，不生成脚本，不制作视频。报告产出后，直接进入 `video-product` 技能，按追爆报告生成脚本并完成后续生产。

**Supported platforms:** 抖音（Douyin）、B 站（Bilibili）、小红书（XHS — 仅视频笔记）

**Not supported:** 微信视频号、TikTok

---

## ⚙️ 执行方式（强制）

本技能涉及多步骤生产流程，你应该 self-spawn 一个 subagent 来执行，原因：subagent 独立上下文，不会因对话历史积累而降低输出质量。

你只负责跟进subagent的执行，避免它们长时间卡在某个步骤，必要时可以提供提示或调整执行策略。

---

## Workflow

### Step 1 — Create workspace

Before anything else, create the working directory for this video under `output_videos/`:

```bash
VIDEO_SLUG="<platform>-<contentId>"  # e.g. douyin-7389abc or bilibili-BV1xx
mkdir -p "output_videos/${VIDEO_SLUG}/references"
```

All downloaded files, analysis results, and generated reports will be saved under this directory. The `references/` subdirectory holds the raw assets (video, audio, key frames) downloaded by the analyzer script.

### Step 2 — Check login (skip for public Bilibili videos)

Use the **login-manager** skill to check the session:

- `platform`: `douyin` | `bilibili` | `xhs`
- Call login-manager's **check** ability for the target platform (XHS uses `xhs-browse`)
- If exit code 2 (session expired), execute the **camoufox-cli 登录流程** described in the login-manager skill (qr-headless + qr-confirm, see browser-guide §0.1), then retry `check`

### Step 3 — Run the analyzer

Set the output directory to the `references/` subdirectory via the `OUTPUT_DIR` environment variable:

```bash
OUTPUT_DIR="output_videos/${VIDEO_SLUG}/references" ./skills/viral-chaser/scripts/viral_chaser.sh <url> [--no-frames]
```

- `<url>`: Full or short-link URL of the video（支持短链，如 `xhslink.com/o/xxx`、`v.douyin.com/xxx`、`b23.tv/xxx`，脚本内部跟随重定向解析）
- `--no-frames`: Skip key frame extraction (faster, audio-only analysis)
- `OUTPUT_DIR`: Must point to the `references/` subdirectory under the workspace created in Step 1

> **⚠️ exec allowlist 注意**：上面这行 `OUTPUT_DIR=... ./script` 是**标准 shell 写法**，但在 openclaw exec allowlist 下，**内联 env 前缀会触发 allowlist miss**。通过 exec 工具调用时，请把 `OUTPUT_DIR` 放到 exec 的 **`env` 字段**里传，而不是写成内联前缀；同理避免 `mkdir ... ; echo` 这类分号复合命令（分号会被当成路径的一部分）。脚本本身已正确读取 `OUTPUT_DIR` 落盘，问题只在调用规范。

The script outputs a **JSON object to stdout**. Read it and proceed with analysis.

**Output JSON structure:**
```json
{
  "ok": true,
  "platform": "douyin",
  "metadata": {
    "contentId": "...",
    "title": "...",
    "desc": "...",
    "author": "...",
    "durationSeconds": 89,
    "coverUrl": "...",
    "stats": { "playCount": 0, "likeCount": 0, "commentCount": 0 }
  },
  "transcript": {
    "text": "全文转录...",
    "segments": [{ "start": 0.0, "end": 5.2, "text": "开场文案" }],
    "estimated": false
  },
  "frames": ["output_videos/<slug>/references/frames/frame_00_0s.jpg", "..."],
  "localPaths": {
    "video": "output_videos/<slug>/references/video.mp4",
    "audio": "output_videos/<slug>/references/audio.wav",
    "tmpDir": "output_videos/<slug>/references"
  }
}
```

- `transcript.estimated`: `true` 表示 `segments` 的时间戳是按音频时长估算的（SiliconFlow ASR 不返回真实时间戳），`false` 表示是 ASR 真实分段。估算分段仍可用于钩子分析与结构拆解，但时间区间是按字数比例分配的近似值。

**Exit codes:**
- `0` = Success
- `1` = Error (URL invalid, download failed, etc.) — report to user
- `2` = Cookie expired — execute the browser-based re-login workflow (see login-manager skill), then retry once

### Step 4 — Read key frames (if available)

For each path in `frames`, use the `Read` tool to load the image and analyze it visually.

```
Read: output_videos/<slug>/references/frames/frame_00_0s.jpg
Read: output_videos/<slug>/references/frames/frame_01_3s.jpg
...
```

---

## Analysis Framework

After receiving the JSON output and reading the frames, generate a **追爆报告** in Markdown and save it to `output_videos/<slug>/raw_article.md`.

### 1. 内容摘要
1–2 sentences: what core value does this video deliver to viewers?

### 2. 开头钩子分析（前 0–10 秒）
Based on `transcript.segments` where `start < 10`:
- **钩子类型**: 提问型 / 冲突型 / 反转型 / 数字型 / 悬念型 / 痛点型 / 利益型
- **具体文案**: quote the exact opening line(s)
- **效果评估**: why this hook works (or doesn't)

### 3. 内容结构拆解
Based on transcript segments, divide into logical sections:

| 段落 | 时间区间 | 功能 | 核心内容 |
|------|---------|------|---------|
| 开场 | 0–Xs | 钩子/引入 | ... |
| 主体一 | X–Ys | 价值/信息传递 | ... |
| 主体二 | Y–Zs | 深化/转折 | ... |
| 收尾 | Z–结束 | CTA/情绪收尾 | ... |

### 4. 爆款元素评估
Rate each element as **强 / 中 / 弱** with a one-line explanation:

| 元素 | 评级 | 说明 |
|------|:----:|------|
| 前 3 秒吸引力 | | |
| 痛点共鸣度 | | |
| 悬念设置 | | |
| 情绪触发 | | |
| 价值清晰度 | | |
| CTA 效果 | | |
| 视觉冲击（基于关键帧） | | |
| 节奏把控 | | |

### 5. 视觉风格分析（基于关键帧图片）
After reading the frame images:
- **色调风格**: 暖色系/冷色系/高饱和/低饱和/黑白
- **构图类型**: 人脸近景 / 产品展示 / 场景空镜 / 文字卡片 / 混合
- **字幕/文字覆盖**: 字体粗细、位置、是否有背景框、动画感
- **整体视觉标签**: 3–5 个关键词（如：「真实感」「强对比」「高信息密度」）

If `--no-frames` was used or frames is empty, note: "（跳过视觉分析，请重新运行不带 --no-frames 参数）"

### 6. 可借鉴点
3–5 concise, directly actionable techniques. One sentence each.

### 7. 目标受众
One sentence describing the primary audience persona.

---

## 衔接 video-product

追爆报告产出后，直接进入 `video-product` 技能流程，并应该明确提示后续工作流程：工作目录为 `output_videos/<slug>/`，直接按`raw_article.md`制作脚本.

---

## Notes

- **Workspace files** are stored in `output_videos/<slug>/` — all downloaded assets and analysis reports are kept together. The `references/` subdirectory contains raw assets from the analyzer.
- **Bilibili DASH format**: if `mediaFormat` is `DASH`, the video and audio streams are separate. The downloaded `video.mp4` contains the video stream only; audio is in `audio.wav` after extraction. This is transparent to the analysis workflow.
- **XHS video notes only**: 小红书图文笔记（image-only）不含视频，viral-chaser 会报错并提示。只有视频笔记（type=video）才能下载和分析。XHS 使用 `xhs-browse` cookie（消费者端域 www.xiaohongshu.com）；xhs 数据抓取委托 `xhs-content-ops`，签名走 relay（xys 格式）。
- **ASR segments**: SiliconFlow ASR（SenseVoiceSmall / TeleSpeechASR）只返回全文 text、不返回分段时间戳。脚本在拿不到真实 segments 时，会按句切分全文并按字数比例在音频时长上**估算**分段（`transcript.estimated=true`）。若需要真实时间戳，可改用支持 verbose_json 的 whisper 类模型（设置 `ASR_MODEL` 环境变量），脚本会优先采用真实 segments。
- **Exit code 2 — cookie expired:** Execute the browser-based re-login workflow described in the login-manager skill's "Agent workflow on exit code 2" section, then retry once. Do not retry more than once.
