---
name: xhs-engagement
description: 通过 Creator HTTP 接口读取小红书已发笔记的互动和数据分析指标，并更新 published-track。
---

# 小红书互动数据

本工具使用与 `xhs-publish` 相同的 Creator 本地 HTTP 会话，凭据在 `~/.openclaw/logins/xhs-creator-local.json`。只读取本账号创作者后台的已发作品。需要登录时按 `xhs-publish` 的 `check → login → 发送二维码图片 → 等用户确认 → login-confirm` 流程处理。

## 命令

```bash
xhs-engagement check
xhs-engagement probe
xhs-engagement list
xhs-engagement fetch --title "标题"
xhs-engagement fetch --row-id <pub_xhs行ID>
xhs-engagement fetch-all
xhs-engagement daily
```

`daily` 按服务端游标仅读取最新的前三页已发布作品和最多前三页数据分析，页间 3 秒；只更新这三页内能匹配到的 `pub_xhs` 记录，没有匹配行时不请求数据分析，旧作品不在本次窗口时不报未匹配。`fetch-all` 等手动命令最多读取十页，超过上限时报错，不把截断结果当作完整取数。单篇详情每轮最多读取五篇，详情请求间隔 3 秒；单篇画像每轮最多查询三篇、仅查询阅读数达到 100 的作品，请求前间隔 3 秒。优先按 `publish_url` 中的作品 ID 匹配；仅在接口没有可用 ID 时允许唯一标题匹配。阅读、评论、点赞、收藏、分享五项必须全部存在并可解析，缺字段不写零值。`probe` 报告字段与分析列表可用性；`list` 输出作品、五项指标及分析列表数据；`fetch --title` 只读，包含该篇详情和可用画像。

数据分析指标写入 `pub_xhs.deep_metrics`，保留接口原字段名：`summary.imp_count` 为曝光，`summary.coverClickRate` 为封面点击比例（如 `0.625` 表示 62.5%）；`detail.impl_count` 为曝光，`detail.cover_click_rate` 为百分数（如 `7.3` 表示 7.3%）；视频的 `detail.finish5s_rate`、`detail.full_view_rate`、`detail.exit_view2s_rate` 为百分数。还保存平均观看时长、涨粉等接口实际返回的字段。`detail_captured_at` 标明详情抓取时间；批量超过五篇时保留先前详情及其时间戳。分析接口不可用时继续更新已验证的五项基础指标，并在结果中报告错误。

单篇画像来自 `note/audience/source/detail`。当接口返回有数据的 `gender`、`age`、`city` 或 `interest` 时，把完整响应 `data` 对象作为 JSON 字符串写入 `pub_xhs.fan_portrait`，只保留最新值。返回 `no_data=true`、画像为空或请求失败时跳过画像列，保留已有值。该接口反映**单篇作品的观众画像**，不能当作账号整体粉丝画像。

`fetch --row-id` 和 `fetch-all` 直接委托 `published-track update-metrics` 写库，其中收藏对应 `favorites` 列，深度指标只保存最新 JSON。`fetch --title` 用于查看单篇 Creator 数据，不写库；写库时提供 `pub_xhs` 行 ID。`probe` 和 `list` 只检查或展示接口返回。

`daily` 按北京时间自然日最多运行一次，按前三页窗口取数并写库，结果的 `creator_notes_scanned` 表示本轮读到的近期作品数。窗口内作品缺指标字段或写库失败时，在结果中报告失败，不把旧库指标当作本轮新数据。运行日志在 `~/.openclaw/logs/xhs-creator-observe.jsonl`，只记录数量、状态和错误码，不记录标题或凭据。

`check` 的退出码：0 有效，2 缺少登录态或明确 401/403 失效，1 为其他接口故障。非认证错误、406、响应结构变化或字段缺失时停止当轮请求并排查，不反复扫码或高频重试。
