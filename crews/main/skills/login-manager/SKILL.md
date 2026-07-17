---
name: login-manager
description: 平台登录态管理。约定各平台登录流程（强制有头手动登录）、探活规则、中央 cookie+UA 存储路径约定。仅管 4 个平台（douyin/kuaishou/bilibili/xhs-browse）。
metadata:
  openclaw:
    emoji: 🔑
    requires:
      bins:
      - node
---

# Login Manager（平台登录态管理）

管 4 个平台的登录态：`douyin` / `bilibili` / `kuaishou` / `xhs-browse`。其他平台（twitter / weibo / zhihu / xianyu / weixin-channel / wx_mp / xhs-publish 等）**不走本 skill**——各平台专属 skill 自管登录。

## 支持的平台

| 平台 key | 登录页 URL（有头打开） | 中央存储文件 |
|----------|----------------------|---------|
| `douyin` | `https://www.douyin.com/` | `~/.openclaw/logins/douyin.json` + `douyin.ua.json` |
| `bilibili` | `https://passport.bilibili.com/login` | `~/.openclaw/logins/bilibili.json` + `bilibili.ua.json` |
| `kuaishou` | `https://www.kuaishou.com/` | `~/.openclaw/logins/kuaishou.json` + `kuaishou.ua.json` |
| `xhs-browse` | `https://www.xiaohongshu.com/` | `~/.openclaw/logins/xhs-browse.json` + `xhs-browse.ua.json` |

---

## 用法（Agent 操作步骤）

### Step 1 — 有头打开登录页

```bash
camoufox-cli --session <platform> --persistent --headed --json open "<登录页 URL>"
```

session 名 = 平台 key（`douyin` / `bilibili` / `kuaishou` / `xhs-browse`），每个平台一个持久化 session。

### Step 2 — 通知用户登录并等待确认

告知用户「**[平台]** 浏览器已打开，请在窗口里手动完成登录，完成后告诉我」。**Stop and wait**，等用户回复确认，不要盲轮询。3 分钟无回复发超时提示并退出。

### Step 3 — 导出 + 验证（用户确认登录后调用）

```bash
login-manager --platform <platform>
```

脚本一条命令闭环：导出 cookie 到临时 → 两层探活验证（cookie 字段 + 平台 pong）→ 通过才 commit 到中央存储 + 导出 UA → close session。验证不过直接 exit 2，**不重试**（避免风控）。

**失败时保留 session**：任何错误路径（导出/读取/验证/commit 失败）都**不 close session**——浏览器进程留着，Agent/用户可在原窗口重试或重登，避免被强制关闭丢登录态又得重新扫码。只有 exit 0 成功路径才 close。脚本内部 camoufox-cli 调用一律带 `--headed`，与 Step 1 的 open 对齐，避免 daemon 模式冲突重启杀掉 session。

| Exit | 含义 | Agent 动作 |
|------|------|-----------|
| `0` | 成功，cookie+UA 已落中央存储 | 继续下游任务 |
| `1` | 参数错 / crash / `SIGN_UNAVAILABLE`（签名缺 OFB_KEY） | 请用户提供 OFB_KEY 后，交 IT engineer 配凭证 |
| `2` | `SESSION_EXPIRED`（探活不过，未 commit） | 提醒人工排查账号状态，不重试 |

---

## 注意事项

**并发约束**：每平台一个持久化 session，session 名 = 平台 key。同一 platform session 上走 fail-first 队列（同 session 已有命令在跑时新命令直接 fail），不要并发开多个登录流。浏览器类下游 skill（如 `xhs-interact`）用 `--session <平台 key> --persistent` 重起无头 session 复用本 skill 落盘的登录态，用完即 close。

**重登纪律**：不自动重试超过一次——频繁重试有封号风险。cookie 只存 `~/.openclaw/logins/`，不进代码 / 日志。profile 丢失 / 指纹错配 → 重建 + 重登录，绝对不允许导入 cookie 造会话。

本技能只负责登录、导出，导出后的Cookie和UA消费按下游技能约定。

---

## 背后的原理（供 `target=host` / `target=node` 时参考）

> 主力后端 = `target=camoufox`，上面命令针对 camoufox。`target=host` / `target=node` 只按本 skill 的**流程 + 约定**走——何时有头 / 探活节奏 / 中央存储路径是**后端无关**的，照本 skill 执行；不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义登录 + 导出 cookie/UA 即可。

**两层探活**（`_shared/check-session.ts`）：
- Tier 1 cookie 关键字段：douyin→`sessionid`+`sid_tt`+`uid_tt`、bilibili→`SESSDATA`/`DedeUserID`、kuaishou→`webday7`/`userId`/`passToken`、xhs-browse→`web_session`。
- Tier 2 平台 pong：bilibili `/x/web-interface/nav`、kuaishou graphql `visionProfileUserList`、xhs-browse `edith.xiaohongshu.com/api/sns/web/v2/user/me`、douyin `/aweme/v1/web/history/read/`。pong 带 TTL 缓存（批量探活把 N 次 pong 压成 1 次）。
- 签名平台缺 `OFB_KEY` → `SIGN_UNAVAILABLE` 仅警告（presence 已过，登录本身成功），不 fail。

**中央存储路径约定**：
```
~/.openclaw/logins/<platform>.json     # { platform, cookies: [...], updated_at }（camoufox-cli cookies export 原生格式 = Playwright add_cookies 格式）
~/.openclaw/logins/<platform>.ua.json  # { userAgent, platform, language, ... }（camoufox-cli identity export 输出）
```
cookie 和 UA **必须同时导出**——同一指纹下的 cookie 才不会被风控错配。下游脚本导入时同时读两文件，拼进 HTTP `Cookie` / `User-Agent` header。

**验证后再 commit**：导出到临时文件 → `verifyCookies` 验过才落中央存储，避免把失效/不完整 cookie 喂给下游。新鲜 pong 不读缓存（登录验证不能用批量探活的 TTL 缓存）。

**强制有头手动登录**：所有平台一律 `--headed`，用户在浏览器里手动扫码 / 短信 / 账号密码完成登录。agent 不主动触发登录动作，只开浏览器等用户。

**严禁 cookie import 造会话**：浏览器操作一律走真实登录后的**持久化 session**（登录态 + 指纹冻结在 session profile 里），不开临时 session 再 `cookies import`。xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹的浏览器会话会错配 → 被风控检测。中央存储的 cookie+UA 只给下游**脚本**做 raw HTTP 抓取用（拼进 header 直接发请求，不经浏览器）。

**HTML 登录墙检测**（脚本 / 纯 HTTP 用）：下游 raw HTTP fetch 期望 JSON 时，session 失效平台可能返回 HTML 登录页（200 `text/html` 或 302→login）而非 JSON error，`resp.json()` 抛乱码错。`_shared/relay-sign.ts` 的 `xhsFetch` 已内置登录墙检测（content-type 含 `text/html` 或 body 以 HTML 标签开头 → 抛 `LoginWallError`，消息以 `SESSION_EXPIRED:` 起头），下游捕获后 emit `SESSION_EXPIRED` + exit 2。新增 raw-HTTP 脚本若不走 `xhsFetch` 应复用同款检测（正则大小写不敏感）。
