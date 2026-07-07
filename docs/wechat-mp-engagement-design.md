# 微信公众号 engagement 数据接入设计（方案 A）

> 2026-07-04 · DEVPLAN Phase 4.6 · 状态：设计阶段，spike 验证待真机测试。
>
> **本轮开发约束**（见 [[30-client-dev-session-2026-07-04]]）：本机实例不动；openclaw 源码读 `~/wiseflow-pro/openclaw/`；阶段完成统一部署。
>
> **本设计**不实施真机 spike（无公众号账号环境）；spike checklist 见文末。

## 一、背景与现状

### published-track 现状

`crews/main/skills/published-track/` 是统一发布追踪：

- 18 个平台表（`pub_<platform>`），其中 `pub_wx_mp` 已就位（字段：reads / shares / favorites / likes / comments / top_comment）
- 抓取入口：`scripts/fetch-and-update-metrics.sh`（封装 login-manager 探活 + fetch-retro-data.ts 抓取 + update-metrics.sh 写入）
- **当前 wx_mp / wx_channel 列入 `MANUAL_PLATFORMS`** —— 只能手动 update，无自动抓取

`fetch-retro-data.ts` 自动支持的平台：
```
SCRIPT_PLATFORMS="xhs bilibili douyin kuaishou"
```

**缺口**：公众号 (`wx_mp`) engagement 数据（阅读数 / 评论数）只能用户手动填。

### 抓取点（公开信息整理）

公众号后台已统一迁移到**新版创作者中心**（2024 后）：

| 功能 | URL（推测，需 spike 验证） |
|---|---|
| 后台入口 | `https://mp.weixin.qq.com/` |
| 扫码登录 | `https://mp.weixin.qq.com/cgi-bin/bizlogin?action=validate` |
| 内容管理列表 | `https://mp.weixin.qq.com/cgi-bin/framehtml/getcontents?type=10&...` |
| 单篇分析 | `https://mp.weixin.qq.com/cgi-bin/framehtml/getappmsgdetail?__biz=...&appmsgid=...` |
| 评论管理 | `https://mp.weixin.qq.com/cgi-bin/framehtml/getcommentlist?action=list&...` |

> **注意**：上述 URL 是基于公开信息推测的；具体参数 / 鉴权 header / 频率限制需 spike 验证。

**单篇阅读数** 抓取路径（推测）：
- 路径 A：单篇分析页 DOM 解析（camoufox `eval` 取 `document.querySelector('.read-count').innerText`）
- 路径 B：内容管理列表 API 直接返回（每个 item 字段含 read_num / like_num）
- 路径 C：群发消息 API `/cgi-bin/masssend?action=get`（已废弃，仅历史数据）

**评论数 / 评论内容** 抓取路径（推测）：
- 评论管理 API `/cgi-bin/framehtml/getcommentlist`

## 二、目标

用 **camoufox-cli + login-manager 拿 cookie + 创作者中心爬虫** 替换 `MANUAL_PLATFORMS` 中 `wx_mp` 的"手动填"。**不碰 relay**（凭据是会话 token，relay 持有无益）。

## 三、约束（D18 + D20 + D8）

- **D18 浏览器方案**：camoufox-cli 主推；不 fork；不 bake chromium
- **D18 并发**：每 agent 一 session（独立 daemon + 独立 profile dir）
- **D20 skill 依赖**：依赖装到 `~/.openclaw/skills/<skill>/vendor/`，由 it-engineer 规范
- **整块 client 容器内闭环**（dev plan 划界）
- **仅支持用户自己有后台权限的号**（创作者中心用公众号账号登录），竞品号拿不到——这是产品约束（不是技术约束）
- **不影响 published-track 现有 API 兼容**：`fetch-and-update-metrics.sh --platform wx_mp` 行为变更不能破坏其他平台的脚本

## 四、方案 A 架构

### 4.1 新增 skill：`crews/main/skills/wx-mp-engagement/`

与现有 `wx-mp-hunter`（抓公众号文章内容）解耦——后者只抓公开内容，**不需登录**；前者要登录后台拿 engagement。

```text
crews/main/skills/wx-mp-engagement/
├── SKILL.md                            # 用户面向
├── scripts/
│   ├── wx-mp-engagement.sh             # wrapper（绝对路径友好）
│   ├── fetch_engagement.py             # 核心：cookie + 抓取 + 写 DB
│   └── tests/
│       └── test_fetch_engagement.py    # 单元测试
```

### 4.2 子命令（与 published-track 集成）

```bash
# 探活（前置）
login-manager.sh check wx-mp

# 失效后：camoufox 扫码登录流程
login-manager.sh qr-headless wx-mp
login-manager.sh qr-confirm wx-mp --session <s> --timeout 180

# 抓取某 row 的 engagement（与 published-track 集成）
wx-mp-engagement.sh fetch --row-id <pub_wx_mp.id>
wx-mp-engagement.sh fetch --source-folder <folder>
wx-mp-engagement.sh fetch-all --days 7   # 批量最近 7 天未更新

# 一键（与 fetch-and-update-metrics.sh 集成）
fetch-and-update-metrics.sh --platform wx_mp --id <rowid>
```

### 4.3 抓取流程

```
1. login-manager.sh check wx-mp → exit 0 继续 / exit 2 触发 qr-headless + qr-confirm
2. 启 camoufox session：login-manager.sh cookie-import wx-mp <session>
3. camoufox-cli --session <session> --persistent --headless open <创作者中心 URL>
4. eval / snapshot 拿数据（DOM 解析 或 API 调用，spike 决定）
5. 解析 → 标准 JSON（reads/likes/comments/top_comment）
6. update-metrics.sh 写 pub_wx_mp 表
7. session-cleanup 释放
```

### 4.4 cookie 域与平台 key

**新增 login-manager 平台**：`wx-mp`（中央存储 `~/.openclaw/logins/wx-mp.json`）

- login_manager.py 加 `wx-mp` 到 `VALID_PLATFORMS`
- `PLATFORM_LOGIN_URL["wx-mp"] = "https://mp.weixin.qq.com/"`
- `PLATFORM_PROBE_URL["wx-mp"]` —— 探活 URL（具体路径 spike 决定，建议：单篇分析页或内容管理首页）

**注意**：`wx-mp` 与 `wx-mp-publisher`（发布用的 AppID/AppSecret）是**两套凭据**——本 skill 只用浏览器 session token，不动 AppID/AppSecret。

### 4.5 并发与 session 隔离

| 用途 | session 命名 | profile dir |
|---|---|---|
| 登录 | `wx-mp-login-{nonce}` | 独立 |
| 抓取（每个任务） | `wx-mp-engagement-{nonce}` | 独立 |
| 抓取（批量） | `wx-mp-engagement-batch-{nonce}` | 独立 |

**每 agent / 每任务一 session**（D18 + 4.5.5 既有约束）。

### 4.6 失败模式

| 症状 | 缓解 |
|---|---|
| `mp.weixin.qq.com` 触发风控 | 加 sleep / 限频（每天 ≤ 1 次全量 + 实时按需） |
| cookie 失效（探活 exit 2） | 走 qr-headless + qr-confirm 重新登录 |
| 创作者中心 DOM 改版 | spike 验证；监控 selector 失效 → 走方案 B |
| 公众号文章未到 24h 无阅读数 | 不报错，记 0；T+1d 重抓 |
| 单篇分析页 403（IP 频限） | sleep 60s 后重试一次，仍失败跳过 |

## 五、与 published-track 集成点

### 5.1 fetch-and-update-metrics.sh 改动

把 `MANUAL_PLATFORMS` 中的 `wx_mp` 移除（保留 `wx_channel` 因为 Phase 4.6 暂不覆盖视频号）：

```diff
- MANUAL_PLATFORMS="wx_mp wx_channel"
+ MANUAL_PLATFORMS="wx_channel"
```

但要兼容脚本当前 wx_mp 分支调用（用 SESSION_EXPIRED + 提示用户），让迁移期不报错。

### 5.2 fetch-retro-data.ts 改动

新增 `wx-mp` 平台分支（与现有 xhs / bilibili / douyin / kuaishou 同样的 cookie + API 抓取模式）：

- cookies：从 `~/.openclaw/logins/wx-mp.json` 加载
- 抓取：调 wx-mp-engagement skill 的 fetch（不是 TS 内重写抓取逻辑，保持 skill 边界清晰）
- 输出：标准 `RetroResult` JSON

### 5.3 凌晨复盘心跳

`published-track` 心跳巡检 → 调 `fetch-and-update-metrics.sh --platform wx_mp --id <rowid>` → 一键走完登录 + 抓取 + 写库。

## 六、与 D8 已搬入 skill 的关系

| skill | 角色 | 本轮是否改 |
|---|---|---|
| `crews/main/skills/wx-mp-hunter/` | 抓公众号**文章内容**（不需登录） | 不改 |
| `crews/main/skills/wx-mp-publisher/` | 公众号**发布**（AppID/AppSecret） | 不改 |
| `crews/main/skills/wx-mp-engagement/` | 公众号**engagement**（新，session token） | 本轮新建 |

## 七、spike 验证 checklist（待真机测试）

> **本轮不做真机 spike**（无公众号账号 + 后台环境）。下列项等统一部署后用户用真账号跑。

| # | 验证项 | 期望 |
|---|---|---|
| 1 | camoufox-cli 启 headless 打开 `mp.weixin.qq.com` 创作者中心 | 页面正常加载，无风控拦截 |
| 2 | 触发扫码登录，PC 端微信扫描 | 30s 内登录成功，cookie 落 `~/.openclaw/logins/wx-mp.json` |
| 3 | 内容管理列表页（推测 `/cgi-bin/framehtml/getcontents`） | DOM 含单篇阅读数 / 点赞数 / 评论数 |
| 4 | 单篇分析页 | DOM 含精确阅读数（区分全部 / 朋友圈 / 朋友 / 公众号 / 历史） |
| 5 | 评论管理页 | API 返回 JSON 列表，含评论内容 / 时间 / 点赞数 |
| 6 | 抓取频率（每篇 1 次） | 不触发微信风控 |
| 7 | 批量抓最近 7 天文章 | 7 篇 ≤ 5 分钟，无封号 |
| 8 | 凌晨复盘心跳集成 | 自动跑通，无需人工 |
| 9 | 竞品号（无后台权限） | 走方案 A 自然失败 → dev plan 接受此为产品约束 |
| 10 | cookie 失效兜底 | `login-manager check wx-mp` exit 2 → 自动触发 qr-headless + 用户扫码 |

**spike 失败回退**：
- 1-5 任一失败 → 走方案 B（容器内 mitmproxy + camoufox，对应 wxdown-service 架构）
- 6-7 失败 → 限频 + 错峰跑（仅心跳时段跑，不按需）
- 8 失败 → 保留 manual update 作为兜底，方案 A 仅按需触发

## 八、本轮交付（骨架，不实施真机 spike）

| 产物 | 路径 | 说明 |
|---|---|---|
| 设计 doc | `docs/wechat-mp-engagement-design.md` | 本文档 |
| 调研笔记 | `docs/wechat-mp-engagement-research.md` | mp.weixin.qq.com 后台结构 + published-track 接入点 |
| skill 骨架 | `crews/main/skills/wx-mp-engagement/` | SKILL.md + 脚本骨架 + 单测 |
| login-manager 增平台 | `crews/main/skills/login-manager/scripts/login_manager.py` | 加 `wx-mp` 平台 + 探活 URL |
| 集成点 | `crews/main/skills/published-track/scripts/fetch-retro-data.ts` | 加 `wx-mp` 分支（薄壳调 wx-mp-engagement skill） |
| 集成点 | `crews/main/skills/published-track/scripts/fetch-and-update-metrics.sh` | `MANUAL_PLATFORMS` 改 |
| spike checklist | `DEVPLAN.md` Phase 4.6 段 | 标记待真机验证项 |

## 九、风险与缓解

| 风险 | 缓解 |
|---|---|
| 创作者中心 DOM 改版 → selector 失效 | 监控 fetch_engagement 失败率，> 20% 触发方案 B |
| 抓取频限封号 | 严格节流：每公众号每天 ≤ 1 次全量 + 实时按需单篇；违规立即降级到 manual |
| 用户公众号未授权后台 | 走 manual update fallback，dev plan 划界 |
| 与 wx-mp-publisher 凭据混淆 | skill 文档明确两套凭据边界；代码层用不同平台 key（`wx-mp` vs publisher AppID） |

---

关联：[phase-4.5-design.md](./phase-4.5-design.md) · [[30-client-dev-session-2026-07-04]] · published-track/SKILL.md
