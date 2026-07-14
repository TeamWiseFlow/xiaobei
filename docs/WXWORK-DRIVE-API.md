# 企业微信微盘（wedrive）relay 接口 — client 接入与测试指南

> 适用：2026-07-06 relay `7add6cf` 起。本文件是 client 仓更新微盘相关技能 / 代码的依据。
> 配套契约：[API-CONTRACT.md](./API-CONTRACT.md) §wxwork。两仓唯一耦合面，已同步。

## 1. 背景：为什么需要这批接口

企业微信微盘 API 有一个硬约束：**应用只能在「自己创建的空间」里建文件夹、传文件**。relay 之前只暴露了 `upload-image` / `upload-video`，既没有「建空间」也没有「建文件夹」接口，client 拿不到合法的 `spaceid` / `fatherid`，上传必失败。

本次补全微盘空间 + 文件管理接口（建空间 / 建文件夹 / 列目录 / 取信息 / 重命名 / 移动 / 删除），并修了 `upload-image` 的一个潜伏 bug（见 §5）。

## 2. 通用约定（所有 wxwork 接口）

- **鉴权**：header `X-OFB-Key: <OFB_KEY>`。OFB_KEY 由 relay 的 auth 服务签发，只验身份，不绑 corp。
- **凭据透传**：每个请求在 body 里带 `corp_id` + `corp_secret`。relay 不落盘、不记日志，转发企业微信前剥离这两个字段。
- **base URL**：生产 `https://relay.openclaw-for-business.com`（路径前缀 `/api/v1`）。
- **统一响应包络**：`{ ok: boolean, ...业务字段, detail: <上游原始回包> }`。`ok:false` 时带 `error` / `code`。
- **token 缓存**：relay 按 `(corp_id, corp_secret)` 缓存 access_token（复用 7200s，secret 变了重取），client 无需自己管 token。

错误码：

| code | HTTP | 含义 |
|---|---|---|
| `MISSING_CORP_CREDENTIALS` | 400 | body 缺 `corp_id` 或 `corp_secret` |
| `MISSING_FIELD` | 400 | drive 管理接口缺必填字段（见各接口「必填」列） |
| `GETTOKEN_FAILED` | 502 | `corp_secret` 错或 `corp_id` 不存在 |
| 上游 `errcode != 0` | 400 | 企业微信拒绝，`detail` 里是原始 `errcode/errmsg` |

## 3. 推荐流程：上传文件到自建空间

```
0. space-create   →  拿到 spaceid（应用自动成为该空间超管）
0a. space-setting →  打开 share_url_no_approve（否则邀请链接加入会被审批卡住）
0b. （可选）space-share → 拿邀请链接发给同事加入该空间
1. create-folder  →  拿到 folder 的 fileid（fatherid 填 spaceid 即根目录）
2. upload-image / upload-video  →  fatherid 用上一步的 fileid
3. （可选）list-files  →  列文件夹内容确认
4. （可选）rename / move / delete  →  后续整理
```

> 应用调用 `space-create` 后自动成为该空间的超级管理员，后续在该空间内建文件夹 / 传文件都合法。
> `fatherid` 在「根目录」时填空间的 `spaceid` 本身。

## 4. 接口清单

### 4.0 `POST /api/v1/wxwork/drive/space-create` — 新建空间

对应企业微信 [93655 `wedrive/space_create`](https://developer.work.weixin.qq.com/document/path/93655)。应用自动成为新空间的超级管理员。

**入参**（JSON）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `corp_id` | 是 | 企业微信 corp_id |
| `corp_secret` | 是 | 应用 secret（需有微盘权限） |
| `space_name` | 是 | 空间标题 |
| `space_sub_type` | 否 | 0:普通空间（目前只支持 0，缺省 0） |
| `auth_info` | 否 | 空间其他成员数组，每项 `{ type(1个人/2部门), userid?, departmentid?, auth(1仅下载/4可预览/7管理员) }`；缺省由上游给默认权限。`auth:7` 最多 3 个、不支持部门 |

**出参**：`{ ok: true, spaceid: "<新空间spaceid>", detail: <上游回包> }`

```bash
curl -X POST https://relay.openclaw-for-business.com/api/v1/wxwork/drive/space-create \
  -H "Content-Type: application/json" -H "X-OFB-Key: $OFB_KEY" \
  -d '{"corp_id":"ww...","corp_secret":"...","space_name":"2026-07素材空间"}'
# → {"ok":true,"spaceid":"sp_xxx","detail":{"errcode":0,"errmsg":"ok","spaceid":"sp_xxx"}}
```

### 4.0.5 `POST /api/v1/wxwork/drive/space-setting` — 空间安全设置

对应企业微信 [97876 `wedrive/space_setting`](https://developer.work.weixin.qq.com/document/path/97876)。**关键用途**：应用建的空间默认「链接加入需审批」，邀请链接发出去同事也加不进来。调这个接口把 `share_url_no_approve` 打开，链接才能直接加入。

> ⚠️ **实测发现（2026-07-06）**：`share_url_no_approve` 只控制「链接加入是否免审批」，**不控制「邀请链接功能是否开启」**。应用建的空间默认「邀请链接功能关闭」，调 97876 无法打开它（试过 `enable_share_url` 等多个候选字段，上游静默忽略）。`space-share`（97877）在此状态下返回 `640028 space setting disable share url`。**要开启邀请链接功能，需在「企业微信管理后台 → 微盘 → 空间安全设置」手动开启**（属 admin 级，API 不暴露）。开启后 `space-share` 才会返回 `space_share_url`。

**入参**（JSON）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `corp_id` | 是 | 企业微信 corp_id |
| `corp_secret` | 是 | 应用 secret |
| `spaceid` | 是 | 空间 spaceid |
| `share_url_no_approve` | 否 | 链接加入空间免审批（true=开 / false=关），不填保持原状 |
| `share_url_no_approve_default_auth` | 否 | 邀请链接默认权限：1仅下载 / 2可编辑 / 4仅预览 / 5可上传下载 / 200自定义 |
| `enable_watermark` | 否 | 水印（仅专业版） |
| `enable_confidential_mode` | 否 | 保密模式 |
| `default_file_scope` | 否 | 文件默认可查看范围：1仅成员 / 2企业内 |
| `ban_share_external` | 否 | 禁止分享到企业外 |

**出参**：`{ ok: true, detail: { errcode:0, errmsg:"ok" } }`

```bash
curl -X POST https://relay.openclaw-for-business.com/api/v1/wxwork/drive/space-setting \
  -H "Content-Type: application/json" -H "X-OFB-Key: $OFB_KEY" \
  -d '{"corp_id":"ww...","corp_secret":"...","spaceid":"sp_xxx","share_url_no_approve":true,"share_url_no_approve_default_auth":5}'
```

### 4.0.6 `POST /api/v1/wxwork/drive/space-share` — 获取空间邀请链接

对应企业微信 [97877 `wedrive/space_share`](https://developer.work.weixin.qq.com/document/path/97877)。应用建的空间默认对普通用户不可见，逐个加成员又麻烦，用这个接口拿一个邀请链接发给同事即可加入。

**入参**（JSON）：`corp_id, corp_secret, spaceid`

**出参**：`{ ok: true, space_share_url: "<邀请链接>", detail: <上游回包> }`

```bash
curl -X POST https://relay.openclaw-for-business.com/api/v1/wxwork/drive/space-share \
  -H "Content-Type: application/json" -H "X-OFB-Key: $OFB_KEY" \
  -d '{"corp_id":"ww...","corp_secret":"...","spaceid":"sp_xxx"}'
# → {"ok":true,"space_share_url":"https://wedrive.work.weixin.qq.com/...","detail":{...}}
```

### 4.0.7 `POST /api/v1/wxwork/drive/file-share` — 获取文件分享链接（文件级）

对应企业微信 [97890 `wedrive/file_share`](https://developer.work.weixin.qq.com/document/path/97890)。**关键用途**：`space-share`（4.0.6）依赖空间「邀请链接功能」开启（admin 后台手动开，API 不暴露），未开启时返回 `640028`。`file-share` 是**文件级**分享，只要求微盘权限，不依赖空间邀请链接功能，**可绕过 640028**。发给同事的链接直接打开文件，不需要加入空间。

**入参**（JSON）：`corp_id, corp_secret, fileid`

**出参**：`{ ok: true, share_url: "<文件分享链接>", detail: <上游回包> }`

```bash
curl -X POST https://relay.openclaw-for-business.com/api/v1/wxwork/drive/file-share \
  -H "Content-Type: application/json" -H "X-OFB-Key: $OFB_KEY" \
  -d '{"corp_id":"ww...","corp_secret":"...","fileid":"fid_xxx"}'
# → {"ok":true,"share_url":"https://drive.weixin.qq.com/s?k=...","detail":{"errcode":0,"errmsg":"ok","share_url":"..."}}
```

> 实测（2026-07-06）：在 `space-share` 报 `640028` 的同一空间里，对空间内文件调 `file-share` 正常返回 `share_url`。**优先用 `file-share` 给同事发文件，`space-share` 仅在需让同事加入整个空间时才用（且需先在管理后台开邀请链接功能）**。

### 4.1 `POST /api/v1/wxwork/drive/create-folder` — 新建文件夹

对应企业微信 [97882 `wedrive/file_create`](https://developer.work.weixin.qq.com/document/path/97882)，relay 强制 `file_type=1`。

**入参**（JSON）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `corp_id` | 是 | 企业微信 corp_id |
| `corp_secret` | 是 | 应用 secret（建议用「通讯录同步」或自建应用 secret，需有微盘权限） |
| `spaceid` | 是 | 空间 spaceid |
| `fatherid` | 是 | 父目录 fileid；根目录填 `spaceid` |
| `file_name` | 是 | 文件夹名（≤255 字符，英文 1、汉字 2） |

**出参**：`{ ok: true, fileid: "<新文件夹fileid>", detail: <上游回包> }`

```bash
curl -X POST https://relay.openclaw-for-business.com/api/v1/wxwork/drive/create-folder \
  -H "Content-Type: application/json" -H "X-OFB-Key: $OFB_KEY" \
  -d '{"corp_id":"ww...","corp_secret":"...","spaceid":"sp1","fatherid":"sp1","file_name":"2026-07素材"}'
# → {"ok":true,"fileid":"fid_xxx","detail":{"errcode":0,"errmsg":"ok","fileid":"fid_xxx"}}
```

### 4.2 `POST /api/v1/wxwork/drive/upload-image` — 上传图片（≤10M）

对应 [97880 `wedrive/file_upload`](https://developer.work.weixin.qq.com/document/path/97880)。**client 仍用 multipart 上传到 relay**，relay 负责转成上游要求的 JSON + base64。

**入参**（multipart/form-data）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `corp_id` | 是 | 表单字段 |
| `corp_secret` | 是 | 表单字段 |
| `spaceid` | 是 | 空间 spaceid |
| `fatherid` | 是 | 目标文件夹 fileid（**必须是本应用创建的文件夹**） |
| `file_name` | 否 | 文件名；缺省用上传文件原名 |
| `file` | 是 | 图片文件（≤10M） |

**出参**：`{ ok: true, fileid: "<fileid>", detail: <上游回包> }`

> 超过 10M 返回 400 并提示走 `upload-video`（分块）。

### 4.3 `POST /api/v1/wxwork/drive/upload-video` — 上传视频 / 大文件（分块）

对应 [98004 `wedrive/file_upload_init/part/finish`](https://developer.work.weixin.qq.com/document/path/98004)，relay 服务端负责分块、SHA、三步流程。入参与 4.2 一致（multipart：`corp_id`+`corp_secret`+`spaceid`+`fatherid`+`file_name`?+`file`）。

**出参**：`{ ok: true, fileid, fast_forward: boolean }`（`fast_forward:true` 表示命中秒传）。

### 4.4 `POST /api/v1/wxwork/drive/list-files` — 获取文件列表

对应 [93657 `wedrive/file_list`](https://developer.work.weixin.qq.com/document/path/93657)。

**入参**（JSON）：`corp_id, corp_secret, spaceid, fatherid, sort_type, start, limit`

| 字段 | 必填 | 说明 |
|---|---|---|
| `sort_type` | 是 | 1:名字升 2:名字降 3:大小升 4:大小降 5:修改时间升 6:修改时间降 |
| `start` | 是 | 首次填 0，后续填上次返回的 `detail.next_start` |
| `limit` | 是 | 分批大小，≤1000 |

**出参**：`{ ok: true, detail: { has_more, next_start, file_list:{item:[...]} } }`。`item` 每项含 `fileid, file_name, file_type(1文件夹/2文件/3文档/4表格/5收集表), file_size, ctime, mtime, file_status, sha, md5, url?`。

### 4.5 `POST /api/v1/wxwork/drive/file-info` — 获取文件信息

对应 [97886 `wedrive/file_info`](https://developer.work.weixin.qq.com/document/path/97886)。入参：`corp_id, corp_secret, fileid`。出参：`{ ok, detail: { file_info: {...} } }`。

### 4.6 `POST /api/v1/wxwork/drive/rename` — 重命名

对应 [97883 `wedrive/file_rename`](https://developer.work.weixin.qq.com/document/path/97883)。入参：`corp_id, corp_secret, fileid, new_name`。出参：`{ ok, fileid, detail: { file: {...} } }`。

### 4.7 `POST /api/v1/wxwork/drive/move` — 移动

对应 [97884 `wedrive/file_move`](https://developer.work.weixin.qq.com/document/path/97884)。入参：`corp_id, corp_secret, fatherid(目标目录), fileid[](要移动的文件数组), replace?(bool, 重名是否覆盖)`。出参：`{ ok, detail: { file_list: {...} } }`。

### 4.8 `POST /api/v1/wxwork/drive/delete` — 删除（批量）

对应 [97885 `wedrive/file_delete`](https://developer.work.weixin.qq.com/document/path/97885)。入参：`corp_id, corp_secret, fileid[](字符串数组)`。出参：`{ ok, detail: { errcode:0, errmsg:"ok" } }`。

## 5. `upload-image` 行为变更（破坏性，client 必读）

旧实现把 multipart 直接透传给上游，且 `spaceid/fatherid` 误放在 query。上游 `file_upload` 实际要求 `application/json` + `file_base64_content`，所以**旧 `upload-image` 在生产从未真正成功过**（之前 client 没走到这步所以没暴露）。

新行为：

- client → relay 仍是 multipart（`file` + 表单字段），**client 调用方式不变**。
- relay → 上游改成 JSON + base64，并加 10M 校验。
- 多了一个可选表单字段 `file_name`（缺省用原文件名）。

> 如果 client 之前为了绕过这个 bug 做过特殊处理（比如自己 base64、自己拼 JSON），现在请改回普通的 multipart 上传。

## 6. client 测试清单

建议按此顺序在测试 corp（有微盘权限）上跑一遍：

- [ ] **建空间**：`space-create` 建一个 `test-space`，记下返回 `spaceid`。应用自动成为该空间超管。
- [ ] **安全设置**：`space-setting` 传 `spaceid` + `share_url_no_approve:true` + `share_url_no_approve_default_auth:5`，打开链接免审批。
- [ ] **取邀请链接**：`space-share` 传 `spaceid`，拿到 `space_share_url`，浏览器打开确认能直接加入空间（不走审批）。（若空间未在管理后台开邀请链接功能，此步会返回 `640028`，跳过即可——下一步用 `file-share` 验证文件级分享。）
- [ ] **取文件分享链接**：上传一个文件后 `file-share` 传其 `fileid`，拿到 `share_url`，浏览器打开确认能直接看文件（不依赖空间邀请链接功能，绕过 640028）。
- [ ] **建文件夹**：`create-folder` 在该空间根目录（`fatherid = spaceid`）建一个 `test-folder`，记下返回 `fileid`。
- [ ] **列根目录**：`list-files`（`fatherid = spaceid`）确认 `test-folder` 出现，`file_type=1`。
- [ ] **上传图片到该文件夹**：`upload-image` 用上一步的 `fileid` 作 `fatherid`，传一张 <10M 图片，记下返回 `fileid`。
- [ ] **列文件夹内容**：`list-files`（`fatherid = 文件夹fileid`）确认图片在，`file_type=2`。
- [ ] **取文件信息**：`file-info` 传图片 `fileid`，确认 `file_info.file_name` 等。
- [ ] **重命名**：`rename` 把图片改成 `renamed.png`，再 `file-info` 确认。
- [ ] **再建一个文件夹 + 移动**：`create-folder` 建 `test-folder-2`，`move` 把图片移过去，`list-files` 确认。
- [ ] **删除**：`delete` 传 `[图片fileid, test-folder-2的fileid]`，再 `list-files` 确认都没了。
- [ ] **大文件分块**：`upload-video` 传一个 >10M 视频，确认 `fast_forward` 字段返回。
- [ ] **错误路径**：缺 `corp_secret` → 400 `MISSING_CORP_CREDENTIALS`；缺 `file_name` → 400 `MISSING_FIELD`；错 `corp_secret` → 502 `GETTOKEN_FAILED`；无 `X-OFB-Key` → 401。

## 7. 未覆盖（按需再加）

本次做了 `space-create`（建空间）+ `space-setting`（安全设置/链接免审批）+ `space-share`（空间邀请链接）+ `file-share`（文件级分享链接，绕过 640028）但没做其余空间管理（重命名/解散空间、成员/部门增删、权限）和回调通知（容量不足 / 空间变更 / 文件变更）——属于 admin 级，跟「建空间 → 建文件夹 → 上传 → 发文件链接」链路无关。client 用到再提，relay 侧加一条 `driveJsonProxy` 透传路由即可，机械活。

## 8. 变更点速查（给 client 做 diff）

- 新增 10 路由：`space-create` / `space-setting` / `space-share` / `file-share` / `create-folder` / `list-files` / `file-info` / `rename` / `move` / `delete`（都在 `/api/v1/wxwork/drive/` 下，JSON body）。
- `upload-image`：client 调用方式不变（multipart），但行为修了；新增可选 `file_name` 字段。
- `upload-video`：未改动。
- 鉴权 / 凭据约定：未改动（仍 `X-OFB-Key` + body 透传 `corp_id`/`corp_secret`）。
