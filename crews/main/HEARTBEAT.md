# 心跳/定时任务

## 凌晨复盘任务

### 执行约束

1. **无时间限制**:任务执行不受深夜时间限制,必须执行完 HEARTBEAT 清单全部内容

2. **遇到技术故障时处理方案**:

   - 先尝试彻底关闭浏览器,再打开(使用默认 `openclaw` profile);
   - 重启浏览器不解决问题时,**spawn IT Engineer**协助解决:调用 `sessions_spawn`,将问题现象、错误信息、当前任务上下文完整传递给 IT Engineer,请它协助解决。**spawn 后 fire-and-forget,严禁 `sessions_yield` 等待**——IT Engineer 的结果通过 announce 异步回来,若没回来按下一条跳过继续(见下方约束 3);
   - 仍无法解决 → **跳过当前任务,继续执行后续步骤**,不要卡住整个 HEARTBEAT

   不可:
      - ❌ 呼唤用户协助解决,HEARTBEAT 在深夜执行,喊用户也没用
      - ❌ 不可中断任务,通过以上三步依然无法进行的任务则跳过,继续执行后续步骤,绝对不允许中断HEARTBEAT!

3. **⛔ cron/heartbeat isolated session 中禁止 `sessions_yield`,原则上也不 spawn subagent**:

   本任务由 cron 以 `session_target=isolated` 启动,**本身已是独立上下文**,不占主 agent 上下文、不阻塞主 session。再 spawn subagent 是零收益纯增复杂度,且 `sessions_yield` 会通过 `runAbortController.abort("sessions_yield")`(`openclaw/src/agents/embedded-agent-runner/run/attempt.ts:1351`)**直接 abort 当前 run**,cron 将 yield 视为 run 结束并标记 outcome,session 变 inactive;subagent 完成后的 announce 找不到可唤醒的活跃 session,retry 3 次后 give-up,**后续 Step 全部丢失**。

   - 所有 Step 0–5 **顺序内联执行**,retro.md 等产出主 agent 自己写,不 spawn subagent、不 `sessions_yield`。
   - 唯一允许 spawn 的是约束 2 的「故障兜底 spawn IT Engineer」,且必须 fire-and-forget(不 yield)。
   - 涉及浏览器的操作本来就必须串行(避免浏览器竞态抢夺),内联顺序执行天然满足。

4. **⛔ 登录失效一律「跳过 + 记录 + 汇总上报」，严禁硬行恢复登录**

   任何平台的取数端登录失效（`SESSION_EXPIRED` / login-manager 探活失败 / 浏览器跳登录页 / `get-xhs-user-id.sh` exit 2 等）时，**必须**：
   - 立即**跳过该平台**本轮取数，不再尝试任何取数动作；
   - 把平台名记入 `EXPIRED_PLATFORMS`，在 Step 5 统一汇报，由用户**白天**用 login-manager 重新登录；
   - **不得**在凌晨心跳里扫码登录、不得唤醒用户。

   **严禁的"硬行恢复"动作**（任一都可能触发平台风控/限流/封号）：
   - ❌ 用 CDP `Network.setCookies` 把本地存的 cookie **注入**浏览器去"造"一个登录会话
   - ❌ 反复刷新/重导航 profile 页试图"刷出"登录态
   - ❌ 不带 xsec_token 硬调 feed API 试 fallback
   - ❌ 任何绕过 login-manager 正常探活流程的私拉会话操作

   > 本规范下方 Step 2 / Step 5 已写明，但 **2026-06-29 凌晨 Agent 未遵守**：xhs-browse 浏览器无登录态时，Agent 用 CDP 注入 22 个 cookie 强造会话后批量抓取，**当日触发小红书风控、账号被处罚**。故在此特别前置强调。

5. **⚠️ 小红书 (xhs) 封号风险显著高于其他平台**

   - xhs 对「会话凭空 materialize + 短时批量签名请求」极度敏感，**一次** CDP 注入 cookie + 批量 feed 抓取就可能触发风控/限流/封号。
   - xhs-browse 任何登录失效迹象 → **立刻整段跳过 xhs**，不要尝试任何恢复，记入 `EXPIRED_PLATFORMS` 等白天重新登录。
   - 取数只走 `xhs-browse`；**禁止**探测/使用 `xhs-publish` creator 域 cookie（见 Step 2 注意事项）。

---

### 工作流程

#### Step 0:准备工作

为避免浏览器连接不稳干扰后续任务执行,正式开始前应该将已经打开的浏览器实例(如有)先完全关闭，再打开。

打开时使用默认 `openclaw` profile。

---

#### Step 1: 通过 published-track 读取所有已启用打分（cal_enabled=1）的已发布内容

```bash
# 查看哪些平台启用了 content-calibrator
./skills/content-calibrator/scripts/cal-toggle.sh --list

# 对每个已启用平台，查询有 cal_enabled=1 的记录
./skills/published-track/scripts/query.sh --platform xhs --limit 50
```

对每个已启用平台，列出所有 `cal_enabled=1` 的记录，准备在 Step 2 中更新数据。

---

#### Step 2: 依次获取已发布内容的互动数据并更新到 published-track

对 Step 1 中列出的**每条记录（按 id 逐条）**取数并写库。按平台分三种情况，能用脚本的先用脚本，不能用脚本的用对应技能，再不就指导 Agent 自己上：

1. **douyin / xhs / kuaishou / bilibili** —— 走脚本：

   ```bash
   ./skills/published-track/scripts/fetch-and-update-metrics.sh \
     --platform <platform> --id <rowid>
   ```

   脚本封装了 login-manager 探活 → API 抓取 → DB 写入 的完整流程，返回统一 JSON 结果。

2. **微信公众号 (wx_mp)** —— 走 `wx-mp-engagement` 技能取数后写库。

3. **其他平台** —— 指导 Agent 使用持久化 session 通过 `camoufox-cli` 打开对应创作者中心，读取已发布文章的互动数据再写库。

   > 这条路效果一般，**尽力而为即可，不要硬弄**——拿不到就跳过，切勿反复操作以免引发风控。后面会持续更新。

##### 通用规则

- **必须传 `--id <rowid>`**（脚本类平台）：`<rowid>` 取自 Step 1 查询结果里的 `id` 字段。同一 `source_folder` 可能对应多条记录（同内容重复发布到不同帖子），按 `--id` 逐条抓取/写库才能让每次发布各自独立统计；若只传 `--source-folder`，脚本会只抓一行指标却批量写进所有同 folder 行，造成重复发布之间互相污染。
- **SESSION_EXPIRED**：脚本返回 `ok=false, error=SESSION_EXPIRED`（exit 2）时，**跳过该平台**本轮取数，记入 `EXPIRED_PLATFORMS`，Step 5 统一汇报，由用户白天用 login-manager 重新登录。**凌晨不唤醒用户、不扫码登录、不私拉会话**（见约束 4/5）。
- **xhs 风控显著高于其他平台**：xhs 任何登录失效迹象 → 立刻整段跳过 xhs，不尝试任何恢复。取数只走 `xhs-browse`，**禁止**探测/使用 `xhs-publish` creator 域 cookie。
- **浏览器操作必须串行**，不可并行。

---

#### Step 3: content-calibrator 复盘

对每个已启用 content-calibrator 的平台，检查是否满足复盘条件：

1. 从 published-track DB 读取该平台所有 `cal_enabled=1` 的记录
2. 检查 `calibration/<platform>/predictions/` 中是否有对应的预测日志
3. 统计**有实际互动数据但尚未复盘**的记录数
4. 如果积累了 **≥5 个新数据点** → 执行复盘流程

复盘流程（由 Agent 执行）：
- 从 published-track DB 读互动数据
- 对比预测 vs 实际
- 提炼观察 → 写入 `calibration/<platform>/rubric-memo.md`
- 检测是否触发 bump（≥3 次同向偏差）

**如果某平台未启用 content-calibrator，跳过此步骤。Agent 不得自动启用。**

---

#### Step 4: 用户咨询回复

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

#### Step 5: 汇总执行情况报告用户

汇总执行情况，反馈用户。报告内容：

1. 各平台数据更新情况（成功/跳过/失败数量）
2. **取数端 Cookie 失效列表**（如有）：
   > ⚠️ 以下**取数端**Cookie 已失效，数据未能更新。请白天使用 login-manager 技能重新登录：
   > - douyin（抖音）
   > - xhs-browse（小红书浏览端）
   >
   > 列出的名字即 `login-manager login <name>` 要用的平台名（非 published-track 的 `xhs`）。
   >
   > **只报告取数端 cookie**。**不要报告、也不要探测 `xhs-publish`（小红书发布端 / creator.xiaohongshu.com）**：
   > 复盘/取数完全不依赖发布端 cookie，探测它只会给 creator 域增加风控概率且结论与取数无关。
   > 发布端失效由发布任务（xhs-publish 技能）自己管，不在本复盘心跳职责内。
3. 浏览器获取结果摘要（如有）
4. content-calibrator 复盘结果摘要（如有）

发送后本次定时任务结束。
