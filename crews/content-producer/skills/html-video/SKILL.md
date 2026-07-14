---
name: html-video
description: 使用 html-video 引擎从 content-graph 和模板生成视频。支持 23+ 模板、多种画面比例、变量注入、逐帧渲染、全项目导出。TTS/BGM 由 openclaw MiniMax 扩展提供，不使用 html-video 内置音频。
metadata:
  openclaw:
    emoji: 🎬
    requires:
      bins:
      - node
      - ffmpeg
---

# html-video — 模板驱动视频生成

## 概述

基于 html-video 引擎的视频生成技能。核心能力：

- **23+ 模板库**：覆盖标题动画、数据可视化、产品宣传、结尾 CTA、社交短视频等场景
- **多画面比例**：9:16、16:9、1:1、4:5 等
- **Content-Graph IR**：结构化分镜（nodes + edges + topo-sort）
- **确定性渲染**：animation freeze → font loading → duration probe → Chromium 录制 → ffmpeg 编码
- **全项目导出**：逐帧渲染 → 帧拼接 → 音频混合（ducking + fades）

**TTS/BGM 说明**：音频生成由 openclaw 的 MiniMax 扩展提供（speech-2.8-hd / music-2.6），不使用 html-video 内置的 MiniMax provider。生成后的音频文件作为项目资产注入 html-video 的 `applySoundtrack`。

## CLI 调用

> **⚠️ 调用规范（必须遵守）**
>
> - **必须**通过 `./skills/html-video/scripts/hv.sh <command>` 调用，hv.sh 内部自动解析 CLI 路径并 `exec node`
> - **禁止**直接 `node .../bin.js` — 路径易错且绕过 allowlist
> - **禁止** `python3 .../bin.js` — bin.js 是 ESM JavaScript，不是 Python 脚本
> - **禁止** `bash hv.sh` 或绝对路径调用 — 使用工作区相对路径 `./skills/html-video/scripts/hv.sh`
> - **禁止**直接 `ffmpeg` / `ffprobe` — 由 hv.sh 内部 subprocess 调用，agent 直接调有 CPU 卡死风险

所有操作通过 `hv.sh` 包装脚本调用：

```bash
# 环境检查
./skills/html-video/scripts/hv.sh doctor

# 模板搜索
./skills/html-video/scripts/hv.sh search-templates --intent "title animation"

# 查看模板详情
./skills/html-video/scripts/hv.sh inspect-template frame-glitch-title

# 项目管理
./skills/html-video/scripts/hv.sh project-create --name "my-video" --aspect "9:16"
./skills/html-video/scripts/hv.sh project-set-template <project-id> --template <template-id>
./skills/html-video/scripts/hv.sh project-set-var <project-id> --key title --value '"文案"'
./skills/html-video/scripts/hv.sh project-set-var <project-id> --key duration_sec --value 4

# 渲染
./skills/html-video/scripts/hv.sh project-render <project-id> --output /path/to/output.mp4

# 项目查询
./skills/html-video/scripts/hv.sh project-list
./skills/html-video/scripts/hv.sh project-show <project-id>
```

## 画面比例

| 比例 | 分辨率 | 典型场景 |
|------|--------|---------|
| `9:16` | 1080×1920 | 短视频、竖屏（默认） |
| `16:9` | 1920×1080 | 横屏视频、YouTube |
| `1:1` | 1080×1080 | Instagram 方形 |
| `4:5` | 1080×1350 | Instagram 竖屏 |

创建项目时通过 `--aspect` 指定，未指定默认 `9:16`。

## 工作流

### 1. Content-Graph 生成

分析脚本内容，自行决定分段，生成 content-graph.json：

```json
{
  "schemaVersion": 1,
  "intent": "promo",
  "synopsis": "视频概要",
  "nodes": [
    {
      "id": "hook-title",
      "kind": "text",
      "frameIntent": "intro",
      "durationSec": 4,
      "templateRef": "frame-glitch-title",
      "variables": { "title": "...", "subtitle": "..." },
      "hasTts": true,
      "ttsText": "配音文案"
    },
    {
      "id": "product-clip",
      "kind": "entity",
      "frameIntent": "image-pan",
      "durationSec": 8,
      "templateRef": "video-clip-916",
      "variables": { "videoSrc": "assets/clip.mp4" },
      "hasTts": true,
      "ttsText": "产品介绍文案"
    }
  ],
  "edges": [
    { "from": "hook-title", "to": "product-clip", "kind": "sequence" }
  ]
}
```

### 2. 素材预获取

素材类节点（如 video-clip）需要先获取素材 MP4：

**获取优先级**（按顺序尝试，成功即停）：

1. **用户预置素材**：`assets/` 中已有对应素材 → 直接使用
2. **`video_generate` 工具**：根据画面需求撰写 prompt，生成后验证时长
3. **`siliconflow-video-gen`**：AI 视频生成（每次 5 秒，可能需多次生成后拼接）
⚠️：`siliconflow-video-gen`只要失败一次，第二次马上降级使用`pexels-footage`或者`pixabay-footage`，绝不允许连续多次调用`siliconflow-video-gen`，以避免触发系统锁死
4. **`pixabay-footage`**：从 Pixabay 免费素材库搜索下载
5. **`pexels-footage`**：Pixabay 无合适结果时，从 Pexels 搜索下载

素材下载规则：

- **一次只下载一个视频**：pixabay-footage 和 pexels-footage 脚本已强制 `--max-clips=1`
- **时长精准匹配**：根据节点目标时长设置 `--min-duration` 和 `--max-duration`，不下载远超需求的素材
- 下载后用 ffprobe 确认实际时长，写入节点 `duration` 字段

### 3. 模板变量注入

所有节点的变量通过 `project-set-var` 注入 html-video 项目。素材节点的 `videoSrc` 替换为 Step 2 获取的 `clip.mp4` 路径，`duration` 替换为 ffprobe 检测的实际时长。

### 4. TTS 生成

- 主力：openclaw MiniMax 扩展（speech-2.8-hd，5 种中文音色）
  - 通过 `tts` 工具调用
  - TokenPlan 订阅 key: `MINIMAX_CODE_PLAN_KEY`
- Fallback：SiliconFlow TTS (MOSS-TTSD-v0.5)
  - 通过 `siliconflow-tts` 技能调用，详见 `siliconflow-tts/SKILL.md`
- BGM：openclaw MiniMax 扩展（music-2.6）
  - 通过 `music_generate` 工具调用
- 生成的音频文件写入项目资产目录，html-video 的 `applySoundtrack` 负责最终混音

### 5. 全项目渲染

```bash
./skills/html-video/scripts/hv.sh project-render <project-id> --output final/video.mp4
```

html-video 自动完成：逐帧渲染 → 帧拼接 → 音频混合。

## 可用模板

### 标题 / 呈现类（presentation）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `frame-glitch-title` | Glitch Title | 3-8s | 科技产品揭示、赛博朋克风格 |
| `frame-kinetic-type` | Kinetic Type | 3-30s | 推广标题、醒目声明 |
| `frame-bold-poster` | Bold Poster | 4-6s | 品牌宣言、杂志封面式开场 |
| `frame-bold-signal` | Bold Signal | 3-6s | 章节分隔、强冲击标题卡 |
| `frame-build-minimal` | Build Minimal | 4-7s | 高端产品/品牌 hero、优雅标题卡 |
| `frame-creative-voltage` | Creative Voltage | 3-6s | 活力品牌/活动标题、手绘风格 |
| `frame-electric-studio` | Electric Studio | 3-6s | 引用/证言揭示、使命声明卡 |
| `frame-warm-grain` | Warm Grain | 3-30s | 产品发布、生活方式品牌 |
| `frame-swiss-grid` | Swiss Grid | 3-30s | 企业幻灯片、极简报告卡 |
| `frame-vignelli` | Vignelli | 3-30s | 社交竖屏、醒目声明卡 |
| `vfx-text-cursor` | Text + Cursor VFX | 3-10s | 代码演示开场、科技叙事 |

### 数据可视化类（data-viz）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `frame-data-chart-nyt` | NYT Data Chart | 5-20s | 编辑数据可视化、年报、对比揭示 |
| `frame-data-rollup` | Data Rollup | 3-8s | 数据动画、周报指标、增长柱状图 |
| `frame-nyt-graph` | NYT Graph | 3-30s | 新闻式统计揭示、折线图 |
| `frame-pentagram-stat` | Pentagram Stat | 3-6s | 单一核心指标/基准揭示、编辑数据幻灯 |

### 产品 / 营销类（marketing / product-demo）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `frame-product-promo` | Product Promo | 3-30s | 产品展示、多功能轮播、hero 推广 |
| `frame-product-promo-30s` | Product Promo · 30s | 25-35s | 30 秒产品推广、B2B SaaS 发布 |
| `frame-liquid-bg-hero` | Liquid Background Hero | 4-12s | 产品发布 hero、SaaS 落地视频 |
| `frame-play-mode` | Play Mode | 3-30s | 轻松社交广告、休闲开场 |

### 讲解 / 氛围类（explainer / ambient）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `frame-decision-tree` | Decision Tree | 3-30s | 操作流程、决策分支 |
| `frame-takram-organic` | Takram Organic | 4-7s | 系统/架构概念揭示、温暖产品故事 |
| `frame-light-leak-cinema` | Light Leak Cinema | 4-10s | 电影感开场、纪录片冷开场 |

### 素材帧类（stock-clip）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `video-clip-916` | Video Clip 9:16 | 由素材时长决定 | 9:16 竖屏素材视频播放、片段嵌入 |

> 本地 workspace 模板（`templates/` 目录下）使用 `<name>-<aspect>` 命名，由 `registry.py` 解析。html-video CLI 模板使用 `frame-` 前缀。在 content-graph 的 `templateRef` 中使用对应的模板 ID。

### 结尾类（intro-outro）

| 模板 ID | 名称 | 时长 | 适用场景 |
|---------|------|------|---------|
| `frame-logo-outro` | Logo Outro Frame | 3-10s | 视频结尾卡、品牌 outro、频道签退 |

> **模板选择提示**：使用 `hv.sh search-templates --intent "<意图>"` 搜索最匹配的模板。例如 `--intent "product launch"` 会推荐 `frame-liquid-bg-hero` 和 `frame-product-promo`。

## 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `MINIMAX_CODE_PLAN_KEY` | 推荐 | MiniMax TokenPlan 订阅 key（openclaw 扩展自动识别） |
| `SILICONFLOW_API_KEY` | fallback | SiliconFlow TTS 备选 |
| `HTML_VIDEO_CLI` | 可选 | html-video CLI 路径（默认自动查找） |
