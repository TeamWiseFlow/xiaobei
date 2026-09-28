# 数据复盘 Workflow（xhs）

**xhs 的所有数据复盘工作都走这个 workflow**——heartbeat 按量触发的 DNA 评估、用户临时发起的"看看数据 / 复盘一下 / 评估这个 DNA"，统一从这里进。复盘一律**根据数据针对 DNA 做**，没有单篇复盘；复盘过程调用跨平台技能 `content-calibrator`（评估引擎：触发规则、账号基线归一化、趋势计算、证据聚合、报告结构）。

本 workflow 提供引擎没有的东西：**xhs 平台的归因方法**（指标语义、互动路径映射、DNA 维度回溯、平台混杂因素）。

## 入口判断

走本 workflow：
- heartbeat 凌晨任务：xhs 有 DNA 触发评估时
- 用户："看看数据怎么样" / "最近复盘一下" / "评估一下 dna-X" / "这个 DNA 最近表现如何" / "为什么没增长"

不走本 workflow：
- 对标账号 / 对标笔记分析 → `account-benchmark.md`
- 建 / 更新 DNA → `style-dna.md`
- 单篇数据疑问（"这篇阅读怎么低"）→ 不是复盘，agent 直接在账号与 DNA 上下文里回答（库内数据 + 下方诊断速查）；若发现指向 DNA 层面的系统性问题，引导用户发起本 workflow 的评估

## xhs 归因方法（平台特有，引擎不包含）

### 指标语义

xhs 互动数据由 `xhs-engagement` 从 Creator 已发作品接口抓取，统一为 5 列：

| 指标 | 含义与解读 |
|------|-----------|
| views | 阅读数（小眼睛），第一层转化结果；封面/标题点击率与推荐/搜索流量共同决定 |
| likes | 点赞，轻认可；与情绪共鸣、内容价值相关 |
| comments | 评论，互动设计 + 争议点 / 共鸣点决定；要读评论动机，不只数评论数 |
| favorites | 收藏，**实用价值信号**；"清单/教程/攻略/模板"类内容天然高；收藏率（收藏/点赞）反映内容可带走程度 |
| shares | 分享，最强传播信号；与选题社交货币属性、身份认同相关 |

数据限制（归因时必须如实标注）：

- Creator 数据分析可提供曝光和封面点击率，见 `pub_xhs.deep_metrics`；播放量足够且后台返回画像时，单篇观众画像见 `pub_xhs.fan_portrait`。缺失时不能推断为零。推荐/搜索/分享流量占比仍不可得，只能结合选题形态与关键词预埋做方向性推断，并标注为推断。
- 精确的传播系数（每次分享带来多少新观众）不可得；只能用 分享/(点赞+评论) 作为传播效率的代理估算。
- 用户可提供创作者中心后台截图（流量来源、粉丝画像、搜索词），作为更高置信度的证据；没有就用库内指标。

### 互动漏斗 → template 语义段 → DNA 维度映射

**图文作品（默认 `dna-0`）**

| 漏斗卡点 | 先怀疑的 template 语义段 | 可回溯的 DNA 维度 |
|---------|--------------------------|------------------|
| 阅读低（推荐/点击瓶颈） | 选题、标题与封面、关键词与用户问题 | topic-angle、title-cover、search-intent |
| 阅读正常但收藏低 | 内容创意与结构、正文表达 | content-idea、body-voice |
| 阅读正常但评论低 | 业务植入与 CTA、内容创意 | interaction-cta、biz-implant、content-idea |
| 点赞低 | 内容创意、正文表达 | content-idea、body-voice |
| 分享低 | 选题、正文表达 | topic-angle、body-voice |
| 关注转化低 | 账号运营子模块、业务植入与 CTA | account-bio、content-mix-cadence、interaction-cta |
| 进店 / 咨询 / 私信转化低 | 业务植入与 CTA | biz-implant、interaction-cta |
| 广告感重（收藏高但评论转冷、负面评论） | 业务植入与 CTA、选题 | biz-implant、interaction-cta、topic-angle |
| 搜索流量弱 | 关键词与用户问题、标题与封面 | search-intent、title-cover |
| 图组跳失 / 图片被吐槽 | 图组、标题与封面 | imageset-visual、title-cover |

**视频作品（`dna-*-video`）**

| 漏斗卡点 | 先怀疑的 template 语义段 | 可回溯的 DNA 维度 |
|---------|--------------------------|------------------|
| 播放低 | 选题、标题与封面、关键词与用户问题 | topic-angle、title-cover、search-intent |
| 完播估算低 | 内容创意、制作规格、口播文案 | content-idea、production-spec、narration-script |
| 搜索流量弱 | 关键词与用户问题 | search-intent |
| 关注转化低 | 账号运营子模块、业务植入与 CTA | account-bio、content-mix-cadence、interaction-cta |
| 进店 / 咨询转化低 | 业务植入与 CTA | biz-implant、interaction-cta |

### 平台混杂因素（归因前必排）

1. **账号成熟度**：新号数据天然低、老号天然高；跨账号绝对值不可比，只看同账号比值与走向。
2. **品类基线差异**：不同赛道互动基线差异极大；不要拿通用阈值判断，优先用该账号自身历史与同赛道对标（`account-benchmark.md` 数据）作参照。
3. **推荐池波动**：小红书推荐放量或收紧造成整体水位漂移——同账号全部作品同步涨跌 → 平台因素，不是 DNA 因素。
4. **选题热度**：热点选题自带流量；单篇突增先查选题是否踩中时效话题。
5. **发布时间与节假日**：工作日 12:00-13:00、18:00-21:00 等高峰时段差异；长假浏览习惯变化。
6. **投流干扰**：薯条 / 聚光等投放带来的增量不是内容能力；有投流的作品单独标注。
7. **限流 / 违规**：检查是否有违规提示、笔记仅自己可见、审核不通过等风控信号；有则先处理合规问题，不做风格归因。
8. **竞品分流**：同赛道新账号或同类内容集中爆发造成相对下滑。

**替代假设纪律**：下任何归因结论前（如"衰退原因是钩子疲劳"），必须逐条检验上表并输出检验结果；排不掉混杂的写「观察」，不写「结论」。未完成检验的归因必须标注"未经替代假设验证，置信度：低"。

## 评估流程

### Step 0 - 确定评估对象

```bash
content-calibrator eval --platform xhs --check
```

- **heartbeat 路径**：全部 `triggered=false` → 在汇总里报各 DNA 待评估进度（n/5），本 workflow 结束；有 `triggered=true` → 对每个触发 DNA 走 Step 1。
- **用户路径**：用户点名某 DNA → 该 DNA 未达阈值时用 `--dna-id <id> --force`；未点名 → 先看 `--check`，优先评估已触发 DNA，都未触发时问用户是否强制评估某个 DNA。

### Step 1 - 聚合证据

```bash
content-calibrator eval --platform xhs                    # 全部触发 DNA
content-calibrator eval --platform xhs --dna-id <id>      # 指定 DNA
```

输出逐条绝对值 + 同账号基线比值 + 每指标趋势走向；`baseline_insufficient` 的记录只作绝对观察。

### Step 2 - 归因分析

按上方「xhs 归因方法」执行，同时遵守 `content-calibrator` 的共性归因原则（趋势优先 / 证据可追溯 / 先排混杂）：

1. 判定只看比值与走向，绝对值只作上下文。
2. 逐条排除平台混杂因素，输出替代假设检验结果。
3. 回读 `xhs/dna/<dna-id>/<dna-id>.dna.md` / `.template.md` 与待评估作品（`source_folder` 下的 `note.md`、`brief.md`、`voiceover.md` 与图片/成片线索），把趋势变化落到 template 语义段与 DNA 维度。

### Step 3 - 报告与标记

1. 写评估报告到 `xhs/dna/<dna-id>/evals/{YYYY-MM-DD}.eval.md`，结构按 `content-calibrator` 的评估产物要求（整体判定 / 趋势表 / template 归因 / 逐条建议 / 观察区）。
2. 标记覆盖的记录，防下轮重复评估：

```bash
content-calibrator eval --platform xhs --mark-evaluated --ids <本轮记录 id，逗号分隔>
```

### Step 4 - 出口

- 向用户呈现：整体判定 + 逐条优化建议（每条注明目标维度 / template 部分与证据篇目）。用户临时发起的复盘可附周复盘视角：本周发布、最高 / 最低信号、有效钩子、有效关键词、有效封面、评论素材、失败假设、下一轮实验（一次只验证一个变量）、停做事项。heartbeat 场景在凌晨汇总里上报，**不唤醒用户**。
- 用户逐条确认后，采纳的建议走 `style-dna.md`「表现反馈」转译进 DNA；**Agent 不得自动更新 DNA**。
- 不涉及风格规则的业务动作（选题方向、栏目增减、发布节奏）直接给行动项，不进 DNA。

## 执行纪律

- 复盘前看指标更新时间：`xhs-engagement daily` 每日采集 Creator 最近三页作品并更新数据库，旧作品不在本轮窗口内时沿用原有时间戳。用户临时发起复盘时先基于有时间戳的库内数据说明新鲜度；用户要求先更新较早作品时可运行 `xhs-engagement fetch-all`，并只以实际写入成功的作品作为本轮新数据。
- heartbeat isolated 会话中本流程由**主 agent inline 执行**，不 spawn subagent、不 sessions_yield（评估需连续回读多文件，隔离会话本就无上下文污染）。
- 估算值必须标注"估算"和估算方法；不可得的数据维度写明"数据不可得"，不跳过、不暗示。
