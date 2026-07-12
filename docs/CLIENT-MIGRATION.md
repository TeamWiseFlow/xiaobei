# client 仓迁移指南 — relay 无状态多租户改造

> 适用：2026-07-06 relay 改造后。本文件是 client 仓（wiseflow 核心）从「relay 存凭据 + OFB_KEY 绑账号」模型迁移到「凭据按请求透传」模型的操作手册。
>
> 配套契约：[API-CONTRACT.md](./API-CONTRACT.md)（两仓唯一耦合面，已同步更新）。

## 1. 为什么要改

relay 即将转为**对外的付费中转服务**，一个实例服务很多用户。旧模型「每个用户一个 OFB_KEY，relay 侧存该用户的公众号/企业微信凭据并做映射」复杂度太高、凭据散落服务端不安全。

新模型：

- `X-OFB-Key` **只验身份**（谁在用），不再绑任何公众号/企业微信账号。
- 每个请求由 **client 在 body 里按请求携带目标账号凭据**（`wechat_app_id`+`wechat_app_secret` / `corp_id`+`corp_secret`）。
- relay **不落盘、不记日志、不存任何用户凭据**；强制 HTTPS；凭据只在请求作用域内存在。

代价：client 要在本地管理多套凭据。收益：relay 无状态、可横向扩、凭据不离开用户掌控。

## 2. OFB_KEY 签发流程（不变）

OFB_KEY 仍是 relay 的唯一身份凭证。签发/吊销走 auth 服务（运维侧强鉴权）：

```bash
# 签发（运维）
curl -X POST https://relay.openclaw-for-business.com/api/v1/auth/issue \
  -H "Content-Type: application/json" \
  -d '{"owner":"<用户标识>","scope":"*","ttl":null}'
# → { "key": "ofb_xxx", "expiresAt": null }

# 吊销
curl -X POST https://relay.openclaw-for-business.com/api/v1/auth/revoke \
  -H "Content-Type: application/json" -d '{"key":"ofb_xxx"}'
```

**变化**：签发入参**不再带 `accounts`**。旧版的 `accounts: { wechat_mp: [...], wechat_corp: [...] }` 字段已废弃，传了也会被忽略；relay 不再需要知道你绑了哪个账号。

## 3. wx-mp 技能改造（公众号草稿发布）

### 旧（已废弃）

client 本地装 `wenyan-cli`，调 `wenyan publish` CLI；relay 侧 `wenyan serve` 持久进程按 OFB_KEY 查公众号凭据。

### 新

HTTP `POST /api/v1/wx-mp/publish`，multipart 表单：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `markdown` | text | 是 | 待发布的 markdown 正文 |
| `wechat_app_id` | text | 是 | 公众号 AppID |
| `wechat_app_secret` | text | 是 | 公众号 AppSecret |
| `theme` | text | 否 | 内置渲染主题 id（`pie`/`lapis`/`default`/…） |
| `custom_theme` | text | 否 | 自定义主题 CSS 文本内容（client 读本地 `.css` 上传；relay 写 per-request 临时目录，不持久化） |
| `images` | file | 否 | 正文图片，可多个 |

错误码（400）：`MISSING_MARKDOWN` / `MISSING_APP_ID` / `MISSING_APP_SECRET` / `INVALID_CUSTOM_THEME`；发布失败 502。仅支持文本+图片（无视频）。普通文章 / 小绿书由 relay 内核心按 `image_list` 是否为空自动分支。`theme` 与 `custom_theme` 同时给时 `custom_theme` 优先。自定义主题由 `generate-wenyan-theme` 技能在 client 本地生成并登记到 `wx-mp-publisher/SKILL.md` 主题表；发布时 client 读对应 `.css` 文件内容作为 `custom_theme` 字段上传，relay 不存主题、不按用户落盘。

### 前后对比

```js
// 旧：CLI 调用
// await $`wenyan publish --appid wxXXX draft.md`

// 新：HTTP POST
const form = new FormData()
form.append('markdown', markdownContent)
form.append('wechat_app_id', creds.appId)
form.append('wechat_app_secret', creds.appSecret)
if (theme) form.append('theme', theme)                 // 内置主题 id
if (customThemeCss) form.append('custom_theme', customThemeCss) // 自定义主题 CSS 文本（读本地 .css）
for (const img of images) form.append('images', img.blob, img.filename)

const r = await fetch('https://relay.openclaw-for-business.com/api/v1/wx-mp/publish', {
  method: 'POST',
  headers: { 'X-Ofb-Key': OFB_KEY }, // 注意：fetch + FormData 不要手动设 Content-Type，让 fetch 带 boundary
  body: form,
})
const { success, data, error } = await r.json()
if (!success) throw new Error(`wx-mp publish failed: ${error}`)
// data.media_id 为草稿 media_id
```

## 4. wxwork 技能改造（企业微信朋友圈 + 微盘）

### 旧（已废弃）

relay 按 `OFB_KEY → accounts.wechat_corp[0]` 选 corp_id，再查 `secrets/wxwork.json` 拿 corp_secret。client 只发业务 body，不带凭据。

### 新

每个请求 body 多带 `corp_id` + `corp_secret` 两个字段。relay 用它们换 access_token，**在转发给企业微信前剥离这两个字段**。

| 端点 | body 类型 | 凭据字段位置 |
|------|-----------|--------------|
| `POST /api/v1/wxwork/moments/add` | JSON | 顶层 `corp_id` / `corp_secret` |
| `POST /api/v1/wxwork/media/upload` | multipart | 表单字段 |
| `POST /api/v1/wxwork/drive/upload-image` | multipart | 表单字段 |
| `POST /api/v1/wxwork/drive/upload-video` | multipart | 表单字段 |

错误码：`MISSING_CORP_CREDENTIALS`（400，缺 corp_id 或 corp_secret）；`GETTOKEN_FAILED`（502，corp_secret 错或 corp_id 不存在）。

### 前后对比

```js
// 旧：moments/add，client 不带凭据
// await fetch(url, { method:'POST', headers:{'X-Ofb-Key':OFB_KEY},
//   body: JSON.stringify({ text, attachments }) })

// 新：moments/add，client 带 corp 凭据（relay 会剥离，不下发企业微信）
await fetch('https://relay.openclaw-for-business.com/api/v1/wxwork/moments/add', {
  method: 'POST',
  headers: { 'X-Ofb-Key': OFB_KEY, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    corp_id: creds.corpId,        // ← 新增
    corp_secret: creds.corpSecret, // ← 新增
    text, attachments, // 原业务字段原样传
  }),
})

// 新：media/upload（multipart），凭据作为表单字段
const form = new FormData()
form.append('corp_id', creds.corpId)
form.append('corp_secret', creds.corpSecret)
form.append('type', 'image')
form.append('media', file.blob, file.filename)
await fetch('https://relay.openclaw-for-business.com/api/v1/wxwork/media/upload', {
  method: 'POST', headers: { 'X-Ofb-Key': OFB_KEY }, body: form,
})
```

`drive/upload-image` / `drive/upload-video` 同 `media/upload`：multipart 里加 `corp_id`+`corp_secret` 两个字段，其余不变。

## 5. 凭据在 client 侧怎么存

relay 不再帮你存，client 自己管。建议（按安全性从高到低）：

1. **系统 keychain**（macOS Keychain / Windows Credential Manager / Linux libsecret）— 首选。
2. **本地 secrets 文件**（如 `~/.wiseflow/credentials.json`，权限 `0600`，**进 `.gitignore`**）：
   ```json
   {
     "wxmp": { "wxXXX": { "appId": "...", "appSecret": "..." } },
     "wxwork": { "wwYYY": { "corpId": "wwYYY", "corpSecret": "..." } }
   }
   ```
3. **环境变量**（CI/容器场景）：`WXMP_APP_ID_<suffix>` / `WXWORK_CORP_SECRET_<corpId>` 等，启动时注入。

**绝对不要**进 git 仓、不要打进镜像层、不要写日志。多账号就在上面结构里多挂几条，发布时按目标账号取对应凭据透传。

## 6. 迁移步骤

1. **取现存的 corp_secret（一次性）**：incu 上旧 `~/wiseflow-relay/secrets/wxwork.json` 里有现有 corp 的 secret（`{corp_id: secret}` 字典）。迁到 client 本地凭据文件后，该文件在 relay 侧已废弃（可删）。
   ```bash
   ssh incu 'cat ~/wiseflow-relay/secrets/wxwork.json'
   # → { "ww38ea1257047a98c9": "<secret>" }  # 拷到 client 本地凭据文件，然后从 relay 删
   ```
2. **取现存的公众号凭据**：原 `wenyan-cli` 本地配置（`~/.wenyan/` 或环境变量）里的 `appId`/`appSecret` 直接迁到 client 本地凭据文件。
3. **改技能调用**：按 §3 / §4 的前后对比改 client 仓里 wx-mp、wxwork 两个技能的发布逻辑。删掉对 `wenyan-cli` CLI 的依赖（relay 已内置 `@wenyan-md/core`，client 不再需要装 wenyan-cli）。
4. **本地验证**：
   ```bash
   # wx-mp：缺 app_id 应得 400 MISSING_APP_ID
   curl -X POST -H "X-Ofb-Key: $OFB_KEY" -F "markdown=x" \
     https://relay.openclaw-for-business.com/api/v1/wx-mp/publish
   # wxwork：缺 corp_id 应得 400 MISSING_CORP_CREDENTIALS
   curl -X POST -H "X-Ofb-Key: $OFB_KEY" -H "Content-Type: application/json" \
     -d '{"text":"hi"}' \
     https://relay.openclaw-for-business.com/api/v1/wxwork/moments/add
   ```
5. **清理**：确认 client 全量切流后，删 incu 上 `~/wiseflow-relay/secrets/wxwork.json`（已废弃）。

## 7. relay 侧已删 / 已改清单

- `secrets/wxwork.json` 加载逻辑、`WXWORK_SECRETS_PATH` 环境变量、`fs.watch` 热更新 — 全删。
- keys.json 的 `accounts.wechat_corp` / `accounts.wechat_mp` 字段 — 已从 incu keys.json 剥离（key 仍有效，只是不再绑账号）。
- `wenyan serve` 持久进程、`wenyan-A` pm2 实例、`/api/v1/wx-mp/` 的多公众号上游 map — 全删，改由 `wx-mp-proxy`（端口 3004）导入 `@wenyan-md/core` 作为库直接调用。
- `resolveTokenForRequest`：从 `req.ofbKey.accounts.wechat_corp[0]` + secrets 文件 → 改读 `req.body.corp_id` + `req.body.corp_secret`。
- tokenCache：从按 `corp_id` 分桶 → 改按 `(corp_id, sha256(corp_secret))` 分桶（同 corp 同 secret 复用；secret 变了重取，避免错 secret 搭便车）。
- `/health`：wxwork 不再报告 `secretsLoaded`；wx-mp/wxwork 的 `/health` 仅内部端口直连，不公开暴露。

## 8. 不变的部分

- `X-OFB-Key` 鉴权、限流、吊销、过期语义 — 不变。
- sign 服务（`/sign/xhs/*`、`/sign/douyin`）— 不变。
- publish-relay（`/publish/bilibili`、`/publish/douyin`）— 不变。
- awada-gateway — 不变（本轮未动，待后续调整计划）。
- 响应包络 `{ success, data, error }` — 不变。
