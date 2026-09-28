---
name: viral-chaser
description: 用户转发/分享抖音、B站、小红书视频链接(v.douyin.com / b23.tv / xhslink.com / xhslink.cn),要求拆解分析时使用（俗称「追爆」）：下载视频、ASR 转写、全片关键帧抽取、结构化拆解，产出拆解分析报告（含视频 meta、逐帧画面分析、结构占比、内容形态与制作指向）。也是各平台 DNA 采样的取数主力：可按 DNA 样本格式归档转录稿。抖音图集（图文作品）只下载图片与文本，不做转写。仅产出报告，视频生产需另外委托 content-producer。
metadata:
  openclaw:
    emoji: 🎯
    requires:
      bins:
      - node
      - ffmpeg
---

## 🔑 前置：ASR 凭据（仅首次）

本技能的语音转写走公共 ASR 路由（`crews/main/skills/_shared/asr.py`），凭据在哪家走哪家：

1. **火山录音文件极速版**（`VOLC_ASR_*`，优先）——需单独开通语音模型，见下
2. **百炼业务空间**（`WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`）
3. **百炼 agent plan**（`AWK_API_KEY`）

三组任一组在环境里即可运行；都缺失时分析器退出码 2 并提示配置。

### 火山开通指引（选火山路线时）

火山引擎豆包语音 · 录音文件极速版（资源 ID `volc.bigasr.auc_turbo`）。即便账号已订购火山 Code Plan，语音模型仍需**单独开通**，否则调用会返回鉴权/权限错误。

**判断是否已开通**：直接跑 Step 3 分析器，若 ASR 报错含 `status=45xxxxx` 或权限相关码，说明未开通，按下面流程开通一次即可。

**开通流程**（未开通时，根据下面提示并引导用户在火山引擎控制台操作一次）：

1. 登录火山引擎控制台，左侧控制面板进入 **「开通管理」**
2. 选择 **「语音模型」** 选项卡
3. 找到 **「Doubao-录音文件识别2.0」** 这一项，点击它的 **「立即使用」**
4. 在跳转页面的「服务详情」里，选择 **「极速版」** 标签卡（对应实例名称 `Speech_Recognition_Seed_AUC2000000854311547266`，资源 ID `volc.bigasr.auc_turbo`），点击 **「试用」**（赠送 20 小时，可先用，后续再点开通付费）
5. 在该极速版页面可同时获得三项凭据：**APP ID**（数字）、**Access Token**、**Secret Key**。把 **APP ID + Access Token** 提供给小贝（旧控制台双头鉴权，对应 `VOLC_ASR_APP_ID` + `VOLC_ASR_ACCESS_KEY`）；**Secret Key 不需要给**（旧控制台账号用不上，填进 `X-Api-App-Key` 反而会报 `45000010 appid mismatch`）。由小贝写入实例环境变量。

**环境变量**（开通后由小贝配置，用户无需手动设置）：

| 变量 | 说明 |
|------|------|
| `VOLC_ASR_APP_ID` | 旧控制台**数字 APP ID**（如 `1216386473`），用于 `X-Api-App-Key`。旧控制台双头鉴权必需 |
| `VOLC_ASR_ACCESS_KEY` | 旧控制台 Access Token，用于 `X-Api-Access-Key`。与 `VOLC_ASR_APP_ID` 成对使用 |
| `VOLC_ASR_APP_KEY` | 新控制台 APP Key，用于 `X-Api-Key` 单头鉴权。仅新控制台账号需要；旧控制台账号不要把 Secret Key 填到这里（会报 `45000010 appid mismatch`） |
| `VOLC_ASR_RESOURCE_ID` | 资源 ID，默认 `volc.bigasr.auc_turbo`，一般无需改 |

> 鉴权二选一（脚本优先旧控制台双头）：同时给出 `VOLC_ASR_APP_ID`+`VOLC_ASR_ACCESS_KEY` → 旧控制台双头；否则用 `VOLC_ASR_APP_KEY` → 新控制台单头。**旧控制台 `X-Api-App-Key` 要的是数字 APP ID，不是 Secret Key。**

> **写入流程**：用户把 `VOLC_ASR_APP_ID` / `VOLC_ASR_ACCESS_KEY`（或新控制台的 `VOLC_ASR_APP_KEY`）交给小贝后，**小贝应 spawn 一个 `IT engineer` 作为 subagent** 去把这两个变量添加到实例环境变量中——IT engineer 掌握如何在本机环境变量 / 服务配置里安全添加此类密钥的规范。小贝本人不要直接写环境变量文件。

> **关于接口选型**：火山 ASR 分录音文件标准版 2.0（`volc.seedasr.auc`，单价最低，但只接受音频公网 URL，需自备 TOS 对象存储）、极速版（本技能采用，支持本地文件 base64 直传、一次返回）、闲时版（24h 内返回，不适合交互流程）、流式（实时上屏用）。viral-chaser 输入是本地 audio.wav，极速版免托管、原生返回时间戳，综合最合适。若后续为降本要切标准版 2.0，需额外引入 TOS 上传环节。

# Viral Chaser（追爆分析 — 报告产出）

Use this skill when:
- 用户提供抖音 / B 站 / 小红书视频链接，希望分析并制作同类视频
- 需要分析爆款视频的结构和公式

**本技能仅产出追爆报告**，不生成脚本，不制作视频。如需据此生成视频，需另行委托 `content-producer` （spawn subagent）执行。

**Supported platforms:** 抖音（Douyin — 视频作品 + 图集图文作品）、B 站（Bilibili）、小红书（XHS — 仅视频笔记, 如果是图文的话则转向执行 `xhs-hunter fetch`。）

**Not supported:** 微信视频号、TikTok

---

## ⚙️ 执行方式（强制）

本技能涉及多步骤生产流程，你应该 self-spawn 一个 subagent 来执行，原因：subagent 独立上下文，不会因对话历史积累而降低输出质量。

你只负责跟进subagent的执行，避免它们长时间卡在某个步骤，必要时可以提供提示或调整执行策略。

---

## Workflow

### Step 1 — Create workspace

Before anything else, create the working directory for this video under the source platform's 平台运营文件夹 `<platform>/ref/`（`<platform>` 取视频来源平台代号：douyin / bilibili / xhs）:

```bash
PLATFORM="douyin"  # 视频来源平台代号：douyin / bilibili / xhs
VIDEO_SLUG="<platform>-<contentId>"  # e.g. douyin-7389abc or bilibili-BV1xx
mkdir -p "${PLATFORM}/ref/${VIDEO_SLUG}/references"
```

若调用方 workflow 指定了产出落点（如把参考素材收进在制作品目录 `<platform>/outputs/<work>/references/`），则按指定位置建工作目录，内部结构不变。

All downloaded files, analysis results, and generated reports will be saved under this directory. The `references/` subdirectory holds the raw assets (video, audio, key frames) downloaded by the analyzer script.

### Step 2 — Run the analyzer（内置探活 + 下载 + 转写 + 关键帧）

一条命令闭环：取数、下载、ASR、抽帧。抖音的探活已合并进脚本；小红书由 `xhs-hunter` 管理 PC 会话并下载视频，无需另外拼接取数或下载命令。

```bash
viral-chaser <url> [--no-frames]
```

- `<url>`: Full or short-link URL of the video（支持短链，如 `xhslink.com/o/xxx`、`v.douyin.com/xxx`、`b23.tv/xxx`，脚本内部跟随重定向解析）
- `--no-frames`: Skip key frame extraction (faster, audio-only analysis)
- `OUTPUT_DIR`（环境变量）：落盘目录，必须指向 Step 1 建的 `references/` 子目录

> **⚠️ exec allowlist 注意**：`OUTPUT_DIR=... viral-chaser ...` 内联 env 前缀会触发 allowlist miss。通过 exec 工具调用时，把 `OUTPUT_DIR` 放到 exec 的 **`env` 字段**里传，不要写成内联前缀；同理避免 `mkdir ... ; echo` 这类分号复合命令。脚本本身已正确读取 `OUTPUT_DIR` 落盘，问题只在调用规范。

**登录态**：douyin 抓取前通过 `_shared/check-session.ts` 探活；bilibili 公开视频免探活。小红书复用 `xhs-hunter` 的 PC 会话，签名由 OFB Relay 提供；缺会话时按 `xhs-hunter` 的扫码登录流程处理。

The script outputs a **JSON object to stdout**. Read it and proceed with analysis.

**Output JSON structure:**
```json
{
  "ok": true,
  "platform": "douyin",
  "kind": "video",
  "metadata": {
    "contentId": "...",
    "title": "...",
    "desc": "...",
    "author": "...",
    "authorSignature": "账号简介（对标账号样本的 account-bio 维度用）",
    "authorUid": "...",
    "durationSeconds": 36,
    "width": 1080,
    "height": 1920,
    "orientation": "vertical",
    "ratio": "vertical",
    "publishTime": "2026-09-04T10:12:00.000Z",
    "hashtags": ["话题1", "话题2"],
    "coverUrl": "...",
    "stats": { "playCount": 0, "likeCount": 12, "commentCount": 0, "shareCount": 0, "collectCount": 0 }
  },
  "transcript": {
    "text": "全文转录...",
    "segments": [{ "start": 0.0, "end": 5.2, "text": "开场文案" }],
    "estimated": false
  },
  "frames": ["<platform>/ref/<slug>/references/frames/frame_00_0s.jpg", "..."],
  "localPaths": {
    "video": "<platform>/ref/<slug>/references/video.mp4",
    "audio": "<platform>/ref/<slug>/references/audio.wav",
    "tmpDir": "<platform>/ref/<slug>/references"
  }
}
```

- `kind`: `video`（正常视频作品）或 `note`（抖音图集图文作品）。`note` 时 `transcript` 为 `null`、`frames` 为空，另给 `images: [".../image_00.jpg", ...]`（最多 20 张）与 `metadata.imageCount`；图文样本的视觉证据就是这些图片。
- `metadata.orientation`: 由 width/height 推出的 `vertical` / `horizontal` / `square`；平台拿不到宽高时为空串，必须自己 `ffprobe` 本地成片补齐，不得猜。
- 各字段平台支持度不同：抖音给全套；小红书从 `xhs-hunter` 取得标题、正文、作者、发布时间、话题与互动计数，时长和宽高从本地视频读取，PC 笔记详情不提供播放数；B 站给时长与三项互动。缺失一律在报告里写「接口未返回」，不编造。
- `frames`: 最多 12 张，覆盖开场（0s / 3s）、各口播段中点与全片比例点（25% / 50% / 63% / 75% / 90%）——**反转植入类作品的反转点通常在 55%-76%，只抽前几秒会完全错过**。

- `transcript.estimated`: `false` 表示 `segments` 是火山 ASR 返回的**真实时间戳**（utterance 级，毫秒精度转秒）；`true` 仅在接口异常未返回 utterances 时出现，此时按句切分全文并按字数比例在音频时长上估算分段，时间区间为近似值。正常情况下始终为 `false`。

**Exit codes:**
- `0` = Success
- `1` = Error（URL invalid / download failed），或 `SIGN_UNAVAILABLE`（签名缺 OFB_KEY，重登救不了，交 IT engineer 配凭证）
- `3` = `SECURITY_BLOCK`（小红书返回安全限制）— 停止本轮该平台采样，不立即重跑或重登
- `2` = `SESSION_EXPIRED`（会话缺失或失效）— 小红书走 `xhs-hunter login`；抖音/B 站按对应登录流程处理

### Step 3 — Read key frames (if available)

For each path in `frames`, use the `Read` tool to load the image and analyze it visually.

```
Read: <platform>/ref/<slug>/references/frames/frame_00_0s.jpg
Read: <platform>/ref/<slug>/references/frames/frame_01_3s.jpg
...
```

---

## Analysis Framework

读完 JSON 与全部关键帧后，产出**追爆报告**，保存到 `<platform>/ref/<slug>/raw_article.md`。报告既要能给人看，也要能直接喂 DNA 采样（见最后一节）。

### 1. 作品 meta 信息

| 项 | 内容 |
|----|------|
| 作品类型 | 视频 / 图文（`kind`） |
| 时长 | xx s（`durationSeconds`） |
| 画幅 | 竖屏 9:16 / 横屏 16:9（`orientation` + `width`×`height`） |
| 发布时间 | `publishTime`（接口未返回时写「未返回」） |
| 作者与简介 | `author` + `authorSignature`（对标账号样本必记） |
| 话题标签 | `hashtags` |
| 互动数据 | 播放 / 点赞 / 评论 / 分享 / 收藏（逐项写；接口未返回的项注明） |
| 来源 | 原视频 URL + 内容 ID + 抓取日期 |

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
| 图文笔记 | main 直接生产（图文不走 CP） |

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
> ASR 说明：火山引擎极速版，真实时间戳（estimated=false）
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

- 图文作品（`kind: "note"`）没有口播全文：把正文原样抄进「## 正文全文」，图片路径列在「## 图组」下，其余元信息与结构标注照写。
- 逐字引语与转述必须分开标注，不得把概括写成原话。
- 拿不到的字段写「接口未返回」或「未观测」，不编造。

## Notes

- **Workspace files** are stored in `<platform>/ref/<slug>/` — all downloaded assets and analysis reports are kept together. The `references/` subdirectory contains raw assets from the analyzer.
- **Bilibili DASH format**: if `mediaFormat` is `DASH`, the video and audio streams are separate. The downloaded `video.mp4` contains the video stream only; audio is in `audio.wav` after extraction. This is transparent to the analysis workflow.
- **XHS video notes only**: 小红书图文笔记（image-only）不含视频，viral-chaser 会报错并提示。只有视频笔记（type=video）才能下载和分析。
- **XHS 取数与下载走 `xhs-hunter`**：传完整笔记链接（短链或含 `xsec_token` 的详情链接），脚本调用 `xhs-hunter fetch --output-dir ... --download-media`，直接使用其 `video.mp4`，再执行转写与抽帧。不可访问或 token 不匹配时，从站内搜索结果重新获取该笔记链接；不要自行请求 HTML 或下载视频 URL。
- **ASR segments**: 语音转写使用火山引擎豆包语音·录音文件极速版（`volc.bigasr.auc_turbo`），原生返回 utterance 级真实时间戳（`start_time`/`end_time`，毫秒），脚本转成秒后填入 `transcript.segments`，`estimated=false`。仅在接口异常未返回 utterances 时，才按句切分全文并按字数比例在音频时长上估算分段（`estimated=true`）作为兜底。开通/鉴权见文首「前置：开通火山语音模型」。
- **Exit code 2 — cookie expired:** 抖音/B站按 `login-manager` 重登；小红书运行 `xhs-hunter login` 扫码并在确认后执行 `xhs-hunter login-confirm`。Do not retry more than once.
