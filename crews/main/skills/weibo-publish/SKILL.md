---
name: weibo-publish
description: 微博内容发布：脚本预览、媒体上传、提交结果保存和 published-track 入库。
metadata:
  openclaw:
    emoji: 📤
    requires:
      bins:
        - node
---


# 微博发布

登录使用 `weibo-hunter login/export`，执行前检查 `weibo-publish check`。

`weibo-publish methods` 返回支持参数及取值。

```bash
weibo-publish publish --text "正文" --source-folder /绝对路径/weibo/outputs/作品 --account default
weibo-publish publish --text "正文" --source-folder /绝对路径/weibo/outputs/作品 --account default --confirm
```

默认只预览，不访问平台。`--text @/绝对路径/content.md` 读取正文文件；媒体用真实本地文件。`--record-title` 可指定记录标题。文字、最多 15 张图片或视频；图像与视频互斥。支持 --visibility public/private/friends/fans、--topic 和 --poi-name。没有自动删除接口。文字、图文与短视频发布已有实号成功记录；更大文件的上传、其他参数组合与审核结果仍须分别核验。

视频发布先上传整份文件、确认上传与等待转码，再提交微博。上传请求默认最多等待 300 秒；预览的 `video_transport` 显示上传与进程总超时。慢速网络可按本次上传需要设置 `PLATFORM_API_WEIBO_VIDEO_UPLOAD_TIMEOUT_SECONDS`，只接受 30–900 的整数秒数；进程总超时为上传超时加 420 秒，默认 720 秒。确认发布时沿用预览的设置；调用工具的执行超时应大于进程总超时，并为前置校验和保存收据留余量。工具返回运行中时继续等待同一进程，不另起发布。

```bash
PLATFORM_API_WEIBO_VIDEO_UPLOAD_TIMEOUT_SECONDS=600 weibo-publish publish --text @/绝对路径/content.md --video /绝对路径/video.mp4 --source-folder /绝对路径/weibo/outputs/作品 --account default
```

核对文本、媒体、账号、可见范围与声明后，已有发布授权时加 --confirm。需要平台 AI 声明而接口没有声明字段时停止，交用户在原平台完成；不要将简介里的“AI”字样当作平台声明。不要填不存在的参数或模拟上传成功。

脚本串行发布并保存 `publish-result.weibo.json`，取得完整微博 ID 后生成规范链接并自动调用 published-track record，关联作品目录的 dna-meta.json 和账号 alias。提交明确成功但未返回微博 ID 时，先保存 accepted 收据，再最多查询 7 次本人作品首页（每次最多 20 条、间隔 5 秒），用本次上传的媒体 ID、作者与提交时间精确匹配视频；不按最新一条、标题或正文猜作品。

`published:true, recorded:false` 表示作品已识别、记录失败，重跑同一目录只补入库。`accepted:true, resolution_pending:true` 表示平台已接受提交，但作品 ID 尚未确认；保留 accepted 收据，稍后重跑同一目录只做结果查询，不再发布。调用工具的执行超时还应为这些查询留余量。已有 submitting/unknown 结果文件时禁止重发，先检查本人作品或原平台并由用户核实结果；不要删除收据换目录重发。下一条独立作品使用新的作品目录。

提交结果与实际可见、审核通过分开记录。返回失败、风控或超时后停止，不换通道重发。发布调用和结果文件不负责平台指标采集。

视频失败先读取返回值及收据的 `diagnostic.detail.request`：`video_upload` 的 NETWORK/timeout 表示上传请求超时；`video_transcode` 表示等待转码阶段；`video_submit` 表示最终提交阶段。诊断仅返回超时秒数、HTTP 状态和 CSRF 头是否存在，不输出 Cookie 或 Token。不要仅凭视频体积将超时判成平台大小限制，也不要把 `invalid csrf token` 判为整份登录态过期。

视频提交的 CSRF 头从本次实际请求 Cookie 中取 `XSRF-TOKEN`，包括本次流程响应的 Cookie 更新。缺少 Token 时脚本停止提交：先用 `weibo-publish check` 在线校验 API 会话，再用 `weibo-hunter login-status` 检查专属 `weibo` 窗口；需要重新 export 时遵循 hunter 登录指引，不从旧 profile 单独补 Token。仍被拒时保留收据与诊断交研发核查，不自动重登或删除 unknown 收据再提交。
