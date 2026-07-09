---
name: twitter-post
description: Compose and publish a post (text, image, or video) to Twitter/X using
  camoufox-cli (headless browser automation; built-in browser tool only as fallback).
  Supports single posts, threads, quote tweets, reply tweets, and long posts
  (Premium/Blue up to 25,000 chars).
metadata:
  openclaw:
    emoji: 🐦
---

# Twitter/X 发布技能

Use this skill when:
- The user wants to post text, images, or video to Twitter/X
- You need to share a created article excerpt or key insights on X
- You need to cross-post content to international audiences
- You need to **quote tweet** another post with your own comment
- You need to **reply** to a specific tweet (engagement use case)
- You have a Premium/Blue account and need **long post** (up to 25,000 chars)

**Prerequisites**: camoufox-cli session 已登录 x.com（登录态持久化在 session profile 里）。冷会话先访问一次首页预热。login-manager 非必需——Twitter 发布/互动是纯浏览器操作，只有当想把 cookie 导出给 API 用时才走 login-manager。

---

## 浏览器方案（重要）

**优先 camoufox-cli**：headless persistent session（登录态存 session profile）+ DataTransfer/File 注入上传。camoufox-cli 无头即可完成 x.com 登录与发布，反侦测能力强、资源占用低。操作要点：`snapshot` 拿 ref → `fill`/`click` 按 ref 操作，别自己 hack selector。

**fallback**：仅当 camoufox-cli 在 X 上持续触发风控时，切换到 openclaw 内置 `browser` tool（见 `browser-guide` §1-B）。下面的 workflow 步骤（Navigate / Click / snapshot eval / upload）是通用浏览器自动化语义，**默认用 camoufox-cli 执行**，不要因为措辞里有"snapshot/eval"就改用内置 browser tool。

---

## 通用约束

- 文件上传用 camoufox-cli 的 DataTransfer/File 注入（参考 `douyin-publish`）；若走 fallback 内置 browser tool，需先把文件复制到 `/tmp/openclaw/uploads/`（沙箱限制）
- 上传可能返回「超时错误」，但这**不代表上传失败**！上传后检查页面状态（缩略图是否出现）
- **不要通过检查 `input.files.length` 是否为 0 判定上传是否失败！** `input.files.length == 0` 不代表上传失败。
- 遇到 `timed out. Restart the OpenClaw gateway ...` 错误时，**不需要重启、不需要报错**！等待 30 秒后在原页面继续操作即可。若仍无法操作，再等 30 秒；若还不行，尝试关闭浏览器后重开；只有关闭重开后仍报错才是真的出错，需停止并反馈用户。
- 正文输入使用 `type` + `slowly: true`，不要用 `fill()`

### 字符计数规则（X 平台特殊）

- **URL 永远算 23 字符**（不论实际长度）— 在算 limit 时要预先扣除
- **Emoji 算 2 字符** / 个
- 标准 280 字符限制（普通账号）
- Premium/Blue 25,000 字符（"long post"，URL bar 显示"Post all"而非"Post"）

### Anti-automation limit

- 单条帖 ≥ 30 min 间隔（**不是** 15 min——30 min 是平台风险阈值）
- 单日 ≤ 50 帖（含 reply / quote / retweet / 长帖）
- 单周 ≤ 200 帖
- 触发风控后 24h 静默
- 频次跟踪：写到 `~/.openclaw/agents/main/sessions/twitter-frequency.json`（每次 post 后 append）

---

## Post Types 决策表

| 场景 | 用哪个 Workflow | 入口 URL |
|------|---------------|----------|
| 新推纯文/图/视频 | Workflow: Post Plain Text / Image / Video | `https://x.com/compose/post` |
| 推连续串 | Workflow: Thread | `https://x.com/compose/post` |
| 引用某推+评论 | **Workflow: Quote Tweet** | `https://x.com/compose/post`（从其他推页 quote）|
| 回复某推 | **Workflow: Reply to Tweet** | `https://x.com/<user>/status/<id>`（回复按钮）|
| 长文（>280 字符）| **Workflow: Long Post** | `https://x.com/compose/post`（检测 Premium 蓝标）|
| 标准帖发后取 stats | Workflow: Post Parse Stats | 任意已发推 |

---

## Workflow: Post Plain Text

```
1. Navigate to https://x.com/compose/post
2. Wait for the compose box to load
3. Click into the text area and type the content
   - Plain text only (no Markdown)
   - Max 280 characters for standard accounts
4. Verify character count — trim if over limit
5. **立即点击 "Post" 按钮——不要等待用户确认！**
6. Wait for success confirmation (URL changes or "Your post was sent" toast)
7. Extract and report the post URL
8. **Parse stats**：
   - snapshot eval: `JSON.stringify({
       retweet: document.querySelector('[data-testid="retweet"]')?.innerText,
       like: document.querySelector('[data-testid="like"]')?.innerText,
       reply: document.querySelector('[data-testid="reply"]')?.innerText,
       view: document.querySelector('[href*="/analytics"]')?.innerText,
       permalink: window.location.href
     })`
9. Update frequency tracker
```

---

## Workflow: Post with Image

```
1. Navigate to https://x.com/compose/post
2. Wait for the compose box to load
3. Click the media icon (camera/photo button below compose box)
4. Upload the image file using the file picker
5. Wait for image upload to complete (thumbnail appears)
6. Click into the caption area and type the caption
   - Plain text only (no Markdown)
   - Max 280 characters for standard accounts
7. **立即点击 "Post" 按钮——不要等待用户确认！**
8. Wait for confirmation and report the post URL
9. Parse stats (same as plain text)
10. Update frequency tracker
```

**Patchright 1.60+**：也可用 `locator.drop()` 直接拖拽图片到 compose 区域：
```javascript
const imgBuf = fs.readFileSync(imagePath);
await page.locator('[data-testid="tweetTextarea_0"]').drop({
  files: { name: 'image.png', mimeType: 'image/png', buffer: imgBuf }
});
```

---

## Workflow: Post with Video

```
1. Navigate to https://x.com/compose/post
2. Click the media icon
3. Upload the video file (MP4 recommended, max 512MB, max 2min 20sec)
4. Wait for video processing — this can take 30–120 seconds or more for larger files. Look for the thumbnail preview to confirm completion.
5. Click into the caption area and type the caption
   - Plain text only (no Markdown)
   - Max 280 characters for standard accounts
6. **立即点击 "Post" 按钮——不要等待用户确认！**
7. Wait for upload confirmation and report the post URL
8. Parse stats (same as plain text)
9. Update frequency tracker
```

---

## Workflow: Thread (multiple posts)

```
1. Navigate to https://x.com/compose/post
2. Click into the compose box and type the first tweet
   - Plain text only (no Markdown)
   - Max 280 characters for standard accounts
3. Click the "+" icon to add another tweet to the thread
4. Click into the new compose box and type the second tweet
   - Plain text only (no Markdown)
   - Max 280 characters for standard accounts
5. Repeat for each additional tweet
6. Click "Post all" to publish the full thread
7. Parse stats for the **last** tweet (representative)
8. Update frequency tracker (count = number of tweets in thread)
```

---

## Workflow: Quote Tweet

**场景**：引用别人的推 + 自己的评论（BD / 互动 / 营销场景强）

```
1. Navigate to source tweet URL（如 https://x.com/username/status/1234567890）
2. Click "Repost" icon → 选择 "Quote"（不是 "Repost"）
   - ⚠️ 区分 "Repost"（纯转推，无评论）vs "Quote"（引用+评论）
3. Compose box 打开，**已自动填入引用卡片**
4. Click into text area below the quoted card
5. Type your comment (max 280 chars)
6. Verify character count
7. **立即点击 "Post" 按钮**
8. Wait for confirmation, report post URL
9. Parse stats (same as plain text)
10. Update frequency tracker
```

**Pitfall**：
- ❌ 选 "Repost" 而不是 "Quote" → 推出去没评论，BD 场景失去意义
- ❌ 评论超过 280 字符 → 按钮变灰，**不**自动转 Long post
- ❌ 评论里直接放 raw URL（占 23 字符）→ 实际可发字符更少

---

## Workflow: Reply to Tweet

**场景**：BD 监控 mentions → 智能回复（也可作 twitter-interact skill 的入口）

```
1. Navigate to source tweet URL（如 https://x.com/username/status/1234567890）
2. Click "Reply" icon（不是 reply 文本框）
3. Compose box 打开，**自动显示 reply context**
4. Type your reply (max 280 chars)
5. Verify character count
6. **立即点击 "Reply" 按钮**（不是 "Post"）
7. Wait for confirmation, report reply URL
8. Parse stats (replies can also get view counts)
9. Update frequency tracker
```

**Pitfall**：
- ❌ 选 "Reply" 时落入 quote 模式（X 旧 UI 行为）→ 不会加 reply 关系
- ❌ 串太长（> 280）→ 按钮变灰
- ❌ 频率过高 → 风控（见 Anti-automation limit）

---

## Workflow: Long Post

**前置**：用户是 **Premium / Blue** 订阅（X 蓝标）。普通账号本工作流**不适用**。

**检测 Premium**：
```
snapshot eval: document.querySelector('[data-testid="icon-verified"]') !== null
// 或 UI 中是否有 "Premium" 字样
```

```
1. Navigate to https://x.com/compose/post
2. Wait for compose box to load
3. Type content up to 25,000 chars
4. **注意**：URL 仍 23 字符，Emoji 仍 2 字符
5. 按钮文字从 "Post" 变成 "**Post all**"（X 长帖是 1 个"post all"动作，但内容被服务端分页）
6. Click "Post all"
7. Wait for confirmation (URL changes)
8. Extract permalink (实际是 thread 形式：tweet + 续贴)
9. Parse stats for **first** tweet
10. Update frequency tracker (count = 1，long post 算 1 次)
```

**Pitfall**：
- ❌ 普通账号硬塞 25K → 按钮变灰 / 截断
- ❌ 不验 Premium 状态 → 普通账号调本工作流失败率高
- ⚠️ Long post 实际上服务端分页（thread-like），permalink 拿的是 first tweet

---

## Workflow: Post Parse Stats

> post 后立即拿 stats（view / reply / retweet / like），用于复盘。

```
1. After post success (any workflow ending with "Wait for confirmation")
2. 已在推文页面，URL = https://x.com/<user>/status/<id>
3. Wait 3-5s for X to populate stats
4. snapshot eval:
   const stats = JSON.stringify({
     retweet: document.querySelector('[data-testid="retweet"]')?.innerText,
     like: document.querySelector('[data-testid="like"]')?.innerText,
     reply: document.querySelector('[data-testid="reply"]')?.innerText,
     view: document.querySelector('a[href*="/analytics"]')?.innerText,
     bookmark: document.querySelector('[data-testid="bookmark"]')?.innerText,
     permalink: window.location.href
   })
5. Output: { ok, permalink, stats: { retweet, like, reply, view, bookmark } }
```

**注意**：
- view 数 Premium 账号可见；普通账号无
- 30 min 后 stats 才稳定（X 算法）
- 嵌入 evaluate 走 `document.querySelector('selector')?.innerText` —— selector 可能因 X UI 改版变，spike 验证

---

## Frequency Tracker（**新**）

```python
# ~/.openclaw/agents/main/sessions/twitter-frequency.json
{
  "last_post_at": "2026-07-05T09:30:00+08:00",
  "today_count": 5,
  "week_count": 23,
  "platform": "twitter"
}
```

**每次 post 成功后 append**：
1. 读 JSON（不存在则初始化 0/0）
2. 距 last_post_at < 30 min → **警告用户** + 询问是否继续（仍可继续，但 mark as high-risk）
3. 距 last_post_at < 5 min → **强制建议延后**（强烈风控风险）
4. today_count += N（thread 算 N 条）
5. today_count > 50 → **拒绝 + 告知用户明早再发**
6. week_count > 200 → 同上
7. 写入 JSON

---

## Content Limits

| Type | Limit |
|------|-------|
| Text (standard) | 280 characters (URL=23, Emoji=2) |
| Text (Premium/Blue) | 25,000 characters (long post) |
| Images | Up to 4 per post |
| Video | Max 512 MB, max 2m 20s |
| GIF | Max 15 MB |
| Reply | 280 characters |
| Quote Tweet | 280 characters (in comment) |
| Thread | Unlimited tweets, each ≤ 280 |

---

## Error Handling

| Situation | Action |
|-----------|--------|
| Login page appears | Session expired — inform user to re-login via browser |
| Character limit exceeded (280) | Trim content or use thread format |
| Character limit exceeded (Premium 25K) | Trim or use thread |
| Media upload fails | Retry once; check file format and size |
| Rate limit error | **Wait 30 min minimum** (not 15) + check frequency tracker |
| Post button greyed out | Content is empty or over limit — check before clicking |
| Frequency tracker warns high-risk | Ask user: continue or defer to tomorrow? |
| Quote 按钮选成 Repost | Undo（出现"Reposted"提示 → click "Undo" → 重新选 Quote）|
| Reply 按钮消失 | Refresh page（X UI 偶发 bug）|
| Long post 按钮文字不是 "Post all" | 用户不是 Premium → 切换到 standard 280 流程 |

---

## Notes

- Do NOT mention internal tool names or errors in any post
- All post content must comply with X's terms of service
- If posting on behalf of company: verify the content tone matches the company voice in MEMORY.md
- 抓 stats 仅在 post 成功页有效；不要在 compose 页面（还没有 stats）
- Quote / Reply 都要先**确认是哪种按钮**（X UI 把 "Repost" 和 "Quote" 放一起）
- 频率统计：本 skill 只采集 stats，不做评分

---

## 参考

- [X Help: Types of Posts](https://help.x.com/en/using-x/types-of-posts) — Reply / Quote / Long post 定义
- [X Algorithm 2026](https://www.teract.ai/resources/twitter-algorithm-2026) — reply weighted 27x like, 30 min 关键窗口
