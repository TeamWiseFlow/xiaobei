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

### 1. login-manager 中央 cookie

```bash
# 探活（exit 0 = 有效）
login-manager.sh check twitter

# 失效后：camoufox 扫码登录
login-manager.sh qr-headless twitter
# → 发 QR PNG 给用户
login-manager.sh qr-confirm twitter --session <s> --timeout 180
```

### 2. camoufox-cli 已安装

`camoufox-cli@0.6.2` 全局（Dockerfile 阶段 1 / 本机通过 npm install -g）。

### 3. 频率跟踪文件（首次自动创建）

`~/.openclaw/agents/main/sessions/twitter-interact-frequency.json` —— 每次成功操作后自动 append。

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

### 自定义 session 名（多任务并行）

```bash
# 脚本化并行：每条用独立 session（不传 session，脚本自动生成）
# 主流程结束必须 cleanup（run 自动 cleanup）
```

---

## 工作流程

### 单条 like（典型）

```
1. login-manager.sh check twitter
   ├─ exit 0 → 继续
   └─ exit 2 → 走 qr-headless + qr-confirm
2. camoufox-cli --session twitter-like-<nonce> --persistent --headless open https://x.com/i/web/status/<id>
3. camoufox-cli --session ... eval "
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
| Cookie 失效（login-manager exit 2）| 走 qr-headless + qr-confirm |
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

### pitfall: 跨任务 session 复用

- **症状**：同一 session 名被两个 task 共用 → cookie state 污染
- **workaround**：**每任务用新 session name**（`secrets.token_hex(4)` nonce 唯一保证）

### pitfall: X UI 改版 → selector 失效

- **症状**：`[data-testid="like"]` 等找不到
- **workaround**：本 skill selector 是公开推测，spike 验证后更新；当前 main agent 看到 exit 1 时**应**触发 selector 检查

---

## 相关 skill

- `twitter-post`（Quote / Reply / Long post 在那边）
- `login-manager`（cookie 中央存储 + camoufox session）

---

## Notes

- **Reply / Quote 流程在 twitter-post**（typed publish 是"发布"范畴，不在本 skill）
- **发布频率与互动频率分开追踪**（不互相影响）
- **不**与 published-track 共享频率统计（本 skill 自有 FREQ_TRACKER_PATH）
- **BD 场景主推**：关注目标用户（follow）+ 点赞目标推（like）+ 收藏（bookmark）— 这三个是 BD 自动化常用组合
- **风控告警阈值**：日累计 50% 上限时输出 warning（不是 hard block）
