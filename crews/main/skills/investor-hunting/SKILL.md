---
name: investor-hunting
description: 通过搜索渠道主动发掘潜在投资人/投资机构，筛选匹配度，去重记录，可选触达。参照 BD lead-hunting 模式，针对投资人场景定制。
metadata:
  openclaw:
    emoji: 🔍
---

# Investor Hunting 技能

通过搜索渠道主动发掘潜在投资人/投资机构，按匹配度筛选，去重记录到 ir-record，可选发起触达。

**依赖技能**：`smart-search`（构造搜索 URL）、`browser-guide`（浏览器操作）、`investor-outreach`（触达话术）、`email-ops`（邮件）、`ir-record`（去重记录）

---

## 前置条件

执行前需确认以下信息：
- 目标投资人类别（angel/vc/pe/cvc）和关注领域
- 搜索渠道列表及对应搜索关键词
- 匹配度判定标准（投资阶段、领域、管理规模、已投案例等）
- 每次最大探索量
- 反馈形式（列表报告 / Email 联系 / 社交平台触达）

---

## 搜索渠道

| 渠道 | 方式 | 说明 |
|------|------|------|
| 投资数据库 | smart-search + browser | IT桔子、企查查、天眼查——搜索投资事件、机构列表 |
| 融资新闻 | smart-search | 搜索"XX轮融资"、"XX领投"——从新闻中提取参投方 |
| 竞品融资记录 | smart-search | 搜索竞品融资新闻，提取其投资人作为潜在目标 |
| 社交平台 | smart-search + browser | 微博/小红书/即刻——搜索投资人内容、创投圈讨论 |
| LinkedIn | browser-guide | 搜索投资人 profile（需登录） |

---

## 执行流程

### Step 1: 准备工作

1. 读取 HEARTBEAT.md 获取当前配置（目标类别、渠道、关键词、判定标准、最大探索量）
2. 确保浏览器可用（遵循 browser-guide）
3. 初始化 ir-record 数据库（幂等）：`./skills/ir-record/scripts/init-db.sh`

### Step 2: 逐渠道搜索

对 HEARTBEAT.md 中配置的每个渠道，按顺序执行：

1. 使用 smart-search 技能构造该渠道的搜索 URL
2. 导航到搜索结果页，等待加载
3. 收集搜索结果中的投资人/机构信息（最多取配置的最大探索量）
   - 提取：姓名、机构、职位、关注领域、来源 URL

### Step 3: 逐投资人判定

对每个搜索到的投资人/机构，按顺序执行：

1. **去重检查**：
   ```bash
   ./skills/ir-record/scripts/check-investor.sh --name <姓名> --firm <机构名>
   ```
   如果 `{"exists": true}`，则跳过，继续下一个

2. **获取更多信息**（如搜索结果信息不足）：
   - 导航到投资人/机构详情页（投资数据库 profile、LinkedIn 等）
   - 读取投资偏好、已投项目、管理规模等信息

3. **匹配度判定**：
   - 按 HEARTBEAT.md 中预设的判定标准，判断是否为潜在投资人：
     - 投资阶段是否匹配（种子/天使/A轮/...）
     - 关注领域是否与公司业务相关
     - 管理规模是否在目标范围
     - 已投案例是否有同类/相邻赛道
   - 判定为潜在投资人需给出明确理由和匹配度评分（high/medium/low）

4. **记录到数据库**（不管是否符合标准）：
   ```bash
   ./skills/ir-record/scripts/record-investor.sh \
     --name <姓名> --type <angel|vc|pe|cvc|fo|other> --firm <机构名> \
     --title <职位> --email <邮箱> --source <来源> \
     --focus-areas <关注领域> --match-score <high|medium|low> \
     --status new --notes <判定理由>
   ```

5. **操作间隔**：每个投资人之间保持 30-60 秒间隔，避免平台风控

### Step 4: 汇总报告

1. 统计本批次结果：探索总数、符合数、跳过数（已记录）

2. 列出所有符合标准的潜在投资人：
   - 姓名、机构、职位、匹配度、关注领域、判定理由、来源

3. 按 HEARTBEAT.md 中配置的反馈形式执行：
   - **列表报告**：仅汇总报告，不触达
   - **Email 联系**：对 high 匹配度的投资人，使用 investor-outreach 生成话术，经用户确认后用 email-ops 发送
   - **社交平台触达**：对 high 匹配度的投资人，通过社交平台私信触达（需用户确认）

4. 使用 message 工具将汇总报告发送给用户

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 渠道搜索结果为空 | 记录渠道名称，跳过，继续下一个 |
| 投资人详情页无法访问 | 记录"无法访问"后跳过，不阻塞流程 |
| 浏览器异常 | 等待 30 秒后继续；若仍不行，等 30 秒再试；关闭重开后仍报错则停止并反馈用户 |
| 平台风控/验证码 | 停止当前渠道操作，记录并继续下一个 |
| 持续错误 | spawn IT Engineer 协助排查，当前任务标记为部分完成 |
