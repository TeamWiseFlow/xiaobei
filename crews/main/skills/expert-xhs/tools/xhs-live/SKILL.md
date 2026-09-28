---
name: xhs-live
description: 小红书直播间原子操作：频道与广场、直播间资料、评论与业务信息读取，WebSocket 事件监听，以及经确认的直播文字评论。
metadata:
  openclaw:
    emoji: 🔴
    requires:
      bins:
      - python3
      - node
---

# 小红书直播间

使用 `xhs-live` wrapper。先运行 `xhs-hunter check`；登录态复用 `xhs-hunter login` 建立的 PC 会话 `~/.openclaw/logins/xhs-pc-local.json`。缺少会话时先完成 PC 扫码；不要用 Creator Cookie 或浏览器导出的其他指纹会话拼接。

```bash
xhs-live methods
xhs-live call list_categories
xhs-live call square_feed --kwargs '{"size":20}'
xhs-live call current_room_info --args '["直播间 room_id"]'
xhs-live listen --room-id '直播间 room_id' --seconds 60 --max-events 100
xhs-live send '直播间 room_id' '已确认的评论文本' --host-id '主播 user_id'
```

`listen` 逐行输出 JSON 事件，最后输出事件数；每次最多监听 3600 秒、1000 条。关注 `decoded.room` 的弹幕、进场、点赞、礼物、关注等事件；无对应字段时保留原始帧，不能编造事件。需要长期控场时分段监听并定期汇总。

`call` 支持 `methods` 列出的直播 HTTP 接口，`--args` 为 JSON 数组，`--kwargs` 为 JSON 对象。`join_room`、`viewer_heart` 等会改变服务端观看状态；只在实际进入/维持直播时调用。`gift_panel` 与 `charge_panel` 只读取面板，不会赠礼或充值。若需按 WebSocket 发送完整直播文字帧，先从当前房间状态取得必要字段，再用 `room-text <room_id> --payload <JSON>`；不要猜测昵称、身份、优先级等字段。

发评论前向用户展示确切文案与目标直播间并取得授权。接口提交异常或结果不明时停止，先到直播间核实，不自动重发。直播控场编排见 `../../workflows/live-control.md`。
