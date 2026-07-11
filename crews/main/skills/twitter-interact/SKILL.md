---
name: twitter-interact
description: Twitter/X 互动操作技能——支持点赞 / 取消点赞 / 转推 / 取消转推 / 收藏 /
  取消收藏 / 关注 / 取关。camoufox-cli 主推路径 + login-manager 中央 cookie + 频率限制。
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

### 1. login-manager 中央 cookie + 有头登录（原则 3）

```bash
# 探活（exit 0 = 有效）
login-manager.sh check twitter

# 失效后：有头登录（twitter 必须有头，原则 3——不无头截图 QR）
login-manager.sh login-headed twitter
# → camoufox-cli --session twitter --persistent --headed open https://x.com
# → 用户在弹出的 Firefox 窗口完成登录
# → login-manager 导出 cookie + UA（forked cli identity export）
#   到 ~/.openclaw/logins/twitter.json + twitter.ua.json
# → close
```

> twitter 不走无头 QR 流程（与 wechat-channel / wx-mp 不同）。原因：X 登录风控对无头 + QR 识别严格，有头人工登录最稳。

### 2. camoufox-cli（forked）已安装

本仓 `patches/camoufox-cli/` 的 fork（基线上游 `camoufox-cli@0.6.2` + upload + fail-first 队列 + identity export）。`patches/camoufox-cli/build.sh` 全局安装替换 `$PATH` 上的上游版。

### 3. 频率跟踪文件（首次自动创建）

`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json` —— 每次成功操作后自动 append。

### 4. 单一持久化 session `twitter`（原则 1）

所有互动操作共享同一个 `--persistent` session `twitter`（指纹冻结 + cookie 留 profile）。并发调用由 forked cli 的 **fail-first 队列**串行拒绝——脚本不自动排队、不自动等待，读到 `session twitter 正忙` 文本时 exit 3，调用方（agent）应等待当前操作完成后再试。

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
1. login-manager.sh check twitter
   ├─ exit 0 → 继续
   └─ exit 2 → 提示走 login-headed（原则 3，有头登录）
2. camoufox-cli --session twitter --persistent --headless open https://x.com/i/web/status/<id>
   └─ 若 session 正忙 → forked cli 返回 fail-first 文本 → 脚本 exit 3（不 close，不排队）
3. camoufox-cli --session twitter --json eval "
     document.querySelector('[data-testid=\"like\"]').click();
     'clicked';
   "
4. 检查频率限制（check_freq_limit）
   ├─ 通过 → 写 FREQ_TRACKER_PATH
   └─ 不通过 → exit 1
5. login-manager.sh session-cleanup twitter <session>
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
| Cookie 失效（login-manager exit 2）| 提示走 login-headed（原则 3，有头登录）|
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
- **workaround**：本 skill selector 是公开推测，spike 验证后更新；当前 main agent 看到 exit 1 时**应**触发 selector 检查

---

## 相关 skill

- `twitter-post`（Quote / Reply / Long post 在那边，用 forked cli `upload` 命令传媒体）
- `login-manager`（cookie + UA 中央存储；登录走 `login-headed twitter`，导出用 forked cli `identity export`）

---

## Notes

- **Reply / Quote 流程在 twitter-post**（typed publish 是"发布"范畴，不在本 skill）
- **发布频率与互动频率分开追踪**（不互相影响）
- **不**与 published-track 共享频率统计（本 skill 自有 FREQ_TRACKER_PATH）
- **BD 场景主推**：关注目标用户（follow）+ 点赞目标推（like）+ 收藏（bookmark）— 这三个是 BD 自动化常用组合
- **风控告警阈值**：日累计 50% 上限时输出 warning（不是 hard block）
- **forked cli 新命令**：`upload`（本 skill 不用，无媒体）/ `identity export`（login-manager 登录时导出 UA）/ fail-first 队列（本 skill 依赖，串行化并发）
- **AiToEarn 上游参考**（`yikart/AiToEarn` v2.4.0 `74e884f0`）：twitter 互动走 Twitter API v2 + OAuth（`POST /users/{id}/likes` 等），本 skill 不搬 API 架构（spec 要求 camoufox-cli），只吸收操作语义（like/unlike/retweet/follow 子命令结构 + 频率纪律）。如未来配齐 X OAuth 凭证，可加 API 路径作为更快/更稳的 fallback。
