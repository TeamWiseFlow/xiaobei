---
name: wechat-channels-publish
description: 通过 forked camoufox-cli 挰久化 session wechat-channel 发布视频到微信视频号。处理 wujie shadow DOM（snapshot 穿透），支持视频上传、标题描述填写、即时发布。
metadata:
  openclaw:
    emoji: 📺
---

# 微信视频号发布

通过 **camoufox-cli** 持久化 session `wechat-channel`（有且只有一个，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在微信视频号创作者中心发布视频。视频号创作者中心使用 **wujie 微前端**，所有表单元素在 `<wujie-app>::shadow-root` 内——forked cli 的 `snapshot` 默认穿透 shadow DOM 拿 ref，后续 `click` / `type` / `upload` 按 ref 操作即可，无需 CDP hack。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 何时无头 / 频率限制 / 错误处理约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义调用即可。

---

## 前置条件

1. 持久化 session `wechat-channel` 已登录（登录态存 session profile 里）。本 skill 与 login-manager **完全无关**——自管探活 + 登录，**不导出 cookie/UA 落中央存储**。
2. 首次使用 / 登录态失效时，走**有头手动扫码**登录流（视频号登录页无法无头截 QR，必须弹出有头窗口让用户在浏览器里手动扫码）：
   - `camoufox-cli --session wechat-channel --persistent --headed --viewport 1920x1080 --json open "https://channels.weixin.qq.com/platform/home"`
   - `--viewport 1920x1080`：camoufox 默认按指纹给移动端窗口比例，二维码看不全；强制桌面 1920×1080
   - 告知用户「**微信视频号** 登录已失效，浏览器窗口已打开，请在窗口里用微信扫码确认登录，完成后回复"已扫码"」
   - **Stop and wait**，用户回复后 `snapshot` 验页面已跳走 / QR 消失
   - 登录后**close session**——登录态落磁盘 profile，不留进程占内存；本 skill 下次 `--session wechat-channel --persistent` 重起无头即恢复，用完再 close。

> **不导出 cookie/UA**——登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本 skill 不调用 `cookies export` / `identity export`。
>
> 登录走**有头**（`--headed --viewport 1920x1080`）；业务发布操作走默认无头（camoufox-cli 默认即 headless，无需额外 flag）。

---

## 发布流程

### Step 1: 导航到发布页

```
camoufox-cli --session wechat-channel --persistent --json open "https://channels.weixin.qq.com/platform/post/create"
```

等待 **5 秒**（wujie 需要额外时间初始化 shadow DOM）。

### Step 2: 检查登录态

`snapshot` 看页面 URL 是否含 `login` 或出现登录二维码——命中走前置条件的有头手动扫码登录流。

### Step 3: 上传视频

```
1. snapshot 拿到上传触发按钮 ref（shadow DOM 内的 span.add-icon 或 div.upload-content）
2. camoufox-cli --session wechat-channel --persistent --json click <上传触发-ref>
3. snapshot 拿到弹出的 <input type="file"> ref
4. camoufox-cli --session wechat-channel --persistent --json upload <input-ref> <video.mp4>
   - forked cli upload 命令底层走 Playwright setInputFiles，穿透 shadow DOM，无需 CDP setFileInput / base64 hack
```

**支持的视频格式**：`.mp4`、`.mov`、`.avi`、`.webm`

### Step 4: 等待上传+转码完成

每 3 秒 `snapshot` 检查一次页面状态：
- 上传中：shadow DOM 内存在 `[class*="uploading"]` 或 `[class*="progress"]`
- 转码中：`[class*="transcoding"]`
- 完成：出现 `<video>` 预览或 `[class*="preview-video"]` 或文本"上传成功"/"转码完成"
- 失败：`[class*="upload-fail"]` 或文本"上传失败"
- **最长等待 3 分钟**（大视频转码可能较慢）

### Step 5: 填写标题

```
1. snapshot 拿到标题输入框 ref：input[placeholder*="短标题"]（在 shadow DOM 内）
2. camoufox-cli --session wechat-channel --persistent --json type <标题-ref> "短标题"
   - 建议 6-16 字，最长约 30 字
```

### Step 6: 填写描述

```
1. snapshot 拿到描述输入框 ref：div[contenteditable][data-placeholder="添加描述"]
2. camoufox-cli --session wechat-channel --persistent --json click <描述-ref> 聚焦
3. camoufox-cli --session wechat-channel --persistent --json type <描述-ref> "描述内容 #话题1 #话题2"
   - 话题标签直接写在描述中
   - 最长约 300 字
```

### Step 7: 发布

> 视频号发布不必勾选"原创声明"，发布后用户会在手机端补充。

```
1. snapshot 拿到"发表"按钮 ref（文本为"发表"或"发布"，在 shadow DOM 内）
2. 确认按钮不是 disabled 状态（snapshot 看）
3. camoufox-cli --session wechat-channel --persistent --json click <发表-ref>
4. 若弹出"原创声明弹窗"，snapshot 拿"直接发表"按钮 ref → click
```

### Step 8: 确认发布成功

等待 4 秒后 `snapshot` 检查：
- 页面自动跳转到视频管理列表页
- 或 URL 变为 `https://channels.weixin.qq.com/platform/post/list`
- 刚发表的作品通常在第一个。但可能处于转码中——封面缩略图为灰色，转圈。每隔 5 秒 snapshot 看转码是否完成（封面缩略图出现），完成后才能取链接。

### Step 9: 获取已发布视频链接

发布成功后，在视频号管理后台的视频列表页获取视频公开链接：

```
1. snapshot 找到刚发布的视频（列表第一条，或按标题匹配）ref
2. snapshot 找该视频的"分享"按钮 ref → click
3. snapshot 在弹出的分享面板中找"复制视频链接"按钮 ref → click
4. snapshot eval 从剪贴板或弹窗读取链接：
   camoufox-cli --session wechat-channel --persistent --json eval "navigator.clipboard.readText()"
   链接格式通常为 https://weixin.qq.com/sph/xxxxxx（sph 即视频号拼音缩写）
```

> **注意**：如果刚发布的视频还在审核中，"分享"按钮可能不可用。此时可先完成发布记录（publish_url 留空），待审核通过后再补充链接。

---

## 保存草稿

在 Step 7 中 snapshot 找"存草稿"按钮 ref → click（而非"发表"）。

---

## 手动模式

如果需要人工检查表单后再发布：
1. 完成到 Step 6（所有字段已填写）
2. **不自动 click 发表**，告知用户在浏览器中手动检查并点击
3. 注意：不操作时标签页约 30 秒后可能被重置为空白页

---

## 必做约束

- **用完即 close 持久化 session `wechat-channel`**——登录态 + 指纹冻结在磁盘 profile，不留进程占内存；下次发布 `--session wechat-channel --persistent` 重起无头即恢复。只在 session 卡死时 `camoufox-cli --session wechat-channel --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session wechat-channel 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。

---

## Pitfalls

### pitfall: wujie_shadow_dom

- **触发**：访问创作者中心任何页面
- **症状**：常规 DOM 选择器找不到表单元素
- **workaround**：`camoufox-cli snapshot` 默认穿透 shadow DOM 拿 ref，后续 `click` / `type` / `upload` 按 ref 操作即可。fallback 才需要 `eval` 里手写 `document.querySelector('wujie-app').shadowRoot.querySelector(selector)`

### pitfall: video_transcode_timeout

- **触发**：大视频文件上传后转码
- **症状**：等待超过 3 分钟仍未完成
- **workaround**：增加等待时间，或检查视频格式是否兼容

### pitfall: login_qr_only

- **触发**：访问视频号页面未登录
- **症状**：跳转到扫码登录页，无用户名/密码选项
- **workaround**：走前置条件的有头手动扫码流程（`--headed --viewport 1920x1080`），等待用户在浏览器窗口里用手机微信扫码确认

### pitfall: form_reset_on_idle

- **触发**：填写完表单后长时间不操作
- **症状**：标签页被重置为空白页（约 30 秒空闲超时）
- **workaround**：填完表单后立即发布，或使用手动模式让用户快速操作

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 未登录 | 走前置条件的有头手动扫码登录流，重试一次 |
| 上传失败 | 检查视频格式（mp4/mov/avi/webm），重试一次 |
| 转码超时 | 增加超时时间，或告知用户稍后在创作者中心检查 |
| 发表按钮 disabled | 检查必填字段是否已填写（视频是否上传完成） |
| shadow DOM 元素找不到 | 等待更长时间让 wujie 初始化，或刷新页面 |
| session 正忙（fail-first） | 等当前操作完成再重试，不要盲试 |
