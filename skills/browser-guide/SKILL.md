---
name: browser-guide
description: Best practices for using the managed browser — handling login walls,
  CAPTCHAs, lazy-loaded content, paywalls, and tab cleanup. Phase 4.5+ prefers
  camoufox-cli for login / scraping flows (anti-detect); built-in browser tool
  + patchright remains as fallback for attaching the user's local Chrome.
metadata:
  openclaw:
    emoji: 🌐
    requires:
      bins:
      - camoufox-cli
---

# Browser Best Practices

> **Phase 4.5+ 主推 vs fallback 关系**：
> - **主推**：`camoufox-cli`（反指纹 headless Firefox）— 登录 / 抓取 / 取数场景默认走这条，详见 §0
> - **fallback**：openclaw 内置 `browser` tool + patchright（attach 用户本机 Chrome）— 适用于 camoufox 跑不通 / 用户已有本机 Chrome 需交互的场景，详见 §1-6
>
> 何时用 fallback：① camoufox-cli 在某平台持续触发风控；② 任务需要用户在浏览器里实时操作（人手介入）；③ 单次调试 / 排错

Follow these rules whenever you use the `browser` tool (fallback) or `camoufox-cli` (主推) to interact with web pages.

## 0. Camoufox-CLI 模式（主推）

`camoufox-cli` 是 Phase 4.5+ 反指纹 headless Firefox 包装（D18），优先于内置 `browser` tool。所有路径必须用 **绝对路径** 调用 `camoufox-cli`（在 PATH 里即可直接调，或通过 wrapper）。相关 cookie 管理走 **login-manager** skill（不在本 skill 范围）。

### 0.1 登录流程（qr-headless + qr-confirm）

与平台 cookie 相关的登录一律走 login-manager skill 的两步式：

```bash
# 步骤 A：启 headless 会话 + 截 QR（输出 qr_path 和 session）
login-manager.sh qr-headless xhs-browse

# 步骤 B：用户扫码后，调 qr-confirm 轮询 + 落盘 cookies
login-manager.sh qr-confirm xhs-browse --session xhs-browse-login-abc12345 --timeout 180
```

完整流程、用户消息模板、退出码语义见 **login-manager** skill。本 skill 不重复描述。

**什么时候**用 camoufox-cli 走登录 vs 直接用 browser tool（fallback）：
- 用 camoufox-cli：默认所有情况（反指纹 + 用户体验好 + 无 CDP 依赖）
- 退回 browser tool：camoufox-cli 在某平台持续触发风控，或用户要求在自己 Chrome 里手动登录

### 0.2 抓取 / 取数流程（headless session + cookies import）

需要浏览器交互但不涉及登录态变化的取数（搜索结果、笔记详情、文章内容等）：

```bash
# 1. 从中央存储注 cookie 到临时 camoufox session
login-manager.sh cookie-import <platform> <agent-session-abc>

# 2. 启 session 跑抓取（headless + persistent + cookies 已在）
camoufox-cli --session <agent-session-abc> --persistent --headless --json \
    open "https://www.xiaohongshu.com/search_result?keyword=xxx"

# 3. snapshot / eval 取数
camoufox-cli --session <agent-session-abc> --json snapshot
camoufox-cli --session <agent-session-abc> --json eval "document.body.innerText"

# 4. 任务结束关 session（释放 daemon + 进程）
login-manager.sh session-cleanup <platform> <agent-session-abc>
```

**约束**：第 2 步后只能用 camoufox-cli 的 `snapshot` / `eval` / `click` / `type` 子命令，**不要**混用 openclaw 内置 `browser` tool 指向同一 profile dir（会冲突）。

### 0.3 Session 隔离与并发

**每 agent 一 session**（D18 + 4.5.5）：
- 不同 agent / 不同任务流 → 各自独立 session（独立 daemon + 独立 profile dir + 独立 cookie state）
- 禁止两个 agent 共享 camoufox session（profile dir 冲突会污染 cookie state + 触发风控）
- session 名规则：`{platform}-{purpose}-{nonce}`，如 `xhs-browse-agent-xyz78901`

**指纹模板**：camoufox-cli 启动时读 `<profile dir>/camoufox-cli.json`。Docker 镜像内已 bake 冻结模板到 `/root/.openclaw/logins/_template/`，运行时各 agent session 启动前 `cp` 模板到自己的 profile dir 复用指纹。**不要**在运行时重生成（会污染多 session 的指纹一致性）。

### 0.4 QR 截图与发图

`login-manager.sh qr-headless` 输出的 `qr_path` 是 PNG 本地路径。**用 image 工具加载图片**（不能发本地路径给用户），按 login-manager skill §2 步骤 2 提示用户扫码。

### 0.5 失败模式

| 症状 | 原因 | 缓解 |
|---|---|---|
| `camoufox-cli open` 超时 | Firefox 启动慢 / 系统资源紧张 | 增加 `--timeout`；先 `camoufox-cli close --all` 清残留 |
| `qr-confirm` 一直轮询不到成功 | 平台风控 / 用户未点确认 | 用户手机上确认后再说；不要盲等超过 `--timeout`（默认 180s） |
| `cookie-import` 后访问仍 401 | cookies 过期 / 域不匹配 | 重新走 0.1 登录流；检查平台对应 `xhs-publish` / `xhs-browse` |
| `snapshot` 返回空 DOM | 页面 lazy-load / 反爬 | eval 检查 `document.readyState`；加等待 + 滚动（见 §4） |
| daemon 残留进程 | close 失败 | `camoufox-cli close --all` 兜底；每任务结束必须 cleanup |

---

## 1. Login Prompts（fallback 路径 — 优先 §0 camoufox-cli 主推）

> **fallback 触发条件**：① camoufox-cli 在该平台持续触发风控；② 用户主动要求在自己浏览器里手动登录；③ 单次调试 / 排错。**默认情况下用 §0.1**。

When a page shows a login wall, first identify which login mechanism is offered, then follow the matching procedure below.

**General constraint: retry at most 2 times per login attempt — frequent retries risk account suspension.**

### 1-A. Browser saved credentials

1. Check whether the login form has auto-filled credentials from saved passwords. If so, use them.
2. On failure, continue to 1-B / 1-C / 1-D as appropriate.

### 1-B. QR Code login

When the login page shows a QR code (WeChat Official Account backend, Xiaohongshu creator centre, X/Twitter, etc.):

1. Use `snapshot` to locate the QR code image element. Download / screenshot it and save it to `/tmp/` (e.g., `/tmp/xhs_qr.png`).
2. Send the QR code image downloaded in the previous step to the user via message, making sure to send the image itself rather than the local file path.
3. Notify the user:
   > "**[平台名称]** 登录已失效（或首次使用），请用 **[平台]** APP 扫描以下二维码登录。扫码并在手机上点击确认后，回复"已扫码"。"
4. **Stop and wait** for the user to reply "已扫码"、"好了"、"扫完了" or any equivalent confirmation before continuing.
5. While waiting, poll the page every **3 seconds** using `snapshot` for signs of successful login (URL change, QR code disappears, dashboard/avatar appears). If auto-detected, resume immediately without waiting for the user reply.
6. If no scan occurs within **3 minutes** and no reply arrives, send: _"扫码超时，将继续处理当前可访问的内容。"_ and proceed.

### 1-C. SMS verification login

When the login page asks for a phone number and SMS verification code:

1. Ask the user for the registered phone number for this platform:
   > "**[平台名称]** 需要手机验证码登录，请告知您在该平台注册的手机号。"
2. Once received, enter the phone number and trigger the SMS code request. Attempt at most **2 times** if the first trigger fails.
3. Ask the user for the verification code:
   > "短信验证码已发送，请将收到的验证码回复给我。"
4. Enter the code and complete login. If login fails, inform the user and proceed with accessible content — **do not retry a third time**.

### 1-D. Username / password login

When only a username + password form is available:

1. Check for browser-saved credentials first (see 1-A).
2. If none, ask the user for their preference:
   > "**[平台名称]** 需要账号密码登录，浏览器中未找到预存密码。请选择：① 您自行在浏览器中登录后告知我，② 告知用户名和密码由我代为登录。"
3. If the user chooses ②, receive the credentials and attempt login. Retry at most **2 times** on failure.
4. If login fails after 2 attempts, inform the user and continue with accessible content.

### 1-E. Fallback — login not possible

If login cannot be completed for any reason (timeout, user unavailable, repeated failures):

- **Do NOT stop or abort the task.**
- Continue with whatever content is accessible in the non-logged-in state.
- At the end, include a note in the result: _"注：[平台名称] 未能完成登录，以下内容来自未登录状态，可能不完整。"_

## 2. Simple Verification / CAPTCHA

When a page shows a one-click verification challenge (e.g., a button labelled "去验证", "Verify", "I'm not a robot", or a simple checkbox):

1. Try clicking the verification button/checkbox directly.
2. Wait a few seconds for the page to refresh.
3. Take a snapshot to check whether normal content has loaded.
4. If the page now shows the expected content, continue your task.

## 3. Complex Verification Fallback

If the simple click in Step 2 above **fails** — the page still shows a challenge, the challenge is a puzzle/slider/image-selection CAPTCHA, or an error occurs:

1. **Do NOT retry blindly.** Stop attempting automated verification.
2. Send a message to the user: _"xx 页面有验证码，我无法解决，请在浏览器中完成，完成后请通知我。"_（xx 为页面标题）.
3. Wait for the user to confirm.
4. If no response arrives within **5 minutes**, continue with whatever content is accessible.

## 4. Lazy-Loaded Content

When a page uses lazy loading (infinite scroll, "load more" sections, content that appears only after scrolling):

1. Before scrolling, assess whether the not-yet-loaded content is **relevant** to the current task.
2. If relevant, simulate human-like scrolling: scroll down incrementally, pause briefly between scrolls to allow content to load, then take a snapshot to capture the new content.
3. Repeat until the needed content is visible or no more new content loads.
4. Do NOT scroll too fast, do it as a human would. After 7 times of scrolling, you should stop this turn.
5. If not relevant, skip scrolling and work with what is already loaded.

## 5. Browser `evaluate` Action — Expression Only

When using the browser tool's `evaluate` (or `act` with `kind: "evaluate"`) to run JavaScript in the page context, the `fn` parameter must be a **single expression**, not a statement block. Declarations (`const`, `let`, `var`), semicolons, `for`/`if` statements, and `function` declarations will all cause `Invalid evaluate function` errors.

**Wrong** (statement block — will fail):
```js
const items = document.querySelectorAll('.msg');
let found = false;
for (const item of items) {
  if (item.textContent.includes('target')) { found = true; break; }
}
found ? 'ok' : 'no';
```

**Correct** (wrap in IIFE):
```js
(function() {
  var items = document.querySelectorAll('.msg');
  for (var i = 0; i < items.length; i++) {
    if (items[i].textContent.indexOf('target') > -1) { return items[i].innerText; }
  }
  return 'not found';
})()
```

**Correct** (pure expression, for simple lookups):
```js
document.querySelector('.reply-btn') ? 'found' : 'not found'
```

Rules:
- Always wrap multi-step logic in an IIFE: `(function(){ ... })()`
- For DOM queries that only need to click, prefer `click` action on a selector over `evaluate`
- For reading text, prefer `snapshot` over `evaluate` when possible
- Never use `const`/`let`/`var` declarations or `;` at the top level of `fn`

## 6. Paywall / Subscription Walls

When a page indicates that content is behind a paywall or requires a specific subscription (e.g., "Subscribe to continue reading", "Continue reading with a WSJ subscription", premium-only banners):

1. Send a message to the user describing the situation: _"xx 页面需要订阅，请在浏览器中登录有效账号或者完成付费，完成后请通知我。"_（xx 为页面标题）.
2. Wait for the user to confirm.
3. If no response arrives within **5 minutes**, continue with whatever content is accessible (summary, headline, or any visible excerpt).
