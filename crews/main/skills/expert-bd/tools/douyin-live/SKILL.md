---
name: douyin-live
description: 抖音公开直播间调研与互动：房间、PK、榜单、商品和最近消息查询，弹幕、点赞及实时事件监听。
---

# 抖音直播调研与互动

复用独立 API 会话；Relay 提供 REST 动态字段与 WebSocket 握手字段，本机负责连接、心跳、ACK、解码及有限重连。

主要用于竞争对手调研和直播间互动。按目标房间号或链接访问自己或他人的公开直播间，不要求登录账号为主播；实际访问和发言权限由平台决定。调研编排见 `../../workflows/live-research.md`，互动编排见 `../../workflows/live-interaction.md`。不提供主播后台禁言、踢人或开关播。

```bash
douyin-live room --room "https://live.douyin.com/房间号"
douyin-live pk --room 房间号
douyin-live pk-rank --room 房间号 --side both
douyin-live rank --room-id 实际room_id --anchor-id 主播ID --sec-anchor-id 主播sec_uid
douyin-live ticket-rank --room-id 实际room_id
douyin-live products --room 房间号
douyin-live listen --room 房间号 --duration 60 --max-events 100 --output /受控目录/live-events.jsonl
douyin-live chat --room-id 实际room_id --text "弹幕内容"
douyin-live like --room-id 实际room_id --count 1
```

房间号 `web_rid` 与接口 `room_id` 不相同；用房间响应取得后者。弹幕与点赞默认预览；用户授权后加 `--confirm`。弹幕 ≤200 字，单次点赞 1–20 次。监听不自动发弹幕、不自动回复观众，不送礼；平台风控立即停止。

直播监听覆盖聊天、入场、礼物、点赞、关注、人数及 PK 生命周期/比分/贡献推送。PK 榜查询前后核对局号；`context_changed` 不可归档至旧局。推送贡献榜为部分快照，不能当完整榜；推断的 `context_battle_id` 与服务端确认的 `battle_id` 分开使用。

`douyin-live call <method> --params '{...}'` 查询底层直播端点，包括商品详情；商品评价及数量使用 `douyin-hunter call product_reviews/product_review_counts`。具体参数通过 `douyin-live call --help` 和 `douyin-hunter methods` 查看。会话、设备 ID、短期握手材料缺失时停止，交 `douyin-login`/IT engineer 处理。


`douyin-live history --room 房间号` 获取进房消息快照，最多最近 15 条，不能查询更早历史；`douyin-live media --room 房间号` 返回当前房间实际流地址，关播或未返回时报告不可得。互动工具归 expert-bd；内容搜索和账号作品仍调用一级 douyin-hunter。直播写操作、实时监听及 PK 必须以真实响应核实，不将离线回归当作现场验收。
