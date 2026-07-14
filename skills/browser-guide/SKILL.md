---
name: browser-guide
description: Best practices for using the managed browser — handling login walls,
  CAPTCHAs, lazy-loaded content, paywalls, and tab cleanup. Target=camoufox 主力路径。
metadata:
  openclaw:
    emoji: 🌐
---

# Browser Best Practices

Follow these rules whenever you drive a browser against web pages.

## 0. 浏览器后端选择（先读这一节）

本 skill 默认主力路径是 **`target=camoufox`**——即全局可用的 `camoufox-cli` 命令。**下方所有操作命令、示例、selector 都只针对 `target=camoufox`** 写。

如果你当前是 **`target=host`**（existing-session 真机 Chrome + chrome-mcp relay）或 **`target=node`**（remote-cdp 远端 Chrome）：

- **只按本 skill 列出的「流程 / 步骤 / 提示事项」执行**——不要照搬下面的 `camoufox-cli ...` 命令、`snapshot` ref、`eval` 入参等具体操作和示例。
- 浏览器操作走你当前后端自带的浏览器工具语义（host: chrome-mcp relay；node: remote-cdp + playwright-core），按各后端自身约定调用即可。
- 何时有头 / 何时无头、登录流程顺序、CAPTCHA 处理原则、lazy-load 滚动节奏、paywall 等用户交互约定是**后端无关**的，照本 skill 执行。

### 0.1 camoufox-cli 基本用法

```
camoufox-cli --session <name> [--persistent] [--headed] [--json] <command> [args...]
```

- **`--session <name>`**：会话隔离单元，同名 session 共享一个 profile 目录。**涉及登录的平台用一个且只用一个持久化 session 名**。
- **`--persistent`**：冻结指纹到 `~/.camoufox-cli/profiles/<name>/camoufox-cli.json`（首次生成后冻结）。持久化平台 session 必带；临时性 session（新闻等不登录站点）**不带**——走默认临时 profile，每次随机指纹，关闭自清。
- **`--headed`**：有头模式。**需要用户配合过验证码、扫码、收短信的，或者填表场景，必须 `--headed`**（微信公众号wx_mp和微信视频号weixin_channel可以使用无头模式截图含二维码区域发用户登录）。其他场景，包括探活，都可以使用默认的无头模式。
- **`--json`**：命令输出走 JSON 信封（`{ok, ...}` / `{error, ...}`），agent 解析稳定，推荐常带。
- 命令集（含 `upload` / `identity export`）：
  `open / back / forward / reload / url / title / close / snapshot / click / fill / type / select / check / hover / press / text / eval / screenshot / pdf / scroll / wait / tabs / switch / close-tab / sessions / cookies / install / upload / identity`

**fail-first 队列**：同一 session 已有命令在跑时，新命令**直接 fail**，返回文本：

```
session <name> 正忙，请等待当前操作完成后再试
```

读到这条 fail 文本说明有其他进程在使用同名session，你应该等待一段时间后再重试，卡死用 `camoufox-cli close --all` 兜底 teardown。

### 0.2 snapshot ref 优先

camoufox-cli 的 `snapshot` 返回带 ref 的语义快照（`@e1` `@e2` …），后续 `click` / `fill` / `type` / `upload` / `hover` / `press` 全部**优先传 ref**，不要自己 hack CSS selector。找不到元素时**先 snapshot 看真实 DOM 结构**再决定 selector 改写，不要盲试。

---

## 1. Login Prompts

When a page shows a login wall, first identify which login mechanism is offered, then follow the matching procedure below.

**General constraint: retry at most 2 times per login attempt — frequent retries risk account suspension.**

### 1-A. Browser saved credentials

1. Check whether the login form has auto-filled credentials from saved passwords. If so, use them.
2. On failure, continue to 1-B / 1-C / 1-D as appropriate.

### 1-B. QR Code login

When the login page shows a QR code (WeChat Official Account backend, WeChat Channels, Xiaohongshu creator centre, X/Twitter, etc.):

1. `camoufox-cli --session <s> --json screenshot /tmp/qr-<platform>.png` 截下 QR 图（或 `snapshot` 拿到 QR 元素 ref 后用 `eval` 取其 `src`/`data URI`）。
2. Send the QR code image to the user via message — send the image itself, not the local file path.
3. Notify the user:
   > "**[平台名称]** 登录已失效（或首次使用），请用 **[平台]** APP 扫描以下二维码登录。扫码并在手机上点击确认后，回复"已扫码"。"
4. **Stop and wait** for the user to reply "已扫码"、"好了"、"扫完了" or any equivalent confirmation before continuing.
5. While waiting, poll the page every **3 seconds** (`snapshot` 看 URL 是否跳走 / QR 元素是否消失 / dashboard 是否出现). Auto-detected → resume immediately without waiting for user reply.
6. If no scan within **3 minutes** and no reply arrives, send: _"扫码超时，将继续处理当前可访问的内容。"_ and proceed.

> **显式有头/无头模式场景规则**：只有以下场景需要显式指定 `camoufox-cli` 的有头/无头参数：
> 1. **login-manager 登录**（douyin / kuaishou / bilibili / xhs-publish / xhs-browse 5 平台）——强制 `--headed`，用户在浏览器手动扫码/短信/账号密码
> 2. **需要用户手动过验证**（captcha / 滑块 / 短信）——`--headed`，用户才能在浏览器里手动操作
> 3. **web-form-fill 表单填报**——强制 `--headed`，便于用户时刻观察填报情况、可随时介入纠正
>
> 其他场景默认走 camoufox 持久化 session，**不显式指定有头/无头**——camoufox-cli 默认行为即可。
>
> **wx_mp（公众号）无头截图 QR** 是特例，适用于 `wx-mp-hunter` + `wx-mp-engagement` 两技能。

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

---

## 2. Simple Verification / CAPTCHA

When a page shows a one-click verification challenge (e.g., a button labelled "去验证", "Verify", "I'm not a robot", or a simple checkbox):

1. Try clicking the verification button/checkbox directly（`camoufox-cli --session <s> --json click <ref 或 selector>`）.
2. Wait a few seconds for the page to refresh.
3. `snapshot` 检查正常内容是否已加载.
4. If the page now shows the expected content, continue your task.

---

## 3. Complex Verification Fallback

If the simple click in Step 2 above **fails** — the page still shows a challenge, the challenge is a puzzle/slider/image-selection CAPTCHA, or an error occurs:

1. **Do NOT retry blindly.** Stop attempting automated verification.
2. Send a message to the user: _"xx 页面有验证码，我无法解决，请在浏览器中完成，完成后请通知我。"_（xx 为页面标题）.
   > 涉及登录的 session 必须是 **有头模式**，用户才能在浏览器里手动过验证。无头跑出来的 session 遇验证码先 teardown 再换有头重开。
3. Wait for the user to confirm.
4. If no response arrives within **5 minutes**, continue with whatever content is accessible.

---

## 4. Lazy-Loaded Content

When a page uses lazy loading (infinite scroll, "load more" sections, content that appears only after scrolling):

1. Before scrolling, assess whether the not-yet-loaded content is **relevant** to the current task.
2. If relevant, simulate human-like scrolling: `camoufox-cli --session <s> --json scroll down` 增量滚动，pause briefly between scrolls to allow content to load, then `snapshot` capture new content.
3. Repeat until the needed content is visible or no more new content loads.
4. Do NOT scroll too fast, do it as a human would. After 7 times of scrolling, you should stop this turn.
5. If not relevant, skip scrolling and work with what is already loaded.

---

## 5. 页面内 JS 执行（`eval` / `act kind="evaluate"`）

camoufox-cli 的 `eval` 在页面上下文跑一段 JS 并回结果。**入参必须是一个单一表达式**，不是语句块。`const`/`let`/`var` 声明、分号、`for`/`if` 语句、`function` 声明都会触发 `Invalid evaluate function` 错误。

**Wrong**（语句块 — 会失败）：
```js
const items = document.querySelectorAll('.msg');
let found = false;
for (const item of items) {
  if (item.textContent.includes('target')) { found = true; break; }
}
found ? 'ok' : 'no';
```

**Correct**（IIFE 包裹）：
```js
(function() {
  var items = document.querySelectorAll('.msg');
  for (var i = 0; i < items.length; i++) {
    if (items[i].textContent.indexOf('target') > -1) { return items[i].innerText; }
  }
  return 'not found';
})()
```

**Correct**（纯表达式，简单查询）：
```js
document.querySelector('.reply-btn') ? 'found' : 'not found'
```

Rules:
- Always wrap multi-step logic in an IIFE: `(function(){ ... })()`
- 只需要点击的 DOM 查询，优先 `click <ref>` 而非 `eval`
- 读文本优先 `snapshot` 而非 `eval`
- Never use `const`/`let`/`var` declarations or `;` at the top level of `fn`

---

## 6. Paywall / Subscription Walls

When a page indicates that content is behind a paywall or requires a specific subscription (e.g., "Subscribe to continue reading", "Continue reading with a WSJ subscription", premium-only banners):

1. Send a message to the user describing the situation: _"xx 页面需要订阅，请在浏览器中登录有效账号或者完成付费，完成后请通知我。"_（xx 为页面标题）.
2. Wait for the user to confirm.
3. If no response arrives within **5 minutes**, continue with whatever content is accessible (summary, headline, or any visible excerpt).
