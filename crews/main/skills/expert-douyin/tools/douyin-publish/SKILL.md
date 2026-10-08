---
name: douyin-publish
description: 使用 Camoufox 持久化创作者会话登录并发布抖音视频或图文；统一入口提供本地预览。
---

# 抖音发布

发布使用 Camoufox 持久化 session `douyin`，登录态保存在 profile。本人作品取数由 douyin-engagement 通过 HTTP 完成，仅在进程内临时读取同一 profile 的 cookie/UA。不要调用 login-manager，不手工导出或导入 cookie，不使用 hunter 的 API 会话代替发布会话。

## 登录与检查

```bash
douyin-publish login
douyin-publish check
```

`login` 打开有头创作者中心，请用户完成扫码或页面验证；返回 `awaiting_user_login` 不代表已经登录。用户完成后用 `check` 验证创作者接口，检查会关闭浏览器进程并保留 profile。未登录返回 exit 2；验证码、风控和接口异常停止处理，不无限重试。

## 视频与图文

先展示目标账号、文件、标题和正文，执行不带 `--confirm` 的命令生成本地预览；用户已授权后在同一命令加 `--confirm`。

```bash
douyin-publish video --video /绝对路径/video.mp4 --title "标题" --caption "简介 #话题"
douyin-publish note --images /绝对路径/1.png /绝对路径/2.png --title "标题" --caption "正文 #话题" --original-sound
```

视频入口保留浏览器 AIGC 声明流程，不支持 `--declaration none`。图文默认声明 AI，可按实际来源传 `--declaration none`；原声图文必须明确传 `--original-sound`。图文要选配乐或分步检查时，读同包 `douyin-note-publish` 工具说明；视频分步操作读 `douyin-video-publish`。

只在返回确认的完整作品 ID 与公开链接后入库。exit 3、超时或取链失败时，到作品管理页核实；视频用 `douyin-video-publish get-link --session douyin`，图文用 `douyin-note-publish get-note-link --title "完整标题"`。禁止自动重发。已停用 API 发布及其 job-file/status/verify 子命令，不用它们核查浏览器任务。

发布和取数共用排他锁，串行执行。单账号每 24h 视频和图文合计 ≤5 条；风控后至少 30 分钟不重试。
