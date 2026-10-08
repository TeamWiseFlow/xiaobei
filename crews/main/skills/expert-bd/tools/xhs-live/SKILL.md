---
name: xhs-live
description: 小红书公开直播间调研与互动：频道与广场、房间和业务信息读取、实时事件监听，以及经授权的直播文字评论。
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

主要用于竞争对手调研和直播间互动。目标可以是自己或他人的公开直播间，不要求登录账号为主播；`host_id` 是目标主播 ID。实际访问和发言权限由平台决定，不提供主播后台禁言、踢人或开关播。

```bash
xhs-live methods
xhs-live call list_categories
xhs-live call square_feed --kwargs '{"size":20}'
xhs-live call current_room_info --args '["直播间 room_id"]'
xhs-live listen --room-id '直播间 room_id' --seconds 60 --max-events 100
xhs-live send '直播间 room_id' '已确认的评论文本' --host-id '主播 user_id' --confirm
```

`listen` 逐行输出 JSON 事件，最后输出事件数；每次最多监听 3600 秒、1000 条。关注 `decoded.room` 的弹幕、进场、点赞、礼物、关注等事件；无对应字段时保留原始帧，不能编造事件。按用户约定的观察窗口分段监听并汇总。

`call` 支持 `methods` 列出的直播 HTTP 接口，`--args` 为 JSON 数组，`--kwargs` 为 JSON 对象。`join_room`、`viewer_heart` 等会改变服务端观看状态；只在实际进入/维持直播时调用。`gift_panel` 与 `charge_panel` 只读取面板，不会赠礼或充值。若需按 WebSocket 发送完整直播文字帧，先从当前房间状态取得必要字段，再用 `room-text <room_id> --payload <JSON>`；不要猜测昵称、身份、优先级等字段。

发评论前核对确切文案、目标直播间和已有授权范围；超出授权才补充确认。接口提交异常或结果不明时停止，先到直播间核实，不自动重发。竞争对手调研见 `../../workflows/live-research.md`，直播互动见 `../../workflows/live-interaction.md`。

`send`、`room-text`、`send-captured-frame` 和 `call` 写方法默认预览，已有授权时加 `--confirm`。直播发送与监听仍需真实账号验收，不将离线通过当作现场成功。
