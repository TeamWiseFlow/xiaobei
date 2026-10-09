# 小红书内容生产 Workflow

从选题到发布的内容运营流程，覆盖**图文笔记**与**视频笔记**。用户说“帮我写一篇小红书笔记”“发个小红书”“这篇照着做一篇”“把这个草稿改成小红书风格”走这个。

用户指定群聊误发式或问答式连续讨论流卡片时，切到 `native-ui-cards.md` 完成选题、出图、发布与记录；本流程处理其他图文和视频。

**分工硬边界**：

- 图文笔记、长文内容：main agent 直接生产（含标题、正文、图组、话题标签与发布）。
- 已有视频素材的简单加工：main agent 直接做（`video-edit` / `talking-head-cut`）。
- 视频全案：main agent 负责选题策划、按 DNA 出 Brief、拟定短标题与视频描述、准备素材（含简单加工）、监督 CP 进程、成片后的发布与运营；视频全案的成片制作委托 `content-producer`。口播类视频的口播文案由 main agent 写好随 Brief 交付（真人口播时指导用户按口播稿录音，完成后向用户取得录音文件），其余声画制作归 CP。

## Step 0 - 入口判断

### 1. 识别产出形态

| 形态 | 判断 | 处理 |
| --- | --- | --- |
| 图文笔记 | 默认 | 标题 + 正文 + 图组；`xhs-publish --mode image` |
| 视频笔记 | 用户明确说视频笔记 / 发视频 | 视频为主体；已有素材轻加工由 main 做，全案走 Brief 委托 CP |

### 2. 识别用户输入类型

| 输入 | 模式 |
| --- | --- |
| 只有粗略想法或方向 | 想法模式 |
| 参考笔记 / 文章 | 参考模式 |
| 已有草稿 | 草稿模式 |
| 已有视频素材 | 素材模式 |
| 用户要求完整视频全案 | Brief 模式 |

草稿模式包含「风格转写」：保留事实与结论边界，只按账号 DNA 与小红书语境重写表达。

### 3. 小红书链接的意图判断

- **风格吸收**：“把这篇的风格提取出来”“以后照着这个味道写” → `style-dna.md`
- **内容参考**：“照着这篇做一篇”“这个选题我们也做一篇” → 本流程
- 意图不明时先问用户。

### 4. 与改稿的边界

已完成笔记的改标题、改正文、换封面、换图走 `editing.md`。本流程把用户输入当作素材，产出新笔记。

## Step 1 - 生产契约锁定

### 1. 确定 DNA

1. 用户指定 `dna-id` 时只用该 DNA。
2. 未指定时用默认 `dna-0`。
3. 不得临场拼风格。
4. 目标 DNA 不存在时，先走 `account-setup.md` / `style-dna.md`。
5. 参考风格要吸收进 DNA 时，先更新 DNA 再生产。

写前读取：

```text
xhs/dna/{dna-id}/{dna-id}.dna.md
xhs/dna/{dna-id}/{dna-id}.template.md
```

DNA template 是 main agent 的生产输入模板：**图文 DNA 的 template = 图文写作模板**（选题、标题与封面、关键词与用户问题、内容创意与结构、正文表达、图组、业务植入与 CTA）；**视频 DNA 的 template = Brief 正文模板 +（可选）口播文案模板**。都不规定创作细节：逐句正文之外的排版参数、镜头表、转场或编码细节归执行方。

### 2. 读取业务知识

从 `business_knowledge.md` 提取：

- 产品 / 服务与核心差异
- 目标读者与痛点
- 转化目标与平台内动作
- 红线、合规限制与品牌语气

关键信息缺失先问用户，不虚构。

### 3. 采集生产要求

| 项目 | 规则 |
| --- | --- |
| 产出形态 | 图文 / 视频；未明确默认图文 |
| 主题 / 方向 | 用户指定时不得另起炉灶 |
| 搜索意图 | 从 DNA 搜索意图地图取主关键词、相关词、用户可能提问；无结论时向用户确认 |
| 素材 | 用户提供的图片、文案、截图、案例、视频片段优先 |
| 目标读者 | 未指定时按 DNA 受众关系推导；涉及业务事实时再核对 `business_knowledge.md` |
| 标题 | 硬限制 ≤ 20 字；覆盖主关键词或用户问题 |
| 图组 | 硬限制 ≤ 18 张；用户提供优先 |
| 行动引导 | DNA 要求时只放一个平台内动作 |
| workflow | 视频全案已确定形态时写 CP `expert-video` 支持的 workflow（reversal-ad / collage-broll / deck-talk）；未确定则省略（省略 = CP 按其通用制作流程做） |

优先级：

```text
用户明确交付要求 + 业务事实 / 红线
> 用户提供的素材
> DNA template 的生产规则
> business_knowledge.md 中的相关事实
> Agent 的一般内容判断
```

## Step 2 - 素材获取与整理

先建 `xhs/outputs/<note-name>/`，下设 `materials/`。

1. 图文笔记链接 → `xhs-hunter fetch <完整链接> --output-dir xhs/outputs/<note-name>/references --download-media` 保存正文、有序图片与真实指标；本 workflow 回读正文、封面和逐图结构完成参考分析，不调用 viral-chaser。
2. 视频笔记链接 → self-spawn subagent 走 `viral-chaser`。
3. 本地图片 / 视频 / 音频 / 文档 → 复制或提取进 `materials/`。
4. 建立素材清单：用户原话、事实、数据、案例、画面素材、授权信息、待确认项。
5. 区分必用素材、参考素材、对标素材；冲突时问用户，商业事实以 `business_knowledge.md` 和用户最新说明为准。

## Step 3 - 选题与搜索意图

### 选题调研

1. 从 DNA 搜索意图地图取主关键词、相关词、长尾句与用户可能提问。
2. 用 `xhs-hunter search-notes` 对主关键词做一次有界站内搜索（`--count 20`，不连续翻页）；已有近期样本够用时直接复用。
3. 提炼真实用户讨论、痛点、争议点、常见提问与高热内容形式。
4. 有价值线索归档为参考素材，不直接替代用户事实。

### 选题输出

给出 1-3 个选题方向，每个方向必须说明：

- 覆盖哪个主关键词 / 用户问题
- 使用哪些用户素材
- 对应 DNA 的哪些内容目标；如涉及业务目标，说明对应关系
- 符合 DNA 的哪些选题组合、内容形式与高数据创意
- 产出形态建议：图文 / 视频 / 混合节奏中的哪一环

用户已明确主题时只做轻量核实，不另起炉灶。

## 【确认】选题与搜索意图

第一个必停节点。确认主题、主关键词与目标用户问题。

## Step 4 - 标题与话题标签

1. 标题 ≤ 20 字，优先覆盖主关键词或用户问题的自然表达。
2. 标题模式按 DNA 的 `title-packaging`，不照抄参考标题。
3. 话题标签 ≤ 10 个，内联在正文中；按核心词 / 场景词 / 人群词 / 痛点词组织，不堆砌。
4. 用户指定标题或标签时逐字或按原意执行。
5. 简介与正文可提及产品与业务，但不得出现联系方式、二维码或站外引流；禁止谐音绕检测。

## 【确认】标题与标签

第二个必停节点。用户确认后才进入正文或视频 Brief。

## Step 5A - 图文正文

图文笔记由 main 直接写 `xhs/outputs/<note-name>/note.md`。

1. 正文 ≤ 1000 字，首个一级标题行写标题，正文保留换行节奏。
2. 按 DNA 的定位、核心传达、搜索意图、互动目标组织内容；不套用固定逐句模板。
3. 开头必须兑现标题与封面承诺，优先回答用户问题或给出核心结论。
4. 用户必用素材优先进入正文，不得为了形式删除关键事实。
5. 商业承诺、服务范围、价格和案例必须与 `business_knowledge.md` 一致。
6. DNA 要求业务植入时，按 `biz-implant` 决定位置、载体与衔接句；DNA 要求 CTA 时，按 `interaction-cta` 只选择一个平台内动作：评论 / 收藏 / 关注 / 进店 / 咨询 / 搜索品牌词。
7. 风格转写只改表达与结构呈现，不改事实含义、数据、案例、引用和结论边界。
8. 同主题改写可借鉴参考结构，文字必须用自己的素材与表达重写，禁止搬运。

## Step 5B - 视频全案 Brief

视频全案不写全片脚本，main 只产出 `xhs/outputs/<note-name>/brief.md`：

```markdown
# 小红书视频制作 Brief

- 视频名 / slug：
- platform：xhs
- workflow：reversal-ad / collage-broll / deck-talk（视频形态未确定时省略本字段；省略 = CP 按其通用制作流程做，叙事 / 动效 / 蒙太奇手法由 CP 据创意自定）
- deck-talk 专属（仅该类型填写）：在 Brief 中逐项写 `- presenter_source：footage/avatar/audio`（兼容 none）、`- visual_source：slides/broll/mixed`、`- audio_origin：recorded/cloned/designed/stock-tts`、`- presenter：绝对路径`（需小窗时）、`- audio：绝对路径`（avatar/audio 模式）。实拍先用 talking-head-cut 剪好再交 CP；数字人交肖像+音频或音色档案；纯音频模式交音频，CP 配 B-roll。记录授权。
- 选题与观看理由：
- 核心传达：
- 内容创意：创意原型 + 展开逻辑 + 记忆点
- 关键词与用户问题：主关键词、相关词与长尾句、用户可能的提问（供 CP 理解内容指向，不做 SEO 操作）
- 业务植入与 CTA：植入位置与方式原型 + 内容与业务的衔接句要求 + CTA 主目标与句式（只写要求，不写 DNA 规则原文）
- 标题与简介：笔记标题、发布正文、话题标签（main 定稿）
- 封面要求：封面主文案 + 视觉方向
- 制作规格：横屏 / 竖屏、时长带、画面风格、配音音色与声音形态、BGM 与音效、字幕
- 口播文案：`voiceover.md` 绝对路径 / 真人口播录音绝对路径 / 不适用（口播 = 真人出镜、数字人、真人录音；剪辑配解说的**旁白归 CP 写**，写「不适用」）
- 素材清单：逐条**绝对路径** + 来源 + 授权（无素材时写「无，由 CP 按 Brief 取材」）
- 交付物与验收：`video.mp4` + `cover.jpg` + `final-deliver.md`，回报三者绝对路径；验收标准
- 闸门：GATE A / GATE B 批准人（用户或 main 代理批准 + 批准范围）
- 禁止事项：事实与承诺边界、合规红线、禁用方向
```

Brief 硬性规则：

- **不写 DNA**：Brief 里不出现 dna-id、DNA 文档路径或 DNA 规则原文——CP 看不到 main 的 DNA，只按 Brief 制作。
- **不建工作区**：main 不替 CP 建目录、不指定项目路径；CP 在自己的 workspace 下自建工作区。双方 T3 权限可互访取文件。
- **素材给绝对路径**：main 负责素材准备，把绝对路径写进 Brief。
- **甲乙方关系**：需求方向、品牌事实、发布文案归 main；制作方案、分镜、渲染参数归 CP。

### 口播文案规则

- **口播（真人出镜 / 数字人 / 真人录音）的口播稿一律由 main agent 出**：`narration-script`（口播文案子模块）启用时按其结构写，未启用时按用户要求与 Brief 核心传达写，保存为作品目录下的 `voiceover.md`，在 Brief 中给**绝对路径**。CP 不重写，只做声画实现；剪辑配解说的**旁白归 CP 写**，main 不出旁白稿。
- **真人口播**：明确要用用户真人声音时，指导用户按口播稿录音，完成后向用户取得录音文件，落到作品目录并在 Brief 中给绝对路径。
- **口播子模块未启用**：口播终稿仍由 main 写——按用户要求与 Brief 的核心传达 / CTA 要求直接撰写（不依赖 DNA 子模块），落 `voiceover.md` 并在 Brief 给绝对路径；「不适用」即旁白类（剪辑配解说归 CP 写）或非口播视频。
- 用户必用的事实、案例、承诺和 CTA 必须进入 Brief 或口播终稿，不得为了形式删除关键事实。

## 【确认】正文 / Brief

第三个必停节点：

- 图文：确认正文与图组方向。
- 视频：确认 Brief（及口播终稿，如有）后才委托 CP。
- Brief 变更时更新版本并推送变更要点；已开工中间产物按新版取舍，弃用部分记入交付说明。

## Step 6 - 图组 / 视频制作

### 图文图组

1. 读取 DNA 的图组视觉与标题封面结论，只取风格边界。
2. 图片来源优先级：用户素材 → `campaign_assets/` → `awk-img-gen` → `pexels-footage` / `pixabay-footage`。
3. 封面必须存在，兑现标题承诺；生成图发用户确认。
4. 图文建议 3:4 竖版，图片 ≤ 18 张，顺序按信息推进。
5. 图片与正文分工：图承载证据、过程、对比或清单；文承载判断、细节与行动。

### 视频制作

| 情况 | 处理 |
| --- | --- |
| 用户直接提供成片 | 校验格式与时长，复制到作品目录 |
| 已有素材需简单加工 | main 用 `video-edit` / `talking-head-cut` 处理 |
| 全案制作 | 委托 `content-producer`：只交 Brief 一份（素材、口播文案 / 录音以绝对路径写在 Brief 内），不指定 CP 工作区；指定 `workflow` 必须采用；未指定时 CP 按其通用制作流程做，叙事 / 动效 / 蒙太奇手法由 CP 据创意自定；Brief 缺失或创意不足以直接写剧本时，CP 会走其 story-develop intake workflow 与 Brief owner 收敛 Brief。成片与封面按 CP 回报的绝对路径取回作品目录 |

视频封面优先从成片选帧；需要更强视觉冲击时用 `awk-img-gen`。

## 【确认】正文与图组 / 成片与封面

第四个必停节点。图文确认正文、图组与封面；视频确认成片、封面、标题正文与发布描述。

## Step 7 - 存文件

`xhs/outputs/<note-name>/`：

- 图文：`note.md`、封面与图组图片、`materials/`、`dna-meta.json`
- 视频：`brief.md`、`voiceover.md`（如启用）、`note.md`（标题 + 发布正文）、`video.mp4`、`cover.jpg`、`materials/`、`dna-meta.json`
- `dna-meta.json`：`{"platform":"xhs","dna_id":"<dna-id>"}`

## Step 8 - 发布

发布走 `xhs-publish`：

```bash
# 1. 探活（批量发布只探活一次）
xhs-publish check
# exit 0 = 有效；exit 2 = 无会话或认证失效 -> xhs-publish login，发送返回的二维码图片，等用户确认后 xhs-publish login-confirm，再探活一次

# 2. 图文发布
xhs-publish --mode image --title "标题" --body "正文（含 #话题1 #话题2）" --images img1.jpg img2.jpg img3.jpg

# 2'. 视频发布
xhs-publish --mode video --title "标题" --body "正文" --video video.mp4 --cover cover.jpg
```

- `--body` 必须传实际文字，不能传文件路径或 `$(cat file)`；从 `note.md` 读出后硬编码进命令。
- 笔记含 AI 合成内容时，在对应 `xhs-publish` 命令末尾加 `--ai-declaration`，发布时一并提交平台侧声明；纯实拍素材不加。
- 返回 `{"ok": true, "note_id": ..., "url": ...}` 才算成功；`AUTH_EXPIRED` 重登后重试一次；`RATE_LIMIT` 等 30 分钟后重试。
- 单账号每天 ≤ 1-3 篇；触发风控立即降级，30 分钟内不重试。
- 发布失败伴随登录异常迹象时停止重试，记下来走重登流程，不批量撞风控。

## Step 9 - 记录

发布成功后：

```bash
published-track record \
  --platform xhs \
  --source-folder xhs/outputs/<note-name>/ \
  --account <发布账号 alias> \
  --publish-url <xhs-publish 返回的 url>
```

`dna_id` 自动从 `dna-meta.json` 读取。互动数据由每日任务统一抓取，复盘走 `review.md`。
