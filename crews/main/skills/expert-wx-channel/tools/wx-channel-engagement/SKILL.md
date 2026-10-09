---
name: wx-channel-engagement
description: 微信视频号已发布作品数据抓取，写入 published-track 的 pub_wx_channel 表。wechat-channel session 登录。
---

# wx-channel-engagement — 工具说明

> 本文是 `expert-wx-channel` 专家包内的工具说明书，不独立出现在技能列表中。由相关 Workflow 指引调用。

通过 **camoufox-cli + 与 `wechat-channels-publish` 共管的 `wechat-channel` 持久化 session + 视频号助手后台爬虫**，从视频号助手「内容管理 → 作品管理」页抓已发布视频的播放/点赞/评论/分享/收藏，写入 published-track 的 `pub_wx_channel` 表。

**思路**：视频号助手后台 `channels.weixin.qq.com/platform/` 的作品管理页把每条已发布视频的播放/点赞/评论/分享/收藏列在行内，走「作品管理页 → 解析 innerText → 按完整视频描述匹配 → 提行内数字」。

**输入**：`--row-id`（pub_wx_channel 行 id，fetch 单篇）或不带参数（list / fetch-all 批量）。行内数据按 `row.title`（数据库字段名，语义为完整视频描述）在作品管理页匹配。

> **只用视频描述，不用短标题**：视频号发布页改版后可以同时填视频描述与短标题，但作品管理页只展示视频描述，短标题抓不到。因此入库（`published-track record --title`）与本工具的匹配一律用完整视频描述，短标题不写库、不参与匹配。
**输出**：行内 metrics（plays / likes / comments / shares / favorites），并经 published-track `update-metrics` 写入 `pub_wx_channel`。
**限制**：仅支持用户**自己有后台权限的号**（视频号助手用微信扫码登录）。竞品号拿不到——这是产品约束，不是技术约束。

---

## Session 共享约束（与 `wechat-channels-publish` 共管）

本工具与 `wechat-channels-publish` **共用同一个 `wechat-channel` 持久化 session**，靠 session 名字符串约定共享同一 profile 目录与登录态——任一工具登录后另一个不需重登，反之亦然。单一 session、单一 IP、单一 profile，避免多 session 多 IP 的风控风险。

- **fail-first 队列**：同 session 已有命令在跑时，新命令直接 fail。读到 `session wechat-channel 正忙` → exit 3，调用方（agent）等待当前操作完成后再试，不自动排队、不自动 close 正在跑的 session。
- **登录态闭环**：不导出 cookie/UA/token——登录态在 `wechat-channel` session profile 里就位即可。失效时走本工具 `login` + `login-confirm` 重登流。
- **不走 login-manager**：本工具自管 `wechat-channel` session 的探活 + 登录 + 重登。

---

## 前置条件

### 1. wechat-channel session 登录态

camoufox-cli 命令统一 `--session wechat-channel --persistent`，登录态在 session profile 里已就位即可。

**登录态判断**：camoufox 打开 `channels.weixin.qq.com/platform/` 看 redirect URL：
- 跳到 `/platform/home` 或 `/platform/post/list` 等后台路径 = 登录就位
- 跳到 `login` / 扫码页 = 失效，需重登

**失效重登流程**（走本工具自己）：
```bash
wx-channel-engagement login           # camoufox 无头截 QR PNG 落 /tmp/qr-wx-channel.png
# 发 QR PNG 给用户 → **Stop and wait**：等用户回复"已扫码/已完成"再往下走，不盲轮询、不催促
wx-channel-engagement login-confirm   # 短窗口 settle 验证（30s）+ close session（不导出 cookie/UA/token）
# exit 2 = 未就位：用户只扫码没在手机上点"确认登录" → 提示用户点确认后重跑本命令
# （二维码页还活着，无需重新扫码）；已确认仍未就位 → 重跑 login 生成新二维码
```

`login` 返回 `already_logged_in: true` 时无需扫码，直接执行后续命令。扫码失败 / 用错账户后，**不要直接重跑 `login`**——旧 cookie 污染 profile，重跑拿到的 QR 扫了也不生效。先带 `--reset` 清 profile 再重登：
```bash
wx-channel-engagement login --reset   # 删 profile 目录 + 重新 open，从干净状态拿 QR
```

退出码：
- `0` 成功
- `1` 通用错误（参数错 / row 找不到 / 完整视频描述未匹配）
- `2` session 失效（后台首页跳登录页）
- `3` session 正忙（fail-first 队列）

### 2. published-track DB 已就位

```bash
ls ~/.openclaw/workspace-main/db/published_track.db
# 初始化（如未建）：按 published-track 技能的初始化流程处理
```

---

## CLI

```bash
wx-channel-engagement login                    # camoufox 无头截 QR PNG，等扫码
wx-channel-engagement login-confirm            # 验登录就位 + close session
wx-channel-engagement probe                    # 打开视频号助手后台 dump DOM/截图/innerText，调试用
wx-channel-engagement list                     # 列出后台所有视频号作品 + 行内 metrics
wx-channel-engagement fetch --row-id <id>      # 抓单篇（按 row.title 在作品管理页匹配）
wx-channel-engagement fetch-all                # 批量刷新（心跳用）：打开作品管理页首页一次，匹配 pub_wx_channel 全部行写库；不翻页，首页没有的行报 NOT_ON_FIRST_PAGE 跳过
```

---

## 抓取流程

### 注意点

1. **视频号助手后台 URL**：`https://channels.weixin.qq.com/platform/`（登录后跳转到这里）
   - 作品管理页：`https://channels.weixin.qq.com/platform/post/list`
   - **视频号助手后台使用 wujie 微前端**，所有表单元素在 `<wujie-app>::shadow-root` 内——camoufox-cli 的 `snapshot` 默认穿透 shadow DOM 拿 ref，但 `eval` 读 `document.body.innerText` 时**不穿透 shadow DOM**，需要用 `eval` 手写 `document.querySelector('wujie-app').shadowRoot` 拿 shadow 内文本。
   - **仅抓最近 20 条作品**（作品管理页默认展示）：发布超过 ~30 天的老视频数据已稳定，每天重抓无收益只增风控暴露。老内容不在列表里自然跳过，**不要加翻页逻辑去补抓**。复盘如需老内容数据，用 DB 里已有的历史值。

2. **登录态来源**：camoufox 打开后台首页后从 redirect URL 判登录态。登录态在 `wechat-channel` session profile 里就位即可，**不导出 cookie/UA/token**。

3. **Cookie 导入禁忌**：⚠️ **严禁** `camoufox-cli cookies import` 造会话（浏览器方案严禁 cookie 导入）。本工具与 `wechat-channels-publish` 共管 `wechat-channel` 持久化 session，camoufox-cli 命令统一 `--session wechat-channel --persistent`，登录态在 session profile 里已就位，**不开独立 session、不 import cookie**。撞 fail-first 队列（同 session 正被占用）就等占用方完成再串行接力，**不**自动 close 正在跑的 session。

4. **数据提取方式**：不依赖 selector，直接用 `document.body.innerText` 解析（穿透 shadow DOM 后）。页面 innerText 结构清晰：
   ```
   <完整视频描述>
   <发布时间>
   <播放数> <点赞数> <评论数> <分享数> <收藏数>
   ```
   > 具体结构需 `probe` 实测确认。如果 innerText 不穿透 shadow DOM 拿不到数据，fallback 到 `eval` 注入 JS 手动读 `wujie-app.shadowRoot` 内文本。

### fetch 流程

```
1. camoufox 打开视频号助手后台首页
   ├─ redirect URL 跳 login/扫码页 → exit 2（调用方触发本工具 login + login-confirm）
   └─ redirect URL 跳 /platform/home 等后台路径 → 继续
2. lookup_published_row(row_id) -> 拿 title / publish_url
3. 复用 wechat-channel 持久化 session（不开独立 session、不 import cookie）：
   camoufox-cli --session wechat-channel --persistent --json open "https://channels.weixin.qq.com/platform/post/list"
4. eval JS 解析作品管理页 innerText -> [{title, metrics}, ...]
5. match_article(rows, row.title) -> 按完整视频描述归一化匹配
6. update-metrics --platform wx_channel --id <row_id> ... -> 写 pub_wx_channel
7. finally: close session（登录态在磁盘 profile，不留进程占内存；下次 fetch 按需重起无头 session，profile 桥接登录态）
```

---

## 输出 JSON 示例

```json
{
  "ok": true,
  "row_id": 42,
  "title": "测试视频",
  "publish_url": "https://weixin.qq.com/sph/xxx",
  "session": "wechat-channel",
  "metrics": {
    "plays": 1234,
    "likes": 56,
    "comments": 12,
    "shares": 8,
    "favorites": 3
  },
  "update": {"ok": true, "action": "updated"}
}
```

---

## 写库接口

行内 metrics 经 published-track 的纯写库流程写入 `pub_wx_channel`（`platform=wx_channel`、`id=<row_id>`），工具内部已完成，调用方无需另行写库。

> 微信视频号互动数据由本工具读取并写库。

---

## 约束

- **浏览器方案**：camoufox-cli 主推；不 fork；不 bake chromium
- **并发**：本工具与 `wechat-channels-publish` 共管 `wechat-channel` 持久化 session，fail-first 队列串行接力，不自动 close 正在跑的 session
- **登录态管理**：不导出 cookie/UA/token——登录态在 `wechat-channel` session profile 里就位即可。失效时走本工具 `login` + `login-confirm` 重登（重登后登录态在 profile 里就位），再 camoufox 打开后台首页
- **凭据边界**：本工具只用浏览器 session token；**不动** `wechat-channels-publish` 的发布凭据

---

## Pitfalls

### pitfall: wujie_shadow_dom

- **触发**：访问视频号助手后台任何页面
- **症状**：常规 DOM 选择器找不到表单元素，`document.body.innerText` 拿不到 shadow DOM 内文本
- **workaround**：camoufox-cli `snapshot` 默认穿透 shadow DOM 拿 ref；`eval` 读 innerText 时需手写 `document.querySelector('wujie-app').shadowRoot.innerText` 拿 shadow 内文本。fallback 才需要 `eval` 里手写 `document.querySelector('wujie-app').shadowRoot.querySelector(selector)`

### pitfall: 后台 DOM 改版

- **症状**：innerText 解析返回空或数据错位
- **workaround**：跑 `probe` 命令检查 `02_list.html` 和 `03_inner_text.txt` 确认页面结构，调整解析逻辑

### pitfall: 抓取频限封号

- **症状**：突然 403 / 风控页
- **workaround**：严格节流——每视频号账号每天 ≤ 1 次全量；违规立即降级到 manual update

### pitfall: session 正忙（fail-first 队列）

- **症状**：`wechat-channels-publish` 正在跑发布流程，本工具撞 fail-first 队列，exit 3
- **workaround**：这是**预期行为**（单一 session + fail-first 队列）。agent 读到 exit 3 应等待当前操作完成再重试，**不**自动排队、**不**自动 close session（close 会 tear down 正在跑的发布操作）

### pitfall: token 过期

- **症状**：作品管理页显示"请重新登录"
- **workaround**：登录态与 `wechat-channels-publish` 共寿命，失效则 camoufox 打开后台首页跳登录页 → exit 2 → 走本工具 `login` + `login-confirm` 重登流，再用新登录态打开后台首页

---

## Notes

- **限频建议**：单视频号账号每 24h 全量 ≤ 1 次；单篇按需触发
- **camoufox-cli 注意**：本工具全部命令统一 `--session wechat-channel --persistent`（与 `wechat-channels-publish` 共管的持久化 session），headless 是默认行为；登录态从 session profile 桥接
- **报错约束**：调用方（agent）报告失败时必须原样转述脚本 stderr + exit code，禁止根据 DB 字段（如 `publish_url` 是否为空）自行归因
