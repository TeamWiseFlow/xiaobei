# wiseflow-relay 接口契约

> 本文件是 relay 与 client 两仓的**唯一耦合面**。改接口必须先改本文件并通知 client 仓维护者。

## 通用约定

- **前缀**：`/api/v1/`（兼容期 tx-relay 旧路径保留，见 HANDOVER §5）
- **鉴权**：`X-OFB-Key: <OFB_KEY>`（除 `POST /auth/issue` 与健康检查外必填）
- **响应包络**：

```json
{ "success": true, "data": <any>, "error": null, "meta": { "requestId": "...", ... } }
```

错误时 `success: false`、`data: null`、`error: { code, message }`。HTTP 状态码：200 成功；400 入参错；401 鉴权错；403 越权；429 限流；5xx 服务错。

## auth（Phase 1）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/auth/issue` | `{ owner, scope, ttl? }`（运维侧强鉴权） | `{ key, expiresAt }` |
| POST | `/auth/revoke` | `{ key }` | `{ revoked: true }` |

## sign（Phase 2，已实现）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/sign/xhs/headers` | `{ uri, method?, payload?, params?, cookies, xsec_appid? }` | `{ data: { headers: { x-s, x-s-common, x-t, x-b3-traceid, x-xray-traceid, Cookie, ... } } }`（仅签名） |
| POST | `/sign/douyin` | `{ queryString, postData?, ua? }` | `{ data: { a_bogus } }`（仅签名） |
| POST | `/sign/bilibili/wbi` | `{ params, imgKey, subKey }` | `{ data: { wts, w_rid } }`（仅签名字段，client 合并到原参数） |

**不提供 proxy 端点**（不在 relay 上替 client 调小红书/抖音/B站业务接口）：relay 是固定公网 IP，频繁替 client 代请求会被平台风控/封 IP。client 拿到签名 header / 签名参数后，**在自己的浏览器上下文/小程序里发请求到平台 API**。

`/sign/xhs/headers` 一次性同时返回 **新 + 老**两套签名字段（`x-s` 老格式 / `x-s-common` 新格式），client 按场景选用：
- 取数 / 浏览 / feed 拉取 → 用 `x-s`
- 发布 / 写操作（发笔记、点赞、关注、评论）→ 用 `x-s-common`

`xsec_appid` 默认 `xhs-pc-web`；client 调用非 PC web 端时传 `xhs-mp-web` / `xhs-app` 等。

- douyin 只签 `a_bogus`（纯函数，client 自带 msToken/webid）；relay 不代发。
- douyin vendor 有 init-once 全局状态，relay 每次签名 spawn 独立子进程隔离。
- bilibili WBI 纯签名：`w_rid = md5(sortedQuery + mixinKey)`，`wts = floor(now/1000)`。relay 只算 `{wts, w_rid}`，**不拉 nav、不发任何平台请求**。`imgKey`/`subKey` 的拉取（`/x/web-interface/nav` → `data.wbi_img.{img_url,sub_url}` 文件名去扩展名）与缓存由 client 负责（对应上游 `sign.py` 的 `BilibiliPythonSigner` 在 client 侧）。client 拿 `{wts, w_rid}` 合并到原参数自行拼 URL 发请求。

## publish-relay（Phase 3）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/publish/bilibili` | `{ videoUrl, title, desc, tags, cover }` | `{ data: { bvid } }` |
| POST | `/publish/douyin` | `{ videoUrl, title, tags }`（仅 API 逆向路线） | `{ data: { ... } }` |

<!-- video-relay 已于 2026-07-04 整体取消。原端点说明保留仅作历史记录，下次 client 仓 review 后可删除。
## video-relay（已取消 — DEPRECATED 2026-07-04，原 Phase 3）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/video/generate` | `{ provider, model, prompt, params }` | `{ data: { task_id } }` |
| GET | `/video/task/:id` | — | `{ data: { status, videoUrl, progress } }` |

`status`：`pending` / `running` / `succeeded` / `failed`。`videoUrl` 须公开可访问。
-->


## awada（Phase 4）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/awada/inbound` | 平台 webhook 原始报文 | `{ success }` |
| GET | `/awada/outbound?lane=<id>` | long-poll / WS，`X-OFB-Key` 鉴权 | 消息流 |

## tx-relay（无状态多租户 — 2026-07-06 改造）

> **凭据透传原则**：`X-OFB-Key` 仅验身份（谁在用），不绑任何公众号/企业微信。每个请求由 client 在 body 里**按请求**携带目标账号凭据（`wechat_app_id`+`wechat_app_secret` / `corp_id`+`corp_secret`）。relay 不落盘、不记日志、不存任何用户凭据；强制 HTTPS。

### wx-mp（公众号草稿发布）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| GET | `/wx-mp/health` | — | `{ success: true }`（仅 3004 直连，不公开） |
| POST | `/wx-mp/publish` | multipart：`markdown`(text) + `wechat_app_id`(text) + `wechat_app_secret`(text) + `theme`?(text) + `custom_theme`?(text，CSS 内容) + `images`?(file，可多) | `{ success, data: { media_id?, article_url? } }` |

错误码：`MISSING_MARKDOWN` / `MISSING_APP_ID` / `MISSING_APP_SECRET` / `INVALID_CUSTOM_THEME`（400）；发布失败 502。仅支持文本+图片（无视频）。两种模式由核心按 `image_list` 是否为空自动分支（普通文章 / 小绿书）。

`theme` 为内置主题 id（`pie`/`lapis`/`default`/…）；`custom_theme` 为自定义主题 CSS **文本内容**（由 client 读本地 `.css` 文件上传）。两者同时给时 `custom_theme` 优先（与 wenyan-cli `--custom-theme` 一致）。relay 把 `custom_theme` 写到 per-request 临时目录后随请求清理，**不持久化、不落盘、天然用户隔离**——relay 不存任何用户主题。

### wxwork（企业微信朋友圈 + 微盘）

| 方法 | 路径 | 入参 | 出参 |
|------|------|------|------|
| POST | `/wxwork/media/upload` | multipart：`corp_id`+`corp_secret`+`type`?+`media`(file) | `{ ok, media_id, type }` |
| POST | `/wxwork/moments/add` | JSON：`{ corp_id, corp_secret, text, attachments, ...add_moment_task 原参 }` | `{ ok, moment_id }` |
| POST | `/wxwork/drive/upload-image` | multipart：`corp_id`+`corp_secret`+`spaceid`+`fatherid`+`file_name`?+`file`(image, ≤10M) | `{ ok, fileid }` |
| POST | `/wxwork/drive/upload-video` | multipart：`corp_id`+`corp_secret`+`spaceid`+`fatherid`+`file_name`?+`file`(video) | `{ ok, fileid, fast_forward }` |
| POST | `/wxwork/drive/space-create` | JSON：`{ corp_id, corp_secret, space_name, space_sub_type?, auth_info? }` | `{ ok, spaceid, detail }` |
| POST | `/wxwork/drive/space-setting` | JSON：`{ corp_id, corp_secret, spaceid, share_url_no_approve?, share_url_no_approve_default_auth?, ... }` | `{ ok, detail }` |
| POST | `/wxwork/drive/space-share` | JSON：`{ corp_id, corp_secret, spaceid }` | `{ ok, space_share_url, detail }` |
| POST | `/wxwork/drive/create-folder` | JSON：`{ corp_id, corp_secret, spaceid, fatherid, file_name }` | `{ ok, fileid, detail }` |
| POST | `/wxwork/drive/list-files` | JSON：`{ corp_id, corp_secret, spaceid, fatherid, sort_type, start, limit }` | `{ ok, detail }` |
| POST | `/wxwork/drive/file-info` | JSON：`{ corp_id, corp_secret, fileid }` | `{ ok, detail }` |
| POST | `/wxwork/drive/rename` | JSON：`{ corp_id, corp_secret, fileid, new_name }` | `{ ok, fileid, detail }` |
| POST | `/wxwork/drive/move` | JSON：`{ corp_id, corp_secret, fatherid, fileid[], replace? }` | `{ ok, detail }` |
| POST | `/wxwork/drive/delete` | JSON：`{ corp_id, corp_secret, fileid[] }` | `{ ok, detail }` |
| POST | `/wxwork/drive/file-share` | JSON：`{ corp_id, corp_secret, fileid }` | `{ ok, share_url, detail }` |

错误码：`MISSING_CORP_CREDENTIALS`（400，缺 corp_id 或 corp_secret）；`MISSING_FIELD`（400，drive 管理接口缺必填字段）；`GETTOKEN_FAILED`（502，corp_secret 错或 corp_id 不存在）。`moments/add` 与 drive 管理接口的 `corp_id`/`corp_secret` 在转发企业微信前由 relay 剥离，不下发。tokenCache 按 `(corp_id, corp_secret)` 分桶。drive 管理接口（space-create/space-setting/space-share/create-folder/list-files/file-info/rename/move/delete/file-share）为 JSON 透传，对应企业微信微盘 `wedrive/space_create|space_setting|space_share|file_create|file_list|file_info|file_rename|file_move|file_delete|file_share`；`create-folder` 强制 `file_type=1`。`upload-image` 由 relay 把 multipart 转成上游要求的 JSON+`file_base64_content`（≤10M，超过请走 `upload-video` 分块）。

> 收敛前 tx-relay 保留原路径与原鉴权（`x-api-key`）的兼容期已结束（本轮整体替换部署）。旧 `secrets/wxwork.json` 与 keys.json 的 `accounts.wechat_corp`/`accounts.wechat_mp` 字段均已废弃，见 [CLIENT-MIGRATION.md](./CLIENT-MIGRATION.md)。
