---
name: xhs-im
description: 小红书私信会话、单聊与群聊历史、未读、文本收发、标记已读、撤回消息及删除会话；复用 xhs-hunter PC 会话。
metadata:
  openclaw:
    emoji: 💬
    requires:
      bins:
        - python3
        - node
---

# 小红书私信

先运行 `xhs-hunter check`，会话缺失或失效走 `xhs-hunter login`。本工具归 expert-bd，复用 hunter 保存的 PC 会话，不混用 Creator Cookie。

## 读取

```bash
xhs-im list --limit 30 --cursor 0
xhs-im groups --limit 30 --cursor 0
xhs-im history --conversation 用户ID --limit 30 --cursor 0
xhs-im history --conversation group:群ID --limit 30 --cursor 0
xhs-im unread
xhs-im listen --seconds 60 --max-events 100
```

列表 cursor 是页码，历史 cursor 是上一页真实 store_id。保留原始响应，不猜游标或字段。群聊仅支持列表和历史，字段需用真实返回核对。监听逐行输出 JSON，每次最多 3600 秒、1000 条。

## 写操作

以下命令默认只预览；已有用户授权时，在同一命令加 `--confirm`。

```bash
xhs-im send 用户ID "用户授权的文本"
xhs-im read --conversation 用户ID
xhs-im revoke --conversation 用户ID --message 真实消息ID
xhs-im delete --conversation 用户ID
```

仅支持单聊文本发送。`read` 在脚本内从真实会话列表取得 read_store_id 和未读数；缺会话或字段即停，不用默认零伪造回执。`revoke` 撤回指定消息，`delete` 删除本账号的会话，不能解释为替对方删除消息。群聊拒绝发送、已读、撤回和删除。

WebSocket `send` 返回 submitted 与 mid 只代表向连接提交，不能当作送达或已读。提交结果不明先查历史，不直接重发。只有确认未提交时才用 HTTP 发送：

```bash
xhs-im call send_short_link_message --kwargs '{"receiver":"用户ID","content":"已授权正文"}' --confirm
```

`methods` 列出底层接口；`call` 的写方法同样默认预览，加 `--confirm` 执行。只传真实接口字段，不猜捕获帧或加密消息。

这些私信写操作与实时监听仍需真实账号验收，离线回归通过不等于平台已送达。私信材料只存当前任务受控目录，不写入代码仓。
