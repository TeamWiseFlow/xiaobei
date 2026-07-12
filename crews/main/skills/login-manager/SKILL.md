---
name: login-manager
description: 平台登录态管理指导文件。约定各平台登录流程（强制有头手动登录）、探活规则、中央 cookie+UA 存储路径约定。仅管 5 个平台（douyin/kuaishou/bilibili/xhs-publish/xhs-browse），其他平台完全不涉及。实际 cookie/UA 导出由 camoufox-cli 的 cookies export + identity export 完成，本 skill 无脚本。
metadata:
  openclaw:
    emoji: 🔑
---

# Login Manager（平台登录态管理 — 纯指导文件）

本 skill 是**纯 SKILL.md 指导文件**，无脚本。cookie / UA 的导出/导入由 **camoufox-cli** 的 `cookies export` / `cookies import` / `identity export` 命令完成（全局可用的 `camoufox-cli` 命令）。

在任何需要平台 cookie 的 skill（xhs-content-ops / xhs-publish / douyin-publish / viral-chaser / published-track 等）调用前，先用本 skill 的流程把登录态就绪。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 探活节奏 / 中央存储路径约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义登录 + 导出 cookie/UA 即可。

---

## 支持的平台（仅这 5 个）

| 平台 key | 登录模式 | 中央存储文件 |
|----------|---------|---------|
| `douyin` | **有头手动** | `~/.openclaw/logins/douyin.json` + `~/.openclaw/logins/douyin.ua.json` |
| `bilibili` | **有头手动** | `~/.openclaw/logins/bilibili.json` + `~/.openclaw/logins/bilibili.ua.json` |
| `kuaishou` | **有头手动** | `~/.openclaw/logins/kuaishou.json` + `~/.openclaw/logins/kuaishou.ua.json` |
| `xhs-publish` | **有头手动**（创作者域 `creator.xiaohongshu.com`） | `~/.openclaw/logins/xhs-publish.json` + `~/.openclaw/logins/xhs-publish.ua.json` |
| `xhs-browse` | **有头手动**（消费者域 `www.xiaohongshu.com`） | `~/.openclaw/logins/xhs-browse.json` + `~/.openclaw/logins/xhs-browse.ua.json` |

> **不在这 5 个之内的平台**（twitter / weibo / zhihu / xianyu / weixin-channel / wx_mp 等）的登录态管理**不走本 skill**——各平台专属 skill 自管登录（持久化 session 内闭环，见各 skill SKILL.md）。本 skill 不为它们落中央 cookie。
>
> **wx_mp（公众号）特例**：wx_mp 不归本 skill 管，自己一套独立的探活/登录/导出体系，由 `wx-mp-hunter` + `wx-mp-engagement` 两技能共用（走 camoufox-cli + 无头截 QR）。导出的 `wx_mp.json` + `wx_mp.ua.json` 依然落 `~/.openclaw/logins/` 同目录，只是管理自管、本 skill 不沾。详见 `docs/platform-login-and-browser-spec.md` §4。

> **xhs 双平台说明**：小红书的浏览/互动和发布使用不同的 cookie 域，因此拆为两个独立平台：
> - `xhs-publish`：创作者平台（`creator.xiaohongshu.com`），用于发布笔记/视频
> - `xhs-browse`：消费者端（`www.xiaohongshu.com`），用于搜索、浏览、互动

### 登录模式约定（强制统一有头）

- **有头手动**：所有 5 个平台一律 `--headed` 启 session，用户在浏览器里手动扫码 / 短信 / 账号密码完成登录。agent 不主动触发登录动作，只开浏览器等用户。
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

### UA 文件格式（`camoufox-cli identity export` 输出，对应原则 4）

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

**关键**：cookie 和 UA **同时导出**（原则 4）。所有用中央 cookie 的下游脚本/技能，导入 cookie 时**同时导入 UA**——同一指纹下的 cookie 才不会被风控错配（见 spec §8 profile 丢失处理）。

---

## 登录流程（agent 操作手册）

### 步骤 0：探活（先验当前登录态是否还有效）

对持久化 session（涉及登录的平台一律走持久化，见 spec 补充 A），先打开 session 探活：

```bash
SESSION="<platform>"   # 持久化 session 名 = 平台 key，见下方约定
camoufox-cli --session "$SESSION" --persistent --headless --json open "<平台首页 URL>"
sleep 3
camoufox-cli --session "$SESSION" --json snapshot
# snapshot 看页面是否跳到登录页 / 出现登录按钮 / 互动数据是否正常
# → 没跳登录页、内容正常 = 登录态有效，可 close 后交下游用
# → 跳到登录页 / 出现登录按钮 = 登录态失效，走步骤 1 重登
camoufox-cli --session "$SESSION" --json close
```

### 步骤 1：启 session 打开登录页（强制有头手动）

```bash
# 所有 5 平台一律有头
camoufox-cli --session <platform> --persistent --headed --json open "<平台登录页 URL>"
# 有头窗口弹出后，告知用户在浏览器里手动登录（扫码 / 短信 / 账号密码）
```

**持久化 session 命名约定**：session 名 = 平台 key（`douyin` / `bilibili` / `kuaishou` / `xhs-publish` / `xhs-browse`）。每个平台**一个且只有一个持久化 session**（原则 1，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）。

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

两个文件都写成功后，login-manager 流程结束。可 `close` session 或留着给下游用。

> **原则 5 强化**：**严禁浏览器方案导入 cookie**造一个登录会话。cookie 只能由「真实登录 → export」产出，下游需要登录态就开 session 走 import（见下方「下游导入模式」）。任何「用 cookie 造一个登录会话」的动作禁止——xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹会错配 → 被风控检测（2026-06-29 CDP 注入 22 cookie 触发风控的教训）。

---

## 下游导入模式（其他 skill 用中央 cookie/UA 时）

下游 HTTP skill（viral-chaser / xhs-content-ops 等）从 `~/.openclaw/logins/<platform>.json` + `~/.openclaw/logins/<platform>.ua.json` 加载，**同时导入 cookie 和 UA**：

```python
import json
cookies = json.load(open("~/.openclaw/logins/<platform>.json"))["cookies"]
ua = json.load(open("~/.openclaw/logins/<platform>.ua.json"))["userAgent"]
# 给 raw HTTP：header 里同时带 cookie 和 UA
cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if domain in c['domain'])
headers = {"Cookie": cookie_header, "User-Agent": ua}
```

下游 camoufox-cli skill 需登录态时，开持久化 session + import cookie + import UA：

```bash
SESSION="<下游自命名，不要复用平台 session 名>"   # 见下方「并发约束」
camoufox-cli --session "$SESSION" --persistent --headless --json open "<首页>"
camoufox-cli --session "$SESSION" --persistent --json cookies import ~/.openclaw/logins/<platform>.json
# UA 由 camoufox-cli 在 persistent profile 里已冻结，不需要再 import；只在脚本侧 raw HTTP 时才手动 import UA
```

> camoufox-cli `cookies import` 格式与 `cookies export` 完全对称（= Playwright `add_cookies` 格式），零转换。

---

## 并发约束

- **每平台一个持久化 session**：session 名 = 平台 key。同一平台的重登 / 下游 import 走 fail-first 队列（同 session 已有命令在跑时新命令直接 fail）——不要在同一 platform session 上并发开多个登录流。
- 下游 skill 用中央 cookie 时**开独立 session 名**（如 `xhs-browse-fetch-<nonce>`），不要复用平台持久化 session 名。
- 不同 agent / 不同登录流程 → 各自独立 session，独立 profile dir。

---

## Notes

- **Do not retry login more than once automatically** — frequent retries risk account suspension (per browser-guide guidelines)
- **Bilibili** public video access often works without cookies; only request login if video is unavailable
- **Never store cookies in code or logs** — the session files are stored only in `~/.openclaw/logins/`
- **camoufox 探活失败时不要盲试**：`open + snapshot` 现场检查 session 内页面状态，再决定是否触发重登
- **profile 丢失 / 损坏 / 指纹错配** → 重建 + 重登录，**绝对不允许导入 cookie 造会话**（spec §8，补充 D）
