# 心跳/定时任务

## 凌晨复盘任务

### 执行约束

1. **无时间限制**:任务执行不受深夜时间限制,必须执行完 HEARTBEAT 清单全部内容

2. **遇到技术故障时处理方案**:

   - **spawn IT Engineer**协助解决:调用 `sessions_spawn`,将问题现象、错误信息、当前任务上下文完整传递给 IT Engineer,请它协助解决。**spawn 后 fire-and-forget,严禁 `sessions_yield` 等待**——IT Engineer 的结果通过 announce 异步回来,若没回来按下一条跳过继续(见下方约束 3);
   - 仍无法解决 → **跳过当前任务,继续执行后续步骤**,不要卡住整个 HEARTBEAT

   不可:
      - ❌ 呼唤用户协助解决,HEARTBEAT 在深夜执行,喊用户也没用
      - ❌ 不可中断任务,通过以上三步依然无法进行的任务则跳过,继续执行后续步骤,绝对不允许中断HEARTBEAT!

3. **⛔ cron/heartbeat isolated session 中禁止 `sessions_yield`,原则上也不 spawn subagent**:

   本任务由 cron 以 `session_target=isolated` 启动,**本身已是独立上下文**,不占主 agent 上下文、不阻塞主 session。再 spawn subagent 是零收益纯增复杂度,且 `sessions_yield` 会**直接 abort 当前 run**,cron 将 yield 视为 run 结束并标记 outcome,session 变 inactive;subagent 完成后的 announce 找不到可唤醒的活跃 session,retry 3 次后 give-up,**后续 Step 全部丢失**。

   - 所有 Step 1–4 **顺序内联执行**,评估报告等产出主 agent 自己写,不 spawn subagent、不 `sessions_yield`。
   - 唯一允许 spawn 的是约束 2 的「故障兜底 spawn IT Engineer」,且必须 fire-and-forget(不 yield)。

4. **⛔ 登录失效一律「跳过 + 记录 + 汇总上报」，严禁硬行恢复登录**

   任何平台的取数端登录失效（`SESSION_EXPIRED` / 探活失败 / 浏览器跳登录页等）时，**必须**：
   - 立即**跳过该平台**本轮取数，不再尝试任何取数动作；
   - 把平台名记入 `EXPIRED_PLATFORMS`，在 Step 4 统一汇报，由用户**白天**重新登录；
   - **不得**在凌晨心跳里扫码登录、不得唤醒用户。

   **严禁的"硬行恢复"动作**（任一都可能触发平台风控/限流/封号）：
   - ❌ 用 CDP `Network.setCookies` 把本地存的 cookie **注入**浏览器去"造"一个登录会话
   - ❌ 反复刷新/重导航 profile 页试图"刷出"登录态

   > 本规范下方 Step 1 / Step 4 已写明，但 **2026-06-29 凌晨 Agent 未遵守**：xhs-browse 浏览器无登录态时，Agent 用 CDP 注入 22 个 cookie 强造会话后批量抓取，**当日触发小红书风控、账号被处罚**。故在此特别前置强调。

5. **⚠️ 小红书 (xhs) 封号风险显著高于其他平台**

   - xhs 对「会话凭空 materialize + 短时批量签名请求」极度敏感，**一次** CDP 注入 cookie + 批量 feed 抓取就可能触发风控/限流/封号。
   - xhs 任何登录失效迹象 → **立刻整段跳过 xhs**，不要尝试任何恢复，记入 `EXPIRED_PLATFORMS` 等白天重新登录。
   - 取数走 `xhs-engagement`；

---

### 工作流程

#### Step 1: 各平台已发布作品取数

按下表从上到下顺序执行。每个平台先查询启用状态，仅返回 `ok=true, enabled=true` 时执行该平台批量取数命令一次；未启用直接跳过，状态读取失败记入汇总后继续下一平台。

| 平台专家包 | 状态查询 | 批量取数命令 |
| --- | --- | --- |
| expert-douyin | `published-track platform-status --platform douyin` | `douyin-engagement daily` |
| expert-xhs | `published-track platform-status --platform xhs` | `xhs-engagement daily` |
| expert-wx-channel | `published-track platform-status --platform wx_channel` | `wx-channel-engagement fetch-all` |
| expert-wx-mp | `published-track platform-status --platform wx_mp` | `wx-mp-engagement fetch-all` |

- 取数窗口、作品匹配、分页和指标来源按对应专家包的 engagement 工具说明执行；由工具回填 `published-track`，心跳不额外逐条取数或补翻页。
- 按各工具的逐条结果汇总完整成功、部分成功、跳过和失败。提供 `complete` 时，`complete=false` 必须报告缺项；有 `unavailable` / `unavailable_reasons` 或分析错误时，列出本次实际取得的指标、缺项及原因。缺失值不填零，不把保留的旧值算作本次取得；`ok=true` 不代表所有指标齐全。
- 失败保留原始输出及退出码。登录失效或超时（如 `SESSION_EXPIRED`、`API_SESSION_MISSING`、`API_SESSION_EXPIRED`、`RUNTIME_EXPIRED`、`PLATFORM_AUTH_REJECTED`、`PLATFORM_LOGIN_REJECTED` 或 exit 2）记入 `EXPIRED_PLATFORMS`；身份验证待处理也记入汇总。停止该平台本轮后续取数，继续下一平台，不自动重新登录或发送验证码。
- `NOT_ON_FIRST_PAGE` 按对应工具规则跳过该记录；`CREATOR_ITEM_NOT_FOUND` 保留作品 ID 并报告待核对链接及账号，不按标题猜作品 ID。

目前定时取数支持表内四个平台，其他平台跳过。全部平台处理后进入 Step 2。

---

#### Step 2: content-calibrator DNA 表现评估（按量触发）

数据采集每天跑，但 DNA 评估**按量触发**——每个（平台, DNA）的成熟待评估记录（发布 ≥3 天 且 `perf_evaluated=0`）累积 **≥5 条**才评估一轮。先跑廉价阈值检查（各启用平台各一次）：

```bash
content-calibrator eval --platform <platform> --check
```

返回 JSON：`{dnas: [{dna_id, pending, triggered}]}`
- 全部 `triggered=false` → 本轮评估跳过，不消耗后续 token
- 有 `triggered=true` 的 DNA → 进入 评估

**对于douyin/wx_mp/wx_channel/xhs平台** → 走该平台专家包内的 review workflow

> 触发的 DNA 属于哪个平台，就按该平台专家包的 review workflow 执行完整复盘（聚合、平台归因、写报告、标记全在 workflow 内；**workflow 不取数**——本轮数据已在 Step 1 采集就位）：

> - **wx_mp** → expert-wx-mp 的 Review Workflow（`skills/expert-wx-mp/workflows/review.md`）
> - **douyin** → expert-douyin 的 Review Workflow（`skills/expert-douyin/workflows/review.md`）
> - **wx_channel** → expert-wx-channel 的 Review Workflow（`skills/expert-wx-channel/workflows/review.md`）
> - **xhs** → expert-xhs 的 Review Workflow（`skills/expert-xhs/workflows/review.md`）

**对于其他平台** → 尚未匹配DNA系统，直接跳过此步

**Agent 不得自动更新 DNA**——评估建议经 Step 4 上报，用户逐条确认后走对应平台专家包的 style-dna workflow 回写。

---

#### Step 3: 用户咨询回复

> 现阶段暂时跳过

巡检如下平台：，针对项目咨询类的留言、回复、私信进行简短回复,如:

```
项目那里下载?
怎么用?
代码仓在哪里?
支持 xxx 功能吗?
...
```

---

#### Step 4: 汇总执行情况报告用户

汇总执行情况，反馈用户。报告内容：

1. 各平台数据更新情况（完整成功/部分成功/跳过/失败数量；部分成功列出作品 ID、缺失指标及原因）
2. **取数端登录态失效列表**（如有）：
   > ⚠️ 以下**取数端**登录态已失效，数据未能更新。请白天通知小贝重新登录：
   > - douyin（抖音）
   > - xhs-creator-local（小红书创作者端）
   > - wx-channel（微信视频号)

3. DNA 表现评估摘要（如有）：列出本轮评估的 DNA（平台 / dna-id / 覆盖篇数）+ 整体判定（改善 / 平稳 / 下滑）+ 关键归因；无触发 DNA 时写「无 DNA 达到评估阈值」并附各 DNA 待评估计数。
4. **DNA 优化建议待确认（如有）**：列出评估报告中的逐条建议（建议内容 + 目标维度/template 部分 + 证据篇目）。**Agent 不得自动更新 DNA**。用户白天逐条确认后，指示走对应平台专家包的 style-dna workflow 回写 DNA。
5. 用户咨询回复摘要。

发送后本次定时任务结束。
