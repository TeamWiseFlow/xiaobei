# 数据复盘 Workflow（douyin）

**douyin 的所有数据复盘工作都走这个 workflow**——heartbeat 按量触发的 DNA 评估、用户临时发起的"看看数据 / 复盘一下 / 评估这个 DNA"，统一从这里进。复盘一律**根据数据针对 DNA 做**，没有单篇复盘；复盘过程调用跨平台技能 `content-calibrator`（评估引擎：触发规则、账号基线归一化、趋势计算、证据聚合、报告结构）。

本 workflow 提供引擎没有的东西：**douyin 平台的归因方法**（指标语义、互动路径映射、DNA 维度回溯、平台混杂因素）。

## 入口判断

走本 workflow：
- heartbeat 凌晨任务：douyin 有 DNA 触发评估时
- 用户："看看数据怎么样" / "最近复盘一下" / "评估一下 dna-X" / "这个 DNA 最近表现如何" / "为什么没增长"

不走本 workflow：
- 对标账号 / 对标视频分析 → `account-benchmark.md`
- 建 / 更新 DNA → `style-dna.md`
- 单条数据疑问（"这条播放怎么低"）→ 不是复盘，agent 直接取数在账号与 DNA 上下文里回答；若发现指向 DNA 层面的系统性问题，引导用户发起本 workflow 的评估

## douyin 归因方法（平台特有，引擎不包含）

### 指标语义

| 指标 | 含义与解读 |
|------|-----------|
| plays | 播放数，第一层转化结果；标题/封面/推荐流量共同决定 |
| likes | 点赞，轻认可；与内容价值和结尾引导相关 |
| comments | 评论，互动设计 + 争议点 / 共鸣点决定；要读评论动机，不只数评论数 |
| shares | 分享，最强传播信号；与选题社交货币属性、实用价值相关 |
| favorites | 收藏，实用价值信号；"清单/教程/模板"类内容高 |

数据限制（归因时必须如实标注）：

- `douyin-engagement` 自动取数仅覆盖公开详情实际返回的点赞、评论、分享和收藏；播放量、完播、跳出、平均观看、曝光、点击率、画像及留存当前不自动获取。缺项标注不可得，库内默认零不能当作实测零。
- 播放量缺失或过期时不计算点赞率、评论率等以播放为分母的指标；根据可得互动量及同账号基线分析。不能从视频时长或互动量推导实测完播、跳出、观看时长，基础取数成功不代表后台数据完整。
- 精确的传播系数（每次分享带来多少新观众）不可得；只能用 分享/(点赞+评论) 作为传播效率的代理估算。
- 用户级留存数据不可得。
- 用户主动提供创作者中心截图、导出或深指标时，可作为补充证据；库内历史播放量和 `deep_metrics` 也必须核对采集时间、来源及口径，不能称为本次自动采集值。保留时间窗口，不能把 5 秒完播率当成整条完播率。

### 互动漏斗 → template 语义段 → DNA 维度映射（视频作品）

| 漏斗卡点 | 先怀疑的 template 语义段 | 可回溯的 DNA 维度 |
|---------|--------------------------|------------------|
| 播放低（推荐/点击瓶颈） | 选题、标题与封面 | topic-angle、title-cover |
| 点击后快速划走（有用户提供的观看证据） | 内容创意、制作规格、口播文案 | content-idea、production-spec、narration-script |
| 点赞低 | 内容创意、选题 | content-idea、topic-angle |
| 评论低 | 内容创意（讨论点）、口播文案 | content-idea、narration-script |
| 分享低 | 选题、内容创意 | topic-angle、content-idea |
| 收藏低 | 内容创意、制作规格 | content-idea、production-spec |
| 关注转化低 | 账号运营子模块、业务植入与 CTA | account-bio、content-mix-cadence、interaction-cta |
| 组件点击 / 私信 / 成交转化低 | 业务植入与 CTA | biz-implant、interaction-cta |
| 广告感重（负面评论、掉粉、植入点完播跳水） | 业务植入与 CTA、选题 | biz-implant、interaction-cta、topic-angle |
| 画面/时长/音色被吐槽 | 制作规格、视频形态与制作指向 | production-spec、video-form |

图文作品（`dna-*-note`）改按图文 template 语义段归因：选题、标题与封面、内容创意与结构、正文表达、图组、业务植入与 CTA，对应维度 `topic-angle`、`title-cover`、`content-idea`、`body-voice`、`imageset-visual`、`biz-implant`、`interaction-cta`。

### 平台混杂因素（归因前必排）

1. **账号成熟度**：新号数据天然低、老号天然高；跨账号绝对值不可比，只看同账号比值与走向。
2. **推荐池波动**：抖音推荐放量或收紧造成整体水位漂移——同账号全部作品同步涨跌 → 平台因素，不是 DNA 因素。
3. **选题热度**：热点选题自带流量；单条突增先查选题是否踩中时效话题。
4. **发布时间与节假日**：发布时段、长假期间刷视频习惯变化。
5. **投流干扰**：DOU+ 等投放带来的增量不是内容能力；有投流的作品单独标注。
6. **限流 / 违规**：检查是否有违规提示、仅粉丝可见等风控信号；有则先处理合规问题，不做风格归因。
7. **竞品分流**：同赛道新账号或同类内容集中爆发造成相对下滑。

**替代假设纪律**：下任何归因结论前（如"衰退原因是钩子疲劳"），必须逐条检验上表并输出检验结果；排不掉混杂的写「观察」，不写「结论」。未完成检验的归因必须标注"未经替代假设验证，置信度：低"。

## 评估流程

### Step 0 - 确定评估对象

```bash
content-calibrator eval --platform douyin --check
```

- **heartbeat 路径**：全部 `triggered=false` → 在汇总里报各 DNA 待评估进度（n/5），本 workflow 结束；有 `triggered=true` → 对每个触发 DNA 走 Step 1。
- **用户路径**：用户点名某 DNA → 该 DNA 未达阈值时用 `--dna-id <id> --force`；未点名 → 先看 `--check`，优先评估已触发 DNA，都未触发时问用户是否强制评估某个 DNA。

### Step 1 - 聚合证据

```bash
content-calibrator eval --platform douyin                    # 全部触发 DNA
content-calibrator eval --platform douyin --dna-id <id>      # 指定 DNA
```

输出逐条绝对值 + 同账号基线比值 + 每指标趋势走向；`baseline_insufficient` 的记录只作绝对观察。

### Step 2 - 归因分析

按上方「douyin 归因方法」执行，同时遵守 `content-calibrator` 的共性归因原则（趋势优先 / 证据可追溯 / 先排混杂）：

1. 判定只看比值与走向，绝对值只作上下文。
2. 逐条排除平台混杂因素，输出替代假设检验结果。
3. 回读 `douyin/dna/<dna-id>/<dna-id>.dna.md` / `.template.md` 与待评估作品原文（`source_folder` 下的转录 / Brief / 口播终稿），把趋势变化落到 template 语义段与 DNA 维度。

### Step 3 - 报告与标记

1. 写评估报告到 `douyin/dna/<dna-id>/evals/{YYYY-MM-DD}.eval.md`，结构按 `content-calibrator` 的评估产物要求（整体判定 / 趋势表 / template 归因 / 逐条建议 / 观察区）。
2. 标记覆盖的记录，防下轮重复评估：

```bash
content-calibrator eval --platform douyin --mark-evaluated --ids <本轮记录 id，逗号分隔>
```

### Step 4 - 出口

- 向用户呈现：整体判定 + 逐条优化建议（每条注明目标维度 / template 部分与证据篇目）。用户临时发起的复盘可附周复盘视角：本周发布、最高 / 最低信号、有效钩子、有效关键词、有效人格信号、评论素材、失败假设、下一轮实验（一次只验证一个变量）、停做事项。heartbeat 场景在凌晨汇总里上报，**不唤醒用户**。
- 用户逐条确认后，采纳的建议走 `style-dna.md`「表现反馈」转译进 DNA；**Agent 不得自动更新 DNA**。
- 不涉及风格规则的业务动作（选题方向、栏目增减、发布节奏）直接给行动项，不进 DNA。

## 执行纪律

- 复盘不取数：互动数据新鲜度由每日 `douyin-engagement daily` 采集并写入 `published-track` 保证；用户临时发起复盘时直接基于库内已有数据做，仅当用户明确要求“先更新数据”时才先调用 `douyin-engagement fetch --row-id <id>` 或 `daily`，再进入复盘。
- heartbeat isolated 会话中本流程由**主 agent inline 执行**，不 spawn subagent、不 sessions_yield（评估需连续回读多文件，隔离会话本就无上下文污染）。
- 估算值必须标注"估算"和估算方法；不可得的数据维度写明"数据不可得"，不跳过、不暗示。
