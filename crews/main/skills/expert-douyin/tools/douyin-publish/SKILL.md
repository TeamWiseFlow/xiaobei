---
name: douyin-publish
description: 通过统一 API 会话发布抖音视频和原声图文，支持扫码登录、AI 声明、双封面、验证续接与发布结果核查。
---

# 抖音发布

创作者与采集、互动共用 `douyin-login` 管理的 API 会话，不启动 Camoufox，不读取浏览器 profile，不使用 login-manager。主站与创作者分别维护 token 和证书，工具自动刷新；不要拼接其他账号的 Cookie、UA 或安全材料。

## 登录与检查

先执行 `douyin-publish check` 验证本人 UID、创作者会话和作品读取。已有有效 API 登录无需再次扫码。只有明确未登录或用户要求重新登录时执行 `douyin-publish login`，将返回的二维码交用户扫码，再执行 `douyin-login poll --timeout 120` 完成身份确认。登录 MFA 按 `douyin-login` 手册处理。

检查失败区分认证、风控、限频与计算错误；不因创作者接口失败就重新初始化采集账号。未结案提交必须保留，恢复原账号后只核查，不重发。

## 视频与图文

核对目标账号、媒体、标题、正文和声明。不带 `--confirm` 只做本地预览，无网络副作用；已有发布授权后在原命令加 `--confirm`。

```bash
douyin-publish video run --video /绝对路径/video.mp4 --title "标题" --caption @/绝对路径/body.txt --cover-vertical /绝对路径/vertical.jpg --cover-horizontal /绝对路径/horizontal.jpg
douyin-publish note run --images /绝对路径/1.png /绝对路径/2.png --title "标题" --caption @/绝对路径/body.txt --original-sound
```

正文文件使用 UTF-8 和真实换行，文件只放已确认的纯正文与话题，不含标题或交付说明；不拼接 shell 命令读取正文。短正文仍可直接传入，以 `@` 开头的参数按文件路径处理。

视频需要 3:4 竖封面和 4:3 横封面，工具等比补底并写入最终请求；默认 AI 声明，视频不接受 `--declaration none`。图文默认 AI 声明，非 AI 内容可传 `--declaration none`；仅支持明确指定 `--original-sound` 的原声图文，不承诺 HTTP 配乐选择。浏览器填表、草稿和配乐命令不能替代 HTTP 入口。

已授权上传、暂不提交时，在 `run --confirm` 后加 `--prepare-only`；核对 `state: prepared` 后用相同类型的 `publish --confirm` 提交原请求。可见性用 `--visibility public|private|friends`，默认 public。

具体收据、二次验证和结果核查先读 [HTTP 发布与验证续接](references/http.md)。视频补充见 [视频说明](references/video.md)，图文补充见 [图文说明](references/note.md)。

## 结果核查与记录

`status` 只读本地收据；`resume` 和 `get-link` 核查本次任务。提交前保存意图；网络异常、空响应或验证要求发生后，任何续接都不会自动再 POST。返回 `submission_attempted: true` 且无确认 ID 时报告“已尝试提交，正在核实”，不能说未发布或重发。验证完成也不等于发布成功。

只有真实作品 ID 与完整链接才能调用 `published-track record` 入库并去重。平台接受、公开、可播放、审核通过分别判断，不用全局最新旧作品替代本次作品。用户已确认发布成功时据此结案，不要求重复确认；未核实的公开和播放状态保持未知。

旧浏览器收据保留原文件，不自动迁入 API 任务，不清除旧 profile。遗留未结案任务会阻止新的提交；历史状态核查与用户确认结案由维护者按原任务处理，不能借换登录方式重发。

发布与取数串行执行。单账号每 24h 视频和图文合计不超过 5 条；风控后至少 30 分钟不重试。
