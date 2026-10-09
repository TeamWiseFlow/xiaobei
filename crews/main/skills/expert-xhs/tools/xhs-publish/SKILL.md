---
name: xhs-publish
description: 通过 Creator 本地 HTTP 会话发布小红书图文和视频笔记，并管理 Creator 扫码登录。
---

# 小红书发布

本工具由 `expert-xhs` 的发布 Workflow 调用。客户端负责 Creator HTTP 请求、媒体上传和发布，签名由 OFB Relay 提供（需配置 `OFB_KEY`）；`xhs-engagement` 复用同一登录态。会话存于 `~/.openclaw/logins/xhs-creator-local.json`（0600），Cookie 和会话状态持久化。只要 Cookie 有效，后续命令直接复用，不必每次扫码。

## 登录流程

1. 发布前运行 `xhs-publish check`。退出码 0 表示有效；2 表示缺少会话或明确认证失效；1 表示接口或环境故障，先排查。
2. 仅在需要重新登录时运行 `xhs-publish login`。它启动后台扫码任务并返回 `qr_path`，默认图片在 `/tmp/qr-xhs.png`，权限 0600。若二维码尚未生成，按返回错误排查或稍后重试；不要并发启动多个登录。
3. 使用当前会话的图片发送工具，把 `qr_path` 指向的 PNG 作为图片发给用户，然后**停止并等待用户回复已扫码/已确认**。脚本只生成图片，不代发飞书或微信消息。不要仅发路径给远程用户，也不要把登录二维码发给其他人。
4. 用户确认后运行 `xhs-publish login-confirm`。退出码 0 且 `ok: true` 才算登录成功；`LOGIN_PENDING` 表示手机端确认还没完成，稍后再查；二维码过期或失败时重新运行 `login`，再发送新图片。登录成功后会话原子落盘；旧会话只有新登录验过时才替换。

二维码图片是短期临时文件，登录结束会删除。后台日志在 `~/.openclaw/logs/xhs-creator-login.log`；不向用户转发日志。`xhs-publish check` 使用签名 `user/info` 验证，不反复扫码排查非认证错误。

## 彻底清空本地账号与换号

用户要求彻底清空本地小红书账号时，先结束小红书业务请求和后台扫码任务，再删除创作者端 `~/.openclaw/logins/xhs-creator-local.json` 与采集端 `~/.openclaw/logins/xhs-pc-local.json`、对应登录状态及二维码、含凭据的备份；设置了 `XHS_CREATOR_SESSION_FILE` 或 `XHS_PC_SESSION_FILE` 时清理其实际路径，保留业务数据和其他平台会话。换号时先结束旧扫码任务，再按本节流程用目标账号重新登录；需要保留旧号时先将其会话以 0600 权限备份，不保留时先清空。创作者端与采集端独立登录，整体换号还须按 `xhs-hunter` 的登录流程切换采集端，确认两端均由目标账号扫码，并分别运行 `xhs-publish check` 和 `xhs-hunter check` 验证；只重登一端不会切换另一端。

## 发布

```bash
xhs-publish --mode image --title "标题" --body "正文 #话题" --images /绝对路径/1.png /绝对路径/2.png
xhs-publish --mode video --title "标题" --body "正文 #话题" --video /绝对路径/video.mp4 --cover /绝对路径/cover.jpg
# 笔记含 AI 合成内容时，在对应发布命令末尾加 --ai-declaration
```

标题 1–20 字，正文 1–1000 字；图文需 1–18 张图片，视频需 `--video`。`--topics` 可补充话题，合计最多 10 个；`--private` 设为仅自己可见。笔记含 AI 合成内容时加 `--ai-declaration`，发布请求会带上创作者端的“笔记含 AI 合成内容”声明；纯实拍内容不加。正文中的 `#话题` 自动整理为 Creator 可识别的内联话题格式。`--body` 传实际文字，多行最好传真实换行；脚本也会把字面量 `\n` 归一化。

发布前让用户确认标题、正文、图片顺序及可见性。提交成功必须同时有 `ok: true` 和 `note_id`，再记录返回的 `url`。`SUBMISSION_UNKNOWN` 或 `SUBMISSION_UNCONFIRMED` 时先到创作者后台核查，**不要自动重发**。接口明确拒绝时根据错误码处理。操作结果写入 `~/.openclaw/logs/xhs-creator-observe.jsonl`，不含正文或 Cookie。

发布 Workflow 负责判断内容是否需要 AI 声明，并在调用发布命令时传入 `--ai-declaration`。
