---
name: viral-chaser
description: 视频追爆与 DNA 样本分析。产出结构、声画风格与制作指向的拆解报告。也可分析用户提供的本地视频。只处理视频，制作另交 content-producer。
metadata:
  openclaw:
    emoji: 🎯
    requires:
      bins:
      - node
      - ffmpeg
      - ffprobe
      - python3
---

## 🔑 前置：ASR 凭据（仅首次）

本技能的语音转写走公共 ASR 路由（`skills/_shared/asr.py`），凭据在哪家走哪家：

1. **火山录音文件极速版**（`VOLC_ASR_*`，优先）
2. **百炼业务空间**（`WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`）：`qwen-audio-3.1-asr-flash` → `qwen-audio-3.0-asr-flash`
3. **百炼 agent plan**（`AWK_API_KEY`）：`qwen-audio-3.0-asr-flash`

按序尝试已配置的供应商；业务空间内先尝试两个候选模型，均失败才继续 Agent Plan。设置 `BAILIAN_ASR_MODEL` 后百炼每个端点仅调用该模型。百炼 Flash 单次音频不超过5分钟；较长视频使用火山后端。

三组任一组在环境里即可运行；都缺失时分析器退出码 2 并提示配置。

# Viral Chaser（追爆分析 — 报告产出）

Use this skill when:
- 用户提供抖音 / 小红书 / 快手 / TikTok / X / 微博视频链接，或本地视频，希望拆解分析
- 需要分析爆款视频的结构和公式

**本技能仅产出追爆报告**，不生成脚本，不制作视频。如需据此生成视频，需另行委托 `content-producer` （spawn subagent）执行。

**采集路由：** 抖音、小红书、快手、TikTok、X、微博分别用 `douyin-hunter`、`xhs-hunter`、`kuaishou-hunter`、`tiktok-hunter`、`x-hunter`、`weibo-hunter`。其他平台暂不支持，需要使用用户已提供的本地视频，不在本技能恢复下载逻辑。analyzer 不依赖来源平台，只接受本地视频与可选独立音轨。

**视频限定：** 图文内容的分析不在本技能范围内。

---

## ⚙️ 执行方式（强制）

本技能涉及多步骤生产流程，你应该 self-spawn 一个 subagent 来执行，原因：subagent 独立上下文，不会因对话历史积累而降低输出质量。

你只负责跟进subagent的执行，避免它们长时间卡在某个步骤，必要时可以提供提示或调整执行策略。

---

## Workflow

### Step 1 — Create workspace

将工作目录建在来源平台的运营文件夹 `<platform>/ref/`（平台代号 douyin / xhs / kuaishou / tiktok / twitter / weibo）下：

```bash
mkdir -p "<platform>/ref/<slug>/references"
```

若调用方 workflow 指定了产出落点（如把参考素材收进在制作品目录 `<platform>/outputs/<work>/references/`），则按指定位置建工作目录，内部结构不变。

来源链接、hunter 返回的作品资料、下载的视频和音轨、分析产物保存在同一工作目录；`references/` 存放素材与 analyzer 产生的音频、关键帧。本地输入按调用方指定的工作目录归档，不猜测来源平台。

### Step 2 — 调用对应 hunter 获取资料与下载视频

先读取来源平台 hunter 的 SKILL.md，按其流程完成登录检查、链接解析、作品资料获取和视频下载。探活、会话失效、签名与平台风控均在 hunter 阶段处理；失败时停止本次采样，analyzer 不处理这些错误或恢复登录。

| 来源 | 采集技能 | 交给分析阶段的产物 |
|---|---|---|
| 抖音 | `douyin-hunter` | 本地视频、作品资料与完整来源链接 |
| 小红书 | `xhs-hunter` | 本地视频、作品资料与含 xsec_token 的真实链接 |
| 快手 | `kuaishou-hunter` | 本地视频与作品资料 |
| TikTok | `tiktok-hunter` | 本地视频与作品资料 |
| X/Twitter | `x-hunter` | 本地视频与推文资料 |
| 微博 | `weibo-hunter` | 本地视频与微博资料 |

抖音和小红书的独立采集命令示例：

```bash
douyin-hunter fetch --url '<视频链接>' --video-only --download-media --output-dir '<工作目录>/references'
xhs-hunter fetch '<视频链接>' --video-only --download-media --output-dir '<工作目录>/references'
```

这些 hunter 将视频保存为 `video.mp4`、资料保存为 `note.json`。以各自实际输出为准；保留原始资料，不让 agent 重写为 analyzer 的输入 schema。新增平台使用 `<hunter> fetch <视频链接> --video-only --download-media --output-dir <目录>`，视频文件名与扩展名以 media_paths 返回为准。

只分析本地视频时跳过 hunter 采集。图文不进入 analyzer。

### Step 3 — 运行 analyzer（转写与关键帧）

用 `viral-chaser` wrapper 调用 `scripts/analyzer.ts`。脚本只读本地媒体，内部完成音频提取、公共 ASR 转写与抽帧，不接收平台 URL、不读取平台登录态、不调用 hunter 或下载器。

```bash
viral-chaser --video '<工作目录>/references/video.mp4' --output-dir '<工作目录>/references'
```

若 hunter 提供独立音轨（与视频同步的独立音轨），用 `--audio '<本地音轨路径>'` 指定同一视频的同步音轨；不下载音轨 URL。`--no-frames` 跳过抽帧，只用于用户明确只需转写时。`--output-dir` 优先于已有 `OUTPUT_DIR` 环境变量，未指定则写入视频所在目录。

The script outputs a **JSON object to stdout**. Read it and proceed with analysis.

**Output JSON structure:**
```json
{
  "ok": true,
  "kind": "video",
  "metadata": {
    "durationSeconds": 36,
    "width": 1080,
    "height": 1920,
    "orientation": "vertical",
    "hasAudio": true
  },
  "transcript": {
    "text": "全文转录...",
    "segments": [{ "start": 0.0, "end": 5.2, "text": "开场文案" }],
    "estimated": false,
    "durationSeconds": 36,
    "truncated": false
  },
  "frames": ["<platform>/ref/<slug>/references/frames/frame_00_0s.jpg", "..."],
  "localPaths": {
    "video": "<platform>/ref/<slug>/references/video.mp4",
    "audio": "<platform>/ref/<slug>/references/analysis-audio.wav",
    "tmpDir": "<platform>/ref/<slug>/references"
  },
  "warnings": []
}
```

- `kind`: 仅 `video`；图文不下载、不分析，转对应平台专家 workflow。
- `metadata` 由本地 ffprobe 得到，只含时长、宽高、画幅和视频是否自带音轨。来源平台、作品 ID、标题、作者/简介、发布时间、话题和互动计数从 Step 2 的 hunter 资料读取；缺失写「接口未返回」，本地输入无资料时写「未提供」，不编造。小红书 PC 笔记资料不提供播放数。
- `frames`: 最多 12 张，覆盖开场（0s / 3s）、各口播段中点与全片比例点（25% / 50% / 63% / 75% / 90%）——**反转植入类作品的反转点通常在 55%-76%，只抽前几秒会完全错过**。
- `transcript.estimated=false` 表示使用公共 ASR 返回的真实时间戳；`true` 表示接口没有返回分段时按音频时长估算。报告据实际结果注明，不能将估算时间写为精确时间。
- 音频提取最多前 10 分钟；`transcript.truncated=true` / `TRANSCRIPT_PARTIAL` 表示转写未覆盖全片，必须写清转写范围。关键帧仍按完整视频时长采样，不能把未转写区间当作没有口播。
- `KEY_FRAMES_PARTIAL` 表示部分抽帧失败；报告记录视觉样本缺口，不能用旧帧或文字推测补齐。

**Exit codes:**
- `0` = Success
- `1` = 本地媒体、音轨、ASR 请求或分析错误，按 `error` / `message` 排查
- `2` = `ASR_NOT_CONFIGURED`，配置公共 ASR 凭据；与平台登录态无关

### Step 4 — Read key frames (if available)

For each path in `frames`, use the `Read` tool to load the image and analyze it visually.

```
Read: <platform>/ref/<slug>/references/frames/frame_00_0s.jpg
Read: <platform>/ref/<slug>/references/frames/frame_01_3s.jpg
...
```

---

## Analysis Framework

读完 hunter 资料、analyzer JSON 与全部关键帧后，产出**追爆报告**，保存到工作目录的 `raw_article.md`。报告既要能给人看，也要能直接喂 DNA 采样（见最后一节）。

### 1. 作品 meta 信息

| 项 | 内容 |
|----|------|
| 作品类型 | 视频（`kind: video`） |
| 时长 | xx s（`durationSeconds`） |
| 画幅 | 竖屏 9:16 / 横屏 16:9（`orientation` + `width`×`height`） |
| 发布时间 | hunter 的实际发布时间字段（接口未返回时注明） |
| 作者与简介 | hunter 的作者资料与简介（对标账号样本必记，缺失注明） |
| 话题标签 | hunter 返回的话题信息 |
| 互动数据 | hunter 的播放 / 点赞 / 评论 / 分享 / 收藏（逐项写；接口未返回的项注明） |
| 来源 | 原视频 URL + 完整内容 ID + 采集日期；本地输入则标注用户提供 |

### 2. 内容摘要

1–2 句：这条作品给观众的核心价值或核心情绪是什么。

### 3. 开头钩子分析（前 0–10 秒）

基于 `transcript.segments` 中 `start < 10` 的段：

- **钩子类型**：提问型 / 冲突型 / 反转型 / 数字型 / 悬念型 / 痛点型 / 利益型
- **具体文案**：逐字摘录开场句
- **声画是否同步**：画面、字幕、口播是否在同一秒传递同一个重点
- **效果评估**：这个钩子为什么留人（或为什么不留）

### 4. 结构拆解（按时间占比）

按功能把全片切段，**每段给时间区间与占全片百分比**：

| 段落 | 时间区间 | 占比 | 功能 | 核心内容 |
|------|---------|------|------|---------|
| 开场 | 0–Xs | xx% | 钩子/引入 | ... |
| 主体一 | X–Ys | xx% | 信息/剧情推进 | ... |
| 转折 | Y–Zs | xx% | 反转/揭示 | ... |
| 收尾 | Z–结束 | xx% | CTA/情绪收尾 | ... |

必须额外标注：

- **反转点位置**（若有）：占总时长的百分比，以及反转是靠什么衔接的（口播因果句 / 意象复用 / 身份彩蛋 / 戏中戏）。
- **植入或转化段占比**（若有）：产品/服务出现在哪一段、占比多少、是否集中。
- **主悬念**：一句话复述贯穿全片的悬念；说明它在哪一秒被回答。

### 5. 关键帧逐帧分析

对 `frames` 里每一张都用视觉模型读取，逐帧一行（不要只看首帧）：

| 帧 | 时间码 / 占比 | 画面内容 | 字幕或贴图文字 | 景别与构图 | 色调与质感 | 品牌/产品是否出现 | 可否作封面 |
|----|--------------|----------|---------------|-----------|-----------|------------------|-----------|
| frame_00 | 0s / 0% | ... | ...（逐字抄） | 近景/中景/远景、主体位置 | 冷暖、饱和、颗粒 | 是/否 | 是/否 |

`--no-frames` 或 frames 为空时注明：「（跳过视觉分析，请重新运行不带 --no-frames 参数）」。

### 6. 视觉与声音风格汇总

基于逐帧结果与转录：

- **色调风格**：暖/冷、高饱和/低饱和、黑白；是否有明显的两段式对比（如解说段冷暗、植入段明亮）
- **画面形态**：实拍 / 影视或开源片源 / 录屏 / 图文卡片 / AIGC / 混剪
- **字幕与贴图**：字体粗细、位置、背景框、箭头标注、重点字变色放大
- **声音形态**：原声口播 / TTS 旁白 / 纯画面 + 字幕；BGM 类型与主从关系；音效使用（如反转处 whoosh）
- **整体视觉标签**：3–5 个关键词

### 7. 内容形态判定与制作指向

判定这条作品属于哪种视频内容形态，并给出**制作指向**——只能写真实存在的资源名：

| 观测到的形态 | 制作指向 |
|-------------|----------|
| 影视解说 / 剧情解说 + 反转植入（「万万没想到」式） | Content Producer `expert-video` → Reversal Ad workflow |
| PPT / 幻灯或 B-roll 大画面 + 实拍/数字人口播小窗，或用户音频+B-roll | Content Producer `expert-video` → Deck Talk workflow |
| 人物全屏口播或其他自由镜头声画制作 | Content Producer `expert-video` → 不指定类型 workflow，走通用制作流程 |
| 一句文稿转视觉隐喻的纸拼贴动画 | Content Producer `expert-video` → Collage B-roll workflow |
| 纯 AIGC 动画 / 剧情短片 / 蒙太奇（需从零出脚本分镜） | Content Producer `expert-video` → **不指定类型 workflow**（CP 按其通用制作流程做，据创意自定叙事 / 动效 / 蒙太奇手法） |
| 已有素材简单拼接、加旁白、烧字幕 | main `video-edit` |
| 已有真人口播素材去口气词、剪高光 | main `talking-head-cut` |
| 产品操作录屏 | main `ui-demo` |

判定要写依据：口播占比、素材来源、画面是否连续叙事、有无产品段。

### 8. 内容创意

- **创意内核**：一句话说清这条作品的创意是什么
- **展开逻辑**：悬念 / 反转 / 递进 / 对比 / 清单 / 实测
- **记忆点**：观众会记住或复述的那一个点
- **可复用套路**：换成别的主题还能怎么用（这是 DNA 的 `content-idea` 维度要的）

### 9. 爆款元素评估

每项评 **强 / 中 / 弱** + 一句说明：

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

### 10. 可借鉴点与目标受众

- **可借鉴点**：3–5 条，每条一句、可直接执行。
- **目标受众**：一句话人群画像。
- **ASR 校正注记**：转写与画面字幕不一致时（谐音、专有名词、案名），逐条列出原文与校正依据（哪一帧的字幕）。

### 11. DNA 样本归档（喂 style-profiler 用）

这条作品要进 DNA 时，把报告转成一份**样本文字稿**，落 `<platform>/ref/<dna-id>/transcripts/<sample-id>.md`，格式如下（`<platform>-style-profiler report --input` 直接吃这个文件：首个一级标题即作品标题）：

```markdown
# 样本文字稿：<作品标题>（sample-id: <sample-id>）

> 来源：<对标账号名 + 账号 ID / 用户提供>
> 原视频 URL：<url>（内容 ID <id>）
> 时长：xxs ｜ 画幅：竖屏 9:16 ｜ 点赞 x ｜ 评论 x ｜ 播放量：<数值或「接口未返回」>
> 发布时间：<publishTime 或「未返回」> ｜ 抓取日期：YYYY-MM-DD ｜ 拆解报告：<platform>/ref/<slug>/raw_article.md
> ASR 说明：公共 ASR 路由；时间戳为<真实/估算>（estimated=<实际值>），转写覆盖<实际范围>
> ⚠️ ASR 谐音校正：<逐条列出，注明依据的画面字幕帧；无则写「无」>
> 转录约定：逐字引语为原话引用（含时间戳）；标注 [剧情概括] 的段为报告中段转述，非逐字。

## 口播全文（含时间戳）

- 0.04–5.32s：<逐字>
- 5.36–8.84s：<逐字>
- 8.9–14.3s：[剧情概括] <转述>

## 结构标注（取自拆解报告）

- 0–24.6s（≈71%）：<段功能与内容>
- 24.7–25.7s（≈3%）：<反转过渡>
- 25.7–35.3s（≈26.5%）：<植入段>
```

- 逐字引语与转述必须分开标注，不得把概括写成原话。
- 拿不到的字段写「接口未返回」或「未观测」，不编造。

## Notes

- 原始平台资料由 hunter 保存；analyzer 仅生成本地媒体分析数据，不增加新平台适配器。
- 快手/TikTok/X/微博沿用“hunter 采集 → 本地 analyzer → 拆解报告”的流程，登录检查、短链解析与下载限制以各 hunter 文档为准。
- 只有转写与抽帧完成并核对结果后才写分析结论；hunter 失败不运行 analyzer，本地分析失败不重新采集或恢复平台登录。
