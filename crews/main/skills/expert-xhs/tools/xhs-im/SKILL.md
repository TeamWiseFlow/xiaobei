---
name: xhs-im
description: 小红书 PC 私信原子操作：会话列表、历史、未读、WebSocket 收信和经确认的文本发送；复用 xhs-hunter PC 登录态。
metadata:
  openclaw:
    emoji: 💬
    requires:
      bins:
      - python3
      - node
---

# 小红书私信

使用 `xhs-im` wrapper，先运行 `xhs-hunter check`。它复用 `xhs-hunter login` 保存在 `~/.openclaw/logins/xhs-pc-local.json` 的 PC 会话。所有命令输出 JSON；`listen` 输出逐行事件。收信前先检查登录态与目标用户 ID。

```bash
xhs-im methods
xhs-im call get_chats --kwargs '{"limit":20,"page":0}'
xhs-im call get_message_history --kwargs '{"chat_user_id":"用户 ID","limit":30}'
xhs-im call get_unread
xhs-im listen --seconds 60 --max-events 100
xhs-im send '接收方 user_id' '用户批准的私信正文'
```

`xhs-im send` 通过 WebSocket 提交一条文本私信，返回 `state=submitted` 与消息 ID；这只表示已向连接提交，不能当作对方收到或已读。WebSocket 不可用时，确认未送达后可用 HTTP 兜底：

```bash
xhs-im call send_short_link_message --kwargs '{"receiver":"接收方 user_id","content":"已批准的正文"}'
```

如果 WebSocket 提交结果不明，先查会话历史，不能直接改用 HTTP 重发。用户未授权的私信不发送。`call` 可访问 `methods` 列出的其他 PC 私信接口；撤回、删除、已读回执和离线消息确认会修改服务端状态，需依据实际用户任务执行。已抓取的私信内容只放当前任务所需的受控工作区文件，不写入代码仓。
