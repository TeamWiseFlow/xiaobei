---
name: aigc-video-gen
description: AIGC 视频片段生成（声画同出），支持文生、图生和参考生视频。audio 子命令使用百炼 qwen-audio-3.1-tts-next 生成背景音、音效、环境音及带背景/环境的人声；纯人声用 awk-tts，纯 BGM 用 bgm-library。
metadata:
  openclaw:
    emoji: 🎞️
    requires:
      bins:
        - python3
        - ffmpeg
        - ffprobe
---
# AIGC Video Gen — 百炼 Wan3.0 / HappyHorse、火山 Seedance、MiniMax Hailuo

直连阿里云百炼业务空间 / Token Plan Wan3.0、火山方舟 Seedance 或 MiniMax Hailuo 端点生成视频片段（声画同出）。同模型声画同步出，无需单独 TTS。百炼业务空间 `qwen-audio-3.1-tts-next` 提供独立声音场景生成能力（`audio` 子命令），一次输出人声、背景音、音效和环境音。

> 本 skill 是公共能力，供 main agent（`video-edit` 素材补充环节的"为组装目的 AIGC 补充"）和 content-producer 共同调用。

## 平台与模型

| 平台 | 环境变量 | 视频模型 | 音频模型 |
|------|---------|---------|---------|
| 百炼业务空间 | `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`） | `wan3.0-video-prime` → `wan3.0-video` | `qwen-audio-3.1-tts-next` |
| 百炼 Token Plan | `AWK_API_KEY` | `wan3.0-video` | — |
| 火山引擎方舟 | `VOLC_SEEDANCE_API_KEY` | `doubao-seedance-2-5-260628`、`doubao-seedance-2-0-fast-260128` | — |
| MiniMax Hailuo | `MINIMAX_API_KEY` | `MiniMax-H3` | — |

- 三个平台的上述视频模型**均支持声画同出**（t2v / i2v / r2v 三种模式）。
- **视频平台自动判断写在 `aigc-video-gen.sh` 里**：argv 含 `--platform <value>` 时转发到对应供应商脚本（剔除 `--platform` 参数）；无 `--platform` 时按 env 自动判——有 `MINIMAX_API_KEY` 走 MiniMax，否则有 `VOLC_SEEDANCE_API_KEY` 走火山，否则有 `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`/`WORKSPACE_ID` 走百炼，否则有 `AWK_API_KEY` 走百炼（agent plan 兜底，排最后：它是主模型 key，只在无显式视频平台凭据时触发），皆无则输出提示让 Agent 改用 `pexels-footage` / `pixabay-footage`（退出码 2）。
- **入口脚本**（共享逻辑在 `scripts/aigc_common.py`）：
  - `scripts/gen_minimax.py` — MiniMax Hailuo 视频生成（含 `--ref-audio` 多模态参考）
  - `scripts/gen_volc.py` — 火山引擎 Seedance 视频生成
  - `scripts/gen_dashscope.py` — 百炼业务空间 / Token Plan Wan3.0 视频
  - `scripts/gen_audio.py` — 百炼业务空间声音场景生成与已有结果恢复
  - `scripts/audio_media.py` — 完整解码计时与受限 WAV 占位头修复
- **音频固定业务空间**：`audio` 直接调用百炼业务空间，不受 MiniMax/火山视频凭据影响；可显式传 `--platform dashscope`，其他平台直接报错。缺完整业务空间凭据退出码2，不回退 Token Plan、legacy 或其他供应商。

## 声音能力选用

| 需求 | 使用技能 |
|------|---------|
| 背景音、音效、环境音，或带背景/环境的人声（如口播 + 激昂配乐） | 优先 `aigc-video-gen audio`，一次生成完整音轨 |
| 单纯的人声旁白、干声 TTS、音色复刻/设计 | `awk-tts` |
| 单纯的 BGM / 背景音乐 | `bgm-library` 搜索、试听、下载并保留署名 |

先按声音需求选入口。完整混合音轨直接交后期与画面合成，不默认再分别生成 TTS/BGM，也不叠加第二条配乐。甲方已锁定的原音轨继续保留，不为使用新模型重配。

### ⚠️ MINIMAX_API_KEY 缺失处理

MiniMax Hailuo-H3 视频生成要求环境变量中提供 `MINIMAX_API_KEY`。**缺 `MINIMAX_API_KEY` 时需实时提醒用户提供 key**，然后交 **IT engineer** 配置：

```
[error] MINIMAX_API_KEY 未设置 —— 请实时提醒用户提供 key,然后交 IT engineer 配置
```

Agent 读到此报错后的处理流程：
1. 实时向用户说明需要 MiniMax API key 才能使用 Hailuo-H3 视频生成能力
2. 请用户提供 key
3. 把 key 交给 IT engineer 配置到环境变量 `MINIMAX_API_KEY`
4. 配置完成后重试

### 百炼模型选择规则

先按凭据确定端点模式，再选择模型。业务空间默认使用统一模型 `wan3.0-video-prime`，无需按任务拼接模型名称；Token Plan 使用 `wan3.0-video`，legacy 端点保留原有按模式候选链。

| 模式 | 业务空间首选模型 | Token Plan 首选模型 | 输入 |
|------|----------------|-------------------|------|
| **t2v** | `wan3.0-video-prime` | `wan3.0-video` | 仅提示词 |
| **i2v** | `wan3.0-video-prime` | `wan3.0-video` | `--image` 首帧；Wan3.0 还可配 `--last-frame` 尾帧 |
| **r2v** | `wan3.0-video-prime` | `wan3.0-video` | Wan3.0 图片/视频/音频参考 |

- 业务空间候选链：`wan3.0-video-prime` → `wan3.0-video`，所有模式共用；不回退 HappyHorse。
- Token Plan 默认仅 `wan3.0-video`，不尝试未登记的 prime；显式指定 HappyHorse 时仍校验其旧能力。legacy 候选链：`happyhorse-1.1-{mode}` → `happyhorse-1.0-{mode}` → `wan2.7-{mode}`。
- `gen_dashscope.py` 自动沿当前端点的候选链回退，不切换端点或凭据。
- **`--model <id>` 可显式覆盖**（关闭候选链 fallback，只用该模型）；非必要不覆盖。
- 显式模型也执行素材与参数校验；Wan3.0 必须使用业务空间凭据。

### Wan3.0 参数与素材

按[Wan3.0 使用指南](https://help.aliyun.com/zh/model-studio/wan3-video-generation-guide)和[API 参考](https://help.aliyun.com/zh/model-studio/wan3-video-generation-api-reference)准备输入：

- 输出支持 `480P` / `720P` / `1080P`，时长为2–30秒或 `-1`（智能时长）。有参考视频时，输入视频总时长与输出时长之和须≤30秒。
- 首帧/首尾帧与参考素材互斥，尾帧必须配首帧。脚本对首帧/首尾帧自动发送 `ratio=adaptive`；提前准备目标比例的首帧。
- `--ref-image` 最多10张，`--ref-video` / `--ref-audio` 各最多5段；可重复传入，可组合，也支持仅音频参考。视频/音频各自总时长≤15秒。
- 图片支持公网 URL、本地路径、data URI 和 OSS 临时 URL；单张≤20MB、单边240–8000px、宽高比≤8:1，格式 JPEG/PNG/BMP/WEBP，PNG 不含透明通道。视频/音频使用公网 URL 或平台上传得到的 OSS 临时 URL。
- 视频参考为 MP4/MOV，单段1–15秒、≥16fps、≤100MB；音频参考为 WAV/MP3，单段1–15秒、≤15MB。
- 默认输出声音；`--no-audio` 发送 `audio=false`。传媒体时可省略 prompt；复杂参考任务应在提示词中按顺序引用“图1”“视频1”“音频1”。
- 视频编辑用 `--ref-video`，prompt 明确编辑意图，并传 `--ratio adaptive --duration -1`；延长视频时 prompt 明确延长方向，并用 `--ratio adaptive`。

### 百炼端点双模式规则

| 模式 | 触发条件 | 端点 |
|------|---------|------|
| 业务空间（优先） | `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY` | `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1` |
| agent plan | 无业务空间凭据时用 `AWK_API_KEY` | `https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1` |
| legacy 兼容 | 都没有但 `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY` 在 | `https://dashscope.aliyuncs.com/api/v1`（老部署） |

> `WORKSPACE_ID` 配了但业务空间 key 缺失时打 warning 落 agent plan。端点模式对火山（doubao-seedance 系列）和 MiniMax 无效。

### 火山候选链

- 仅支持 **Seedance 2.5 → Seedance 2.0 fast**；指定 `--model` 也只能选这两个模型 ID。
- 分辨率使用 `480P` / `720P`（默认）；2.5 时长 4–30 秒，fast 为 4–15 秒，均可传 `-1` 自动时长。超过 15 秒或参考素材超过 fast 上限时，候选链只保留 2.5，不缩短时长或丢弃素材来回退。
- `--ref-image` / `--ref-video` / `--ref-audio` 可重复传入；2.5 上限分别为 30/10/10，fast 为 9/3/3；仅音频输入只走 2.5。图片支持 URL、本地文件、data URI、`asset://`；音视频支持公网 URL 或 `asset://`。
- 首帧/首尾帧和全模态参考互斥；尾帧必须配首帧。2.5 首帧/首尾帧自动传 `ratio=adaptive`，输出跟随首帧比例，应提前准备目标比例的首帧图。
- 2.5 视频编辑使用 `--ref-video`，并显式设置 `--ratio adaptive --duration -1`；视频延长使用 `--ratio adaptive`。在 prompt 明确说明编辑/延长意图，模型据此识别任务，不要把普通参考生成与编辑混淆。
- 火山不接受直接上传含真人人脸的参考图/视频；需使用平台支持的模型原始产物、预置虚拟人像或已授权素材，见[官方说明](https://ark.volcengine.com/region:cn-beijing/docs/ark/seedance-2-0#5c67c9a1)。
- 模型与任务差异参见[模型发布公告](https://docs.volcengine.com/docs/ark/model-release-announcement?lang=zh)、[2.5 提示词与任务指南](https://docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide?lang=zh)。
- ⚠️ **火山视频生成只认 `VOLC_SEEDANCE_API_KEY`，不回退 `ARK_API_KEY`**：`ARK_API_KEY` 是火山主模型（doubao 对话）的 key。将原 `AWK_GEN_KEY` 的配置名改为 `VOLC_SEEDANCE_API_KEY`；旧名不再读取，也不参与自动选路。

### MiniMax Hailuo 候选链

- 候选链：`MiniMax-H3`（主力，H3 模型，官方文档示例唯一模型）。
- MiniMax-H3 支持 t2v / i2v / r2v 三种模式，模式映射与百炼/火山对齐。
- 鉴权：HTTP header `Authorization: Bearer ${MINIMAX_API_KEY}`。
- MiniMax 视频生成走 **V2 异步任务模型**：`POST /v2/video_generation` 创建任务 → `GET /v2/query/video_generation/{task_id}` 轮询 `task.status` → 成功时 `task.content.url` 即成片下载地址（无需 file_id / files/retrieve 换链）。
- 请求体用 `content[]` 多模态数组：每个元素 `type`（text/image_url/video_url/audio_url）+ `role`（first_frame/last_frame/reference_image/reference_video/reference_audio）。

#### H3 多模态参考约束（官方文档）

`content[]` 支持的输入组合（对应不同生成场景）：

| 场景 | content 组合 |
|------|-------------|
| 文生视频 | 仅一个 `text` |
| 图生视频-首帧 | `text` + 1 `image_url`（`role=first_frame` 或不填） |
| 图生视频-尾帧 | `text` + 1 `image_url`（`role=last_frame`） |
| 图生视频-首尾帧 | `text` + 2 `image_url`（`role` 分别 `first_frame`/`last_frame`） |
| 多模态参考生视频 | `text` + `reference_image`/`reference_video`/`reference_audio` 组合 |

**互斥约束**：图生视频（`first_frame`/`last_frame`）与多模态参考（`reference_*`）不可混用——`content` 中出现 `reference_*` 任一 role，就不能再有 `first_frame`/`last_frame`，反之亦然。

**仅音频不可**：多模态参考不可仅输入 `reference_audio`，须至少包含 1 个 `reference_video` 或 `reference_image`。

脚本侧 `gen_minimax.py` 的 `cmd_video` 入口已校验上述两条约束，违反即 `die`：
- `--image`/`--last-frame` 与 `--ref-image`/`--ref-video`/`--ref-audio` 同时出现 → 互斥报错
- 仅 `--ref-audio` 无 `--ref-image`/`--ref-video` → "不可仅输入音频"报错

### 模式与时长上限

| 模式 | 触发条件 | 百炼 Wan3.0（业务空间/Token Plan） | 百炼显式 HappyHorse | 火山 Seedance | MiniMax Hailuo |
|------|---------|-------------------|----------------|-------------|---------------|
| t2v | 无媒体输入 | 2–30s 或 -1 | 3–15s | 2.5：4–30s；fast：4–15s | 4–15s |
| i2v | `--image` 首帧 | 2–30s 或 -1，支持尾帧 | 3–15s，仅首帧 | 2.5：4–30s；fast：4–15s | 4–15s |
| r2v | 参考素材 | 2–30s 或 -1，视频输入+输出≤30s | 3–15s，单张参考图 | 2.5：4–30s；fast：4–15s | 4–15s |

**脚本规划规则**（调用方约定，本脚本不强制）：
- 常规工作流每个片段时长 **不得超过 15 秒**；明确使用 Wan3.0 或 Seedance 2.5 长镜头时可到30秒
- 超过所选模型上限的内容**必须在脚本中拆成多个片段**

### 转场片段规范（i2v 首尾帧插值）

用 i2v 生成两段素材之间的转场片段（如反转植入的「画面转场式」）时：

- **首帧 / 尾帧图**分别取自前后两段素材的关键帧；**选帧即锁定景别**——首帧景别偏松会导致整段转场弃用重生成，用与前后段匹配的景别帧做首帧。
- prompt 必须含**风格对齐要求**：对齐相邻素材的材质 / 光影 / 色调。AIGC 画风漂移是通病，靠「母题延续」弱化——用前后段共享的核心意象（如瞳孔→光晕→数据面板）做过渡主体，prompt 里写明。
- 转场片段**帧率由生成端决定，无 CLI 参数指定**；Wan3.0 输出30fps，其他模型按成片核验。与主素材帧率不一致时由拼接工具统一。
- 生成后先**抽帧自检**（确认首尾之间是真实渐变而非硬切、画风可接受），再进拼接；首版不满意时重生成优于硬修。

## Run

通过 PATH 调用 wrapper，无需拼接脚本路径。

### 视频生成（默认子命令 video，可省略）

```bash
# 平台/模型全自动（推荐）
aigc-video-gen \
  --prompt "画面从纯色空场开始，依次滑入时钟 → 人物与剪刀 → 胶片，最终定格。固定机位。音频：纸片嗒嗒声 + BGM。" \
  --duration 5 \
  --ratio 9:16 \
  --output output_videos/<topic>/generations/01.mp4

# 显式指定模型（关闭候选链 fallback）
aigc-video-gen --platform dashscope --model "wan3.0-video" --image first-frame.png --last-frame last-frame.png \
  --prompt "<声画同出描述>" --output output_videos/<topic>/generations/01.mp4

# r2v（用户提供参考图，人物故事）
aigc-video-gen --ref-image character_reference.jpg \
  --prompt "<声画同出描述>" --duration 8 --ratio 9:16 \
  --output output_videos/<topic>/generations/02.mp4

# Wan3.0 多模态参考（需业务空间凭据；无声输出可加 --no-audio）
aigc-video-gen --platform dashscope --model "wan3.0-video" \
  --ref-image character_reference.jpg --ref-image product_reference.jpg \
  --ref-audio "https://example.com/reference.mp3" \
  --prompt "图1的人物展示图2的产品，按音频1的节奏动作" --duration 10 \
  --output output_videos/<topic>/generations/03.mp4

# 显式指定 MiniMax 平台
aigc-video-gen --platform minimax --model "MiniMax-H3" \
  --prompt "<声画同出描述>" --output output_videos/<topic>/generations/03.mp4
```

### 声音场景生成（audio 子命令）

```bash
# 口播 + 激昂背景音乐，直接生成一条完整音轨
# 在提示词中明确台词、音色、表达方式和背景，不把场景指令当作台词。
aigc-video-gen audio \
  --prompt '短视频励志口播。年轻男声，坚定有力，吐字清晰，说：“从今天开始，把想法变成行动。”背景是激昂的管弦乐，音量低于人声，结尾自然收束。' \
  --output output_videos/<topic>/audio/narration.wav

# 环境音 / 音效，不需要人声
aigc-video-gen audio \
  --prompt '雨夜环境音：持续细雨拍打窗户，远处偶尔有闷雷；无说话声。' \
  --output output_videos/<topic>/audio/ambience.wav

# 长口播与声音场景写入 UTF-8 提示词文件；本地参考音频由脚本编码提交
aigc-video-gen audio --prompt-file output_videos/<topic>/audio/scene.txt \
  --ref-audio reference.wav --output output_videos/<topic>/audio/scene.mp3
```

- 使用 `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`，并开通 `qwen-audio-3.1-tts-next` 权限。沿用项目的 `WORKSPACE_ID` 名称。
- `--prompt` / `--prompt-file` 二选一，1–3000字符；中英文。写清任务、人物音色、台词、表达方式、背景/环境和声音先后变化；台词用引号标出，多人称呼保持一致。
- `--ref-audio` 最多3条，按传入顺序用 `@voice1`、`@voice2`、`@voice3` 引用。支持公网 URL 或本地 WAV/MP3/OGG Opus；本地文件由脚本检查每条≤30秒、≤10MB后编码为 Base64，URL 的格式/大小/时长由服务端验证。不得引用不存在的编号；不使用 TTS 系统音色或复刻音色 ID。
- 同步生成，使用 `input.text_prompt`，调用 `/services/audio/tts/SpeechSynthesizer`；不轮询视频任务。WAV/MP3 按输出后缀选择，默认48kHz双声道。完整音频 URL 有效期24小时，生成后立即下载并验证可完整解码。
- 不提供 `--duration`；播客最多240秒，其他场景最多120秒，超过限制先按叙事边界拆分。提示词里的“约28秒”和 `--rate` 都不保证精确时长；生成后按完整解码的实测时长核对画面与末句，不裁掉台词凑时长。用于剪辑与字幕对齐时优先输出 WAV。
- `--output` 必须是当前工作区的相对路径，如 `douyin/outputs/<work>/audio/scene.wav` 或 `output_videos/<topic>/audio/scene.wav`；不接受绝对路径或越出工作区的路径。提示词文件与参考音频属于输入，可用绝对路径。
- metadata 中的 `duration` 按完整解码后的采样数计算，`duration_source=decoded-samples`；`decoded_samples` 为每声道采样帧数，实际 `sample_rate` / `channels` 一并记录。`probe_duration` 仅为探测值，VBR MP3 可能按码率估算；`reported_duration` 是接口报告，`usage.duration` 是计费字段，均不替代实测值。恢复旧 metadata 时把原时长留在 `previous_duration`。
- WAV 检查 RIFF/chunk 边界。仅当命中支持的 PCM16 占位长度头、实际数据采样块完整、且数据时长与接口 `reported_duration` 相差不超过0.01秒时，才修正两个长度字段；保留 `.original.wav`、原文件哈希和 PCM 哈希，PCM 数据不变。普通截断、未知错误头、采样块不完整或时长无法互证均报错，不把短文件强行修成“成功”。
- 下载或验证失败在 metadata 保存诊断、生成链接和已有原始字节，不覆盖先前有效音频，不重新提交生成。只有 `status=downloaded` 才表示音频已通过下载/解码校验；此状态不代表台词和听感已经验收。metadata 含临时签名链接，排障交付时不要直接外发原件。
- 对照批准稿逐句检查重复、漏句、词句替换与末句完整，并实际试听语速、自然度和背景/人声比例。参考音频不保证逐字保真；ASR 差异须听校，不能仅凭转写认定模型改词，也不能据单个样本认定某个参考输入必然造成重复。
- 本模型不返回字级字幕或独立干声。带人声的完整音轨可交 `video-producer narration-align <project> --audio <实际音频文件名> --asr --force` 走公共 ASR 获取时间戳（文件名须与 WAV/MP3 产物一致；跳过同名旧 TTS 字幕并更新旧对齐结果），再逐句核对台词与尾音；不要按文案字数估时，也不要把混合音轨标成干声。成片审片按 `expert-video` 的完整声音场景规则执行。

#### 已有结果恢复（不重新生成）

```bash
# 优先复用已保留的原始下载；没有本地文件时才从同一生成链接重新下载
# 不需要模型凭据，不提交新的生成请求，不与 --output 或生成参数同用
aigc-video-gen audio --resume douyin/outputs/<work>/audio/scene.json

# 旧版失败记录没有原件路径时，显式指定此前取回的原始文件
# 原件只读；目标仍使用 metadata 中原有的工作区输出路径
aigc-video-gen audio --resume douyin/outputs/<work>/audio/scene.json \
  --source douyin/outputs/<work>/audio/scene-original.wav
```

对 `status=downloaded` 且已有本地音频的旧记录，`--resume` 只做本地解码、更新可靠时长，不访问生成接口或下载链接。失败时保留原件并报告具体原因；链接失效且没有本地原件时停止，不能自动新生成。

接口：[音频生成指南](https://docs.bailian.console.aliyun.com/zh/model-studio/audio-generation)、[API参考](https://docs.bailian.console.aliyun.com/zh/model-studio/audio-generation-api)。

## Parameters

### 视频生成参数（video 子命令，可省略 video）

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt` | 按模型 | 声画描述：旁白文案 + BGM + 音效；Wan3.0 传媒体时可省略 |
| `--duration` | 8 | 视频时长（秒），范围见模式表；Wan3.0 / Seedance 支持 -1 智能时长 |
| `--ratio` | `9:16` | 画面比例 |
| `--resolution` | `720P` | Wan3.0 `480P` / `720P` / `1080P`；HappyHorse `720P` / `1080P`；火山 `480P` / `720P` |
| `--image` | — | 首帧图像路径（i2v 模式） |
| `--last-frame` | — | 尾帧图像路径；Wan3.0 / Seedance 支持，HappyHorse 不支持 |
| `--prev-segment` | — | 上一段视频本地路径：脚本自动抽取其末帧作为本段首帧（人物故事首尾帧对齐，与 `--image` 互斥） |
| `--ref-image` | — | 用户参考图；Wan3.0 可重复传入最多10张，HappyHorse 仅一张 |
| `--ref-video` | — | Wan3.0 / Seedance / MiniMax 参考视频 URL；Wan3.0 可重复传入最多5段 |
| `--ref-audio` | — | Wan3.0 / Seedance / MiniMax 参考音频 URL；Wan3.0 可重复传入最多5段，Wan3.0 / Seedance 2.5 支持仅音频参考 |
| `--no-audio` | off | Wan3.0 / Seedance 关闭输出声音；默认为有声视频 |
| `--platform` | auto | 覆盖平台自动检测：`volcengine` / `dashscope` / `minimax`；不指定则按 env 自动判 |
| `--model` | auto | 显式指定模型 ID（关闭候选链 fallback）；不指定则按模式走首选 + 候选链 |
| `--output` | required | 输出 MP4 路径（必须在 `output_videos/` 或 `<platform>/outputs/` 下，供应商脚本内部 `ensure_safe_output` 校验） |

### 声音场景参数（audio 子命令）

| Flag | Default | Description |
|------|---------|-------------|
| `--platform` | `dashscope` | 仅百炼业务空间，可省略 |
| `--prompt` / `--prompt-file` | 生成时必填 | 文本或 UTF-8 文件，二选一，1–3000字符；不与恢复模式同用 |
| `--resume` | — | 已有 metadata JSON，只恢复下载/校验/修复与实测计时；不新生成 |
| `--source` | — | 恢复模式的已有原始音频文件，可选；不修改该输入文件 |
| `--ref-audio` | — | 公网 URL / 本地 WAV、MP3、OGG Opus，可重复最多3条 |
| `--format` | 输出后缀 | `wav` / `mp3`，须与输出后缀一致 |
| `--sample-rate` | `48000` | 8000 / 16000 / 24000 / 44100 / 48000 Hz |
| `--channels` | `2` | 1（单声道）或2（双声道） |
| `--volume` | `50` | 输出音量0–100 |
| `--rate` | `1.0` | 语速0.5–2.0 |
| `--seed` | 服务端默认 | 请求随机种子 |
| `--model` | `qwen-audio-3.1-tts-next` | 固定已支持模型，无候选链回退 |
| `--output` | 生成时必填 | 当前工作区相对 WAV/MP3 路径，须在 `output_videos/tmp/fragments/artifacts` 或 `<platform>/outputs/` 下；绝对路径不可用，恢复时沿用 metadata 路径 |

## Output

- **视频生成**：MP4 视频片段 + 同名 `.json` metadata；百炼记录实际使用模型、端点模式、请求比例与发送比例、声音开关
- **声音场景生成**：WAV/MP3 + 同名 `.json` metadata，记录模型、业务空间、提示词、参考来源、输出参数、音频链接/ID、生成与实测时长及 request_id；不保存参考音频 Base64
- 决策审计：workdir 下 `decisions.log`（append-only，记候选链 fallback）

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WORKSPACE_ID` + `MODELSTUDIO_API_KEY` / `DASHSCOPE_API_KEY` | 百炼业务空间视频与 Qwen Audio 声音场景 |
| `AWK_API_KEY` | 百炼 agent plan 视频 key（token-plan 端点；无业务空间凭据时启用），不用于独立音频生成 |
| `VOLC_SEEDANCE_API_KEY` | 火山 Seedance 视频生成专用的普通方舟 API key（非 Coding/Token Plan，不可与 `ARK_API_KEY` 混用） |
| `MINIMAX_API_KEY` | MiniMax API key（仅 Hailuo-H3 视频生成） |

## Fallback 路径

`MODELSTUDIO_API_KEY`/`DASHSCOPE_API_KEY`/`WORKSPACE_ID`/`AWK_API_KEY`、`VOLC_SEEDANCE_API_KEY`、`MINIMAX_API_KEY` 均未配 → 视频 wrapper 退出码 2，Agent 应改用 `pexels-footage` / `pixabay-footage` 走 Stock Footage 模式兜底。

音频缺少完整百炼业务空间凭据时退出码2，按需补齐凭据；不要自动改成纯 TTS、曲库 BGM 或视频素材来替代所需声音场景。
