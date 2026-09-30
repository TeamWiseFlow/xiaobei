# 定时执行（可选）

> 本文件是 `expert-bd` 专家包附属说明：BD 各 workflow 如何落为定时任务。

**原则**：`expert-bd` 的所有 workflow 默认按**一次性任务**执行。**仅当用户明确希望周期性执行**（如每天一次、每周一次）时，才将配置写入 workspace 的 `HEARTBEAT.md` 并配 cron。不要主动建议或预填定时任务。

## 启用流程

1. 先按对应 workflow 跑通一次，与用户确认全部配置要素（平台 / 关键词 / 策略 / 信源 / 提取标准 / 交付形式）。
2. 参照下方模板，把**用户实际启用的模式**写入 `HEARTBEAT.md`（不要预填未启用的模式；多模式并存时按顺序排列，模式之间用 `---` 分隔）。
3. spawn IT engineer 按段内执行时间 / 频率配置 cron。
4. 在 `MEMORY.md`「已启用的定时任务」段登记任务名、cron 表达式与启用日期。

## 停用流程

从 `HEARTBEAT.md` 删除对应配置段落，spawn IT engineer 移除对应 cron，并从 `MEMORY.md` 登记段移除。

---

## HEARTBEAT.md 写入模板

### Lead Hunting（潜在客户探索）

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

**执行**：按 `expert-bd` 的 Lead Hunting Workflow 执行
```

### Intel Gathering（商业情报采集）

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

**执行**：按 `expert-bd` 的 Intel Gathering Workflow 执行
```

### Competitor Watch（竞争对手 / 重点客户动向监控）

```markdown
### Competitor Watch（动向监控）

**状态**：已启用

**监控对象**：
- 竞品 - <对象名>：<信源列表>
- 客户 - <对象名>：<信源列表>

**动向提取标准**：
- <什么算动向>

**交付形式**：<重大动向即时告警 + 定期简报 / 仅简报 / 仅监控表格>

**执行时间**：<cron 表达式>

**执行**：按 `expert-bd` 的 Competitor Watch Workflow 执行
```

---

## 定时执行约束（心跳批跑时）

- **只在心跳里批跑用户已配置的策略**，不发起配置外的接触；不主动帮用户发起 BD 接触（用户说"现在要联系 X 客户"才执行）。
- **不修改 `bd-record` / `info-record` 中用户已建档的条目**（推进 / 标记 passed 由用户白天决定）。
- **凌晨不扫码登录**：cookie 失效 → 跳过该平台，记入 `EXPIRED_PLATFORMS`，白天提醒用户重登。
- 各模式仍受平台风控与工具自身频率限制约束（见各工具说明）。

## 汇报格式（心跳总报告加一段）

```
## BD 巡检
- Lead Hunting：扫了 X 个新内容，发现 Y 个潜在客户（已写入 bd-record）
- Intel Gathering：采集 W 条情报（已写入 info-record）
- Competitor Watch：识别 V 条动向，重大 M 条（已告警 / 已写入 info-record）
（无新内容的模式跳过）
```
