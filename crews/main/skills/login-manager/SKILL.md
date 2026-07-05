---
name: login-manager
description: Manage platform login state (cookies) for Douyin, Bilibili, Kuaishou,
  XHS, and other platforms. Uses camoufox-cli to capture QR login flows and export
  cookies to a central store.
metadata:
  openclaw:
    emoji: 🔑
    requires:
      bins:
      - python3
      - camoufox-cli
---

# Login Manager（平台登录态管理，camoufox-cli 路径）

Use this skill **before** calling any skill that requires platform cookies (viral-chaser, xhs-content-ops, xhs-publish, etc.). It ensures valid cookies are available, performing QR-code-based re-login via `camoufox-cli` when session expires.

> 📍 **exec 调用方式**：本 skill 的 wrapper 路径为 `~/.openclaw/workspace-main/skills/login-manager/scripts/login-manager.sh`（具体路径以部署时 setup-crew 注入为准；TOOLS.md 也会给出）。**不要**用 `cd <dir> && ./scripts/xxx.sh` 复合形式（触发 allowlist miss），也**不要**用相对路径 `./scripts/...`（agent 容易误拼 CWD/前缀）。

---

## Storage Location

All platform sessions are stored at:

```
~/.openclaw/logins/{platform}.json
```

File format (camoufox-cli 原生 JSON 格式，= Playwright `add_cookies` 期望格式)：

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

Supported platform values: `douyin` | `bilibili` | `kuaishou` | `xhs-publish` | `xhs-browse` | `weibo` | `zhihu` | `wechat-channels`

> **小红书双平台说明**：小红书的浏览/互动和发布使用不同的 cookie 域，因此拆为两个独立平台：
> - `xhs-publish`：创作者平台（`creator.xiaohongshu.com`），用于发布笔记/视频
> - `xhs-browse`：消费者端（`www.xiaohongshu.com`），用于搜索、浏览、互动

---

## CLI（统一入口）

所有命令通过 `login-manager.sh`（绝对路径调用）：

```bash
# 探活类
login-manager.sh check <platform>        # 探活；exit 0=有效, 2=失效
login-manager.sh read  <platform>        # 输出中央 JSON
login-manager.sh write <platform>        # 从 stdin 写中央 JSON
login-manager.sh status-all              # 批量探活

# camoufox 会话管理
login-manager.sh qr-headless <platform> [url]   # 启 headless 会话 + 截图 QR → stdout JSON
login-manager.sh qr-confirm <platform> --session <session>   # 轮询扫码 → cookies export 落盘
login-manager.sh cookie-export <platform> <session>   # 从已登录 camoufox session 落中央 JSON
login-manager.sh cookie-import <platform> <session>   # 从中央 JSON 注 camoufox session
login-manager.sh session-cleanup <platform> <session> # 关闭 camoufox session
```

退出码：
- `0` — 成功
- `1` — 通用错误
- `2` — session 失效 / 扫码超时 → 触发重新登录流程

---

## Usage

### 1. 检查 session 有效性

```bash
login-manager.sh check xhs-browse
```

行为：
1. 读 `~/.openclaw/logins/xhs-browse.json`
2. 文件缺失 / 为空 → exit 2
3. 用 stored cookies 探活平台 URL，HTTP 200/3xx → exit 0 + 输出 `{ok, platform, updated_at, cookie_count}`
4. 探活失败 → exit 2

### 2. Session 失效后的 QR 重新登录流程（exit 2 后）

当 `check` 返回 exit 2 时，按以下两步走：

#### 步骤 A：启 headless + 截图 QR

```bash
login-manager.sh qr-headless xhs-browse
```

输出 JSON：
```json
{
  "ok": true,
  "session": "xhs-browse-login-abc12345",
  "platform": "xhs-browse",
  "qr_path": "/tmp/qr-xhs-browse-1783152197.png",
  "login_url": "https://www.xiaohongshu.com/"
}
```

**agent 流程**：
1. 把 `qr_path` 指向的 PNG 用 image 工具加载（**不要发本地路径**）
2. 发给用户：「**小红书** 登录已失效（或首次使用），请用 **小红书** APP 扫描以下二维码登录。扫码并在手机上点击确认后，回复"已扫码"。」
3. **Stop and wait** 等用户回复"已扫码" / "好了" / "扫完了"
4. 拿到 `session` 字段，给步骤 B 用

#### 步骤 B：轮询扫码成功 + 落盘

```bash
login-manager.sh qr-confirm xhs-browse --session xhs-browse-login-abc12345 --timeout 180
```

行为：
1. 轮询 camoufox session 内的 `window.location.href` + QR 元素存在性
2. URL 离开 login 页 + QR 元素消失 → 判定登录成功
3. 调 `camoufox-cli cookies export ~/.openclaw/logins/xhs-browse.json` → 写入中央存储
4. 输出 `{ok, platform, session}` → exit 0
5. 180s 内未成功 → exit 2

### 3. 关闭用过的 camoufox session

```bash
login-manager.sh session-cleanup xhs-browse xhs-browse-login-abc12345
```

释放 daemon + Firefox 进程，profile dir 保留（cookies 已在中央存储）。

### 4. 批量探活

```bash
login-manager.sh status-all
```

扫描 `~/.openclaw/logins/` 所有平台，输出 JSON 总览：

```json
{
  "platforms": [
    {"platform": "xhs-browse", "ok": true, "updated_at": "...", "cookie_count": 12},
    {"platform": "douyin",     "ok": false, "updated_at": "...", "cookie_count": 5}
  ],
  "total": 2,
  "valid": 1,
  "expired": 1
}
```

### 5. 其他 skill 取 cookie 模式

下游 HTTP skill（viral-chaser / xhs-content-ops 等）从 `~/.openclaw/logins/{platform}.json` 加载 cookie，薄适配 3 行（camoufox-cli 原生格式 = Playwright 格式）：

```python
import json
cookies = json.load(open(f"~/.openclaw/logins/{platform}.json"))["cookies"]
# 给 raw HTTP：
header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if domain in c['domain'])
# 给 Playwright/patchright Python：
#   context.add_cookies(cookies)  # 零适配
```

---

## 并发约束

- **每 agent 一 session**：禁止两个 agent 共享同一个 camoufox session（profile dir 冲突会污染 cookie state）
- session 名规则：`{platform}-{purpose}-{nonce}`，如 `xhs-browse-agent-xyz78901`
- 不同 agent / 不同登录流程 → 各自独立 session，独立 profile dir

## 实现约束

- **不 fork camoufox-cli**：原生 CLI 够用
- **不 bake chromium**：Dockerfile 阶段 1 只装 camoufox Firefox 二进制
- **保留 patchright fallback**：本 skill 替换 CDP 路径后，openclaw 内置 browser tool + patchright 仍可作用户 Chrome attach fallback（见 browser-guide §fallback）

---

## Notes

- **Do not retry login more than once automatically** — frequent retries risk account suspension (per browser-guide guidelines)
- **QR code login is preferred** for Douyin and Kuaishou — ask user to scan with mobile app
- **Bilibili** public video access often works without cookies; only request login if video is unavailable
- **Never store cookies in code or logs** — the session files are stored only in `~/.openclaw/logins/`
- **camoufox 探活失败时不要盲试**：用 `cookie-import` + `camoufox-cli eval` 现场检查 session 内 cookie 状态，再决定是否触发 QR 登录
