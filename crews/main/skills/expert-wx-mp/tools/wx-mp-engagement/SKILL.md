---
name: wx-mp-engagement
description: 抓取公众号已发布文章的阅读/点赞/评论/分享/收藏数据，写入 published-track 的 pub_wx_mp 表。
---

# wx-mp-engagement — 工具说明

> 本文是 `expert-wx-mp` 专家包内的工具说明书，不独立出现在技能列表中。由相关 Workflow 指引调用。

通过 **camoufox-cli + 本工具自管的 wx_mp 持久化 session + 创作者中心列表页爬虫**，从公众号后台「发表记录」页抓已发布文章的阅读/点赞/评论/分享/收藏，写入 published-track 的 `pub_wx_mp` 表。

**思路**：创作者中心后台的「发表记录」页面把每篇已发布文章的阅读/点赞/评论/分享/收藏列在行内，走「发表记录页 → 解析 innerText → 按标题匹配 → 提行内数字」，不需要打开单篇分析页。

**限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录）。竞品号拿不到——这是产品约束，不是技术约束。

---

## 前置条件

### 1. wx_mp session 登录态（本工具自管）

wx-mp-engagement 自管 camoufox 持久化 session `wx_mp`，camoufox-cli 命令统一 `--session wx_mp --persistent`，登录态在 session profile 里已就位即可，**不导出 cookie/UA/token**。

**登录态判断**（不再会话前探活）：直接 camoufox 打开创作者中心首页，看 redirect URL：
- 跳到 `/cgi-bin/home?...&token=xxx` = 登录就位
- 跳到 `login` / `scanloginqrcode` = 失效，需重登

**失效重登流程**（走本工具自己）：
```bash
wx-mp-engagement login           # camoufox 无头截 QR PNG 落 /tmp/qr-wx-mp.png
# 发 QR PNG 给用户 → **Stop and wait**：等用户回复"已扫码/已完成"再往下走，不盲轮询、不催促
wx-mp-engagement login-confirm   # 短窗口 settle 验证（30s）+ close session（不导出 cookie/UA/token）
# exit 2 = 未就位：用户只扫码没在手机上点"确认登录" → 提示用户点确认后重跑本命令
# （二维码页还活着，无需重新扫码）；已确认仍未就位 → 重跑 login 生成新二维码
```

退出码：
- `0` 成功
- `1` 通用错误（参数错 / row 找不到 / 标题未匹配）
- `2` session 失效（创作者中心首页跳登录页）

### 2. published-track DB 已就位

```bash
ls ~/.openclaw/workspace-main/db/published_track.db
# 初始化（如未建）：按 published-track 技能的初始化流程处理
```

---

## CLI

```bash
# dump 创作者中心 DOM + 截图 + 解析出的文章列表 JSON
wx-mp-engagement probe
# 产物落在 ./wx-mp-engagement-probe/：01_center.png / 02_list.png / 02_list.html / 03_articles.json

# 列出后台所有文章 + 行内 metrics
wx-mp-engagement list

# 抓单篇（按 row.title 在列表页匹配）
wx-mp-engagement fetch --row-id <pub_wx_mp.id>

# 批量刷新（心跳用）：打开发表记录页首页一次，解析页内全部文章，
# 匹配 pub_wx_mp 全部行写库；不翻页，首页没有的行报 NOT_ON_FIRST_PAGE 跳过
wx-mp-engagement fetch-all
```

---

## 工作流程

### 注意点

1. **发表记录页 URL**：`https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token=<TOKEN>&lang=zh_CN`
   - 不是 `appmsg?action=list`（那是草稿箱）
   - **必须带 token 参数**，否则显示"请重新登录"
   - **`count=20` 是有意设计，不是 bug**：只抓最近 20 篇的 engagement。发布超过 ~30 天的老文章数据已稳定，每天重抓无收益只增风控暴露。老内容不在列表里自然跳过，**不要加翻页逻辑去补抓**。复盘如需老内容数据，用 DB 里已有的历史值。

2. **Token 来源**：camoufox 打开首页后从 redirect URL 实时提 token（首页自动重定向到 `/cgi-bin/home?...&token=xxx`）。token 与 wx_mp session 同寿命，失效则一并失效（首页跳登录页 → 走本工具重登流）。

3. **Cookie 导入禁忌**：⚠️ **严禁** `camoufox-cli cookies import` 造会话（浏览器方案严禁 cookie 导入）。本工具自管 `wx_mp` 持久化 session，camoufox-cli 命令统一 `--session wx_mp --persistent`，登录态在 session profile 里已就位，**不开独立 session、不 import cookie**。撞 fail-first 队列（同 session 正被占用）就等占用方完成再串行接力，**不**自动 close 正在跑的 session。

4. **数据提取方式**：不依赖 selector，直接用 `document.body.innerText` 解析。页面 innerText 结构清晰：
   ```
   06月30日
   已发表
   文章标题
   转载/原创/视频号
   <阅读数> <赞> <分享> <喜欢(爱心icon)> <评论(留言)> <划线> <投票> <额外?>
   ```

### fetch 流程

```
1. camoufox 打开创作者中心首页
   ├─ redirect URL 跳 login/scanloginqrcode → exit 2（调用方触发本工具 login + login-confirm）
   └─ redirect URL 跳 /cgi-bin/home?token=xxx → 继续
2. lookup_published_row(row_id) -> 拿 title / publish_url
3. 复用 wx_mp 持久化 session（不开独立 session、不 import cookie）：
   camoufox-cli --session wx_mp --persistent --json open "https://mp.weixin.qq.com/"
4. 读 redirect URL 拿 token（open 首页自动重定向到 /cgi-bin/home?...&token=xxx）：
   camoufox-cli --session wx_mp --json url
5. camoufox-cli --session wx_mp --persistent --json open "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token=<TOKEN>&lang=zh_CN" -> 发表记录页
6. camoufox-cli --session wx_mp --json eval <innerText 解析 JS> -> [{title, metrics}, ...]
7. match_article(rows, row.title) -> 按标题归一化匹配
8. update-metrics.sh --platform wx_mp --id <row_id> ... -> 写 pub_wx_mp
9. finally: close session（登录态在磁盘 profile，不留进程占内存；下次 fetch 按需重起无头 session，profile 桥接登录态）
```

---

## 输出 JSON 示例

```json
{
  "ok": true,
  "row_id": 42,
  "title": "测试文章",
  "publish_url": "https://mp.weixin.qq.com/s?__biz=xxx&mid=123",
  "session": "wx_mp",
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

wx_mp 的互动数据直接使用本工具，agent 直调 wrapper：

```bash
wx-mp-engagement fetch --row-id <rowid>
```

本 skill 内部流程：
1. camoufox 打开创作者中心首页，看 redirect URL 判断登录态（跳登录页 = 失效，exit 2）
2. 从 redirect URL 提 token，camoufox 抓创作者中心发表记录页
3. 解析 innerText 按标题匹配拿 metrics
4. 委托 `published-track` 的 update-metrics 流程，以 `platform=wx_mp`、`id=<rowid>` 写入 `pub_wx_mp`

> `update-metrics.sh` 是 published-track 的纯写库脚本，本 skill 写库就走它。

---

## 约束

- **浏览器方案**：camoufox-cli 主推；不 fork；不 bake chromium
- **并发**：本工具自管 `wx_mp` 持久化 session，fail-first 队列串行接力，不自动 close 正在跑的 session
- **登录态管理**：不导出 cookie/UA/token——登录态在 wx_mp session profile 里就位即可。失效时走本工具 `login` + `login-confirm` 重登（重登后登录态在 profile 里就位），再 camoufox 打开首页拿新 token 拼列表页 URL
- **凭据边界**：本 skill 只用浏览器 session token；**不动** `wx-mp-publisher` 的 AppID/AppSecret

---

## Pitfalls

### pitfall: 创作者中心 DOM 改版

- **症状**：innerText 解析返回空或数据错位
- **workaround**：跑 `probe` 命令检查 `02_list.html` 确认页面结构，调整解析逻辑

### pitfall: 抓取频限封号

- **症状**：突然 403 / 风控页
- **workaround**：严格节流——每公众号每天 ≤ 1 次全量；违规立即降级到 manual update

### pitfall: 公众号文章未到 24h 无阅读数

- **症状**：阅读数 0（实际是未刷新）
- **workaround**：不报错，记 0；T+1d 重抓（fetch-all 自动覆盖）

### pitfall: token 过期

- **症状**：列表页显示"请重新登录"
- **workaround**：token 与 wx_mp session 同寿命，失效则 camoufox 打开首页跳登录页 → exit 2 → 走本工具 `login` + `login-confirm` 重登流（重登后登录态在 profile 里就位），再用新 token 拼列表页 URL

### pitfall: 列表页 URL 必须带 token

- **症状**：不带 token 的 URL 显示"请重新登录"
- **workaround**：从 camoufox 打开首页后的 redirect URL 实时提 token（首页自动重定向到 `/cgi-bin/home?...&token=xxx`），再拼列表页 URL

---

## Notes

- **限频建议**：单公众号每 24h 全量 ≤ 1 次；单篇按需触发
- **camoufox-cli 注意**：本 skill 全部命令统一 `--session wx_mp --persistent`（本工具自管的持久化 session），headless 是默认行为；token 从 session 内 redirect URL 实时拿
- **报错约束**：调用方（agent）报告失败时必须原样转述脚本 stderr + exit code，禁止根据 DB 字段（如 `publish_url` 是否为空）自行归因。token 从首页 redirect URL 提取，**与 `publish_url` 无关**——`publish_url` 仅用于输出 JSON，不参与抓取逻辑
