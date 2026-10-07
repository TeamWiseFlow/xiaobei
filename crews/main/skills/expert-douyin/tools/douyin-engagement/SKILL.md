---
name: douyin-engagement
description: 抖音本人已发作品播放量、公开互动量查询与 published-track 指标回填。
---

# 抖音数据取数

使用 `douyin-login` 独立 API 会话，从创作者作品列表读取本人作品的播放量，从公开作品详情读取点赞、评论、分享和收藏数量。

```bash
douyin-engagement check
douyin-engagement list
douyin-engagement fetch --row-id 发布记录ID
douyin-engagement daily
```

`daily` 取最近 30 条发布记录，按完整作品 ID 匹配并更新 `published-track`。每批共享一次创作者列表分页查询，每页 50 条、最多 10 页；找到目标作品即停止，再逐条查询公开详情。`list` 返回库内发布记录；`check` 验证主站账号及创作者作品列表可读，不代表发布权限或后台深指标完整可用。

播放量只使用创作者列表中账号 UID 与当前登录账号一致、完整作品 ID 与发布链接一致的 `statistics.play_count`。其他账号、列表中未找到的作品、分页达到上限或字段缺失时，播放量标为不可得；公开详情的 `play_count` 不用于补值。账号切换导致身份不一致时停止该记录写入。

结果的 `metrics` 只含本次可得的指标，`field_sources` 标明各字段来源，`unavailable` 与 `unavailable_reasons` 列出缺项及原因。`ok` 表示已成功回填可得指标，`complete` 表示五项基础指标全部可得；`ok: true`、`complete: false` 仍须报告缺项。缺值不填零，平台实际返回的零值正常保存。

只更新实际取得的字段；创作者列表失败仍可更新公开互动量，公开详情失败仍可更新已核验的本人播放量。不可得的指标及历史深指标保留原值，不能描述成本次自动采集结果。当前工具不自动获取完播、跳出、平均观看、曝光、点击率、画像或留存等后台深指标；用户主动提供后台数据时可使用 `published-track update-metrics` 补录，并注明时间与来源。

`fetch` 查询指定数据库行 ID；它不是平台作品 ID。没有发布链接或作品 ID 时先补记录，不按标题猜作品。认证失败走 `douyin-login`；Relay 故障、风控或指标不可得要保留错误原因，不重复发布。
