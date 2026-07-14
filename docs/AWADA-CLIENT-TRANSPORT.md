# awada-extension ↔ relay 网关传输契约

> 适用对象：**awada-extension（client 侧 bot）** 开发者。
> 本仓 relay 提供 HTTP/WS 网关，代理 bot 与 Redis Streams 之间的读写。
> **client 不再直连 Redis**；改走本网关。本文是唯一耦合面，与 `docs/API-CONTRACT.md` 同级权威。

## 1. 角色与方向（关键，先读）

权威约定见 `services/awada-server/src/REDIS_INFRASTRUCTURE.md`：

| stream | 谁写 | 谁读 |
|---|---|---|
| `awada:events:inbound:{lane}` | **server**（platform webhook 入列） | **bot**（你） |
| `awada:events:outbound:{lane}` | **bot**（你，回执） | **server**（发回 platform） |

awada-server（relay 侧 TS）只做两件事：收 platform webhook 写 inbound、读 outbound 发回 platform。**它不消费 inbound。** 消费 inbound、跑 LLM、写 outbound 的是 **bot = awada-extension = 你**。

网关是 bot 的传输代理：让你**读 inbound**、**写 outbound**，不暴露 Redis。

## 2. 鉴权

每个请求带 header：

```
X-OFB-Key: <你的 OFB_KEY>
```

- key 由 relay admin 签发，`scopes` 数组含 `awada:lane:<laneId>` 才能访问该 lane。
- 无任何 `awada:lane:*` scope → `403 AWADA_NOT_SUBSCRIBED`（未购买 awada 增值服务）。
- 有 awada scope 但不含请求的 lane → `403 FORBIDDEN_LANE`。
- 速率限制：每 key `rpm`（签发时定），超限 `429`。
- key 过期/吊销 → `401`。

## 3. HTTP 端点

Base URL：`https://<relay-domain>/api/v1/awada`（incu 上经 nginx TLS）。

### GET /inbound?lane=&block_ms=&count=&last_id=

**bot 读 inbound** — 长轮询拉取待处理事件。

| 参数 | 说明 |
|---|---|
| `lane` | 必填，lane id |
| `block_ms` | 长轮询阻塞毫秒，默认 2500，上限 10000 |
| `count` | 单次最多拉取条数，默认 10，上限 100 |
| `last_id` | 上次返回的 `lastId`；首次不传（网关从历史 pending `0` 开始消费） |

响应 200：

```json
{
  "success": true,
  "data": {
    "events": [
      { "id": "1234-0", "event": { /* InboundEvent envelope */ } }
    ],
    "lastId": "1234-0"
  },
  "error": null
}
```

`event` 是 awada 标准 InboundEvent（`schema_version=1`，含 `event_id`/`meta`/`payload`）。网关拉到即 `XACK`，不会重复投递同一条；处理失败请写回 outbound（见下）或本地 DLQ。

### POST /outbound?lane=

**bot 写 outbound** — 回传 LLM 结果给 server，由 server 发回 platform。

请求体：

```json
{
  "payload": [ /* ContentObject[] 或透传 */ ],
  "meta": {
    "platform": "worktool",
    "tenant_id": "...",
    "channel_id": "...",
    "user_id_external": "...",
    "session_id": "...",
    "source_event_id": "<对应 inbound 的 event_id>",
    "reply_to_message_id": "..."
  }
}
```

`meta` 字段：

| 字段 | 必填？ | 说明 |
|---|---|---|
| `platform` | **必填** | server 据此找 bot 配置发回 platform。从 inbound `event.meta.platform` 原样回传 |
| `channel_id` | **必填** | 群聊=群标识、私聊=`'0'`，server 据此判群/私聊定接收者。从 inbound `event.meta.channel_id` 原样回传 |
| `user_id_external` | **必填** | 私聊接收者标识。从 inbound `event.meta.user_id_external` 原样回传 |
| `tenant_id` | 建议 | 多租户路由用。从 inbound `event.meta.tenant_id` 回传 |
| `session_id` | 可选 | 链路追踪 |
| `source_event_id` | 建议 | 对应 inbound 的 `event_id`，回执关联 / 链路追踪 |
| `reply_to_message_id` | 可选 | 平台原消息 id（如企微 reply_to） |

> **关键**：`platform` / `channel_id` / `user_id_external` 缺省会被填成 `'unknown'`，多 bot 场景会路由失败或投错对象。最简做法：把 inbound `event.meta` 整个回传，再覆盖 `source_event_id`。

响应 200：

```json
{ "success": true, "data": { "streamId": "1234-0", "eventId": "<uuid>" }, "error": null }
```

错误响应（非 2xx）：

```json
{ "success": false, "data": null, "error": { "code": "FORBIDDEN_LANE", "message": "..." } }
```

`code` 见 §2（`AWADA_NOT_SUBSCRIBED` / `FORBIDDEN_LANE` / `BAD_REQUEST` / `REDIS_ERROR`）；鉴权失败 401/429 不走此信封。

### GET /health

无鉴权。`{ "data": { "service": "awada-gateway", "redis": true } }`。

## 4. WS 端点（推荐用于长连接）

### WS /inbound?lane=

升级时带 header `X-OFB-Key: <OFB_KEY>`（与 HTTP 同一鉴权）。升级成功后：

**server → client 帧**（推 inbound 事件）：

```json
{ "id": "1234-0", "event": { /* InboundEvent */ } }
```

**client → server 帧**（写 outbound 回执）：

```json
{
  "type": "reply",
  "payload": [ /* ContentObject[] */ ],
  "meta": {
    "platform": "worktool",
    "channel_id": "...",
    "user_id_external": "...",
    "tenant_id": "...",
    "source_event_id": "<对应 inbound 的 event_id>"
  }
}
```

`meta` 字段同 §3 POST /outbound：`platform` / `channel_id` / `user_id_external` **必填**（server 据此路由回 platform），从 inbound `event.meta` 原样回传；最简做法是整个 `event.meta` 回传再覆盖 `source_event_id`。

server 回 `reply_ok`：

```json
{ "type": "reply_ok", "streamId": "1234-0", "eventId": "<uuid>" }
```

- 30s 心跳（ws ping）。
- **必须 ack**：网关推事件后**不 XACK**，等你的 `{type:"ack",id}` 帧。未 ack 的事件留在 PEL，断线重连后由网关 XAUTOCLAIM 回收重投（min-idle 65s，仅回收锁已过期的 stale 交付）。所以处理完一条就发 ack，否则重连后会重收。
- 错误帧：`{ "error": { "code": "...", "message": "..." } }`。

## 5. session_lock / 幂等

- **session_lock 在网关侧**（relay Redis），client 不碰。同一 session_key 并发事件由网关串行化（锁 TTL 60s，bot 处理一条的硬上限）。
- **processed 幂等在网关侧**（`awada:{lane}:processed:{event_id}`，TTL 24h）。WS 模式下 **ack 时**才标记 processed —— 所以 unacked 交付在重连后能被重投，不会丢。
- **至少一次**语义：极少数情况下（你 ack 了但网关进程恰好崩溃在 ack 处理中）同一条会重投。bot 侧业务应按 event_id 幂等，或容忍重复。
- client 只需：收到 event → 处理 → POST /outbound 回执 → 发 `{type:"ack",id}`。无需自己做锁/去重。

## 6. 已删除 / 不再使用

- `session_conv`（Coze conversation_id）：历史遗留，已删，client 不要传。
- 直连 Redis：不再支持，端口不暴露。

## 7. lane 绑定与计费

- 一个 OFB_KEY ↔ 0 或多个 lane。awada 是**增值服务**（按月租），与 VIP Club 内含的 sign/wxmp/wxwork 无关。
- 租 lane = relay admin 建一个 lane（绑一个 platform，如一个企业微信机器人账号）+ 给你的 OFB_KEY 加 `awada:lane:<id>` scope。
- 一个 lane 绑定**恰好一个 platform**（1:1，不再支持按规则投递多 lane）。

## 8. 最小接入示例（伪代码）

```js
const ws = new WebSocket("wss://relay/api/v1/awada/inbound?lane=" + LANE, {
  headers: { "X-OFB-Key": OFB_KEY },
});
ws.on("message", async (raw) => {
  const frame = JSON.parse(raw);
  if (frame.event) {
    const reply = await runLLM(frame.event); // 你的 bot 逻辑
    ws.send(JSON.stringify({
      type: "reply",
      payload: reply,
      // 路由字段必填：原样回传 inbound 的 meta，再覆盖 source_event_id
      meta: { ...frame.event.meta, source_event_id: frame.event.event_id },
    }));
    ws.send(JSON.stringify({ type: "ack", id: frame.id }));
  }
});
```

## 9. 变更记录

- 2026-07-06：初版。方向修正为 bot 侧代理（GET /inbound 读、POST /outbound 写、WS /inbound）。此前若 client 实现过 POST /inbound / GET /outbound，需翻转。
- 2026-07-06：D5b — WS 必须 ack。processed 改在 ack 时标记（unacked 重连可重投，不丢消息）。网关 XAUTOCLAIM 周期回收 stale PEL。至少一次语义，bot 侧按 event_id 幂等。
- 2026-07-06：明确 reply（POST /outbound + WS reply 帧）的 `meta.platform` / `channel_id` / `user_id_external` **必填**——server 直接据此路由回 platform，不按 `source_event_id` 反查 inbound。client 须从 inbound `event.meta` 原样回传。补 HTTP 错误信封形状；§8 示例补 ack 帧。
