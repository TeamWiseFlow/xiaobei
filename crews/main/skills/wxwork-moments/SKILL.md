---
name: wxwork-moments
description: Publish content (text + images/video/link) to WeChat Work (企业微信) customer
  moments via wiseflow-relay. Credentials (corp_id + corp_secret) read from daemon.env
  and passed per-request; relay is stateless.
metadata:
  openclaw:
    emoji: 📱
    requires:
      bins:
      - python3
---

# WeChat Work Moments Publisher（企业微信朋友圈发布）

经 relay 透传凭据发布企业微信客户朋友圈。

---

## 凭据与存储位置

- **企业微信凭据** `WXWORK_CORP_ID` + `WXWORK_CORP_SECRET` 存放在 `daemon.env`（实例级，朋友圈 + 微盘共用）。
- **relay 身份** `OFB_KEY` + `RELAY_BASE_URL` 同样来自 `daemon.env`（entrypoint 注入）。

### 凭据缺失时 Agent 行为

1. 若 `WXWORK_CORP_ID` / `WXWORK_CORP_SECRET` 未配置：**先读同目录 `REFERENCE.md`**，按其中的步骤指导用户获取企业 ID + 应用 Secret（含 relay 可信 IP `123.60.18.144` 的配置、微盘 / 客户联系权限开通）。
2. 收到值后，**交给 IT engineer** 写入 `daemon.env` 并重启实例（或按 `REFERENCE.md` 用户自助 + 重启）。
3. 若 `OFB_KEY` 未配置：同样让 IT engineer 在 `daemon.env` 配置后重启。

---

## 发布命令

通过 PATH 调用 wrapper：`wxwork-moments "<正文>" [附件...]`，无需拼接脚本路径。

### 纯文字

```bash
wxwork-moments "正文内容"
```

### 图文（最多 9 张图）

```bash
wxwork-moments "正文内容" /path/to/img1.jpg /path/to/img2.png
```

### 视频（1 个，≤ 30 秒，≤ 10MB）

```bash
wxwork-moments "正文内容" /path/to/video.mp4
```

### 图文链接（必须传封面图）

> ⚠️ 链接模式**必须**附封面图，否则发布失败。

```bash
wxwork-moments "推荐阅读" --link https://example.com/article "文章标题" /path/to/cover.jpg
```

---

## Agent 行为约束

> 以下规则**严格执行**，不得跳过。

1. **等待脚本完整返回后**再进行下一步，脚本包含上传和发布两个网络请求，耗时可能超过 10 秒，期间告知用户"正在上传素材 / 正在发布……"，**禁止**在脚本结束前自行拼接其他 curl 命令。
2. 脚本已处理凭据读取、素材上传、发布等全部步骤，**无需**手动执行任何中间步骤。
3. 脚本输出最后一行若以 `✓` 开头表示成功；以 `✗` 开头表示失败，需将错误信息完整告知用户。
4. 正文中不要包含换行 "\n"，wxwork api 不能解析 "\n"。

---

## 附件限制速查

| 附件类型 | 限制 |
|---------|------|
| 图片（jpg/png/gif） | 最多 9 个 |
| 视频（mp4/mov）     | 最多 1 个，时长 ≤ 30 秒，大小 ≤ 10MB |
| 图文链接            | 最多 1 个，可附 1 张封面图 |
| 图片与视频/链接      | 不可同时存在 |

---

## Error Handling

| 错误信息 | 原因 | 处理 |
|---------|------|------|
| `WXWORK_CORP_ID / WXWORK_CORP_SECRET 未配置` | daemon.env 缺凭据 | 按 `REFERENCE.md` 引导用户获取，交 IT engineer 写 daemon.env + 重启 |
| `OFB_KEY 未配置` | daemon.env 缺 OFB_KEY | 让 IT engineer 配置后重启 |
| `MISSING_CORP_CREDENTIALS`（relay 400） | 请求体缺 corp_id/corp_secret | 检查 daemon.env 是否生效（需重启） |
| `GETTOKEN_FAILED`（relay 502） | corp_secret 错或 corp_id 不存在 | 核对凭据；按 `REFERENCE.md` 重新获取 |
| `no privilege` | 应用未开通客户联系权限 | 按 `REFERENCE.md` 第 3 步开通 |
| `图片最多 9 张` | 超出数量限制 | 减少传入文件数量 |

---

## Notes

- 朋友圈任务创建成功后，指定员工会在企业微信中收到一键发布提醒
- `moment_id` 可用于后续在企业微信管理后台（客户联系 → 客户朋友圈）查询发布状态
- 临时素材（media_id）有效期 **3 天**，脚本每次发布时重新上传，无需手动管理
- relay 在转发给企业微信前会剥离 `corp_id` / `corp_secret`，不下发

---

企业微信朋友圈分发无需执行 `published-track` 相关操作。
