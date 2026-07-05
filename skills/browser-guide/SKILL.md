---
name: browser-guide
description: 浏览器使用规则。涉及浏览器操作时**优先 camoufox-cli**，内置 browser
  tool 仅在 camoufox 跑不通 / 用户明确要求 / 需要用户实时操作界面时使用。
  **绝不**修改 openclaw.json 中 browser 配置。
metadata:
  openclaw:
    emoji: 🌐
    requires:
      bins:
      - camoufox-cli
---

# Browser Guide

> **核心规则**：本 skill **不是**教你"如何使用浏览器"——camoufox-cli 与内置 `browser` tool 各自有 SKILL.md / docs。本 skill 是 **浏览器工具选择的硬规则**，所有 agent 必须遵守。

---

## 1. 工具选择规则（**最重要**）

| 场景 | 用什么 |
|------|------|
| 登录 / 扫码 / Cookie 导入 / 平台反爬敏感 | **camoufox-cli**（主推，反指纹 headless Firefox）|
| 数据抓取 / 批量取数 / SPA hydration | **camoufox-cli** |
| **用户需要在自己浏览器里实时操作** | 内置 `browser` tool（headless=false 有头模式） |
| **camoufox-cli 在某平台持续触发风控** | 内置 `browser` tool（fallback）|
| **用户明确要求** | 内置 `browser` tool（用户在某场景偏好）|
| 单次调试 / 排错 | 内置 `browser` tool（更快上手）|

**默认规则**：**任何场景都先用 camoufox-cli**，只有上述 4 种"兜底场景"才用内置 `browser` tool。

---

## 2. camoufox-cli 使用要点

### 2.1 登录流程
- **两步式**：先 `login-manager qr-headless <platform>` 启 headless + 截 QR → 再 `qr-confirm <platform> --session <s> --timeout 180` 轮询 + 落 cookie
- 完整流程在 `login-manager` skill，不在本 skill 重复

### 2.2 取数流程
- `cookie-import <platform> <session>` 注 cookie → `camoufox-cli --session <s> --persistent --headless open <url>` → snapshot / eval / click / type → `session-cleanup`

### 2.3 调用约定
- **绝对路径**调用 `camoufox-cli`（PATH 友好）
- session 名格式：`<platform>-<purpose>-<nonce>`（`secrets.token_hex(4)` 唯一）
- 每任务一 session，结束 `session-cleanup`

### 2.4 详细流程
- `login-manager` skill（cookie 中央存储 + 9 子命令）
- `browser-guide` SKILL.md §2.2（之前详细取数流程保留——略，agent 自行查看）

---

## 3. 内置 `browser` tool 使用要点（**fallback 而已**）

### 3.1 什么场景用
- §1 列的 4 种"兜底场景"：**用户实时操作 / camoufox 风控 / 用户明确要求 / 调试**

### 3.2 默认配置（用户已配）
- `browser.headless: false`（有头模式）
- `browser.attachOnly: false`
- `browser.defaultProfile: openclaw`

### 3.3 注意事项
- **不**主动改 `openclaw.json` 的 browser 配置（即使 camoufox 不灵）
- cookie 不走中央存储（browser tool 用内置 Chrome profile）—— 跟 camoufox 路径隔离
- 调试 / 排错可临时改 `headless: true`，但**必须告知用户**，并完成后恢复

---

## 4. 硬规则（**违反即 agent 自查**）

1. **默认走 camoufox-cli**（§1 表格清晰）
2. **不**主动修改 `~/.openclaw/openclaw.json` 的 `browser.*` 配置
3. **不**主动修改 `~/.openclaw/openclaw.json` 的 `agents.defaults` / `agents.list[].browser`
4. 内置 `browser` tool 只在 §1 表格的 4 种兜底场景下使用
5. **所有浏览器操作必须走 cookie 中央存储**（login-manager）+ camoufox session，或走内置 browser tool 的内置 profile——**不**自创 cookie 文件路径
6. 浏览器操作结束**必须 cleanup**（`login-manager session-cleanup <platform> <session>` 或 browser tool 的 close tab）

---

## 5. 频率限制（**默认遵守**）

- 单日 camoufox session 创建 ≤ 50（每个 agent）
- 同一平台 cookie 复用即可，**不**每次重新登录
- 风控触发后 24h 静默 + 告知用户
- 详见 `login-manager` skill + 各平台 skill 的 pitfall 章节

---

## 6. 反检测规则

- camoufox-cli 用 `~/.camoufox-cli/profiles/_template/camoufox-cli.json` 指纹模板（Docker bake 时生成）
- 每个 agent session cp 模板 → 独立 profile dir（指纹一致但 cookie 隔离）
- **不**尝试 disable / patch 指纹检测（违反平台 ToS）

---

## 7. 错误处理

| 现象 | 排查路径 |
|------|----------|
| camoufox-cli 启 headless 失败 | 检查 `camoufox-cli install --with-deps`；CPU/RAM 是否够 |
| cookie import 后访问仍 401 | 走 `login-manager qr-headless + qr-confirm` 重登 |
| 反复触发风控 | **不再第 3 次**；告知用户考虑换账号 / 暂停 24h |
| browser tool 找不到元素 | 截图后告知用户手动操作 |

---

## 8. 相关 skill

- `login-manager`（9 子命令 + cookie 中央存储）
- `twitter-post` / `twitter-interact`（camoufox-cli 主推使用范例）
- `douyin-publish` / `wechat-channels-publish`（浏览器自动化发布范例）
- `wx-mp-hunter`（公众号文章抓取）
- `xhs-content-ops` / `xhs-publish`（小红书抓/发，**仅 client 端**）