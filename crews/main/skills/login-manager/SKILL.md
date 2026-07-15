---
name: login-manager
description: 平台登录态管理。约定各平台登录流程（强制有头手动登录）、探活规则、中央 cookie+UA 存储路径约定。仅管 4 个平台（douyin/kuaishou/bilibili/xhs-browse），其他平台完全不涉及（xhs-publish 自管登录，见 xhs-publish SKILL.md）。
metadata:
  openclaw:
    emoji: 🔑
    requires:
      bins:
      - node
---

# Login Manager（平台登录态管理）

本 skill 提供**导出+验证脚本** `login-manager --platform <p>`（wrapper → `scripts/export-and-verify.ts`）：导出 cookie 到临时 → 两层探活验证（cookie 字段 + 平台 pong，借 `_shared/check-session.ts` `verifyCookies`）→ 通过才 commit 到中央存储 + identity export → close session。验证不过直接报错（exit 2），**不重试**，避免风控。

> **打开浏览器 + 通知用户登录这一步不放进脚本**——涉及通知用户、对话确认，脚本化会卡住对话。Agent 自己 `camoufox-cli --session <p> --persistent --headed open <loginUrl>`，告知用户在窗口内登录，与用户对话确认登录完成后，再调 `login-manager --platform <p>` 导出+验证。cookie / UA 的底层导出仍由 **camoufox-cli** 的 `cookies export` / `identity export` 完成。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 探活节奏 / 中央存储路径约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义登录 + 导出 cookie/UA 即可。

---

## 导出+验证脚本（Agent 确认登录后调用）

`login-manager --platform <p>`（wrapper 直调 `scripts/export-and-verify.ts`，绝对路径见 TOOLS.md）。

平台 ∈ `douyin` / `bilibili` / `kuaishou` / `xhs-browse`。

**前置（Agent自己做，不进脚本）**：
1. `camoufox-cli --session <p> --persistent --headed --json open <平台登录页 URL>`
2. 告知用户「**[平台]** 浏览器已打开，请在窗口里手动完成登录，完成后告诉我」
3. 与用户对话，等用户确认登录完成（Stop and wait，不盲轮询）

**然后调脚本**，脚本流程：
1. `camoufox cookies export <tmp>` 导出 cookie 到临时文件（不直接落中央存储——先验过再 commit）。
2. **两层探活验证**（`_shared/check-session.ts` `verifyCookies`，新鲜 pong 不读缓存）：
   - Tier 1 cookie 关键字段：douyin→sessionid+sid_tt+uid_tt、bilibili→SESSDATA/DedeUserID、kuaishou→webday7/userId/passToken、xhs-browse→web_session。
   - Tier 2 平台 pong：bilibili `/x/web-interface/nav`、kuaishou graphql `visionProfileUserList`、xhs-browse `edith.xiaohongshu.com/api/sns/web/v2/user/me`、douyin `/aweme/v1/web/history/read/`。
   - 签名平台缺 `OFB_KEY` → `SIGN_UNAVAILABLE` 仅警告（presence 已过，登录本身成功），不 fail。
   - 验证不过 → exit 2，**未 commit 中央存储**，不重试。
3. 验过 → commit `~/.openclaw/logins/<p>.json` + `identity export <p>.ua.json`。
4. **close session**——登录态已落磁盘 profile + 中央存储，不留浏览器进程占内存。

Exit：`0`=成功 / `1`=参数错·crash / `2`=SESSION_EXPIRED（探活不过，未 commit）。

> Agent 不必再分两次构造 `cookies export` / `identity export` 命令——确认登录后一条 `login-manager --platform <p>` 闭环导出+验证。下方「登录流程（agent 操作手册）」是分步说明，供排故 / `target=host` 后端参考。

---

## 支持的平台（仅这 4 个）

| 平台 key | 登录模式 | 中央存储文件 |
|----------|---------|---------|
| `douyin` | **有头手动** | `~/.openclaw/logins/douyin.json` + `~/.openclaw/logins/douyin.ua.json` |
| `bilibili` | **有头手动** | `~/.openclaw/logins/bilibili.json` + `~/.openclaw/logins/bilibili.ua.json` |
| `kuaishou` | **有头手动** | `~/.openclaw/logins/kuaishou.json` + `~/.openclaw/logins/kuaishou.ua.json` |
| `xhs-browse` | **有头手动**（消费者域 `www.xiaohongshu.com`） | `~/.openclaw/logins/xhs-browse.json` + `~/.openclaw/logins/xhs-browse.ua.json` |

> **不在这 4 个之内的平台**（twitter / weibo / zhihu / xianyu / weixin-channel / wx_mp / xhs-publish 等）的登录态管理**不走本 skill**——各平台专属 skill 自管登录（持久化 session 内闭环，见各 skill SKILL.md）。本 skill 不为它们落中央 cookie。
>
> **wx_mp（公众号）特例**：wx_mp 不归本 skill 管，自己一套独立的探活/登录/导出体系，由 `wx-mp-hunter` + `wx-mp-engagement` 两技能共用（走 camoufox-cli + 无头截 QR）。导出的 `wx_mp.json` + `wx_mp.ua.json` 依然落 `~/.openclaw/logins/` 同目录，只是管理自管、本 skill 不沾。
>
> **xhs-publish（小红书发布）特例**：xhs-publish 走创作者域 `creator.xiaohongshu.com`，cookie 与 xhs-browse 消费者域是两套独立登录、不能共用。发布端登录 + 探活由 `xhs-publish` 技能**自管**（`scripts/login-and-verify.ts` + `check-login.ts`，探活走创作者域 `personal_info` 裸 GET，无需签名）。本 skill 不沾 xhs-publish。

> **xhs 双平台说明**：小红书的浏览/互动和发布使用不同的 cookie 域，因此拆为两个独立平台：
> - `xhs-publish`：创作者平台（`creator.xiaohongshu.com`），用于发布笔记/视频——**自管登录**（见 xhs-publish SKILL.md）
> - `xhs-browse`：消费者端（`www.xiaohongshu.com`），用于搜索、浏览、互动——本 skill 管

### 登录模式约定（强制统一有头）

- **有头手动**：所有 4 个平台一律 `--headed` 启 session，用户在浏览器里手动扫码 / 短信 / 账号密码完成登录。agent 不主动触发登录动作，只开浏览器等用户。
- 本 skill **不再有无头特例**——历史上 wx_mp 曾用无头截图 QR，现 wx_mp 已移出本 skill 自管，本 skill 内全部平台强制有头。

---

## 中央存储路径约定

```
~/.openclaw/logins/<platform>.json          # cookie（camoufox-cli 原生 JSON 格式 = Playwright add_cookies 格式）
~/.openclaw/logins/<platform>.ua.json       # UA + 指纹摘要（camoufox-cli identity export 输出）
```

### cookie 文件格式（camoufox-cli `cookies export` 原生输出）

```json
{
  "platform": "xhs-browse",
  "cookies": [
    {
      "name": "web_session",
      "value": "xxx",
      "domain": ".xiaohongshu.com",
      "path": "/",
      "expires": -1,
      "httpOnly": true,
      "secure": false,
      "sameSite": "Lax"
    }
  ],
  "updated_at": "2026-07-04T12:00:00+00:00"
}
```

### UA 文件格式（`camoufox-cli identity export` 输出）

```json
{
  "userAgent": "Mozilla/5.0 ...",
  "platform": "Win32",
  "language": "zh-CN",
  "languages": ["zh-CN", "zh", "en-US", "en"],
  "viewport": { "width": 1920, "height": 1080 },
  "persistent": "/home/u/.camoufox-cli/profiles/xhs-browse",
  "identity": { "os": "windows", "locale": "zh-CN", "fingerprintHash": "a1b2…16hex" },
  "exportedAt": "2026-07-11T…"
}
```

**关键**：cookie 和 UA **同时导出**。所有用中央 cookie 的下游脚本/技能，导入 cookie 时**同时导入 UA**——同一指纹下的 cookie 才不会被风控错配。

---

## 登录流程（agent 操作手册）

### 步骤 0：探活（先验当前登录态是否还有效）

对持久化 session（涉及登录的平台一律走持久化），先打开 session 探活(这一步不是登录，可以用默认无头模式)：

```bash
SESSION="<platform>"   # 持久化 session 名 = 平台 key，见下方约定
camoufox-cli --session "$SESSION" --persistent --json open "<平台首页 URL>"
sleep 3
camoufox-cli --session "$SESSION" --json snapshot
# snapshot 看页面是否跳到登录页 / 出现登录按钮 / 互动数据是否正常
# → 没跳登录页、内容正常 = 登录态有效，探活完即 close session（登录态在磁盘 profile，下游按需重起无头复用）
# → 跳到登录页 / 出现登录按钮 = 登录态失效，走步骤 1 重登
```

### 步骤 1：启 session 打开登录页（强制有头手动）

```bash
# 所有 4 平台一律有头
camoufox-cli --session <platform> --persistent --headed --json open "<平台登录页 URL>"
# 有头窗口弹出后，告知用户在浏览器里手动登录（扫码 / 短信 / 账号密码）
```

**持久化 session 命名约定**：session 名 = 平台 key（`douyin` / `bilibili` / `kuaishou` / `xhs-browse`）。每个平台**一个且只有一个持久化 session**（fail-first 队列：同 session 已有命令在跑时新命令直接 fail）。

### 步骤 2：等用户完成登录

告知用户「**[平台]** 浏览器已打开，请在窗口里手动完成登录，完成后告诉我」。等用户回复后 `snapshot` 验登录态就位。

**Stop and wait**，不要盲轮询。3 分钟内无回复发超时提示「扫码超时，将继续处理当前可访问的内容」并退出。

### 步骤 3：导出 cookie + UA 落中央存储

登录成功后**同时导出 cookie 和 UA**：

```bash
# cookie 落中央存储
camoufox-cli --session <platform> --persistent --json cookies export ~/.openclaw/logins/<platform>.json

# UA + 指纹摘要落中央存储（fork 加的 identity export 命令，与 cookies export 对称）
camoufox-cli --session <platform> --persistent --json identity export ~/.openclaw/logins/<platform>.ua.json
```

两个文件都写成功后，login-manager 流程结束。**随即 close session**——登录态已落两处：磁盘 profile（`~/.camoufox-cli/profiles/<platform>/`）+ 中央 cookie/UA 文件，不留浏览器进程占内存。下游浏览器类 skill（`xhs-interact` / `douyin-publish` 等）用 `--session <platform> --persistent` 重起**无头** session 即从磁盘 profile 恢复登录态，用完再 close。session 卡死时由调用方手动 `camoufox-cli --session <platform> --json close` teardown。

> **严禁**：**严禁 camoufox-cli（浏览器方案）通过 `cookies import` 导入 cookie 造一个登录会话**。浏览器操作一律走 login-manager 真实登录后的**持久化 session**（登录态 + 指纹冻结在 session profile 里），不开临时 session 再 import cookie 那一套。xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹的浏览器会话会错配 → 被风控检测。
>
> **cookie 导入仅供脚本 / 纯 HTTP 消费**：中央存储的 cookie + UA 文件只给下游**脚本**（`viral-chaser` / `xhs-content-ops` / `published-track` / `douyin-publish` / `xhs-publish` 等的 Python / TS 脚本）做 raw HTTP 抓取用——脚本侧把 cookie 拼进 `Cookie` header、把 UA 填进 `User-Agent` header 直接发 HTTP 请求，**不经浏览器**。脚本**必须同时导入 cookie 和 UA**（同一指纹下的 cookie 才不会被风控错配）。
>
> **浏览器类下游 skill**（如 `xhs-interact` 这类纯 camoufox-cli 操作技能）共享同一持久化 session 名即可——用 `--session <平台 key> --persistent` 重起无头 session，从磁盘 profile 恢复本 skill 登录态，**不开独立 session、不 import cookie、用完即 close**。

---

## 下游导入模式（仅脚本 / 纯 HTTP 用）

下游脚本（viral-chaser / xhs-content-ops / published-track / xhs-publish / douyin-publish）从 `~/.openclaw/logins/<platform>.json` + `~/.openclaw/logins/<platform>.ua.json` 加载，**同时导入 cookie 和 UA** 喂给 raw HTTP header（同一指纹）。

> 该同时导入已由各下游脚本在代码里硬保证**——每个脚本都显式读 `{platform}.json` 的 `cookies` 数组 + `{platform}.ua.json` 的 `userAgent` 字段，拼进 HTTP `Cookie` / `User-Agent` header，UA 缺失时回退 DEFAULT_UA。

**浏览器类下游 skill 不走本节**：camoufox-cli 操作的技能（如 `xhs-interact`）用 `--session <平台 key> --persistent` 重起无头 session 复用本 skill 落盘的登录态，不另开临时 session、不 import cookie、用完即 close。

### HTML 登录墙检测（脚本 / 纯 HTTP 用，大小写不敏感）

下游脚本做 raw HTTP fetch 期望 JSON 时，若 session 失效，平台可能返回 **HTML 登录页**（200 `text/html` 或 302→login）而非 JSON error code。此时 `resp.json()` 会抛 "Unexpected token <" 乱码错，agent 看不懂、不会触发重登。

`_shared/relay-sign.ts` 的 `xhsFetch` 已内置登录墙检测：响应 content-type 含 `text/html` 或 body 以 HTML 标签开头 → 抛 `LoginWallError`（消息以 `SESSION_EXPIRED:` 起头），下游脚本捕获后 emit `{ok:false, error:"SESSION_EXPIRED", platform}` + exit 2，交本 skill 重登。

**检测正则大小写不敏感**（借鉴 OpenCLI 229b3b0）：`/^<(?:!doctype|html|head|body|title)(?:[\s>/]|$)/i`——覆盖 `<!DOCTYPE`/`<!doctype`/`<!Doctype`/`<html`/`<HTML`/`<Html`/`<head`/`<HEAD`/`<body`/`<title>` 等所有大小写变体，末尾 `[\s>/]` 做 word boundary 防 `<htmlfoo>` 误匹配。新增的 raw-HTTP 脚本若不走 `xhsFetch`，应复用同款检测，别只 `startsWith('<!DOCTYPE')` 几种硬大小写。

---

## 并发约束

- **每平台一个持久化 session**：session 名 = 平台 key。同一平台的重登 / 多个浏览器类 skill 共用 session 名时走 fail-first 队列（同 session 已有命令在跑时新命令直接 fail）——不要在同一 platform session 上并发开多个登录流；浏览器操作 skill 串行排队，各自用完即 close（登录态在磁盘 profile，不靠常驻进程）。
- 不同 agent / 不同登录流程 → 各自独立 session，独立 profile dir。

---

## Notes

- **Do not retry login more than once automatically** — frequent retries risk account suspension (per browser-guide guidelines)
- **Never store cookies in code or logs** — the session files are stored only in `~/.openclaw/logins/`
- **camoufox 探活失败时不要盲试**：`open + snapshot` 现场检查 session 内页面状态，再决定是否触发重登
- **profile 丢失 / 损坏 / 指纹错配** → 重建 + 重登录，**绝对不允许导入 cookie 造会话**
