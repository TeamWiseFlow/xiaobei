---
name: douyin-engagement
description: 通过 HTTP 接口获取本人已发布视频和图文的基础、深度指标，复用发布 profile 登录态并回填发布记录。
---

# 抖音已发布作品取数

取数使用 HTTP 请求，不在浏览器页面内抓取。脚本临时从 Camoufox 持久化 session `douyin` 的 profile 读取 cookie 和 UA，读取后关闭浏览器，凭据只保留在进程内存。与发布共用 profile 和排他锁；不使用 login-manager、中央 cookie 文件或 hunter 的 API 会话。

冷启动时脚本先打开 `about:blank` 加载持久 profile；已有浏览器时沿用其有头/无头模式，直接读取，不导航当前页面。读取失败保留已有窗口；脚本自己启动的浏览器在失败时清理。读取成功后关闭浏览器，再发 HTTP 请求。

```bash
douyin-engagement check
douyin-engagement list
douyin-engagement fetch --row-id 12
douyin-engagement daily
```

未登录时执行 `douyin-publish login`，在有头窗口完成扫码后重跑 `check`。`list` 只读取发布记录；`fetch` 的 row-id 是数据库行 ID，`daily` 扫描最近 30 条记录。

脚本通过 HTTP 请求创作者 `item/list`，最多 10 页，每页 50 条，以完整作品 ID 匹配。视频和图文均支持。播放、点赞、评论、分享、收藏优先使用创作者指标；缺失的后四项再由 `fetch-retro-data.ts` 调用公开 `aweme/detail` 补充，公开播放量始终不采用。创作者接口不依赖签名；公开详情使用 OFB Relay 签名，缺少凭证时报告缺项，不影响已取得的创作者指标。

工具调用 `published-track update-metrics` 写库。平台实际返回的完播、跳出、封面点击率等其余数值写入 `deep_metrics`，来源 `douyin:creator_item_list`；基础字段来源逐项记录在 `field_sources`。响应未提供的深指标不承诺可用。

以 `metrics`、`deep`、`field_sources` 和 `unavailable_reasons` 为准；明确的零正常写入，缺失不补零。完整 ID 保留整数精度，不按标题猜作品。未找到作品、游标异常、接口空体、风控即报告原因；不能改用公开播放量补数。库内旧值不算本次采集值。

`SESSION_EXPIRED`（exit 2）表示登录态缺失或失效。`PROFILE_SESSION_UNAVAILABLE` / `PROFILE_SESSION_INVALID`（exit 1）表示初始化或读取故障，登录状态尚未确认；报告 `stage` 和 `reason`，按技术故障处理，不要求重新登录。其余错误按返回原因停止；采集失败不触发重发。发布和取数不可并行。
