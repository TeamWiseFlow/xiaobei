---
name: wx-mp-hunter
description: Search WeChat Official Accounts, retrieve the account's latest post list,
  and fetch full article content by URL. Also supports interactive QR-code login flow
  for session management.
metadata:
  openclaw:
    emoji: 📰
    requires:
      bins:
      - node
---

# WeChat Official Account Hunter (wx-mp-hunter)

Use this skill when:
- The user wants to search for a WeChat Official Account (公众号) by keyword
- The user wants to list the latest posts of a specific Official Account
- The user wants to fetch the full text of a WeChat article by its `mp.weixin.qq.com` URL
- The user provides a `mp.weixin.qq.com/mp/homepage` topic/homepage URL and wants to collect article links from that page

**Does NOT support:** WeChat Video Accounts (视频号), comments, or engagement metrics (those require Credentials).

---

## ⚠️ Agent 行为约束（必须遵守）

1. **严格按本 SKILL.md 的步骤执行**，不得在服务器结果未返回时自行编排下一步。
2. **等待服务器响应**：每次执行脚本命令后，必须等待脚本返回 JSON 结果。若结果需要时间，**先向用户说明"正在请求服务器，请稍候……"**，然后等待。
3. **严禁提前假设结果**：不得在脚本输出 JSON 之前就根据假设继续后续步骤。
4. **批量前必须小样本验证**：批量抓全文前，必须先 `check-session`，再选 1 篇文章 `fetch` 验证链路成功；成功后才能批量。
5. **路径规则**：文中所有 `./scripts/` 路径均相对于本技能所在目录（即 `<skill>` 标签 `location` 属性所指目录），**不是**工作区（workspace）目录。执行时必须按本技能的实际安装路径拼接，不得从工作区 CWD 出发拼接。

---

## Prerequisites

Wrapper 脚本路径：`./scripts/wx-mp-hunter.sh`

所有命令通过 wrapper 调用，无需手动拼接 node 命令：

```bash
./scripts/wx-mp-hunter.sh <command> [args...]
```

Session 存储路径：`~/.openclaw/logins/wx_mp.json`（可通过 `WX_SESSION_FILE` 覆盖）
Session TTL：**4 天**（到期自动触发重登）

---

## Step 0 — 登录探活

**每次使用前可选地检查 session 是否有效：**

```bash
./scripts/wx-mp-hunter.sh check-session
```

| 返回值 | 含义 |
|--------|------|
| `{"ok": true}` | session 有效，可直接使用 |
| `{"ok": false, "error": "SESSION_EXPIRED"}` (exit 2) | 需要重新登录 |

---

## 自动重新登录流程（Session 过期时触发）

**触发条件**：任意命令返回 `"error": "SESSION_EXPIRED"`（exit code 2），或首次使用无 session 文件。

### 第 1 步 — 生成二维码

```bash
./scripts/wx-mp-hunter.sh login-qr
```

等待脚本输出 JSON（**不要提前进入下一步**）：

```json
{
  "ok": true,
  "qr_path": "/tmp/wx_mp_qr.png",
  "qr_base64": "<base64 PNG>",
  "message": "二维码已保存，请用微信（公众号管理员账号）扫码，完成后运行 login-confirm"
}
```

> **注意**：二维码图片已自动保存到 `/tmp/wx_mp_qr.png`，脚本**不会**尝试打开它，也**不需要**手动打开。

### 第 2 步 — 将二维码发给用户

使用 openclaw 飞书 plugin 能力，将二维码图片（路径 `/tmp/wx_mp_qr.png`）直接发送给用户。  
**不要**只发本地文件路径——用户在飞书客户端中无法访问 agent 本地文件系统。

同时告知用户：
> "公众号 Cookie 已失效，请用微信（公众号管理员账号）扫描以下二维码重新授权。扫码并点击确认登录后，回复"已扫码"。"

### 第 3 步 — 等待用户确认

**停止执行，等待用户回复。** 用户回复"已扫码"、"好了"、"扫完了"或类似确认语即可继续。

### 第 4 步 — 确认登录

```bash
./scripts/wx-mp-hunter.sh login-confirm [--timeout 300]
```

等待脚本返回结果（脚本内部轮询，**agent 只需等待输出，不要中途中断**）：

```json
{"ok": true, "message": "登录成功，session 已保存"}
```

| 情况 | 处理 |
|------|------|
| `{"ok": true}` | 继续执行原来被中断的任务 |
| `ret != 0` 或超时 | 重新从第 1 步开始，告知用户二维码已过期 |

---

## 两条独立工作流

`fetch` 和 `search + account-posts` 是**相互独立**的两条路径，可单独使用：

```
流程 0：登录探活（每次使用前可选）
  └─ check-session

流程 1a：搜索账号 → 获取最新发布列表
  ├─ search <keyword>        → 获取 fakeid
  └─ account-posts <fakeid>  → 获取该账号最新发布文章列表

流程 1b：直接获取指定文章内容（URL 来源不限）
  └─ fetch <url>             → 获取正文

流程 1c：专题页/主页目录链接采集（mp/homepage）
  └─ browser 完整滚动页面和分类 → 提取 mp.weixin.qq.com/s 文章链接 → 如需全文再逐篇 fetch
```

> 当用户直接提供 `mp.weixin.qq.com` 文章链接时，**直接走流程 1b**，无需经过 search / account-posts。
> 当用户提供的是 `mp.weixin.qq.com/mp/homepage` 专题页/主页链接时，当前 CLI 不支持直接列出该页面全部文章；必须按“专题页抓取流程”使用 browser 完整采集目录，再对单篇链接使用 `fetch`。

---

## 专题页抓取流程（mp/homepage）

触发条件：用户提供类似以下 URL，并要求抓取该页面/专题/合集里的文章：

```text
https://mp.weixin.qq.com/mp/homepage?...
http://mp.weixin.qq.com/mp/homepage?...
```

### 目录采集

1. **不要直接承诺“已抓完全部文章”**。先说明该页面是微信动态专题页，需要完整滚动加载后统计。
2. 使用 browser 打开专题页。
3. 先执行整页滚动到底，直到 `document.documentElement.scrollHeight` 连续多次稳定。
4. 查找分类 tab（常见 class：`.jsCate`）。对每个分类逐个执行：
   - 点击分类；
   - 等待内容加载；
   - 从顶部滚动到底，直到高度稳定；
   - 提取所有 `a[href*="mp.weixin.qq.com/s"]` 的标题和链接。
5. 合并顶部推荐与各分类结果，按 URL 去重。
6. 向用户报告：分类列表、原始链接数、去重文章数；如果数量明显偏少，继续滚动或请用户确认页面是否还存在折叠/下拉区域。

### 全文采集

1. 批量抓全文前，必须先运行：
   ```bash
   ./scripts/wx-mp-hunter.sh check-session
   ```
2. 如果返回 `SESSION_EXPIRED`，先执行自动重新登录流程。
3. 登录有效后，只选 1 篇样本运行：
   ```bash
   ./scripts/wx-mp-hunter.sh fetch <article_link> --html
   ```
4. 只有样本返回 `content_text` / `content_markdown` / `content_html` 后，才允许批量抓全文。
5. 如果样本返回 `未找到文章正文 (#js_content)`，用 browser 打开该文章验证页面内容：
   - 如果出现“环境异常”“拖动下方滑块完成拼图”等验证页，**不得尝试绕过验证码或自动拖滑块**；告知用户需要人工完成微信环境验证后再继续。
   - 如果是文章已删除、私有或付费，跳过该文章并记录失败原因。
6. 批量抓取时每篇间隔 1–2 秒；连续失败 3 篇以上时停止批量，先检查错误，不要继续跑完整列表。

---

## 命令详解

### search — 搜索公众号

```bash
./scripts/wx-mp-hunter.sh search <keyword> [--begin N] [--size N]
```

| Option | Default | Description |
|--------|---------|-------------|
| `keyword` | required | 搜索词（账号名或别名） |
| `--begin` | 0 | 分页偏移 |
| `--size` | 10 | 每页数量（最大 20） |

输出示例：
```json
{
  "total": 3,
  "accounts": [
    {
      "fakeid": "MzA3NzAyMzMyMA==",
      "nickname": "Python之禅",
      "alias": "the_zen_of_python",
      "signature": "...",
      "service_type": 0,
      "avatar": "https://..."
    }
  ]
}
```

**注意**：保存 `fakeid`，后续 `account-posts` 命令需要它。

`service_type`：0 = 订阅号，2 = 服务号。

---

### account-posts — 获取指定账号最新发布列表

> 原命令名 `articles` 仍可用（向后兼容），推荐使用 `account-posts`。

```bash
./scripts/wx-mp-hunter.sh account-posts <fakeid> [--begin N] [--size N] [--keyword K]
```

| Option | Default | Description |
|--------|---------|-------------|
| `fakeid` | required | 来自 search 结果 |
| `--begin` | 0 | 分页偏移（每页 20，依次传 0、20、40…） |
| `--size` | 20 | 每页数量（最大 20） |
| `--keyword` | "" | 按标题关键词过滤 |

输出示例：
```json
{
  "total": 312,
  "begin": 0,
  "size": 20,
  "articles": [
    {
      "aid": "2247483649_1",
      "title": "文章标题",
      "link": "https://mp.weixin.qq.com/s/xxxxx",
      "digest": "文章摘要",
      "author": "作者名",
      "create_time": 1710000000,
      "cover": "https://...",
      "item_show_type": 0,
      "is_deleted": false,
      "is_pay_subscribe": 0,
      "wecoin_count": 0
    }
  ]
}
```

**分页**：循环传入 `--begin 0`、`--begin 20`… 直到 `articles` 为空或 `begin >= total`。

`item_show_type`：0/1 = 图文，5 = 视频，6 = 音乐，8 = 图片帖。

`is_pay_subscribe`：0 = 免费，1 = 付费文章（直接 fetch 正文需要公众号管理员 Credential，本 skill 不支持）。`wecoin_count` 为对应的微信豆价格。

**重要**：请求间隔保持 1–2 秒，避免连续快速请求。

---

### fetch — 获取文章全文

```bash
./scripts/wx-mp-hunter.sh fetch <url> [--html]
```

| Option | Description |
|--------|-------------|
| `url` | 文章链接（`mp.weixin.qq.com`） |
| `--html` | 同时返回正文原始 HTML |
| `--download-images` | 把正文图片下载到本地，`content_markdown` 中的图片 URL 替换为本地相对路径 |
| `--output-dir <dir>` | 图片下载目标目录（配合 `--download-images`；默认当前目录） |

输出示例：
```json
{
  "url": "https://mp.weixin.qq.com/s/xxxxx",
  "title": "文章标题",
  "author": "公众号名称",
  "publish_time": "2024-03-10",
  "content_text": "正文纯文本内容...",
  "content_markdown": "段落文字……\n\n![](https://mmbiz.qpic.cn/mmbiz_jpg/xxxxx/0?wx_fmt=jpeg)\n\n继续文字……**加粗**……",
  "images": [
    "https://mmbiz.qpic.cn/mmbiz_jpg/xxxxx/0?wx_fmt=jpeg",
    "https://mmbiz.qpic.cn/mmbiz_png/xxxxx/0?wx_fmt=png"
  ]
}
```

| 字段 | 说明 |
|------|------|
| `content_text` | 纯文本正文（去除所有 HTML 标签） |
| `content_markdown` | Markdown 格式正文，图片以内联 `![](url)` 放在原文位置，保留加粗/斜体/链接；`--download-images` 时 URL 替换为 `images/<hash>.<ext>` 本地相对路径 |
| `images` | 正文所有图片 CDN 链接（从 `data-src` 解析） |

### 图片本地化

加 `--download-images --output-dir <dir>` 后，脚本并发下载（默认 4 并发、单图 ≤5MB、总量 ≤100MB、单图失败重试 1 次）到 `<dir>/images/<hash>.<ext>`，并把 `content_markdown` 里的图片 URL 替换为本地相对路径，便于离线阅读 / 二次加工 / 转存。仅依赖 Node 18+ stdlib，无 npm 依赖。

```
./scripts/wx-mp-hunter.sh fetch <url> --html --download-images --output-dir ./article-out
```

---

## 典型用法示例

**场景 A：监控某账号最新文章**
```
1. check-session            → 探活
2. search "公众号名"         → 得到 fakeid
3. account-posts <fakeid>   → 得到文章列表（第 1 页）
4. fetch <article_link>     → 获取感兴趣文章的正文
```

**场景 B：直接抓取已知 URL 的文章**
```
1. check-session            → 探活
2. fetch <url>              → 直接获取正文
```

**场景 C：批量获取**
```
loop account-posts --begin 0, 20, 40, ...
  for each article link: fetch <link>
  pause 1-2s between requests
```

---

## 错误处理

| Error | 原因 | 处理 |
|-------|------|------|
| `未登录` | 无 session 文件 | 执行登录流程 |
| `"error": "SESSION_EXPIRED"` (exit 2) | Session 过期或 ret=200003 | 执行**自动重新登录流程** |
| `API 错误 (ret=...)` | 微信 API 错误 | 检查网络，重试一次 |
| `HTTP 4xx` on fetch | 文章已删除或私有 | 跳过该文章 |
