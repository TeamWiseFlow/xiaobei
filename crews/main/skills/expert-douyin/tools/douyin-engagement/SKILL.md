---
name: douyin-engagement
description: 抖音已发作品公开互动量查询与 published-track 指标回填。
---

# 抖音数据取数

使用 `douyin-login` 独立 API 会话，从作品详情读取实际返回的点赞、评论、分享和收藏数量。

```bash
douyin-engagement check
douyin-engagement list
douyin-engagement fetch --row-id 发布记录ID
douyin-engagement daily
```

`daily` 取最近 30 条发布记录，逐条按完整作品 ID 查询公开详情并更新 `published-track`。`list` 返回库内发布记录；`check` 仅验证主站会话，不代表创作者后台或作品指标完整可用。

结果的 `metrics` 只含本次可得的互动量，`unavailable` 列出不可得的基础指标。缺值不填零，实际返回的零值正常保存。公开详情中的播放量不作为可靠播放数写库；当前工具不自动获取完播、跳出、平均观看、曝光、点击率、画像或留存等后台深指标。

只更新实际取得的字段，保留库内已有的播放量和历史深指标。报告不能把这些旧值描述成本次自动采集结果；用户主动提供后台数据时可使用 `published-track update-metrics` 补录，并注明时间与来源。

`fetch` 查询指定数据库行 ID；它不是平台作品 ID。没有发布链接或作品 ID 时先补记录，不按标题猜作品。认证失败走 `douyin-login`；Relay 故障、风控或指标不可得要保留错误原因，不重复发布。
