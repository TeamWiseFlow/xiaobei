# HEARTBEAT_TEMPLATE

此文件为 HEARTBEAT.md 的写入模板。当用户确认某个工作模式的配置后，参照以下格式将对应模式写入 HEARTBEAT.md。

**原则**：只写入用户实际启用的模式，不要预填未启用的模式。

> 本模板覆盖的是 main agent（小贝）的 BD / IR 两个工作条块的定时模式。新媒体运营的「每日平台数据复盘」不在此模板内——它默认已在 HEARTBEAT.md 中，由 IT engineer 设 cron 激活执行。BD / IR 模式从本模板复制到 HEARTBEAT.md 后，同样需 spawn IT engineer 设 cron。所有已启用的定时任务应在 MEMORY.md「已启用的定时任务」段登记。

---

## 商务拓展（BD）

### 模式一：Lead Hunting（潜在客户探索）

```markdown
### Lead Hunting（潜在客户探索）

**状态**：已启用

**搜集策略**：<A 发布者画像匹配 / B 评论区潜客挖掘>

**目标平台**：
- xhs：<关键词1>、<关键词2>
- dy：<关键词1>、<关键词2>
- web：<站点URL>：<搜索关键词>

**潜在客户判定标准**：
- 策略 A（发布者画像匹配）：
  - 符合特征：
    - <特征描述1>
  - 排除特征（同行/竞对）：
    - <特征描述1>
- 策略 B（评论区潜客挖掘）：
  - 纳入评论特征：
    - <特征描述1>
  - 排除评论特征：
    - <特征描述1>

**执行参数**：
- 频率：<每天N次 / 每N小时>
- 每次最大探索量：<N个创作者 / N个帖子>
- 反馈形式：<列表报告 / Cold Touch 私信 / Email 联系>（策略 B 及 xhs 仅支持列表报告）
- Cold Touch 话术：<话术内容>
- Email 话术：<话术内容>

**执行**：调用 `lead-hunting` 技能
```

### 模式二：Comment Engagement（评论区拓展）

> ⚠️ 小红书不支持此模式。

```markdown
### Comment Engagement（评论区拓展）

**状态**：已启用

**目标平台**：
- dy：<关键词1>
- fb：<关键词1>

**互动策略**：<direct_comment / reply_dm / direct_dm>

**互动话术**：
- <话术内容>

**执行参数**：
- 频率：<描述>

**执行**：调用 `comment-engagement` 技能
```

### 模式三：Intel Gathering（商业情报采集）

```markdown
### Intel Gathering（商业情报采集）

**状态**：已启用

**监控信源**：
- xhs - <账号名/ID>：<监控说明>
- <网站URL>：<监控说明>

**提取标准**：
- <要提取的信息描述>

**交付形式**：<简报 / 报告 / 监控表格>

**执行时间**：<cron 表达式，如 "0 8 * * *">

**执行**：调用 `intel-gathering` 技能
```

---

## 投资人关系（IR）

### 模式二：Investor Hunting（投资人搜索与触达 - 定时执行）

```markdown
### Investor Hunting（投资人搜索）

**状态**：已启用

**搜索目标**：
- 投资人类别：<天使/VC/PE/CVC/不限>
- 偏好领域：<行业/赛道>
- 地域：<国内/海外/不限>

**搜索渠道**：
- <渠道1>：<搜索关键词>
- <渠道2>：<搜索关键词>

**筛选标准**：
- 匹配特征：
  - <特征描述1>
  - <特征描述2>
- 排除特征：
  - <特征描述1>

**执行参数**：
- 频率：<每天N次 / 每N小时>
- 每次最大搜索量：<N个>
- 自动触达：<是/否>
- 触达话术：<话术内容（如启用自动触达）>

**执行**：按 AGENTS.md IR 模式二流程执行
```

### 模式三：Relationship Tracking（投资人关系维护 - 定时跟进）

```markdown
### Relationship Tracking（关系跟踪）

**状态**：已启用

**跟进规则**：
- 超过 <N> 天未跟进的活跃投资人 → 提醒用户
- 尽调中的投资人 → 每天检查是否有更新
- 每周一生成 Pipeline 摘要

**执行**：
1. 运行 ir-record 进度查询
2. 检查是否有超期未跟进的投资人
3. 如有新进展，更新 MEMORY.md 中的 Pipeline 表
4. 如有需要关注的事项，汇总后推送给用户
```

---

### IR 模式 3 巡检

> 投资人跟进状态机：`new → contacted → bp_sent → meeting → dd → ts → invested/passed`
>
> **7 天过期提醒**：本节新增，配合 `crews/main/skills/ir-record/scripts/query-stale.sh` 使用。

**触发条件**：凌晨复盘心跳 Step 2 数据抓完后，**Step 4 用户咨询回复**之前插一个 Step 2.5。

**Step 2.5 · 投资人过期巡检**：

```bash
# 查 7 天无 contact 进展的投资人
./skills/ir-record/scripts/query-stale.sh --days 7
```

输出 JSON list（按 `days_since_last` 降序），每条含 `id` / `name` / `firm` / `status` / `match_score` / `last_contact_date` / `next_step` / `days_since_last`。

**处理规则**：
- `status` ∈ {`new`, `contacted`, `bp_sent`, `meeting`, `dd`, `ts`} 且 `days_since_last > 7` → **STALE**，加入"待跟进"列表
- `status` ∈ {`invested`, `passed`} → **跳过**（已完结）
- `match_score` = `low` → **跳过**（非重点关注）

**汇报**（Step 5 总报告里加一段）：

```
## IR 巡检
共 N 个投资人超过 7 天无进展，重点跟进：
- 张三 @ 红杉（status=meeting, 13 天无进展, last next_step=5/20 约下轮 meeting）
- 李四 @ 真格（status=bp_sent, 9 天无进展, last next_step=5/24 follow up BP）
（其他 N-K 个已完结 / 非重点，已自动跳过）
```

**约束**：
- 7 天阈值是**默认值**，用户可在 `ir-record/.config.json` 改（待实现）
- 凌晨不主动发起新接触（用现有 `next_step` 提醒用户白天处理）
- 不在心跳里改 `status`（用户白天自己决定推进 / 标记 passed）

---

### BD 三能力巡检

> 配合 `lead-hunting` / `comment-engagement` / `intel-gathering`（已搬入 main/skills）+ `bd-record` / `info-record` 数据层。
>
> **保留 heartbeat 写入模式**：本节定义 BD 的心跳触发 + 数据层写入，**不**在心跳里改用户已建档的线索状态（用户白天决定推进 / 标记 passed）。

**触发条件**：凌晨复盘心跳 Step 5 报告后接 Step 6（BD 巡检）。

**Step 6 · BD 三能力巡检**：

| 模式 | 入口 | 数据层 | 心跳动作 |
|------|------|--------|----------|
| 模式 1 Lead Hunting | `lead-hunting` 技能 | `bd-record` 模式一表（已探索创作者） | 按用户已配置的策略 A/B + 平台 + 关键词，扫一遍最近 N 天的内容，写入 `bd-record` |
| 模式 2 Comment Engagement | `comment-engagement` 技能 | `bd-record` 模式二表（已互动帖子） | 按用户已配置的策略（direct_comment / reply_dm / direct_dm）+ 帖子清单，互动一批 → 写入 `bd-record` |
| 模式 3 Intel Gathering | `intel-gathering` 技能 | `info-record` 情报条目表 | 按用户已配置的监控信源 + 提取标准，采一遍 → 写入 `info-record` |

**3 个模式都按 cron 周期执行**（用户配的 everyday 凌晨 3 点），而不是手动触发。心跳不发起新接触（除模式 2 互动按用户策略批跑）。

**初始化必问**（用户首次启用时）：
- 目标平台（多选，BD 支持 xhs / 视频号 / 抖音 / 知乎等；xhs 走 `xhs-interact`，视频号走 `wechat-channels-publish`）
- 模式 1 搜集策略（A 发布者画像 / B 评论区挖掘）
- 模式 2 互动策略（direct_comment / reply_dm / direct_dm）
- 模式 3 监控信源（账号列表 / URL 列表）
- 提取标准（"什么算符合目标的"）
- 交付形式（简报 / 报告 / 监控表格）
- cron 表达式

初始化完成后，更新 HEARTBEAT.md 的本节配置，spawn IT engineer 配置定时任务。

**汇报**（Step 5 总报告里加一段）：

```
## BD 巡检
- 模式 1 Lead Hunting:扫了 X 个新内容，发现 Y 个潜在客户（已写入 bd-record）
- 模式 2 Comment Engagement:对 Z 个帖子互动（已写入 bd-record）
- 模式 3 Intel Gathering:采集 W 条情报（已写入 info-record）
（其他 0 项的模式跳过）
```

**约束**：
- 不主动帮用户发起 BD 接触（用户说"现在要联系 X 客户"才执行）
- 不修改 `bd-record` / `info-record` 中用户已建档的条目
- 凌晨不扫码登录（cookie 失效 → 跳过该平台，记入 `EXPIRED_PLATFORMS`）

---

## 多模式并存

如用户启用了多个模式，HEARTBEAT.md 中按顺序排列已启用的模式，各模式之间用 `---` 分隔。

## 模式禁用

如用户要求停用某个模式，从 HEARTBEAT.md 中删除对应配置段落，并 spawn IT Engineer 移除对应的定时任务配置。
