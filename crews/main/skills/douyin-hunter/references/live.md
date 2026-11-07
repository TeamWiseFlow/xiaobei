# 抖音公开直播读取

原始房间资料、商品、PK/榜单、最近消息和有界事件监听由 `douyin-hunter live` 提供，复用 `douyin-login` 独立 API 会话。调研分析交 `expert-osbi`，弹幕与点赞交 `expert-bd` 的 `douyin-live`。

```bash
douyin-hunter live room --room 'https://live.douyin.com/房间号'
douyin-hunter live products --room 房间号
douyin-hunter live pk --room 房间号
douyin-hunter live pk-rank --room 房间号 --side both
douyin-hunter live rank --room-id 实际room_id --anchor-id 主播ID --sec-anchor-id 主播sec_uid
douyin-hunter live ticket-rank --room-id 实际room_id
douyin-hunter live history --room 房间号
douyin-hunter live media --room 房间号
douyin-hunter live listen --room 房间号 --duration 60 --max-events 100 --output /受控目录/live-events.jsonl
douyin-hunter live call --help
```

`call` 仅暴露底层直播读取端点，包括商品详情；商品评价及数量用 `douyin-hunter call product_reviews/product_review_counts`。同一入口不支持 live_chat/live_like，即使提供 --confirm 也不发送。

房间号 web_rid 与接口 room_id 不相同，按实际房间响应取得后者。`history` 仅为进房快照最近最多 15 条，不能查询更早历史；`media` 只返回实际存在的流地址，关播或不可得时报告原因。

监听包含实际收到的弹幕、入场、礼物、点赞、关注、人数及 PK 事件，不自动发言或回复。有界监听时长和事件数以 CLI/运行库校验为准，结果保存到调用方指定的 Workspace 目录。

PK 查询前后核对局号，`context_changed` 不归档至旧局。贡献榜推送仅为部分快照，不能当完整榜；推断的 context_battle_id 与服务端 battle_id 分开使用。事件监听不等于音视频转写，礼物/榜单不代表成交额。

history/listen 缺少 webid 时，工具最多从本人身份接口恢复一次经平台下发的标识并缓存；不把已有 device_id 直接代入，不随机生成。WEB_DEVICE_ID_UNAVAILABLE 表示身份响应仍缺字段，保留诊断并复核 douyin-hunter check，不据此认定登出。会话或握手材料缺失时停止；风控与明确登录失效分别报告。公开房间可以属于自己或其他主播，实际访问权限由平台决定。读取与监听仍需真实账号验收。
