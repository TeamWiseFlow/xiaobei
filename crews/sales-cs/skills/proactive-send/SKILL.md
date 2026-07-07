---
name: proactive-send
description: >
  向 awada 客户主动发送消息。在 openclaw 消息处理循环之外直接 POST 到 relay 网关 outbound 端点，无需等待客户发起对话。
metadata:
  openclaw:
    emoji: 📤
---

# 主动发送（proactive-send）

本技能让 sales-cs 在特定业务场景下主动向客户发送消息，而非等待客户发起对话。

---

## 使用方法

```bash
./skills/proactive-send/scripts/send.sh \
  --user-id-external "<user_id_external>" \
  --text "<消息内容>"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--user-id-external` | 是 | 客户的 awada 用户标识，来自对话上下文 Sender 块的 `id` 字段 |
| `--text` | 是 | 发送给客户的消息文本 |

`relayBaseUrl` / `ofbKey` / `platform` / `lane` 自动从 `~/.openclaw/openclaw.json` 的 `channels.awada` 读取。`channel_id` / `tenant_id` 固定为 `"0"`（私聊）。

### 返回值

- 成功：打印 relay outbound stream ID（如 `1234-0`），exit 0
- 失败：打印错误描述到 stderr，exit 1

---

## 注意事项

- 本技能仅提供消息发送能力，**何时使用、发给谁、发什么内容**由调用场景决定
- 请勿在正常对话流程中调用——会破坏对话自然性
- 消息内容应简短、自然、克制
- 走 HTTP `POST /api/v1/awada/outbound?lane=` + `X-OFB-Key` header，不直连 Redis（契约见 `docs/AWADA-CLIENT-TRANSPORT.md` §3）
