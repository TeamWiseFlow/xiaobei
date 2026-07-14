---
name: twitter-interact
description: Twitter/X 互动操作技能——支持点赞 / 取消点赞 / 转推 / 取消转推 / 收藏 / 取消收藏 / 关注 / 取关。camoufox-cli 主推路径 + 持久化 session `twitter`（与 twitter-post 共用，自管探活登录）+ 频率限制。
metadata:
  openclaw:
    emoji: 💬
    requires:
      bins:
      - python3
      - camoufox-cli
---

# Twitter/X 互动操作（twitter-interact）

> **Reply / Quote** 不在本 skill（属于 `twitter-post` 的 Quote Tweet / Reply to Tweet 流程）。
>
> 本 skill 与 login-manager **完全无关**——Twitter 互动是纯浏览器操作，走持久化 session `twitter`（与 `twitter-post` 共用同一个 session），登录态在 session profile 里闭环，**不导出 cookie/UA 落中央存储**。探活 + 登录流程在本 skill 自管，见下方「探活与登录」段。

---

## 适用场景

- 用户："帮我给这条推点赞"
- 用户："转推一下这个"
- 用户："关注 @xxx"
- BD 场景：监控 mentions → 智能回复 + 互动
- 内容运营：批量收藏 / 点赞目标内容

---

## 8 个子命令

| 子命令 | 目标 | 频率限制 |
|--------|------|----------------|
| `like <tweet>` | 点赞 | 1 min / 200 / 日 |
| `unlike <tweet>` | 取消点赞 | 1 min / 200 / 日 |
| `retweet <tweet>` | 转推（纯转，**不**Quote）| 5 min / 50 / 日 |
| `unretweet <tweet>` | 取消转推 | 5 min / 50 / 日 |
| `bookmark <tweet>` | 收藏 | 1 min / 100 / 日 |
| `unbookmark <tweet>` | 取消收藏 | 1 min / 100 / 日 |
| `follow <user>` | 关注用户 | 5 min / 50 / 日 |
| `unfollow <user>` | 取关用户 | 5 min / 50 / 日 |
| `run` | 一键跑（全流程：login 探活 + 操作）| — |

> **频率限制**：平台 anti-automation 阈值 + 经验值（30 min 风险窗口 / reply 27x like 权重）。如触发风控 → 24h 静默。

---

## 前置条件

### 1. 探活与登录（本 skill 自管，不走 login-manager）

走持久化 session `twitter`（与 `twitter-post` 共用同一个 session 名 `twitter`，靠 session 名字符串约定共享同一 profile 目录与登录态——任一技能登录后另一个不需重登）。探活方式：开 session open 平台首页 + snapshot 看是否跳登录页。

`run` 子命令在脚本内自动探活（`_check_session_alive`）；单条子命令（`like` / `retweet` / ...）不内嵌探活，调用方（agent）按下方流程先探活再调单条。

```bash
# 探活（默认无头模式）
camoufox-cli --session twitter --persistent --json open "https://x.com/"
sleep 3
camoufox-cli --session twitter --json snapshot
# snapshot 看页面是否跳到登录页 / 出现登录按钮 / 推文是否正常可见
# → 没跳登录页、内容正常 = 登录态有效，探活完即 close session（登录态在磁盘 profile，后续操作按需重起无头复用）
# → 跳到登录页 / 出现登录按钮 = 登录态失效，走重登
```

重登流程（失效时）——登录流程按 `browser-guide` skill 走有头手动登录（手机号+验证码 / Twitter APP 扫码），登录后**close session**——登录态落磁盘 profile，不留进程占内存。本 skill 做互动操作 + `twitter-post` 做发布操作时用 `--session twitter --persistent` 重起无头即恢复，用完再 close。只在 session 卡死时由调用方手动 `camoufox-cli --session twitter --json close` teardown。

```bash
# X 登录风控对无头 + QR 识别严格，有头人工登录最稳
camoufox-cli --session twitter --persistent --headed --json open "https://x.com/login"
# 告知用户「**Twitter/X** 浏览器已打开，请在窗口里手动完成登录（账号密码 / 手机 APP 扫码），完成后告诉我」
# 等用户回复后 snapshot 验登录态就位
# 登录就位后 close session——登录态落磁盘 profile，本 skill + twitter-post 按需重起无头复用
```

**不导出 cookie/UA**——登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本 skill 不调用 `cookies export` / `identity export`。

### 2. 频率跟踪文件（首次自动创建）

`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json` —— 每次成功互动操作后自动 append。发布频率在 `twitter-post` 的 `twitter-frequency.json`，两者分开追踪、互不影响。

### 3. 单一持久化 session `twitter`（与 twitter-post 共用）

所有互动操作共享同一个 `--persistent` session `twitter`（指纹冻结 + cookie 留 profile）。并发调用由 forked cli 的 **fail-first 队列**串行拒绝——脚本不自动排队、不自动等待，读到 `session twitter 正忙` 文本时 exit 3，调用方（agent）应等待当前操作完成后再试。

**与 `twitter-post` 共 session**：两个技能都用 `--session twitter`，所以共享同一 profile 目录与登录态——twitter-post 登录后 twitter-interact 不需重登，反之亦然。靠 session 名字符串约定即可，无需别的机制。

---

## 使用方式

### 单条操作

```bash
# 点赞
twitter_interact like https://x.com/username/status/1234567890

# 转推
twitter_interact retweet https://x.com/username/status/1234567890

# 关注
twitter_interact follow @openai
# 或
twitter_interact follow https://x.com/openai
```

### 一键跑

```bash
# 一键：login 探活 → 操作
twitter_interact run --tweet-url <url> --action <like|retweet|bookmark>
twitter_interact run --user <handle> --action <follow|unfollow>
```

### 并发约束（fail-first，不并行）

```bash
# 单一 session twitter，并发调用由 forked cli fail-first 队列拒绝
# 脚本读到 "session twitter 正忙" → exit 3，agent 应等待重试（不自动排队）
# 串行使用：每次操作用完即 close session（登录态在磁盘 profile），下一次重起无头复用同一 profile
```

---

## 工作流程

> **实现要点**：脚本 `twitter_interact.py` 内置三个模式，agent 无需手写 eval：
> 1. **article-scoped 探针**：按 tweet_id 定位含 `a[href*="/status/<id>"]` 的 article，按钮查找限定其内——会话页有多 article，bare `querySelector('[data-testid="like"]')` 会抓第一个（父推）误操作。
> 2. **testid 确认菜单**：retweet→`[data-testid="retweetConfirm"]`、unretweet→`unretweetConfirm`、unfollow→`confirmationSheetConfirm`，比 text match 稳且不受本地化影响。
> 3. **晚水合轮询**：Python 侧 20×500ms 找按钮 / article，确认菜单 20×250ms。
> 4. **按钮互换验证状态**：like↔unlike、bookmark↔removeBookmark、retweet↔unretweet、-follow↔-unfollow，点击后轮询对立按钮出现确认成功（非 aria-pressed）。

### 单条 like（典型）

```
1. 探活（见「探活与登录」段）→ 登录态有效继续，失效走重登
2. camoufox-cli --session twitter --persistent open https://x.com/i/web/status/<id>
   └─ 若 session 正忙 → forked cli fail-first → 脚本 exit 3（不 close 正在跑的 session，不排队）
   注：操作执行 + 探活都走默认无头（自动化操作无需用户在场）；只有登录走有头
3. 脚本 _poll_probe(tid, ["unlike","like"])：
   ├─ unlike 在 → 已点赞，输出 note + exit 0（不记频率）
   ├─ like 在 → _click_scoped(tid,"like") → _poll_probe(tid,["unlike"]) 验翻转 → record + 输出
   └─ 10s 内都没找到 → exit 1（DOM 未加载或未登录）
4. check_freq_limit（操作前已校验）→ 通过则 record_action
5. close session（登录态在磁盘 profile，下次 / twitter-post 按需重起无头复用）
6. 输出 {ok, tweet_id, action, session}
```

### retweet（带 confirm 菜单）

```
1-3. 同 like（探针找 unretweet/retweet）
4. _click_scoped(tid,"retweet") → 弹 confirm 菜单
5. _click_confirm("retweetConfirm")：轮询 20×250ms 找 [data-testid="retweetConfirm"] 并 click
   └─ 用 testid 不用 text，结构上不可能选成 Quote
6. sleep 1s → _poll_probe(tid,["unretweet"]) 验翻转 → record
7. 输出 {ok, tweet_id, action, session}
```

### follow

```
1-2. camoufox open https://x.com/<handle>
3. _poll_suffix(["-unfollow","-follow"])：
   ├─ -unfollow 在 → 已关注，note + exit 0
   ├─ -follow 在 → _click_suffix("-follow") → sleep 1s → _poll_suffix(["-unfollow"]) 验翻转 → record
   └─ 都没找到 → exit 1
4. check_freq_limit (follow: 5 min, 50/day)
5. record_action + close session（登录态在磁盘 profile）
```

### unfollow（带 confirm 菜单）

```
1-2. camoufox open https://x.com/<handle>
3. _poll_suffix(["-follow","-unfollow"])：-follow 在 → 未关注 note；-unfollow 在 → 继续
4. _click_suffix("-unfollow") → 弹 confirm
5. _click_confirm("confirmationSheetConfirm")：轮询找 [data-testid="confirmationSheetConfirm"] 并 click
6. sleep 1s → _poll_suffix(["-follow"]) 验翻转
7. close session（登录态在磁盘 profile）
```

---

## 频率限制（详细）

| 动作 | 最小间隔 | 日上限 | 周上限 | 触发后行为 |
|------|----------|--------|--------|----------|
| like | 60s | 200 | 1000 | 24h 静默 |
| retweet | 300s | 50 | 200 | 24h 静默 |
| bookmark | 60s | 100 | 500 | 24h 静默 |
| follow | 300s | 50 | 200 | 24h 静默 |
| unfollow | 300s | 50 | 200 | 24h 静默 |

**频率跟踪文件**：`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json`

```json
{
  "actions": {"like": 23, "retweet": 5, "follow": 2},
  "today_count": 30,
  "week_count": 120,
  "last_action_at": "2026-07-05T09:30:00+08:00",
  "last_action_type": "like"
}
```

---

## 错误处理

| 情况 | 处理 |
|------|------|
| Cookie 失效（探活 exit 2）| 走「探活与登录」段重登流程（browser-guide，有头手动登录），完成后重试一次 |
| session 正忙（forked cli fail-first）| exit 3 + 透传 busy 文本，**不 close**（避免 tear down 正在跑的另一个操作），agent 等待重试 |
| Tweet ID / Handle 解析失败 | exit 1（提示格式错）|
| 频率限制触发 | exit 1（提示等待时间）|
| 按钮已是对立态（unlike/unretweet/-unfollow 在）| 输出 `note: 已...` + exit 0，不记频率 |
| 探针 10s 内未找到按钮 / article（DOM 未水合或未登录）| exit 1，提示检查登录态或 selector |
| 频率触发风控 | 立即记录 + 24h 静默 + exit 1 |

---

## Pitfalls

### pitfall: 会话页抓到父推的按钮（非目标推）

- **症状**：conversation / thread 页有多个 article，bare `document.querySelector('[data-testid="like"]')` 抓第一个（通常是父推），点赞/转推到错的推
- **workaround**：脚本已用 article-scoped 探针——按 tweet_id 找含 `a[href*="/status/<id>"]` 的 article，按钮查找限定其内。agent 不要绕过脚本手写 bare selector

### pitfall: retweet 误选 Quote

- **症状**：点 retweet 按钮后菜单有 "Repost" / "Quote" 两项，选错成 Quote → 推出去带评论
- **workaround**：脚本用 `[data-testid="retweetConfirm"]` 定位确认按钮，结构上不可能选成 Quote。**不要**改回 text match（本地化/改版易碎）

### pitfall: 晚水合——按钮 / confirm 菜单延迟出现

- **症状**：X 是 CSR + 水合，刚 open 完 eval 立刻找按钮常返回 null；confirm 菜单 click 后也需 100-500ms 才渲染
- **workaround**：脚本 Python 侧轮询——按钮/article 20×500ms（共 10s），confirm 菜单 20×250ms（共 5s）。agent 不要用单次 eval + sleep 2s 重试 3 次的旧模式

### pitfall: 用 aria-pressed 判断 like 状态不可靠

- **症状**：X 的 like 按钮 aria-pressed 时有时无、值不一致，按它判状态常误判
- **workaround**：脚本用按钮互换模型——看 unlike 在就是已点赞、like 在就是未点赞，点击后轮询对立按钮出现确认成功。不读 aria-pressed

### pitfall: 频率间隔未严格遵守

- **症状**：连发点赞 / 转推 → X 触发 "This request looks like it might be automated"
- **workaround**：check_freq_limit 在每次操作前校验，**强制** wait

### pitfall: 并发调用撞 fail-first 队列

- **症状**：两个 twitter-interact 调用同时跑 → 第二个收到 `session twitter 正忙` → exit 3
- **workaround**：这是**预期行为**（单一 session + forked cli fail-first）。agent 读到 exit 3 应等待当前操作完成再重试，**不**自动排队、**不**自动 close session（close 会 tear down 正在跑的那个操作）

### pitfall: X UI 改版 → testid 失效

- **症状**：`[data-testid="like"]` / `retweetConfirm` 等找不到
- **workaround**：本 skill 的 testid 积植自 OpenCLI `clis/twitter/`（实战维护中），比公开推测稳；仍需部署后真机验证（见 `docs/post-deploy-verification.md`）。main agent 看到 exit 1 时**应**触发 selector 检查

---

## 相关 skill

- `twitter-post`（Quote / Reply / Long post 在那边，用 forked cli `upload` 命令传媒体）
- `twitter-post` 共用 session `twitter`（靠 session 名约定共享登录态，无需别的机制）

---

## Notes

- **Reply / Quote 流程在 twitter-post**（typed publish 是"发布"范畴，不在本 skill）
- **发布频率与互动频率分开追踪**（不互相影响）
- **不**与 published-track 共享频率统计（本 skill 自有 FREQ_TRACKER_PATH）
- **BD 场景主推**：关注目标用户（follow）+ 点赞目标推（like）+ 收藏（bookmark）— 这三个是 BD 自动化常用组合
- **风控告警阈值**：日累计 50% 上限时输出 warning（不是 hard block）
- **forked cli 新命令**：`upload`（本 skill 不用，无媒体）/ fail-first 队列（本 skill 依赖，串行化并发）——本 skill 不导出 cookie/UA，故不用 `identity export`
