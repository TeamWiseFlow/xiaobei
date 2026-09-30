---
name: douyin-live
description: 抖音直播房间、连麦/PK/榜单、商品与评论查询、弹幕点赞及实时控场事件监听。
---

# 直播运营

复用独立 API 会话；Relay 提供 REST 动态字段与 WebSocket 握手字段，本机负责连接、心跳、ACK、解码及有限重连。

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
