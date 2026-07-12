---
name: twitter-interact
description: Twitter/X 互动操作技能——支持点赞 / 取消点赞 / 转推 / 取消转推 / 收藏 / 取消收藏 / 关注 / 取关。camoufox-cli 主推路径 + 持久化 session 自管登录 + 频率限制。与 twitter-post 共用 session `twitter`。
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
| `run` | 一键跑（全流程：login + 操作 + cleanup）| — |
| `cleanup <session>` | 关闭 camoufox session | — |

> **频率限制**：平台 anti-automation 阈值 + 经验值（30 min 风险窗口 / reply 27x like 权重）。如触发风控 → 24h 静默。

---

## 前置条件

### 1. 探活与登录（本 skill 自管，不走 login-manager）

走持久化 session `twitter`（与 `twitter-post` 共用）。探活方式：开 session open 平台首页 + snapshot 看是否跳登录页。

```bash
# 探活
camoufox-cli --session twitter --persistent --headless --json open "https://x.com/"
sleep 3
camoufox-cli --session twitter --json snapshot
# snapshot 看页面是否跳到登录页 / 出现登录按钮 / 推文是否正常可见
# → 没跳登录页、内容正常 = 登录态有效，可 close 后交后续操作用
# → 跳到登录页 / 出现登录按钮 = 登录态失效，走重登
camoufox-cli --session twitter --json close
```

重登流程（失效时）：

```bash
# X 登录风控对无头 + QR 识别严格，有头人工登录最稳
camoufox-cli --session twitter --persistent --headed --json open "https://x.com/login"
# 告知用户「**Twitter/X** 浏览器已打开，请在窗口里手动完成登录（账号密码 / 手机 APP 扫码），完成后告诉我」
# 等用户回复后 snapshot 验登录态就位
camoufox-cli --session twitter --json close
```

**不导出 cookie/UA**——登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本 skill 不调用 `cookies export` / `identity export`。

### 2. camoufox-cli（forked）已安装

本仓 `patches/camoufox-cli/` 的 fork（基线上游 `camoufox-cli@0.6.2` + upload + fail-first 队列 + identity export）。`patches/camoufox-cli/build.sh` 全局安装替换 `$PATH` 上的上游版。

### 3. 频率跟踪文件（首次自动创建）

`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json` —— 每次成功操作后自动 append。

### 4. 单一持久化 session `twitter`（与 twitter-post 共用）

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

### 单条 like（典型）

```
1. 探活（见「探活与登录」段）
   登录态有效 → 继续
   登录态失效 → 走重登流程（有头手动登录），完成后继续
2. camoufox-cli --session twitter --persistent --headless open https://x.com/i/web/status/<id>
   └─ 若 session 正忙 → forked cli 返回 fail-first 文本 → 脚本 exit 3（不 close，不排队）
3. camoufox-cli --session twitter --json eval "
     document.querySelector('[data-testid=\"like\"]').click();
     'clicked';
   "
4. 检查频率限制（check_freq_limit）
   ├─ 通过 → 写 FREQ_TRACKER_PATH
   └─ 不通过 → exit 1
5. camoufox-cli --session twitter --json close（或留着给下次用，见「必做约束」）
6. 输出 {ok, tweet_id, action, session}
```

### retweet（带 confirm 菜单）

```
1-3. 同 like
4. eval retweet 按钮 → 点击 → 弹出 confirm 菜单
5. sleep 1s → eval confirm 菜单 "Repost"（**不是** "Quote"）
6. check_freq_limit + record
7. cleanup
8. 输出 {ok, tweet_id, action, session}
```

### follow

```
1-2. camoufox open https://x.com/<handle>
3. eval [data-testid$="-follow"] 按钮 → text 是 "Follow" → click
4. check_freq_limit (follow: 5 min, 50/day)
5. record_action + cleanup
```

### unfollow（带 confirm 菜单）

```
1-2. camoufox open https://x.com/<handle>
3. eval "Following" 按钮 → click → confirm 菜单
4. sleep 1s → eval confirm 菜单 "Unfollow"
5. cleanup
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
| Cookie 失效（探活 exit 2）| 走自管重登流程（有头手动登录），完成后重试一次 |
| session 正忙（forked cli fail-first）| exit 3 + 透传 busy 文本，**不 close**（避免 tear down 正在跑的另一个操作），agent 等待重试 |
| Tweet ID / Handle 解析失败 | exit 1（提示格式错）|
| 频率限制触发 | exit 1（提示等待时间）|
| 按钮已点（like 已是 pressed / already following）| 输出 `note: 已...` + exit 0 |
| eval 返回 null（DOM 未加载）| sleep 2s 重试一次（最多 3 次）|
| 频率触发风控 | 立即记录 + 24h 静默 + exit 1 |
| retweet 选错 "Quote" 而非 "Repost" | 立即 Undo + 重新选 Repost（**不**自动 retry，提示用户）|

---

## Pitfalls

### pitfall: like 已按（aria-pressed="true"）

- **症状**：eval 返回 `"already"`，脚本正常退出但不记录频率
- **workaround**：直接输出 `note: 已点赞` 即可，不写频率（重复点赞不消耗配额）

### pitfall: retweet 误选 Quote

- **症状**：点 "Retweet" 后选 "Quote" 而非 "Repost" → 推出去带评论，BD 场景不符预期
- **workaround**：点击 "Repost" 菜单后**严格** text match `Repost` 不含 `Quote`

### pitfall: 频率间隔未严格遵守

- **症状**：连发点赞 / 转推 → X 触发 "This request looks like it might be automated"
- **workaround**：check_freq_limit 在每次操作前校验，**强制** wait

### pitfall: 并发调用撞 fail-first 队列

- **症状**：两个 twitter-interact 调用同时跑 → 第二个收到 `session twitter 正忙` → exit 3
- **workaround**：这是**预期行为**（原则 1 + forked cli fail-first）。agent 读到 exit 3 应等待当前操作完成再重试，**不**自动排队、**不**自动 close session（close 会 tear down 正在跑的那个操作）

### pitfall: X UI 改版 → selector 失效

- **症状**：`[data-testid="like"]` 等找不到
- **workaround**：本 skill selector 是公开推测，部署后真机验证更新（见 `docs/post-deploy-verification.md`）；当前 main agent 看到 exit 1 时**应**触发 selector 检查

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
