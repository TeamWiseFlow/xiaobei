---
name: talking-head-cut
description: 口播类视频（口播/演讲/访谈/直播）的轻剪辑——ASR 转写拿逐字时间戳，去口气词/结巴/静音，或识别高光段剪成集锦。仅做基于人声的轻剪辑，不出脚本不烧字幕；纯画面类素材的集锦剪辑走 video-edit。
metadata:
  openclaw:
    emoji: "🎙️"
    requires:
      bins:
      - python3
      - ffmpeg
      - ffprobe
---

# 口播视频轻剪辑（talking-head-cut）

## 适用场景

用户提供一段**有人说话**的视频（口播、演讲、访谈、直播回放等），要求：

- **去口气词**：删掉嗯/呃/结巴/长静音/假起头/重复句，让口播更干净（`--mode filler`）
- **高光剪辑**：自动识别精彩发言段，剪接成短集锦（`--mode highlight`）
- 两者都要：先去口气词再标高光（`--mode both`）

典型输入：一段 5–60 分钟的口播视频 + 目标时长（如"剪成 60 秒的高光集锦"）。

不适用：

- 视频没有人声、或精彩与否要看**画面**而不是听内容 → 走 `video-edit` 的画面集锦流程
- 用户已经明确告诉剪哪几段 → 直接用 `video-edit extract` 手工抽段拼接
- 需要从零生产视频 → 委托 content-producer
- 需要烧字幕、加 BGM → 剪完后走 `video-edit subtitles` / `video-edit audio-mix`（纯 BGM 使用公共 `bgm-library`：`bgm-library pick "<英文风格标签>"` 选曲下载并保留署名；背景音/环境音用 `aigc-video-gen audio`，保持原口播，不为加背景而重配人声）

---

## 工作区

平台内容用平台运营项目目录 `<platform>/outputs/<video-name>/` 作项目目录；其他零散任务在 `output_videos/` 下建项目文件夹：

```
<project-dir>/                 # 即 <platform>/outputs/<video-name>/ 或 output_videos/<project-en-slug>/
├── source.mp4             # 用户提供的原始视频（重命名后的副本或软链）
├── cut_plan.json          # 检测产物：[{keep, start, end, reason}]
└── highlight.mp4          # 最终成片
```

---

## 流程

### Step 1：检测生 cut_plan.json

```bash
talking-head-cut <source.mp4> \
    --mode highlight \
    --language zh \
    --output <project-dir>/cut_plan.json
```

参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--mode` | `filler` | `filler` 去口气词 / `highlight` 高光剪辑 / `both` 先去口气词再标高光 |
| `--language` | `zh` | 语气词清单选择：`zh` 嗯/呃/额/唔/哎/诶/欸；`en` um/uh/uhm/er |
| `--silence-gap` | `0.6` | 静音段判据：相邻 word gap > 此秒数 |
| `--stutter-repeat` | `4` | 结巴段判据：单字重复 ≥ 此次数 |
| `--similarity-threshold` | `0.6` | 重复句段判据：句间 Jaccard > 此阈值 |
| `--output` | `cut_plan.json` | 计划产物路径 |

产物 `cut_plan.json`：

```json
{
  "ok": true,
  "source": "source.mp4",
  "duration": 1832.5,
  "mode": "highlight",
  "plan": [
    {"keep": true,  "start": 12.3,  "end": 45.8,  "reason": "highlight"},
    {"keep": false, "start": 45.8,  "end": 50.1,  "reason": "silence"},
    {"keep": true,  "start": 50.1,  "end": 88.2,  "reason": "highlight"},
    {"keep": false, "start": 88.2,  "end": 91.0,  "reason": "filler"},
    ...
  ]
}
```

`reason` 枚举：

| reason | 含义 | mode=filler 时 keep | mode=highlight 时 keep |
|--------|------|--------------------|-----------------------|
| `filler` | 语气词段 | false | — |
| `silence` | 静音段 | false | false |
| `stutter` | 结巴段 | false | — |
| `false_start` | 假起头段 | false | — |
| `repeat` | 重复句段 | false | — |
| `highlight` | 高光段 | — | true |
| `normal` | 常规段 | true | false |

> 高光判据（`detect_highlight`）：utterance 字数/时长 > 4 字/秒（zh）或 3 词/秒（en），且与全片文本 Jaccard < 0.3（"新颖段"）。

### Step 2：用户确认 cut_plan.json（关键闸门）

cut_plan.json 落盘后**必须先让用户看一眼**再剪：

- 报告：总时长、keep 段总时长、keep 段数、remove 段数、按 reason 分类的段数与累计时长
- 若 keep 段总时长与用户目标时长差距大（>20%）→ 调阈值重跑 Step 1，不要硬剪
- 用户认 plan 后才进 Step 3

### Step 3：按 cut_plan.json 剪拼成片

剪拼由 `video-edit` 技能的 apply-cut 子命令执行：

```bash
video-edit apply-cut <source.mp4> <project-dir>/cut_plan.json \
    --output <project-dir>/highlight.mp4 \
    --fade-ms 40
```

参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--output` | `<input>_cut.mp4` | 成片输出路径 |
| `--fade-ms` | `40` | 段间 triangular fade 毫秒数（防咔点，0 关闭） |

流程：

1. 读 cut_plan.json，滤 `keep=true` 段
2. ffmpeg `-ss`/`-t` 逐段抽出（libx264 crf 20 + aac 128k + 保持源分辨率帧率）
3. 段间加 `--fade-ms` 毫秒 triangular fade 防咔点
4. ffmpeg `concat` 拼接成片，`+faststart` 优化

### Step 4：成片自检（强制闸门）

剪拼完成后**必须**跑成片自检，自检不过不得交付：

```bash
video-review <project-dir>/highlight.mp4
```

> video-review 是成片自检闸门，verdict=pass 才交付；verdict=fail 按 review 提示修。详见 `video-review` 技能 SKILL.md。

### Step 5：用户确认

向用户展示：

- 成片（发文件本体）
- 关键参数：成片时长、keep 段数、总压缩比（成片时长/源时长）
- cut_plan.json 概要（按 reason 分类的段数与累计时长）

用户确认后流程结束。后续发布由各 publish 技能执行。

---

## 依赖

| 依赖 | 来源 | 说明 |
|------|------|------|
| ffmpeg / ffprobe | 系统 | 抽 WAV、剪拼、concat |
| 公共 ASR 路由 | env 任一组凭据 | 火山极速版（`VOLC_ASR_*`）→ 百炼业务空间 → 百炼 agent plan；拿 word 级时间戳 |
| requests | 仓根 requirements.txt | 调 ASR HTTP API |
| `video-edit` 技能 | 同 workspace | Step 3 剪拼（apply-cut）+ 后续加 BGM（audio-mix） |
| `video-review` 技能 | 公共 skills | Step 4 成片自检 |
| `bgm-library` 技能 | 公共 skills | 纯 BGM 曲源（ccMixter 免版税，免 key，保留署名） |

**ASR 凭证**（任一组）：火山 `VOLC_ASR_APP_ID` + `VOLC_ASR_ACCESS_KEY`（旧控制台双头）或 `VOLC_ASR_APP_KEY`（新控制台单头）；百炼业务空间 `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`；百炼 agent plan `AWK_API_KEY`。全部未配置时退出码 2 并提示走 viral-chaser 开通流程。

---

## 脚本清单

| 调用 | 用途 | 退出码 |
|------|------|--------|
| `talking-head-cut <source> [参数...]` | ASR 转写 + 多层检测生 cut_plan.json | 0 成功 / 1 参数错 / 2 ASR env 未配 / 3 ffmpeg 不存在 |
| `video-edit apply-cut <source> <plan> [参数...]` | 按 cut_plan.json ffmpeg 剪拼成片 | 0 成功 / 1 参数错 / 3 ffmpeg 不存在 |

---

## 禁止事项（强制）

- **禁止跳过 video-review 交付**：剪拼完必须跑成片自检，verdict=pass 才交付
- **禁止硬剪不确认 plan**：cut_plan.json 落盘后必须先让用户确认 keep/remove 段再剪
- **禁止直接写 ffmpeg 命令**：所有 ffmpeg 调用走本技能与 video-edit 的标准化脚本，不在 exec 中拼 ffmpeg 命令
