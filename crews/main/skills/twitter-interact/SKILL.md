---
name: twitter-interact
description: Twitter/X 互动操作技能——支持点赞 / 取消点赞 / 转推 / 取消转推 / 收藏 / 取消收藏 / 关注 / 取关。camoufox-cli 主推路径 + 持久化 session `twitter`（与 twitter-post 共用，探活登录走 browser-guide §1）+ 频率限制。
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
> 探活 + 登录流程见下方「前置：持久化 session `twitter` 与探活登录」段，与 `twitter-post` 完全一致，登录机制走全局 `browser-guide` skill §1。

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
| `run` | 一键跑（全流程：login + 操作 + cleanup）| — |
| `cleanup <session>` | 关闭 camoufox session | — |

> **频率限制**：平台 anti-automation 阈值 + 经验值（30 min 风险窗口 / reply 27x like 权重）。如触发风控 → 24h 静默。

---

## 前置：持久化 session `twitter` 与探活登录

> **本段在 `twitter-post` 与 `twitter-interact` 两份 SKILL.md 中完全一致——改一处必须同步另一处。** 登录机制走全局 `browser-guide` skill §1 Login Prompts，本 skill 不重写登录步骤。

**单一持久化 session `twitter`**：两个技能都用 `--session twitter --persistent`，共享同一 profile 目录与登录态——任一技能登录后另一个不需重登，靠 session 名字符串约定共享，无需别的机制。

**不导出 cookie/UA**：Twitter 阵营是纯浏览器操作，没有脚本类技能消费 cookie，登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本 skill 不调用 `cookies export` / `identity export`，与 login-manager 无关。

### 探活（每次操作前必跑）

```bash
camoufox-cli --session twitter --persistent --headless --json open "https://x.com/"
sleep 3
camoufox-cli --session twitter --json snapshot
# snapshot 判断：
#   没跳登录页、推文正常可见 = 登录态有效 → close 后交后续操作
#   跳到登录页 / 出现登录按钮 = 失效 → 走重登
camoufox-cli --session twitter --json close
```

### 重登（失效时，走 browser-guide §1）

X 登录风控对无头 + 自动化登录严格，**重登必须 `--headed`**，让用户在浏览器窗口手动完成（账号密码 / 手机 APP 扫码 / 2FA / captcha 都在窗口里过）：

```bash
camoufox-cli --session twitter --persistent --headed --json open "https://x.com/login"
# 告知用户：「**Twitter/X** 浏览器已打开，请在窗口里手动完成登录，完成后告诉我」
# 等用户回复后 snapshot 验登录态就位
camoufox-cli --session twitter --json close
```

登录机制细节（saved credentials 优先 / 账号密码 / captcha fallback / 最多重试 2 次）按 `browser-guide` §1-A~1-E + §3 执行，本 skill 不重复。

### 并发约束（fail-first，不并行）

同一 session 已有命令在跑时，forked cli 直接 fail，返回 `session twitter 正忙`。脚本读到该文本 → exit 3，**不 close**（避免 tear down 正在跑的另一个操作），调用方等待重试，不自动排队。

### 任务结束不 close

持久化 session 留给后续自己 / 另一个 twitter 技能复用，**不要 close**。除非明确要重登，才走上面重登流。

### 频率跟踪文件（twitter-interact 专属）

`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json` —— 每次成功互动操作后自动 append。发布频率在 `twitter-post` 的 `twitter-frequency.json`，两者分开追踪、互不影响。

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
# 一键：login → 操作 → cleanup
twitter_interact run --tweet-url <url> --action <like|retweet|bookmark>
twitter_interact run --user <handle> --action <follow|unfollow>
```

### 并发约束（fail-first，不并行）

```bash
# 原则 1：单一 session twitter，并发调用由 forked cli fail-first 队列拒绝
# 脚本读到 "session twitter 正忙" → exit 3，agent 应等待重试（不自动排队）
# 串行使用：上一次操作 close 后再发下一次
```

---

## 工作流程

> **实现要点（移植自 OpenCLI `clis/twitter/`）**：脚本 `twitter_interact.py` 内置三个模式，agent 无需手写 eval：
> 1. **article-scoped 探针**：按 tweet_id 定位含 `a[href*="/status/<id>"]` 的 article，按钮查找限定其内——会话页有多 article，bare `querySelector('[data-testid="like"]')` 会抓第一个（父推）误操作。
> 2. **testid 确认菜单**：retweet→`[data-testid="retweetConfirm"]`、unretweet→`unretweetConfirm`、unfollow→`confirmationSheetConfirm`，比 text match 稳且不受本地化影响。
> 3. **晚水合轮询**：Python 侧 20×500ms 找按钮 / article，确认菜单 20×250ms。
> 4. **按钮互换验证状态**：like↔unlike、bookmark↔removeBookmark、retweet↔unretweet、-follow↔-unfollow，点击后轮询对立按钮出现确认成功（非 aria-pressed）。

### 单条 like（典型）

```
1. 探活（见前置段）→ 登录态有效继续，失效走重登
2. camoufox-cli --session twitter --persistent --headless open https://x.com/i/web/status/<id>
   └─ 若 session 正忙 → forked cli fail-first → 脚本 exit 3（不 close，不排队）
3. 脚本 _poll_probe(tid, ["unlike","like"])：
   ├─ unlike 在 → 已点赞，输出 note + exit 0（不记频率）
   ├─ like 在 → _click_scoped(tid,"like") → _poll_probe(tid,["unlike"]) 验翻转 → record + 输出
   └─ 10s 内都没找到 → exit 1（DOM 未加载或未登录）
4. check_freq_limit（操作前已校验）→ 通过则 record_action
5. 不 close 持久化 session（留给下次 / twitter-post 复用，见前置段）
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
5. record_action + 不 close
```

### unfollow（带 confirm 菜单）

```
1-2. camoufox open https://x.com/<handle>
3. _poll_suffix(["-follow","-unfollow"])：-follow 在 → 未关注 note；-unfollow 在 → 继续
4. _click_suffix("-unfollow") → 弹 confirm
5. _click_confirm("confirmationSheetConfirm")：轮询找 [data-testid="confirmationSheetConfirm"] 并 click
6. sleep 1s → _poll_suffix(["-follow"]) 验翻转
7. 不 close
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
| Cookie 失效（探活 exit 2）| 走前置段「重登」流程（browser-guide §1，有头手动登录），完成后重试一次 |
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
- **workaround**：本 skill 的 testid 移植自 OpenCLI `clis/twitter/`（实战维护中），比公开推测稳；仍需部署后真机验证（见 `docs/post-deploy-verification.md`）。main agent 看到 exit 1 时**应**触发 selector 检查

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
