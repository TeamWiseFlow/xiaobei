---
name: weibo-publish
description: 通过 forked camoufox-cli 持久化 session weibo 在微博发布图文/视频内容。微博 API 对个人开发者不友好，浏览器方案更实用。
metadata:
  openclaw:
    emoji: 📢
---

# 微博发布

通过 **camoufox-cli** 持久化 session `weibo`（一个且只有一个持久化 session，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在微博上发布内容（文字、图片、视频）。微博 API 对个人开发者申请门槛高，浏览器自动化是更实用的方案。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 何时无头 / 频率限制 / 错误处理约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义调用即可。

---

## 前置条件

1. login-manager 已有 `weibo` cookie + UA（中央存储 `~/.openclaw/logins/weibo.json` + `~/.openclaw/logins/weibo.ua.json`）
2. 首次使用 / cookie 失效需走 login-manager **有头手动**登录流（原则 3：weibo 有头登录）：
   - `camoufox-cli --session weibo --persistent --headed --json open "https://weibo.com"`
   - 告知用户「**微博** 浏览器已打开，请在窗口里手动登录，完成后告诉我」
   - 登录就位后**同时导出 cookie + UA**：
     - `camoufox-cli --session weibo --persistent --json cookies export ~/.openclaw/logins/weibo.json`
     - `camoufox-cli --session weibo --persistent --json identity export ~/.openclaw/logins/weibo.ua.json`
   - 关 session：`camoufox-cli --session weibo --json close`

> **同时导入 cookie 和 UA**（原则 4，spec §4.2）：微博设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配。本 skill 走持久化 session `weibo`（登录态 + 指纹冻结在 session profile 里），中央存储的 cookie/UA 仅用于探活与备份。

> weibo 不在 login-manager 支持的 6 平台之列（spec §4），登录态管理**不走 login-manager SKILL.md**——本 skill 自管持久化 session `weibo`，cookie/UA 导出/导入由 forked cli 的 `cookies export` / `identity export` / `cookies import` 命令完成。

---

## 发布文字微博

```
1. 启持久化 session + 打开微博首页：
   camoufox-cli --session weibo --persistent --headless --json open "https://weibo.com"
2. sleep 3 加载，snapshot 拿到输入框 ref
   - 输入框选择器：textarea.W_input 或 [node-type="textEl"] 或 textarea[placeholder*="有什么新鲜事"]
   - 如果找不到，open "https://weibo.com" 刷新后重试
3. click <ref> 聚焦输入框
4. camoufox-cli --session weibo --persistent --json type <ref> "微博内容"
   - 最长 2000 字符
5. snapshot 找发布按钮 ref：a[node-type="submit"] 或 button[action-type="post"] 或文本为"发布"的按钮
6. camoufox-cli --session weibo --persistent --json click <发布按钮-ref>
7. sleep 3，snapshot 确认发布成功（输入框清空或出现"发布成功"提示）
```

---

## 发布图文微博

```
1. 启 session + 打开首页（同文字微博步骤 1-2）
2. snapshot 拿到图片上传按钮 ref：a[node-type="uploadImg"] 或 .W_icon_pic 图标
3. camoufox-cli --session weibo --persistent --json upload <图片-input-ref> <image.jpg> [更多图片...]
   - forked cli upload 命令底层走 Playwright setInputFiles，无需 CDP setFileInput hack
   - 最多 9 张图片，单张不超过 5MB
4. sleep 等待上传完成（snapshot 看缩略图出现在编辑区）
5. 输入文字内容（同文字微博步骤 3-4）
6. 发布（同文字微博步骤 5-7）
```

---

## 发布视频微博

```
1. 启 session + 打开首页（同文字微博步骤 1-2）
2. snapshot 拿到视频上传入口 ref：a[node-type="uploadVideo"]
   或 open "https://weibo.com/p/103495:home"（视频发布页）
3. camoufox-cli --session weibo --persistent --json upload <视频-input-ref> <video.mp4>
   - 视频限制：mp4 格式，最长 15 分钟，不超过 2GB
4. sleep 等待上传完成（snapshot 看进度条到 100%）
5. 填写描述文字（type 命令）
6. 发布（click 发布按钮）
```

---

## 必做约束

- **不主动 close 持久化 session `weibo`**——登录态 + 指纹冻结留着下次用。只在 session 卡死时 `camoufox-cli --session weibo --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session weibo 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。
- 每次发布间隔 60 秒以上，避免触发反垃圾。

---

## Pitfalls

### pitfall: css_module_hash_drift

- **触发**：用 CSS module hash 选择器（如 `.publishBtn_1a2b3c`）
- **症状**：下次部署后选择器失效
- **workaround**：用 `node-type` 属性或 placeholder 文本定位，不用 hash class

### pitfall: input_box_collapsed

- **触发**：微博首页输入框默认折叠
- **症状**：输入框高度很小，无法直接输入
- **workaround**：先 `click` 输入框使其展开，sleep 1 后再 `type`

### pitfall: anti_spam_on_rapid_post

- **触发**：短时间内连续发布多条微博
- **症状**：出现验证码或"操作过于频繁"
- **workaround**：每次发布间隔 60 秒以上

### pitfall: weibo_url_shortener

- **触发**：微博内容中包含 URL
- **症状**：URL 被自动缩短为 t.cn 格式
- **workaround**：这是正常行为，不影响发布

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 未登录 / 登录墙 | 走前置条件的有头手动登录流，重试一次 |
| 输入框找不到 | 刷新页面后重试，或用 placeholder 文本定位 |
| 图片上传失败 | 检查文件大小（<5MB），重试一次 |
| 视频上传超时 | 检查文件大小和网络，等待更长时间 |
| 验证码 / 频率限制 | 等待 60 秒后重试 |
| session 正忙（fail-first） | 等当前操作完成再重试，不要盲试 |

## 发布后

**必须**调用 `published-track` 技能记录本次发布。
