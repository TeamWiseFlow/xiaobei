---
name: wxwork-drive
description: Manage spaces, folders and files in WeChat Work WeDrive (企业微信微盘) via
  wiseflow-relay — create space, create folder, upload image/video, list, info, rename,
  move, delete, and share files via file-level share link. Standard flow
  建空间 → 传文件 → file-share 发分享链接给同事. Credentials (corp_id + corp_secret)
  read from daemon.env and passed per-request; relay is stateless. Space/folder IDs
  cached locally in spaces.json.
metadata:
  openclaw:
    emoji: 💾
    requires:
      bins:
      - python3
      - curl
---

# WeChat Work WeDrive（企业微信微盘空间 + 文件管理）

经 relay 透传凭据，对微盘做完整管理：**建空间 → 建文件夹 → 上传 → 取文件分享链接（`file-share`）发给同事** 是主链路；另有列目录 / 取信息 / 重命名 / 移动 / 删除 / 空间安全设置 / 空间邀请链接等辅助接口。

> ⚠️ **分享标准用法 = `file-share`（文件级），不是 `space-share`（空间级）**。应用建的空间默认「邀请链接功能关闭」且 API 打不开（只能管理后台手动开），`space-share` 在未开启时报 `640028`。`file-share` 只要微盘权限就能用，发给同事直接看文件、无需加入空间。**默认走 `file-share`**，别白白去试 `space-share`。详见下文「典型流程」与「特殊用途接口」。

---

## 关键约束：往哪传文件

企业微信微盘的权限规则：**应用只能往「自己创建的文件夹」或「空间根目录」里传文件**，不能往他人/其他应用建的文件夹传。本应用 `space-create` 建空间后自动成为该空间超级管理员，所以根目录可传；但生产建议先 `mkdir` 建子文件夹再往里传，便于整理。整个文件夹/文件生命周期由本技能自行管理（relay 不替你记 spaceid/fileid）。

---

## 凭据与存储位置

- **企业微信凭据** `WXWORK_CORP_ID` + `WXWORK_CORP_SECRET` 存放在 `daemon.env`（实例级，朋友圈 + 微盘共用）。
- **relay 身份** `OFB_KEY` + `RELAY_BASE_URL` 同样来自 `daemon.env`（entrypoint 注入）。
- **空间/文件夹 ID 缓存** `spaces.json` 存放在本技能目录下（已 gitignore，实例级，非密）：
  ```
  skills/wxwork-drive/spaces.json
  ```
  结构见 `spaces.example.json`：`{default_space, spaces:[{alias, spaceid, default_folderid?}]}`。`<space>` 参数统一接受 alias 或裸 spaceid。

### 凭据缺失时 Agent 行为

1. 若 `WXWORK_CORP_ID` / `WXWORK_CORP_SECRET` 未配置：**先读同目录 `REFERENCE.md`**，按其中步骤指导用户获取企业 ID + 应用 Secret（含 relay 可信 IP `123.60.18.144` 的配置、微盘权限开通）。
2. 收到值后，**交给 IT engineer** 写入 `daemon.env` 并重启实例（或按 `REFERENCE.md` 用户自助 + 重启）。
3. 若 `OFB_KEY` 未配置：同样让 IT engineer 在 `daemon.env` 配置后重启。

---

## 命令

通过 PATH 调用 wrapper，无需拼接脚本路径。

```bash
wxwork-drive <subcommand> [args...]
```

### 空间管理（写 spaces.json）

| 子命令 | 用途 |
|--------|------|
| `space-create <alias> <space_name> [--default]` | 经 relay 创建空间并登记；`--default` 设为默认 |
| `space-add <alias> <spaceid> [--default]` | 登记一个已有空间 |
| `space-ls` | 列已登记空间 |
| `space-default <alias>` | 设默认空间 |
| `space-setting <space> [flags]` | 空间安全设置（开链接免审批等，见下） |
| `space-share <space>` | 取空间邀请链接（应用建的空间默认对普通用户不可见，把链接发给同事即可加入）。**注意：邀请链接功能本身需先在「企业微信管理后台 → 微盘 → 空间安全设置」开启，API（97876）只控制「链接加入是否免审批」，不控制「链接功能是否开启」；未开启时 `space-share` 报 `640028 space setting disable share url`** |
| `file-share <fileid>` | 取**文件级**分享链接（发给同事直接看文件，不需加入空间）。不依赖空间邀请链接功能，绕过 640028。**优先用这个** |
| `folder-default <space_alias> <folderid>` | 设某空间的默认上传文件夹 |

#### `space-setting` flags

| flag | 上游字段 | 说明 |
|------|---------|------|
| `--share-url-no-approve` | `share_url_no_approve=true` | 链接加入空间免审批（**邀请同事前通常要先开这个**，否则链接发出去对方加入会被审批卡住） |
| `--share-url-default-auth N` | `share_url_no_approve_default_auth` | 邀请链接默认权限：1仅下载 / 2可编辑 / 4仅预览 / 5可上传下载 / 200自定义 |
| `--enable-watermark` | `enable_watermark=true` | 水印（仅专业版） |
| `--enable-confidential` | `enable_confidential_mode=true` | 保密模式 |
| `--default-file-scope N` | `default_file_scope` | 文件默认可查看范围：1仅成员 / 2企业内 |
| `--ban-share-external` | `ban_share_external=true` | 禁止分享到企业外 |

只把显式传入的字段带上游，未传的字段保持原状。

### 文件管理（`<space>` 接受 alias 或裸 spaceid）

| 子命令 | 用途 | 关键参数 |
|--------|------|----------|
| `mkdir <space> <file_name> [--fatherid F] [--default-folder]` | 新建文件夹 | `--fatherid` 缺省=空间根；`--default-folder` 把新文件夹记为默认上传文件夹 |
| `upload <file> <space> [--fatherid F] [--name NAME]` | 上传图片/视频 | `--fatherid` 缺省=该空间 `default_folderid` |
| `ls <space> [--fatherid F] [sort_type] [limit] [start]` | 列目录 | `--fatherid` 缺省=空间根；sort_type 1名升2名降3大小升4大小降5mtime升6mtime降 |
| `info <fileid>` | 取文件/文件夹信息 | |
| `rename <fileid> <new_name>` | 重命名 | |
| `move <fatherid> <fileid> [fileid...] [--replace]` | 移动到目标目录 | `--replace` 重名覆盖 |
| `delete <fileid> [fileid...]` | 批量删除 | |

脚本自动：
- 从 `daemon.env` 读 corp 凭据 + relay 身份
- `upload` 按类型/大小自动选 `upload-image`（≤10M 图片）或 `upload-video`（视频或 >10M，relay 侧分块）
- 每条命令输出一行 JSON 结果（供 Agent 解析链式调用）+ 人类可读摘要

### 典型流程：从零上传到自建空间，再发文件分享链接

主链路 = **建空间 → 建文件夹 → 上传 → 取文件分享链接发给同事**。同事拿到链接直接看文件，不需加入空间。

```bash
# 1. 建空间（首次）并设为默认
wxwork-drive space-create main wiseflow素材 --default

# 2. 在空间根建文件夹，并记为默认上传文件夹
wxwork-drive mkdir main 2026-07 --default-folder

# 3. 上传（自动用 default_folderid）
wxwork-drive upload ./cover.jpg main

# 4. 取文件分享链接，发给同事即可直接看文件（不依赖空间邀请链接功能）
wxwork-drive file-share <上一步 upload 返回的 fileid>
# → share_url，发给同事
```

> **为什么主链路用 `file-share` 而不是 `space-share`**：应用建的空间默认「邀请链接功能关闭」，且这个开关 API（97876）打不开，只能去企业微信管理后台手动开。`space-share` 在未开启时报 `640028`。`file-share` 是文件级分享，只要微盘权限就能用，绕过这个限制。所以默认走 `file-share`；只有要让同事加入整个空间协作时才用 `space-share`（且需先在管理后台开邀请链接功能）。

### 特殊用途接口（主链路用不到，按需调）

| 子命令 | 何时用 |
|--------|--------|
| `space-setting` | 要开链接免审批 / 水印 / 保密模式 / 禁止外分享等空间级安全设置时。注意：**它打不开「邀请链接功能」本身**（那个只能管理后台开），只控制「链接加入是否免审批」等子项 |
| `space-share` | 要让同事**加入整个空间**协作（不只是看一个文件）时。前提：已在管理后台开邀请链接功能，否则报 `640028` |
| `ls` / `info` / `rename` / `move` / `delete` | 后续整理：列目录确认、改名、移动、删除 |

---

## 返回值

每条命令最后一行 JSON 即 relay 返回的业务包络（`{ ok, ...字段, detail }`）。常用字段：

- `space-create`：`spaceid`
- `mkdir` / `upload` / `rename`：`fileid`
- `upload`：`fast_forward: true` 表示命中秒传
- `file-share`：`share_url`（文件级分享链接，发给同事直接看文件）
- `space-share`：`space_share_url`（空间邀请链接，需管理后台开邀请链接功能）
- `ls`：`detail.file_list.item[]`，每项含 `fileid / file_name / file_type(1文件夹/2文件/3文档/4表格/5收集表) / file_size / mtime`
- `info`：`detail.file_info`
- `move` / `delete`：`detail`（上游回包）

`fileid` / `spaceid` 永久有效（未删除前），可长期引用。

---

## Agent 行为约束

1. **上传目标要合法**：`fatherid` 必须是空间根（spaceid）或本应用 `mkdir` 拿到的 fileid（或该空间已设 `default_folderid`）。往他人/其他应用建的文件夹传会 `no permission` 失败。
2. **链式调用时从上一条命令的 JSON 行提取 fileid**，不要凭空捏造。
3. **优先用 spaces.json 的 alias / default**，避免每次让用户重复传 spaceid。
4. 视频上传可能耗时较长（100MB 约 1–3 分钟），**等待脚本完整返回后**再进行下一步，期间告知用户"正在上传..."。
5. **禁止**手动拼接 curl 命令替代脚本。

---

## Error Handling

| 错误 | 原因 | 处理 |
|------|------|------|
| `WXWORK_CORP_ID / WXWORK_CORP_SECRET 未配置` | daemon.env 缺凭据 | 按 `REFERENCE.md` 引导用户获取，交 IT engineer 写 daemon.env + 重启 |
| `OFB_KEY 未配置` | daemon.env 缺 OFB_KEY | 让 IT engineer 配置后重启 |
| `MISSING_CORP_CREDENTIALS`（relay 400） | 请求体缺 corp_id/corp_secret | 检查 daemon.env 是否生效（需重启） |
| `MISSING_FIELD`（relay 400） | 缺必填字段（如 file_name） | 补全参数 |
| `GETTOKEN_FAILED`（relay 502） | corp_secret 错或 corp_id 不存在 | 核对凭据；按 `REFERENCE.md` 重新获取 |
| 上游 `errcode != 0`（relay 400） | 企业微信拒绝，`detail` 里是原始 errcode/errmsg | 看 errmsg：`no privilege`→按 REFERENCE.md 开通微盘权限；`no permission`→fatherid 是他人建的文件夹，改用空间根或自己 mkdir 出来的 fileid |

---

## Notes

- relay 在转发给企业微信前会剥离 `corp_id` / `corp_secret`，不下发
- relay 按 `(corp_id, corp_secret)` 缓存 access_token，client 无需自己管 token
- `spaces.json` 只存 ID（非密），gitignore 是因为实例级、避免跨部署污染
- 接口契约详见 `docs/WXWORK-DRIVE-API.md`，上游 API 详见[企业微信微盘文档](https://developer.work.weixin.qq.com/document/path/93654)
- 空间成员/部门增删、权限、空间重命名/解散属 admin 级，本技能不覆盖；用到再让 relay 加透传路由
