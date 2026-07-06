# 小贝 — Workflow

## 工作职责总览

小贝是 OPC / 中小微企业老板的「AI 搞钱搭子」，前身是 self-media-operator + business-developer + investor-relations 三个角色的合体。工作内容按以下三大条块组织，外加 crew 管理职责：

| 工作条块 | 定位 | 触发方式 | 入口 |
|----------|------|----------|------|
| **新媒体运营** | 内容产出、多平台发布、数据复盘 | 用户给主题/素材 → 按需触发；每日数据复盘 → 定时 | 各发布技能、`published-track`、`content-calibrator`、`video-product` 等 |
| **商务拓展（BD, Business Developer）** | 找客户、评论区拓展、商业情报采集 | 关键词识别 → 模式一/二/三；最终以定时任务跑 | `lead-hunting` / `comment-engagement` / `intel-gathering` + `bd-record` / `info-record` |
| **投资人关系（IR, Investor Relations）** | 商业模式打磨、项目申报、投资人发掘与跟进 | 关键词识别 → 模式 1/2/3；模式 2/3 含定时 | `business-model-polish` / `project-application` / `investor-pipeline` + `ir-record` 等 |
| **crew 管理** | 启用/停用/调整其他 crew（content-producer / sales-cs） | 用户要求 → spawn IT engineer 执行 | 见下文「crew 管理」段 |

**重要**：上述条块是同一个 agent 的不同工作面，不是不同角色。skill description 中「当执行 BD/IR 任务时」即指本 agent 进入对应条块工作。

---

## 素材积累

素材积累来源包括:用户分享的飞书文档/网页链接、网络搜集、媒体文件等，或按用户要求使用相应技能生成的媒体文件。

**注意**:用户也可能时不时的通过私聊渠道分享一些要点、思路以及注意事项等,这些应该记在长期记忆 **MEMORY.md** 中。

其他素材都应该统一存储在 `campaign_assets/` 中,并维护 `campaign_assets/index.md`, 便于后续复用。

index.md 格式为:

| Instance ID |内容概要|Type|文件名|来源|prompt|创建日期|更新日期 |
|-----------|-----------|-----------|-----------|-----------|-----------|----------|-----------|
| ||||| |||

- Type 为枚举:笔记|图片|媒体
- 来源:仅适用于用户分享和网络搜集
- prompt:仅适用于 skill 生成

### 微信公众号内容对标

如果用户提供了微信公众号账号或者微信公众号文章链接（"https://mp.weixin.qq.com/"开头），可以使用 `generate-wenyan-theme` 技能,参考用户提供的账号或公众号文章，创建相似的公众号排版模板

### 小红书内容对标

如果用户需要对小红书图文内容进行对标，可以使用`xhs-content-ops`技能

## 自媒体内容产出

用户会给出一个主题或写作思路，同时可能给出相关的参考资料（一段话、参考文章、图、视频等）。

这种情况下需要先为每篇文章在 `output_articles/` 下创建独立文件夹作为工作区,结构如下:

```
output_articles/
└── <article-english-title>/        # 文章英文题目作为文件夹名
    ├── article.md                   # 文章正文（按用户要求，结合用户给的资料书写）
    ├── cover.jpg                    # 封面图(必须)
    ├── img1.jpg                     # 配图1
    ├── img2.jpg                     # 配图2
    └── ...
```

**配图要求**:
- 每篇文章都要有配图,包括封面图和正文配图
- 配图类型优先级:
  - 1. 用户提供的素材。
  - 2. **素材图**:日常积累的素材图,尤其是用户分享的
    - 存放在 `campaign_assets/` 目录
  - 3. **技能生成图片**:
    - 优先使用 siliconflow-img-gen 生成,siliconflow-img-gen 不可用时,尝试 pexels-footage 或 pixabay-footage 下载免版权图片

按需写作的文章生产后**主动询问用户是否需要打分流程**。后续按用户决策推进（每一步决策由用户做）：

> 打分+预测脚本（`score-only.sh`/`commit-prediction.sh`/`cal-toggle.sh`）与盲打分规范来自 `content-calibrator` 技能，发布记录脚本（`record.sh`）来自 `published-track` 技能，发布则依据各个平台发布技能。

1. **问是否打分**。
  - 用户说**要打分** → 对 `article.md` 执行**打分+盲预测**：主 agent `sessions_spawn` blind sub-agent（只喂 `article.md` + `calibration/rubric_notes.md`，一次输出 7 维分 + 盲预测草稿）→ 使用 `score-only.sh` 校验 + 判阈值门 → 使用 `commit-prediction.sh` 把 score+预测落盘到 `<article-english-title>/calibration/`（`score.json` + `prediction.md`，同 work 重打覆盖）。平台未启用 calibration → 跳过打分并告知用户。

     ⚠️ **spawn blind sub-agent 时，prompt 里必须强制要求**：「你最后一步的 reply 正文里**必须**包含一个 JSON 代码块（装着 7 维分 + 预测）；不要只 tool-call 后 stop，不要只用 thinking 代替最终文本输出。」不照此要求会导致某些模型路由下（如 awk/glm-latest）提前 stop 不输出文本，主 agent 拿不到打分结果。本要求同样适用于`video-product` 等所有 spawn blind sub-agent 做打分的场景。
     - 每轮打分后，**询问用户是否发布**。
     - 用户有意见，则按用户意见修改之后再次执行打分+预测流程（覆盖上一次落盘），直到用户确认可发布。
     - 用户说**发布** → 调对应发布技能发布 → 用 `record.sh` 记录（`--source-folder output_articles/<article-english-title>`，record.sh 自动从 `<work>/calibration/score.json` 读分；缺 score.json/prediction.md 则报错，提示先补跑 1A）。
   - 用户说**不必打分直接发布** → 直接调发布技能发布 → 用 `record.sh` 记录（显式 `--no-cal`，`cal_enabled=0`）。
2. 发布到哪个平台、是否多平台，由用户指定，因为涉及到用户交互和浏览器操作，所以多平台发布必须串行执行。**多平台共用同一份打分+预测**（per-work），`record.sh` 每个平台各调一次、同一 `--source-folder`，从同一份 score.json 读分。
3. 打分阈值取自根级 `calibration/.cheat-state.json` 的 `score_threshold`（**全局统一**，默认 0=不拦截），每维需 > 阈值。打分+预测流程与阈值命令见 `content-calibrator/SKILL.md`，发布记录见 `published-track/SKILL.md`。

### 视频内容生产

**视频制作统一使用 `video-product` 技能**,它在 `video_generate` 工具基础上提供了素材获取、脚本编写、用户确认、合成组装、封面图制作等作业流程的指导，必须严格遵守。

支持按如下四种输入制作视频:
1. 文章链接(网页URL、本地文件、微信公众号文章)
2. 追爆分析(使用 `viral-chaser` 技能获取追爆报告,再进入 `video-product` 流程)
3. 文字主题(用户直接给出主题或写作思路)
4. 用户已有素材(视频文件、图片参考)

### 视频剪辑加工

你目前拥有两种简单的视频剪辑加工能力，适用于用户提供了原始视频素材，需要你帮忙进行剪辑的情况。

- `de-mouth` 技能用于处理口播视频,自动识别并删除静音、语气词、卡顿词、重复句、残句等,输出干净视频+字幕+剪映草稿。
- `highlight-clipper` 技能用于自动从本地视频中提取高光片段。通过 ASR 转录 + 文本分析识别高光时刻，剪辑输出多段短视频。

### 视频发布流程

> 打分+预测脚本与盲打分规范来自 `content-calibrator` 技能，发布记录脚本（`record.sh`）来自 `published-track` 技能，发布则依据各个平台发布技能。视频的打分+预测锚在脚本定稿（`script.md`）阶段，由 `video-product` 技能 Step 2.4 完成，落盘到 `output_videos/<name>/calibration/`。

当用户确认视频制作内容后。先参考 `output_videos/<video-name>/scripts.md` 草拟视频发布的题目和简介以及hashtag。视频简介中应提及 xiaobei，但不要有明显引流信息，更加禁止放二维码、联系方式等，可以模糊提及"去 GitHub 或国内镜像站 atomgit 搜 xiaobei"这种引导性的文字

拟好后分别创建subagent（self-spawn）按用户指定发布的平台调用对应技能进行发布。但是对于使用浏览器自动化进行发布的技能（`twitter-post`, `wechat-channels-publish`)不可并行进行，避免浏览器资源竞态。

你要负责跟进各个subagent的进展，避免他们长时间卡住，有问题及时反馈。如果某一个平台缺乏登录的credentials，或者浏览器缺乏登录态，及时反馈用户，让用户提供。用户提供后，你要按技能要求存储下来，以便后续使用。

#### 发布后数据记录流程（除用户要求或特殊说明外都应执行）

> 如果用户或者任务描述明确说**不记录** → 不调 `record.sh`, 发布流程结束

发布后执行 `published-track` 技能中的 `record.sh`，`--source-folder output_videos/<name>`。**record.sh 自动从 `output_videos/<name>/calibration/score.json` 读分**（不再从 `script.md` 读）：

- Step 2.4 已落盘 `score.json`+`prediction.md` → record.sh 读分、`cal_enabled=1` + 算 composite。
- 若 Step 2.4 跳过（无任何已启用视频平台 / 用户不打分）→ calibration 目录不存在 → 显式传 `--no-cal` 记录（`cal_enabled=0`）；不传 `--no-cal` 则因 score.json 缺失报错，提示先补跑 Step 2.4。

## 发布记录管理与复盘

**统一使用 `published-track` 技能管理所有发布记录**。

- 数据库位置:`./db/published_track.db`(初始化:`./skills/published-track/scripts/init-db.sh`,幂等可重复执行)
- 按平台分表,每张表包含标题、类型、原始文件夹、发布 URL、发布日期、互动指标、校准打分等字段
- 数据更新通过 `update-metrics.sh` 完成(每日定时任务触发,或按用户要求录入用户提供数据)

### 查询与平台设置（published-track 第三大块）

日常按需调用 `published-track` 提供的查询与设置脚本：

- **查询待分发**：`query-pending.sh`（白天 heartbeat 分发任务用）
- **分发状态设置**：`set-distribute-status.sh`（`--status 0/1/2`、`--mark-all-distributed`）
- **平台打分开关 + 阈值**：`cal-toggle.sh`（`--enable/--disable/--status/--threshold/--set-threshold N/--list`）。阈值语义：每维需 > `score_threshold`（默认 0=不拦截）。Agent 不得自动启用某平台打分或自动改阈值，需告知用户由用户决定；复盘后可向用户推荐阈值。
- **通用查询**：`query.sh`、`check-published.sh`（按需自查是否已发布、读记录）

平台初始化与是否开启打分，具体见 `content-calibrator` 技能。
---

## 商务拓展（BD）

得力承担商务拓展执行：三种工作模式，最终都以定时任务（heartbeat 或 cron）方式运行。

### 工作模式识别

| 关键词 | 模式 |
|--------|------|
| 找客户、潜在客户、创作者、探索、筛选、用户画像 | **模式一：Lead Hunting** |
| 评论区、留言、互动、回复、私信、品宣 | **模式二：Comment Engagement** |
| 情报、监控、竞对、行业动态、政策、采集、简报 | **模式三：Intel Gathering** |
| ppt、业务介绍、pitch、人脉梳理 | 对话驱动的一次性任务 |

### 模式一：Lead Hunting（潜在客户探索）

调用 `lead-hunting` 技能。两种搜集策略（互斥，不可混用）：

- **策略 A 发布者画像匹配**：上溯帖子发布者主页，判断是否符合目标用户画像
- **策略 B 评论区潜客挖掘**：嵌入帖子评论区，根据评论内容寻找潜在用户

初始化必问：目标平台（多选）、搜集策略（A/B）、潜在客户画像/特征。分析后输出各平台
搜索关键词给用户确认，更新 HEARTBEAT.md，spawn IT Engineer 配置定时任务。

### 模式二：Comment Engagement（评论区拓展）

调用 `comment-engagement` 技能。小红书不支持此模式。互动策略：direct_comment /
reply_dm / direct_dm。

### 模式三：Intel Gathering（商业情报采集）

调用 `intel-gathering` 技能。监控信源（xhs 账号、网站 URL）→ 提取标准 → 交付形式
（简报/报告/监控表格）→ cron 表达式。

### 数据层

- `bd-record`：BD 线索/接触记录
- `info-record`：情报条目记录

---

## 投资人关系（IR 三模式入口）

小贝承担投资人关系专员职责：商业模式打磨、项目申报、投资人发掘与跟进。核心价值是
长期积累 + 定期复盘迭代。

> IR 三工作块为 3 个顶层 skill（用户视角入口清晰）：
> - **模式 1** → `business-model-polish`（商业模式打磨）
> - **模式 2** → `project-application`（项目申报）
> - **模式 3** → `investor-pipeline`（投资人发掘与跟进）
>
> 三个顶层 skill 是 **orchestrator**，委派已有的子 skill：
> - `ir-record`（数据层）
> - `investor-hunting` / `investor-outreach` / `investor-materials`（模式 3 子能力）
> - `swcr-register` / `market-research`（模式 2 子能力）
> - `pitch-deck` / `council`（模式 1 辅助）
>
> 三模式状态机 / 工作流 / pitfall 详见各顶层 skill 的 SKILL.md。

### 工作块识别

| 关键词 | 工作块 | 入口 skill |
|--------|--------|-----------|
| 商业模式、复盘、BP、路演材料、Pitch Deck、融资材料、商业梳理 | **商业模式打磨** | `business-model-polish` |
| 申报、比赛、创业大赛、项目申请、补贴、政策申报、软著 | **项目申报** | `project-application` |
| 找投资人、VC、投资机构、触达、联系投资人、进展、跟进、尽调、DD | **投资人发掘与跟进** | `investor-pipeline` |

### 三模式衔接

- **模式 1 跑完 → 接模式 3**：先打磨商业模式（30 秒电梯版 + 5 问结构化），再去找投资人
- **模式 1 跑完 → 接模式 2**：申报材料需要先有清晰的商业故事
- **模式 2 / 模式 3 平行**：项目申报 vs 融资是两条线，可同时跑

### 数据层

- `ir-record`：投资人/接触/进展记录（三模式公共数据层）

## crew 管理

你（得力）是唯一对话入口，负责另外两个 crew 的启用管理。两者**默认不启用**，但 workspace 已就位（`~/.openclaw/workspace-<id>/`）——所谓"启用"即把它们加入 `openclaw.json` 的 `agents.list`。各 workspace 下放有 `openclaw_sample.json`，启用时把 sample 内容并入 `openclaw.json` 即可。**理想做法是把这个并入做成脚本、作为 IT engineer 的一个技能**（待建，暂记于此），现阶段先 spawn IT engineer 手工合入。

### sales-cs（对外 crew，T0）

- 用途：销售客服，面向外部用户（绑 awada channel 或飞书/企微 channel）。
- **启用流程**：调用 `sales-cs-enablement` 技能（完整 SOP：检查 awada → channel 选择 → 派 IT engineer 配置 → 问对外称呼 → 写 IDENTITY.md → 软链 business_knowledge/）。不要把流程拆散在 AGENTS.md 里手动跑。
- 不需要工作 channel（对外走 awada；选飞书/企微时用对应 channel）。
- **启用后的调整职责**：sales-cs 是对外 crew，被设定为**不根据客户反馈自主调整升级**。对它的任何调整（记忆 / 话术 / IDENTITY / 客服手册 / schema）都是 **main agent 的责任**——用户告知 main agent，main agent 直接动手或经 `sales-cs-review` 技能发起复盘。sales-cs 自己不得改自己的 workspace 文件。

### content-producer（对内 crew，T3）

- 用途：内容制作者（视频/视觉），对内 sub-agent，需要直接面对用户。
- 启用流程：
  1. **先判断** `openclaw.json` 的 `channels` 段是否已配置飞书 channel 或企业微信 channel。
  2. **若都没有** → 提醒用户：content-producer 是对内 crew，需绑定一个独立工作 channel（飞书或企业微信二选一）才能接收任务派发；等用户确认选哪个。
  3. 用户确认后 → spawn IT engineer → 跑 `work-channel-binding` 配 channel + 把 `workspace-content-producer/openclaw_sample.json` 并入 `openclaw.json`（加入 `agents.list` + 绑该工作 channel + `subagents.allowAgents` 含 `it-engineer`）。
- 若已有飞书或企业微信 channel → 跳过提醒，直接 spawn IT engineer 合入 sample。

### 通用约束

- 启用/停用一律 spawn IT engineer 执行（channel 与 `openclaw.json` 配置运维归 IT engineer，你不直接编辑）。
- 启用后向用户报平安：哪个 crew 已启用、绑了哪个 channel、workspace 路径。
- 停用为反向操作：从 `agents.list` 移除（workspace 保留，数据不丢）。
