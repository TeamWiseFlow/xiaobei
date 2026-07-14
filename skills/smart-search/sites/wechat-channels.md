# 微信视频号 (WeChat Channels)

> last_verified: 2026-06-15 | 来源：OpenCLI clis/wechat-channels/publish.js + sitemaps

## 概览

- 域名：`channels.weixin.qq.com`
- 登录要求：**所有操作需登录**（微信扫码）
- Auth 策略：Cookie Warmup + 扫码登录

## 搜索

微信视频号**没有独立的搜索 URL**，搜索入口在微信客户端内。Web 端只能访问创作者中心。

### 可访问的 Web 内容

- 创作者中心：`https://channels.weixin.qq.com/platform/home`
- 视频管理：`https://channels.weixin.qq.com/platform/post/list`

### 替代搜索方式

1. **Bing 搜视频号内容**：`site:channels.weixin.qq.com {keyword}`
2. **微信内搜索**：需在微信客户端操作，Web 无法替代

## Pitfalls

### pitfall: wujie_shadow_dom

- **触发**：访问创作者中心页面
- **症状**：所有表单元素在 `<wujie-app>::shadow-root` 内，常规 DOM 选择器找不到
- **workaround**：`camoufox-cli snapshot` 默认穿透 shadow DOM 拿 ref，后续 `click` / `type` / `upload` 按 ref 操作即可。fallback 才需要 `eval` 里手写 `document.querySelector('wujie-app').shadowRoot.querySelector(selector)`

### pitfall: login_via_qr_only

- **触发**：访问视频号页面未登录
- **症状**：跳转到扫码登录页，无用户名/密码选项
- **workaround**：等待用户在手机微信扫码确认，最长等 2 分钟

### pitfall: video_upload_in_shadow_dom

- **触发**：上传视频文件到发布页
- **症状**：`<input type="file">` 在 shadow DOM 内
- **workaround**：`camoufox-cli upload <ref> <video-path>`（fork 加的 upload 命令，底层 Playwright `setInputFiles`，穿透 shadow DOM）。snapshot 拿到上传 input 的 ref 后直接 upload

## Fallback

视频号搜索无法在 Web 端完成 → 用 Bing `site:channels.weixin.qq.com` 替代

## Re-entry

- 在创作者中心页面 → 继续操作
- 在扫码登录页 → 等待用户扫码后继续
