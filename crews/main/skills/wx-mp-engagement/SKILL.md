---
name: wx-mp-engagement
description: 微信公众号 engagement 数据抓取。通过 camoufox-cli 跑创作者中心拿已发布文章的阅读数 / 点赞数 / 评论数 / 分享数 / 收藏数，写入 published-track的 pub_wx_mp 表。
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

通过 **camoufox-cli + 与 wx-mp-hunter 共用的 wx_mp 持久化 session + 创作者中心列表页爬虫** 替换 published-track `MANUAL_PLATFORMS` 中 `wx_mp` 的"手动填"。**不碰 relay**（凭据是会话 token，relay 持有无益）。

**思路**：创作者中心后台的「发表记录」页面把每篇已发布文章的阅读/点赞/评论/分享/收藏列在行内，走「发表记录页 -> 解析 innerText -> 按标题匹配 -> 提行内数字」，不需要打开单篇分析页。

**限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录）。竞品号拿不到--这是产品约束，不是技术约束。

---

## 前置条件

### 1. wx_mp session 探活 + 失效重登（走 wx-mp-hunter，不走 login-manager）

wx-mp-engagement 与 wx-mp-hunter **共用** camoufox 持久化 session `wx_mp`（靠 session 名约定共享同一 profile 目录与登录态）。探活/登录/导出 cookie+UA+token 落中央存储 全由 wx-mp-hunter 负责。

```bash
# 探活
wx-mp-hunter.sh check

# 失效后：camoufox 扫码登录
wx-mp-hunter.sh login           # camoufox 无头截 QR PNG 落 /tmp/qr-wx-mp.png
# （发 QR PNG 给用户 -> 用户扫码后 -> 主会话回复"已扫码"）
wx-mp-hunter.sh login-confirm   # 验登录就位 + 导出 cookie+UA+token 落中央存储
```

退出码：
- `0` 有效
- `2` 失效 -> 走 wx-mp-hunter login + login-confirm

> wx-mp-engagement **不吃 cookie**——只走 camoufox-cli 操作浏览器，wx_mp session profile 里登录态已就位即可。中央存储的 cookie+UA+token 仅供 wx-mp-hunter 的脚本业务命令（search/account-posts/fetch）用。

### 2. published-track DB 已就位

```bash
ls ~/.openclaw/workspace-main/db/published_track.db
# 初始化（如未建）
~/.openclaw/workspace-main/skills/published-track/scripts/init-db.sh
```

---

## CLI

```bash
# dump 创作者中心 DOM + 截图 + 解析出的文章列表 JSON
wx-mp-engagement.sh probe
# 产物落在 ./wx-mp-engagement-probe/：01_center.png / 02_list.png / 02_list.html / 03_articles.json

# 列出后台所有文章 + 行内 metrics
wx-mp-engagement.sh list

# 抓单篇（按 row.title 在列表页匹配）
wx-mp-engagement.sh fetch --row-id <pub_wx_mp.id>

# 批量抓取最近 N 天未更新（reads=0）的所有 wx_mp 记录
wx-mp-engagement.sh fetch-all --days 7
```

退出码：
- `0` 成功
- `1` 通用错误（参数错 / row 找不到 / 标题未匹配）
- `2` session 失效（与 wx-mp-hunter / fetch-and-update-metrics 呑约一致）

---

## 工作流程

### 关键发现（2026-07-09）

1. **发表记录页 URL**：`https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token=<TOKEN>&lang=zh_CN`
   - 不是 `appmsg?action=list`（那是草稿箱）
   - **必须带 token 参数**，否则显示"请重新登录"

2. **Token 获取**：先访问 `https://mp.weixin.qq.com/`（首页），登录态下会重定向到 `https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=<TOKEN>`，从 URL 中提取 token

3. **Cookie 导入顺序**：必须先 `camoufox-cli open` 创建 session，再 `cookies import`，否则 import 会失败（camoufox-cli 的 cookies import 需要一个已运行的 session）

4. **数据提取方式**：不依赖 selector，直接用 `document.body.innerText` 解析。页面 innerText 结构清晰：
   ```
   06月30日
   已发表
   文章标题
   转载/原创/视频号
   <阅读数> <赞> <评论> <分享> <收藏> <在看?> <额外?>
   ```

### fetch 流程

```
1. wx-mp-hunter.sh check
   ├─ exit 2 -> 退出（调用方触发 wx-mp-hunter login + login-confirm）
   └─ exit 0 -> 继续
2. lookup_published_row(row_id) -> 拿 title / publish_url
3. session_name() -> wx-mp-engagement-{nonce} 独立 session
4. camoufox-cli open "https://mp.weixin.qq.com/" -> 创建 session（不传 --headless）
5. （wx_mp session profile 内登录态已就位，无需 import）
6. camoufox-cli open "https://mp.weixin.qq.com/" -> 用 cookie 访问首页，重定向带 token
7. camoufox-cli url -> 提取 token
8. camoufox-cli open "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token=<TOKEN>&lang=zh_CN" -> 发表记录页
9. camoufox-cli eval <innerText 解析 JS> -> [{title, metrics}, ...]
10. match_article(rows, row.title) -> 按标题归一化匹配
11. update-metrics.sh --platform wx_mp --id <row_id> ... -> 写 pub_wx_mp
12. finally: 不主动 close（wx_mp 持久化 session 留下次用）
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
    "reads": 576,
    "likes": 10,
    "comments": 16,
    "shares": 6,
    "favorites": 1
  },
  "update": {"ok": true, "action": "updated"}
}
```

---

## 与 published-track 集成

`fetch-and-update-metrics.sh --platform wx_mp --id <rowid>`：

```bash
# 由 published-track 现有流程统一调用
fetch-and-update-metrics.sh --platform wx_mp --id 42
# 内部：
#   1. wx-mp-hunter 探活（探测 wx_mp session）
#   2. wx-mp-engagement.sh fetch --row-id 42  ← 本 skill
#   3. update-metrics.sh 写 pub_wx_mp
```

**修改点**：
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

- **症状**：innerText 解析返回空或数据错位
- **workaround**：跑 `probe` 命令检查 `02_list.html` 确认页面结构，调整解析逻辑

### pitfall: 抓取频限封号

- **症状**：突然 403 / 风控页
- **workaround**：严格节流--每公众号每天 ≤ 1 次全量；违规立即降级到 manual update

### pitfall: 公众号文章未到 24h 无阅读数

- **症状**：阅读数 0（实际是未刷新）
- **workaround**：不报错，记 0；T+1d 重抓（fetch-all 自动覆盖）

### pitfall: token 过期

- **症状**：列表页显示"请重新登录"
- **workaround**：重新走 wx-mp-hunter login + login-confirm 流程，获取新 session


### pitfall: 列表页 URL 必须带 token

- **症状**：不带 token 的 URL 显示"请重新登录"
- **workaround**：先访问首页拿 token，再拼列表页 URL

---

## Notes

- **限频建议**：单公众号每 24h 全量 ≤ 1 次；单篇按需触发
- **失败兜底**：本 skill 跑不通时回退到 manual update（`update-metrics.sh --reads ... --likes ... --comments ...` 手动填）
- **camoufox-cli 注意**：当前版本不支持 `--headless` 参数（headless 是默认行为），也不支持 `screenshot --path`，直接传文件路径即可
