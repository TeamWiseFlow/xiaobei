---
name: wx-mp-engagement
description: 微信公众号 engagement 数据抓取。通过 camoufox-cli 跑创作者中心
  拿已发布文章的阅读数 / 点赞数 / 评论数 / 分享数 / 收藏数，写入 published-track
  的 pub_wx_mp 表。
metadata:
  openclaw:
    emoji: 📈
    requires:
      bins:
      - python3
      - camoufox-cli
      - sqlite3
---

# 微信公众号 Engagement 抓取

> ⚠️ **可试跑，selector 待真机 spike 校准**：方案 A（浏览器直接拿）已完整实现，
> 提供 `probe` 子命令 dump DOM/截图供 spike 调 selector。selector / 列表页 URL 基于
> 公开信息推测，真机跑 `probe` 后按 `02_list.html` 校准 `fetch_engagement.py` 顶部
> `LIST_ROW_SELECTORS` / `TITLE_SELECTORS` / `CREATOR_CENTER_LIST_URL` 即可。
>
> **限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录）。竞品号拿不到——这是产品约束，不是技术约束。

通过 **camoufox-cli + login-manager 拿 cookie + 创作者中心列表页爬虫** 替换 published-track `MANUAL_PLATFORMS` 中 `wx_mp` 的"手动填"。**不碰 relay**（凭据是会话 token，relay 持有无益）。

**思路**：创作者中心后台的「内容管理」列表页本身就把每篇已发布文章的阅读/点赞/评论/分享/收藏列在行内，所以走「列表页 → 按标题匹配 → 提行内数字」，不必打开单篇分析页。

---

## 前置条件

### 1. login-manager 探活 + 失效重登

```bash
# 探活
login-manager.sh check wx-mp

# 失效后：camoufox 扫码登录
login-manager.sh qr-headless wx-mp
# （发 QR PNG 给用户 → 用户扫码后 → 主会话回复"已扫码"）
login-manager.sh qr-confirm wx-mp --session <s> --timeout 180
```

退出码：
- `0` 有效
- `2` 失效 → 走 qr-headless + qr-confirm

### 2. published-track DB 已就位

```bash
ls ~/.openclaw/workspace-main/db/published_track.db
# 初始化（如未建）
~/.openclaw/workspace-main/skills/published-track/scripts/init-db.sh
```

---

## CLI

```bash
# spike 第一步：dump 创作者中心 DOM + 截图 + 解析出的文章列表 JSON
wx-mp-engagement.sh probe
# 产物落在 ./wx-mp-engagement-probe/：01_center.png / 02_list.png / 02_list.html / 03_articles.json

# 列出后台所有文章 + 行内 metrics（spike 验证 selector + 日常自查）
wx-mp-engagement.sh list

# 抓单篇（按 row.title 在列表页匹配）
wx-mp-engagement.sh fetch --row-id <pub_wx_mp.id>

# 批量抓取最近 N 天未更新（reads=0）的所有 wx_mp 记录
wx-mp-engagement.sh fetch-all --days 7
```

退出码：
- `0` 成功
- `1` 通用错误（参数错 / row 找不到 / 标题未匹配）
- `2` cookie 失效（与 login-manager / fetch-and-update-metrics 契约一致）

### spike 调 selector 流程

1. `wx-mp-engagement.sh probe` → 看 `02_list.html` 确认列表页真实结构
2. 若 `03_articles.json` 为空 → selector 没命中，改 `fetch_engagement.py` 顶部
   `LIST_ROW_SELECTORS` / `TITLE_SELECTORS` 至命中
3. 若列表页 URL 不对（`02_list.png` 是登录页/空白）→ 改 `CREATOR_CENTER_LIST_URL`
4. 重跑 `list` 确认 `articles` 非空且 metrics 合理 → 再跑 `fetch` / `fetch-all`

---

## 工作流程（fetch）

```
1. login-manager.sh check wx-mp
   ├─ exit 2 → 退出（调用方触发 qr-headless + qr-confirm）
   └─ exit 0 → 继续
2. lookup_published_row(row_id) → 拿 title / publish_url
3. session_name() → wx-mp-engagement-{nonce} 独立 session
4. login-manager.sh cookie-import wx-mp <session>
5. camoufox open <CREATOR_CENTER_LIST_URL>  → 列表页
6. camoufox eval <列表解析 JS>  → [{title, text}, ...]
7. match_article(rows, row.title)  → 按标题归一化匹配
8. parse_metrics_from_text(row.text)  → 行内提 reads/likes/comments/shares/favorites
9. update-metrics.sh --platform wx_mp --id <row_id> ...  → 写 pub_wx_mp
10. finally: login-manager.sh session-cleanup wx-mp <session>
```

---

## 输出 JSON 示例

```json
{
  "ok": true,
  "row_id": 42,
  "title": "测试文章",
  "publish_url": "https://mp.weixin.qq.com/s?__biz=xxx&mid=123",
  "session": "wx-mp-engagement-abc12345",
  "metrics": {
    "reads": 1234,
    "likes": 56,
    "comments": 7,
    "shares": 8,
    "favorites": 9,
    "top_comment": "用户A: 好文"
  },
  "update": {"ok": true, "action": "updated"}
}
```

---

## 与 published-track 集成

`fetch-and-update-metrics.sh --platform wx_mp --id <rowid>`：

```bash
# 由 published-track 现有流程统一调用（修改 MANUAL_PLATFORMS 列表）
fetch-and-update-metrics.sh --platform wx_mp --id 42
# 内部：
#   1. login-manager 探活（探测 wx-mp cookie）
#   2. wx-mp-engagement.sh fetch --row-id 42  ← 本 skill
#   3. update-metrics.sh 写 pub_wx_mp
```

**修改点**（本轮交付的一部分）：
- `fetch-and-update-metrics.sh`：`MANUAL_PLATFORMS` 移除 `wx_mp`（保留 `wx_channel`，本 skill 不覆盖视频号）
- `fetch-retro-data.ts`：加 `wx-mp` 分支，薄壳调本 skill

---

## 约束

- **浏览器方案**：camoufox-cli 主推；不 fork；不 bake chromium
- **并发**：每 agent 一 session（独立 daemon + 独立 profile dir）
- **整块 client 容器内闭环**（不碰 relay）
- **凭据边界**：本 skill 只用浏览器 session token；**不动** `wx-mp-publisher` 的 AppID/AppSecret

---

## Pitfalls

### pitfall: 创作者中心 DOM 改版

- **症状**：parse_dom_metrics 返回全 0（selectors 失效）
- **workaround**：spike 验证 selectors；监控 fetch_engagement 失败率，> 20% 触发方案 B（容器内 mitmproxy）

### pitfall: 抓取频限封号

- **症状**：突然 403 / 风控页
- **workaround**：严格节流——每公众号每天 ≤ 1 次全量；违规立即降级到 manual update

### pitfall: 公众号文章未到 24h 无阅读数

- **症状**：阅读数 0（实际是未刷新）
- **workaround**：不报错，记 0；T+1d 重抓（fetch-all 自动覆盖）

### pitfall: 单篇分析页 403（IP 频限）

- **症状**：HTML 含 403 / 重定向
- **workaround**：sleep 60s 后重试一次，仍失败则跳过该 row，记入 `metrics.update.error`

### pitfall: cookie 跨 session 污染

- **症状**：cookie-import 后访问仍 401
- **workaround**：每个 fetch 任务用新 session name（`secrets.token_hex(4)` nonce 保证唯一）；不要跨任务复用

---

## Spike 验证 checklist（部署后由用户真账号跑）

详见 `docs/wechat-mp-engagement-design.md` §七。

---

## Notes

- Docker 内对内 crew exec full（放开，**不需要**在 ALLOWED_COMMANDS 白名单）
- **限频建议**：单公众号每 24h 全量 ≤ 1 次；单篇分析按需触发
- **失败兜底**：本 skill 跑不通时回退到 manual update（`update-metrics.sh --reads ... --likes ... --comments ...` 手动填）
- **依赖版本**：camoufox-cli@0.6.2（Dockerfile 阶段 1 锁定）
