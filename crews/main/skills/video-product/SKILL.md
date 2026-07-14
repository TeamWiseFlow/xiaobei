---
name: video-product
description: 一站式短视频制作。支持文章链接、追爆报告、文字主题等多种输入，用 gen.py 直连火山 Seedance / 阿里云百炼 Wan2.7-HappyHorse 端点生成视频素材（声画同出），FFmpeg 组装成片。
metadata:
  openclaw:
    emoji: "🎥"
    requires:
      bins:
      - python3
      - ffmpeg
      - ffprobe
---

# video-product — 一站式短视频制作

Use this skill when:
- 需要从文章/追爆报告/文字主题生成完整短视频
- 用户指定主题和已有素材，生成短视频
- viral-chaser 追爆分析后需要产出视频

**本技能支持多种输入来源**，统一走短视频制作流程。

---

## 输入来源与预处理

### 来源 1：文章链接

- 微信公众号链接（`https://mp.weixin.qq.com/` 开头）→ 使用 `wx-mp-hunter` 技能获取标题和正文
- 其他网页链接 → 使用 `web-fetch` 或 `browser` 工具获取标题和正文
- 获取后将文章标题转为英文作为 `topic-en-slug`，正文存入 `raw_article.md`

### 来源 2：追爆报告（viral-chaser 后续）

- `topic-en-slug` 和编排目录由 viral-chaser 已创建，直接使用
- 读取 `追爆报告.md`(也是存储于`raw_article.md`)，按报告中的内容结构、爆款元素和可借鉴点生成脚本
- **不套用三段式结构**，而是按照追爆报告拆解的原视频结构来组织脚本

### 来源 3：文字主题

- 用户直接给出主题或写作思路 → 基于主题撰写脚本
- 可能附带参考资料（一段话、参考文章、图、视频等）

### 来源 4：本地文件

- 读取文件内容，提炼标题作为 `topic-en-slug`

> 如果输入过于简略或无法获取有效内容，与用户沟通调整，或建议先产出文章再转视频。

---

## ⚙️ 执行方式（强制）

本技能涉及多步骤生产流程，你应该 self-spawn 一个 subagent 来执行，原因：subagent 独立上下文，不会因对话历史积累而降低输出质量。

你只负责跟进 subagent 的执行，避免它们长时间卡在某个步骤，必要时可以提供提示或调整执行策略。另外在关键节点要求它向你汇报，你检查后再让它继续执行下一步。

---

## 模型选型与时长限制（脚本创作时必须遵守）

视频素材优先使用 `gen.py` 脚本生成。

### 平台与模型

| 平台 | 环境变量 | 模型 |
|------|---------|------|
| 阿里云百炼（优先） | `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`） | `happyhorse-1.1-i2v`、`happyhorse-1.1-t2v`、`happyhorse-1.1-r2v` |
| 火山引擎方舟 | `AWK_GEN_KEY` | `doubao-seedance-2-0-fast-260128`、`doubao-seedance-2-0-260128`、`doubao-seedance-2-0-mini-260615` |

- 两个平台的上述模型**均支持声画同出**（t2v / i2v / r2v 三种模式）。
- **平台自动判断写在 `gen.py` 里**：有 `MODELSTUDIO_API_KEY` 走百炼，否则有 `AWK_GEN_KEY` 走火山，两者皆无则输出提示让 Agent 改用 `pexels-footage`/`pixabay-footage`（退出码 2）。

### 百炼模型选择规则

按模式选首选模型，`gen.py` 自动沿候选链 fallback（happyhorse-1.1 → 1.0 → wan2.7）。

| 模式 | 首选模型 | 适用场景 |
|------|---------|---------|
| **r2v**（A.1 人物叙事 + A.3 用户参考图） | `happyhorse-1.1-r2v` | A.1 人物故事全段（`--ref-image` 传 `character_reference.jpg`）；A.3 用户提供参考图片段（Step 3.4） |
| **t2v**（A.2 氛围叙事） | `happyhorse-1.1-t2v` | 手机底面、数据动画、产品特写等无重要人物的场景 |
| i2v | `happyhorse-1.1-i2v` | 如果需要指定首帧的话，使用`happyhorse-1.1-i2v`，传入图像会作为首帧图像。|

- 候选链（每模式一条）：`happyhorse-1.1-{mode}` → `happyhorse-1.0-{mode}` → `wan2.7-{mode}`。首选模型不可用或任务失败时 `gen.py` 自动沿链降级，无需人工干预。
- **`--model <id>` 可显式覆盖**（关闭候选链 fallback，只用该模型）；非必要不覆盖。

### WORKSPACE_ID 端点规则

配了 `WORKSPACE_ID` 时，happyhorse 走专属端点 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1`（华北2，更快）；没配则走默认 `https://dashscope.aliyuncs.com/api/v1`。

这个设置对于火山（doubao-seedance系列模型）无效。

### 火山候选链

- 候选链优先级：Fast → Normal → Mini；1080P 自动跳过 Fast（Fast 仅 720p）。
- ⚠️ **火山视频生成只认 `AWK_GEN_KEY`，不回退 `ARK_API_KEY`**：`ARK_API_KEY` 是火山主模型（doubao 对话）的 key，用户可能只想用火山主模型而不用火山生成视频；若回退会误触发火山视频生成。想用火山生成视频必须单独配 `AWK_GEN_KEY`。

### 模式与时长上限

| 模式 | 触发条件 | 百炼happyhorse-1.1上限 | 火山doubao-seedance上限 |
|------|---------|---------|---------|
| t2v（文生视频） | 无 `--image`/`--ref-image`/`--ref-video` | 3–15s | 2–15s |
| i2v（图生视频） | `--image`（首帧） | 3–15s | 2–15s |
| r2v（参考生视频） | `--ref-image`（用户提供参考图） | 3–15s | 2–15s |

**脚本规划规则**：
- 每个片段时长 **不得超过 15 秒**
- 超过上限的内容**必须在脚本中拆成多个片段**

---

## 工作流程

### Step 1 — 工作区目录准备

在 `output_videos/` 下创建项目文件夹，如 `output_videos/<topic-en-slug>/`，作为 project-dir。

> 作为 viral-chaser 技能的后续步骤时，不必执行此步骤，因为 viral-chaser 已经创建好了编排目录。

工作区结构：

```
<project-dir>/
├── raw_article.md         # 原始内容（文章/追爆报告）
├── script.md              # 定稿脚本（含片段拆分和时长标注）
├── character_reference.jpg  # 人物参考图（人物故事模式 A.1，siliconflow-img-gen 生成）
├── artifacts/             # 产出素材
│   ├── 01_xxx.mp4         # 按编号排序的视频片段
│   ├── 02_xxx.mp4
│   └── ...
├── previews/              # 逐段确认用压缩预览（仅用于发聊天确认，不参与合成）
│   └── NN_xxx_preview.mp4
└── video.mp4              # 最终成品
```

### Step 2 — 脚本创作与定稿

脚本必须包含**片段拆分规划**——每个片段对应一次 `gen.py` 调用或一个用户素材，时长不超过模型限制。

#### 2.1a 正常流程（文章/文字主题）

按「开篇抓眼球 → 中段讲卖点 → 结尾促下单」三段式结构撰写脚本。

**三段式结构**：

| 段落 | 时长占比 | 目标 | 示例套路 |
|------|---------|------|---------|
| **开篇抓眼球** | 前 15–20% | 3 秒内让人停止划走 | "99% 的人都不知道…" / "我花了 XX 才搞明白" / 强反差开场 |
| **中段讲卖点** | 60–70% | 展示核心价值，每个卖点一句 | 场景化痛点 → 产品/方法解决 → 数据/案例佐证 |
| **结尾促下单** | 后 15–20% | 明确 CTA，降低决策门槛 | "链接在简介" / "点击立即领取" / "限时优惠只剩 XX 件" |

#### 2.1b 作为 viral-chaser 技能的后续步骤

读取 `raw_article.md`（追爆报告），按报告中的内容结构、爆款元素和可借鉴点生成脚本。**不套用三段式结构**，而是按照追爆报告拆解的原视频结构来组织脚本，保留叙事节奏和钩子类型。

#### 2.2 片段拆分（脚本必含项）

##### 2.2.1 项目音色设定

声画同出模式下，模型按 prompt 中的音色描述生成人声，没有 voice ID 可传。**同一项目内旁白音色、同一角色音色必须跨片段一致**，否则成片声音段间跳变。脚本必须在片段规划表之前定义一份项目级音色设定，每段旁白逐字复用：

```markdown
## 项目音色设定

- 旁白音色：<具体到性别/年龄感/音色质感/语速/语气，如"沉稳男声，30岁左右，略带磁性，语速适中偏慢，叙述感强">
- 角色音色（人物故事模式按角色列，非人物故事可省）：
  - 主角（character_reference.jpg）：<如"年轻女性，温柔清亮，语速偏快，口语化">
  - 配角：<…>
```

上述音色设定是跨片段整个脚本通用的设定，要放置在 `script.md` 中 `## 片段规划` 前面，并最后随片段规划一起发用户确认。

**音色一致性规则（强制）**：
- 音色描述要具体，不得只写"男声/女声"
- **音色描述只在「项目音色设定」里写一次，片段规划表里不重复**——片段规划的「音频描述」列只写旁白文案/BGM/环境音，不写音色
- **调用 `gen.py` 时，必须把本段对应的音色描述逐字拼进 `--prompt`**（旁白段拼旁白音色，人物对话段拼对应角色音色），逐字复用、不得改写、换词、增删修饰——这是声画同出下成片声音统一的唯一保证
- 同一角色跨段必须用同一条音色描述；换角色才换描述
- ⚠️ 声画同出模型（wan2.7 / happyhorse / 火山 Seedance）均**无音色 ID 或参考音锁定能力**，`--ref-audio` 实测三平台都不认。音色一致**只能靠每段 prompt 逐字复用同一条音色描述**来近似保持——这是目前唯一手段，定稿时务必把音色描述钉死、段间一字不改

##### 2.2.2 片段规划

```markdown
## 片段规划

| # | 段落 | 画面描述 | 音频描述 | 时长 | 来源 |
|---|------|---------|---------|------|------|
| 01 | 开篇 | 产品特写，科技感背景，光影流转 | 旁白："99%的人都不知道…" + 悬念BGM起 + 无 | 5s | AI生成 |
| 02 | 中段 | 用户使用场景，手机操作画面 | 旁白："只需要三步…" + BGM + 键盘敲击声 | 8s | AI生成 |
| 03 | 中段 | 数据图表动画，对比效果 | 旁白："效率提升300%" + BGM + 无 | 6s | AI生成 |
| 04 | 结尾 | 产品logo+CTA按钮 | 旁白："立即体验" + BGM收尾 + 无 | 5s | AI生成 |
```

**拆分规则**：
- 每个片段时长 ≤ 15 秒
- 如果用户提供了素材，在「来源」列标注为 `用户素材`，并注明素材文件名
- **每个 AI 生成片段的「音频描述」必须写明三层**（声画同出，gen.py 照此生成声音，定稿时用户确认的就是成片实际听到的）：
  - **旁白解说**：`旁白："具体文案"`，文案是要朗读的整句（不是"说一段开场白"这种泛指），这就是成片台词，用户定稿即确认
  - **背景音乐**：风格/情绪/起止（如"温暖钢琴 BGM 全段铺底，结尾渐弱"）；同一项目 BGM 风格也应统一，跨段复用同一 BGM 描述
  - **环境音/音效**：关键音效（如"键盘敲击声""金币叮声"），无则写"无"
- 画面描述同样要足够详细（人物/场景/动作/镜头运动）
- 编号 `01, 02, 03…` 对应最终 artifacts 中的文件名前缀

#### 2.3 与用户确认脚本（定稿流程）

完成脚本创作后，必须将脚本原文发送给用户（直接发内容文字，不发文件或路径）。如果用户有意见，按用户意见修改，直到用户确认。

用户确认后，把定稿的脚本存入 `script.md`，进入下一步。

#### 2.4 脚本定稿打分+盲预测（content-calibrator）

脚本定稿后、进入生产前，对 `script.md` 做**一次盲打分 + 盲预测**并落盘到 `output_videos/<topic-en-slug>/calibration/`（视频成片后不再打分，打分锚在定稿）。**per-work：一个视频一次打分+预测**，rubric 全平台统一，各平台差异体现在预测的 bucket 上。

前置：目标视频平台中至少有一个已启用 calibration（`calibration/<platform>/.platform-state.json` 存在）。无任何已启用平台 → 跳过本步。

1. 主 agent `sessions_spawn` blind sub-agent（一定要 spawn 第二个 subagent，避免同一个 subagent 自创自评），只喂 `script.md` + `calibration/rubric_notes.md`（统一 rubric），一次输出：
   ⚠️ **spawn 时 prompt 必须强制要求**："你最后一步的 reply 正文里**必须**包含一个 JSON 代码块（装着 7 维分 + 预测）；不要只 tool-call 后 stop，不要只用 thinking 代替最终文本输出。" 不照此要求会导致某些模型路由下（如 awk/glm-latest）提前 stop 不输出文本，主 agent 拿不到结果。
   - 7 维分 ER/HP/SR/QL/NA/AB/PV（0-5）+ per-dim confidence
   - 盲预测草稿：cold-start 期一句话 bet；过 cold-start 则含每个目标平台的 bucket/中枢（各平台 baseline 不同）
2. 调 `score-only.sh --content-path <script.md> --cal-er ? …` 判阈值门（**全局阈值**，一次判定；`--platform` 可选）。
3. 调 `commit-prediction.sh --work-dir output_videos/<topic-en-slug> --platform <主平台> --cal-er ? … --prediction-file <预测草稿>` 把 `score.json` + `prediction.md` 落盘到 `output_videos/<topic-en-slug>/calibration/`（同 work 重打覆盖）。**score.json 即权威记录，不再往 `script.md` 写分数区段。**
4. `passed=false` → 向用户报告 `failing_dims`，由用户决定是否改脚本重打（最多 2 轮，重打覆盖 `score.json`+`prediction.md`）；用户不改则保留分数继续。

详见 `content-calibrator/SKILL.md` 流程 1A。发布时 `record.sh --source-folder output_videos/<name>` 自动从 `calibration/score.json` 读分；本步未落盘则 record.sh 报错（或显式 `--no-cal` 跳过）。

### Step 3 — 用户素材预处理

> **此步骤优先于所有其他生产步骤**。无论 AI 生成模式还是 Stock Footage 模式，用户素材都必须先处理。

如果用户提供了素材（视频文件、图片等），按以下流程处理：

#### 3.1 确认素材归属

对照脚本片段规划，确认每个素材对应哪个片段编号。如果脚本中未明确标注，与用户确认：
- 该素材放在哪个段落（开篇/中段/结尾）？
- 是否需要额外配音或配乐？

#### 3.2 处理视频素材

对于用户提供的 **视频文件**（.mp4/.mov/.webm）：

1. **探测时长**：用 ffprobe 获取视频时长（assemble.py 内置此能力，也可直接读文件属性）
2. **配音配乐检查**：
   - 如果视频**无音轨**或**用户要求补充配音** → 执行 3.3 补音频
   - 如果视频**已有满意音轨** → 直接使用，跳到 3.4
3. **按片段编号命名**：重命名为 `01_xxx.mp4`、`02_xxx.mp4` 等，放入 `artifacts/`

#### 3.3 补配音配乐（用户素材需要时）

当用户素材需要补充音频时：

1. **确定目标时长**：以素材视频的实际时长为准
2. **生成配音**：
   - 优先使用 OpenClaw 内置 TTS 工具（`tts_generate`）
   - 不可用时回退到 `tts.py`（需先创建 `tts_requirement.md`）
   - 生成的音频时长必须与视频时长匹配（TTS 语速可微调以适配）
3. **合成片段**：将配音与视频合成为带音轨的片段

```bash
python3 ./skills/video-product/scripts/assemble.py <project-dir>/artifacts/ --output <project-dir>/artifacts/<NN>_final.mp4
```

4. 将合成后的片段放回 artifacts，保持编号

#### 3.4 处理图片素材

用户提供的**静态图片**（.jpg/.png）**禁止直接转视频**。图片仅作为：
- AI 生成时的**参考图**（`gen.py` 的 `--ref-image` 传入，本地路径或 URL 均可）
- Stock Footage 搜索时的**风格参考**

### Step 4 — 视频素材生产

> 前置条件：Step 3 已完成，用户素材已就位并编号放入 artifacts/。

**只生产脚本中标注为「AI生成」的片段**，用户素材片段已在 Step 3 处理完毕。逐片段调用 `gen.py`，脚本按平台自动选模型（百炼按模式走候选链，火山走 Fast→Normal→Mini 候选链）。

#### 模式 A：AI 生成模式（gen.py，默认）

按脚本片段规划，**根据 Step 2.5 的人物一致性要求，逐个生成**。每片段一条 `gen.py` 调用，串行执行（下一段等上一段下载完成再发）。

##### 模式 A.1：人物故事模式（人物叙事类片段必用，参考图保持人物一致）

人物一致性靠**同一张参考图**：第 0 步生成人物定妆照，**每段都以它为 `--ref-image` 走 r2v**（首选 `happyhorse-1.1-r2v`（沿链 fallback））。**不做段间首尾帧链式生成**（实测意义不大）：每段独立生成，画面不强制连续，叙事连续靠 prompt 文字承接。

**完整流程**：

**第 0 步：生成人物参考图**（整段故事只做一次）

用 `siliconflow-img-gen` 技能生成人物定妆照，保存为 `<project-dir>/character_reference.jpg`。这张图定义人物的脸/发型/年龄/服装，后续所有片段都以它为 `--ref-image` 保持人物一致。

**每段生成（统一 r2v + 参考图）**

```bash
python3 ./skills/video-product/scripts/gen.py \
  --prompt "画面描述：The same character from the reference image — keep face/hair/age/outfit EXACTLY identical to the reference. 本段场景与动作描述。音频描述" \
  --ref-image "<project-dir>/character_reference.jpg" \
  --ratio 9:16 --resolution 720P --duration 8 \
  --output <project-dir>/artifacts/NN_xxx.mp4
```

全段同一张参考图，首选 `happyhorse-1.1-r2v`（沿链 fallback）。**不传 `--image` / `--prev-segment`**（r2v 不收首帧）。

**每段生成后必须发给用户确认，确认后才生成下一段**（确认流程见下文「逐段确认」）。各段独立生成，下一段不依赖上一段产物。

**逐段确认流程**（每段视频生成后执行）：

1. 用 `compress_preview.py` 把该段视频处理成可发送的预览：
   ```bash
   python3 ./skills/video-product/scripts/compress_preview.py <project-dir>/artifacts/NN_xxx.mp4 \
     --output <project-dir>/previews/NN_xxx_preview.mp4
   ```
   - 输入 ≤16MB → 脚本直接拷贝，exit 0，打印 `[ok] under-limit`
   - 输入 >16MB → 脚本逐级压缩到 ≤16MB，exit 0，打印 `[ok] compressed`
   - 压缩失败 → exit 1，打印 `[fail]`
2. 根据脚本结果向用户确认：
   - exit 0 → **把预览视频文件本体直接发到聊天里**（`previews/NN_xxx_preview.mp4`），请用户确认本段画面
   - exit 1 → **把原始片段路径发给用户**，告知"压缩失败，请在本机打开 `<project-dir>/artifacts/NN_xxx.mp4` 查看"，请用户确认
3. 用户确认本段 → 继续生成下一段（独立生成，不带 `--prev-segment`）；用户要求重做 → 调整 prompt 重新生成本段（不推进到下一段）

⚠️ **`previews/` 下的压缩预览仅用于给用户确认，绝不参与最终合成**。`assemble.py` 只扫描 `artifacts/`，`previews/` 自然被排除；预览文件名带 `_preview` 后缀进一步避免混淆。**禁止把预览放进 `artifacts/`**。

**人物故事模式必须遵守**：

- **先生成人物参考图，再逐段生成视频**；**每段都用 `--ref-image`（同一张 `character_reference.jpg`），全程 r2v（`happyhorse-1.1-r2v`），不传 `--image` / `--prev-segment`**
- **逐段确认**：每段生成后必须发用户确认，确认后才生成下一段
- **时长限制**：全段 r2v（happyhorse-1.1-r2v）3–15s；脚本拆分时每段 ≤15s
- **平台偏好**：人物故事模式**优先用百炼（`MODELSTUDIO_API_KEY`）**。火山 Seedance 不支持直接上传含真人人脸的参考图/视频，传 `--ref-image` 人物图可能被拒
- **prompt 对人物明确描述**：每段都写"the same character from the reference image — keep face/hair/age/outfit EXACTLY identical"，靠参考图维持人物一致
- **角色音色跨段一致**：主角音色由「项目音色设定」中的角色条目统一规定，每段 prompt 的旁白音色描述必须逐字复用同一条，不得段间改写——人物故事里同一张脸却换了声音是硬伤
- **画面描述主焦一个明确动作**：单一动作 + 克制摄像机运动，避免同片段引入过多新道具/新人物导致穿帮
- **镜头运动要平和**：推荐 subtle slow push-in / minimal motion / static shot
- **叙事承接**：各段画面独立，prompt 文案上可承接上一段叙事，但不做首尾帧对齐
- `--ref-image` 支持本地路径（脚本自动 base64）或 `http(s)` URL

##### 模式 A.2：t2v 模式（氛围叙事类片段）

不传 `--image`，只写 prompt。适合手机底面、数据动画、产品特写等不含重要人物的场景：

```bash
python3 ./skills/video-product/scripts/gen.py \
  --prompt "画面描述：产品特写镜头，科技感背景，光影流转。音频：转场音效+悬念BGM起" \
  --ratio 9:16 --resolution 720P --duration 12 \
  --output <project-dir>/artifacts/02_xxx.mp4
```

##### 模式 A.3：r2v 模式（仅用户提供参考图时，对应 Step 3.4）

**仅当某片段用户提供了参考图**（Step 3.4 静态图片作为参考）时才走 r2v，首选 `happyhorse-1.1-r2v`（沿链 fallback），传 `--ref-image`：

```bash
python3 ./skills/video-product/scripts/gen.py \
  --prompt "参考图片中的角色/风格在 <新场景> 做 <动作>，音频：…" \
  --ref-image "<用户提供的参考图路径或URL>" \
  --ratio 9:16 --resolution 720P --duration 8 \
  --output <project-dir>/artifacts/03_xxx.mp4
```

- 百炼 r2v 首选 `happyhorse-1.1-r2v`（沿链 fallback），时长 3–15s，**仅支持 `--ref-image`**（不支持 `--ref-video`、不支持首帧 `--image`）。
- A.1 人物故事也走 r2v（同一模型），区别只在参考图来源：A.1 用生成的 `character_reference.jpg`，A.3 用用户提供的图。
- `--ref-image` 支持本地路径（脚本自动 base64）或 `http(s)` URL。

**参数说明**：
- `--prompt`：**画面+音频统一描述**。声画同出，人物对话、旁白、BGM、环境音都写在 prompt 中。
- `--ratio`：默认 `9:16`（竖屏）；`--resolution` 默认 `720P`，用户要高清用 `1080P`。
- `--duration`：按脚本片段时长，**不得超过 15 秒**（百炼 i2v/r2v 最短 3 秒）。
- `--no-audio`：用户明确不要配音时关闭声画同出。
- `--model`：显式指定模型 id，覆盖百炼按模式固定的模型。`--platform` 可覆盖自动检测。
- `--poll-interval` / `--timeout`：默认 15s / 900s，1080P 或长片段可加大 `--timeout`。

**生成后处理**：
- `gen.py` 直接把 MP4 写到 `--output`（按片段编号命名，如 `01_hook_product.mp4`），并同目录写 `<name>.json` 元数据。
- 若生成失败无音轨，后续由 Step 4.5 补 TTS。

##### 生产中常见错误与重试策略

| 错误 | 原因 | 处理 |
|------|------|------|
| `gen.py` 退出码 2 + pexels/pixabay 提示 | 两个平台 env key 都没配 | 按提示走模式 B，或 spawn IT Engineer 配置 `MODELSTUDIO_API_KEY`/`AWK_GEN_KEY` |
| HTTP 401 / API key doesn't exist | key 与平台/地域不匹配 | 检查 env 变量是否对应平台；百炼用 `MODELSTUDIO_API_KEY`，火山用 `AWK_GEN_KEY` |
| HTTP 404 / Invalid model | model id 错误 | 检查 `--model` 是否在支持列表内；火山模型须含 `doubao-` 前缀 |
| 任务 FAILED / 超时 | 渲染慢（1080P/长片段）或参数不兼容 | 百炼沿链自动 fallback（1.1→1.0→wan2.7）；仍失败则降低分辨率/缩短时长重试，或 `--model` 指定模型 |
| r2v 报错退出（传了 `--image`/`--ref-video`） | r2v 仅 `--ref-image`（happyhorse-1.1-r2v 起沿链） | r2v 不收首帧；人物故事统一用 `--ref-image`，不要传 `--image`/`--prev-segment` |
| `--output must be relative to the workspace` / `--output must be under one of: output_videos` | exec 直接调 gen.py，CWD 不在 workspace-media-operator，或 `--output` 用了绝对路径 | **exec 必须显式设 `workdir="/home/wukong/.openclaw/workspace-media-operator"`**，且 `--output` 必须是相对路径形如 `output_videos/<topic>/artifacts/NN_xxx.mp4`。gen.py 内部 `ensure_safe_output()` 强制只允许 `output_videos/` 下的相对路径，靠 `Path.cwd()` 解析根目录；同理 `compress_preview.py` 也要求相对 `--output` 在 `previews/`/`tmp/`/`output_videos/` 下，需要同样的 workdir 设置 |
| `exec denied: allowlist miss` 调 `cd <dir> && python3 ...` | `cd` 不在 allowlist（TOOLS.md 明确禁止），导致整条命令被拒 | 不要用 `cd && cmd` 包装；改用 exec 的 `workdir` 参数显式指定 CWD，命令本身用绝对路径调脚本 + 相对 `--output` |

**重试上限**：`gen.py` 内部做瞬时 HTTP 重试；百炼沿候选链自动 fallback（happyhorse-1.1 → 1.0 → wan2.7），整链都失败退出非 0 再人工重试 1 次，仍不通就告诉老板，不要 yield 死等。

#### 模式 B：Stock Footage 托底模式（gen.py 退出码 2 时）

当 `gen.py` 报"未检测到任何视频生成平台的环境变量"（退出码 2）时，回退到此模式。

**此模式下需要单独生成 TTS 配音**（见 Step 4.5），因为下载的素材无音频。

素材搜集优先级：
1. **`pexels-footage`**：从 Pexels 免费素材库搜索下载（9:16 竖屏）
2. **`pixabay-footage`**：Pexels 不可用或无结果时，从 Pixabay 下载

**素材下载规则**：
- 一次只下载一个视频
- 时长精准匹配（根据脚本片段时长设置 `--min-duration` / `--max-duration`）
- 下载后按脚本片段编号重命名

**质量自检**（仅 stock-footage 模式需要）：

```bash
python3 ./skills/video-product/scripts/check.py <project-dir>/
```

check.py 检测黑帧、分辨率、时长缺口。每下载一段素材后运行一次，直到 `verdict: "accepted"` 且时长满足。

#### Step 4.5 — TTS 配音（仅 Stock Footage 模式或 AI 生成无音频时）

> **AI 生成模式下通常跳过此步骤**：Wan 系列的 `audio: true` 已同步生成音频。

当需要单独生成 TTS 时：

**优先使用 OpenClaw 内置 TTS 工具**（`tts_generate` 或 agent 内置语音合成能力）。

OpenClaw 内置 TTS 不可用时，回退到本地脚本(要求环境变量已经配置SILICONFLOW_API_KEY）：

```bash
python3 ./skills/video-product/scripts/tts.py <project-dir>/ --overwrite
```

需先创建 `tts_requirement.md`：

```markdown
# 配音需求

## 配音文案
<!-- 需要朗读的纯文本，不含 markdown 标题、注释或镜头说明 -->

## 语音要求
- 音色：fnlp/MOSS-TTSD-v0.5:benjamin
- 语速：1.0
- 语气：自然、有吸引力
```

可用语音:

| Voice ID | 说明 |
|----------|------|
| `fnlp/MOSS-TTSD-v0.5:benjamin` | 幽默男声，语速较慢，推荐 |
| `fnlp/MOSS-TTSD-v0.5:charles` | 激昂男声，适合广告 |
| `fnlp/MOSS-TTSD-v0.5:claire` | 清澈女声，推荐 |
| `fnlp/MOSS-TTSD-v0.5:david` | 清脆男声 |
| `fnlp/MOSS-TTSD-v0.5:diana` | 可爱女声，娃娃音 |

### Step 5 — 合成视频

调用 assemble.py 将所有片段按编号顺序拼接为最终成品。

**⚠️ 合成前必须先清理废弃片段**：逐段确认过程中产生的废弃版本（如 `02_choose_path.v1_bad.mp4`、`03_traffic_master.v1_old.mp4` 等）**和正式片段共用同一数字前缀**，assemble.py 会把它们当成对应段一起拼进去，导致成片重复/错乱。合成前先删除或移出 `artifacts/`：

```bash
# 把废弃版本移到 artifacts/_deprecated/ 子目录（assemble.py 非递归扫描，子目录不参与拼接）
mkdir -p <project-dir>/artifacts/_deprecated
mv <project-dir>/artifacts/*.v*_*.mp4 <project-dir>/artifacts/_deprecated/ 2>/dev/null
# 或直接删除：rm <project-dir>/artifacts/*.v*_*.mp4
```

清理后确认 `artifacts/` 顶层只剩 `01_*.mp4 … NN_*.mp4` 每段一个正式片段，再合成：

```bash
python3 ./skills/video-product/scripts/assemble.py <project-dir>/artifacts/ --output <project-dir>/video.mp4
```

合成规则：
- **无外部音频文件**（AI 声画同出模式常态）：assemble.py 保留每段视频自带音轨拼接；个别无音轨的片段自动补静音以保持拼接布局一致，不会把成片变无声
- **有外部音频文件**（`speech.mp3` 等，Stock Footage + TTS 模式）：外部音频替换视频原音轨
- 不烧录字幕

assemble.py 按文件名数字前缀（`01_`、`02_`、`03_`…）顺序拼接，同一前缀内按文件名字典序。

合成后确认 `video.mp4` 存在且非空。

### Step 6 — 制作封面

每个视频都必须配封面图。封面要求：
- **必须包含视频标题文字**，不允许纯图片封面
- 标题文字必须有设计感（字体选择、排版布局、颜色搭配）
- 竖屏封面 1080x1920
- 可以使用视频关键画面作为背景，但文字是必须元素

使用 `siliconflow-img-gen` 制作封面，保存为 `<project-dir>/cover.jpg`。

### Step 7 — 用户确认

向用户展示：
- 成品视频（发文件本体）
- 封面图（发文件本体）
- 关键参数（时长、分辨率、片段数）

用户确认后，流程结束。后续发布由 media-operator 调用对应发布技能执行。

---

## 脚本清单

| 脚本 | 文件名 | 用途 | 使用场景 |
|------|--------|------|---------|
| 视频片段生成 | `./skills/video-product/scripts/gen.py` | 直连火山/百炼端点生成视频片段（声画同出）；百炼按模式走候选链（happyhorse-1.1→1.0→wan2.7），火山走 Fast→Normal→Mini | AI 生成模式（默认） |
| 预览压缩 | `./skills/video-product/scripts/compress_preview.py` | 把视频压到 ≤16MB 用于聊天确认（产物仅用于确认，不参与合成） | 人物故事模式逐段确认 |
| 片段合成 | `./skills/video-product/scripts/assemble.py` | 视频+音频合成 MP4 | 所有模式 |
| 素材自检 | `./skills/video-product/scripts/check.py` | 检查素材质量与时长缺口 | 仅 Stock Footage 模式 |
| TTS 语音合成 | `./skills/video-product/scripts/tts.py` | 读取 tts_requirement.md 生成配音 | 仅 OpenClaw 内置 TTS 不可用时 |

---

## 禁止事项（强制）

违反以下任何一条都会导致系统死机或产出异常，**必须严格遵守**：

- **禁止直接写 ffmpeg 命令**：不得在 exec 中直接调用 ffmpeg/ffprobe，也不得写 Python 脚本内嵌 ffmpeg 调用。所有视频处理一律通过 `./skills/video-product/scripts/` 下的标准化脚本完成
- **禁止从静态图生成视频**：不得将 JPEG/PNG 等静态图片通过 ffmpeg 转为 MP4。用户提供的静态图片仅作为 AI 生成参考图或搜索风格参考

## 注意事项

- **配音语速不得为匹配视频时长而调整**：默认 1.0，只能按用户明确要求修改（Step 3 用户素材补配音时除外，此时语速可微调以适配素材时长）
- **素材按脚本顺序拼接**：assemble.py 按文件名数字前缀排序，搜集素材时务必按脚本片段编号命名
- **AI 生成模式优先**：先调 `gen.py`；仅当其退出码 2（两个平台 env key 都没配）时才走 Stock Footage 模式
- **用户素材优先于 AI 生成**：无论哪种模式，用户提供的素材必须优先使用
- **声画同出**：`gen.py` 默认开启音频生成，prompt 中要详细描述背景音乐+环境音+对话/旁白
- **无配音模式**：用户明确不需要配音时，`gen.py` 传 `--no-audio`；Stock Footage 模式跳过 TTS 步骤
