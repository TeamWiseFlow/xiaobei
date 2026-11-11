---
name: kuaishou-hunter
description: 快手内容搜索与采集：作品、账号、评论、媒体下载；支持范围以 methods 为准，互动写操作走 expert-bd。
metadata:
  openclaw:
    emoji: 🔎
    requires:
      bins:
        - node
---

签名由 Relay 计算，使用 `OFB_KEY` 与可选 `RELAY_BASE_URL`，平台请求和会话仍在客户端。Relay 失败或配额不足时停止，不回退本地签名；400002等验证码只报告 RISK_CONTROL，不自动求解或提交验证。短信登录使用用户提供的真实验证码。


# 快手内容采集

首次扫码登录：用原生 `exec` 运行 `kuaishou-hunter login`，设置 `background:true, timeoutSeconds:660`。保留 exec 返回的后台会话句柄，通过原生 `process poll/log` 查看二维码事件；不要追加 `&`、nohup 或创建脱离工具的后台进程。二维码事件包含 `job_id`、`qr_path` 和状态，把二维码图片交用户扫码并等待其回复。任务完成会返回 `awaiting_confirmation:true`；用户确认后运行 `kuaishou-hunter login-confirm` 校验并保存会话。

`login-confirm` 可查询同账号正在执行的任务：`starting` 表示二维码尚未就绪，`awaiting_scan` 才可使用二维码，`awaiting_phone_confirmation` 表示已扫码待手机确认，`completing` 表示手机已确认、正在保存会话。`LOGIN_WORKER_LOST`/`LOGIN_WORKER_UNRESPONSIVE`、失败或过期时不继续提示扫码旧图；查看原生后台任务。活进程异常时先通过原生 process 结束该任务，进程退出后再 login；已失败或丢失的任务可安全重建。任务总时限为十分钟，不是二维码有效期；平台未提供可核验期限时 `qr_expires_at:null`，不得自行承诺有效秒数。平台报告过期后停止，不静默更换二维码。

短信登录由 `login --method sms --phone <手机号>` 请求，用户给验证码后 `login-confirm --method sms --code <验证码>` 完成；手机与中间票据由脚本保存，不手工拼接。不要在非交互 Agent 环境等待终端输入。快手主站、创作者中心和直播站票据由运行库内同一登录流程管理。


```bash
kuaishou-hunter check
kuaishou-hunter search '关键词' --limit 20
kuaishou-hunter user '<用户ID或主页链接>'
kuaishou-hunter user-posts '<用户ID或主页链接>' --limit 20
kuaishou-hunter comments '<作品链接>' --limit 20
kuaishou-hunter fetch '<作品链接>' --output-dir /绝对路径/样本 --download-media
kuaishou-hunter fetch '<视频链接>' --output-dir /绝对路径/样本 --download-media --video-only
kuaishou-hunter methods
kuaishou-hunter call <resource> <action> [平台选项]
```

普通查询返回 JSON 信封，`data` 是数组或对象，`page` 保留游标；fetch 返回 `note`、`media_paths`，保存 `note.json` 和有序媒体文件。保留真实来源、完整字符串 ID 与原始计数，缺项为 null，不补零。终端缩略 ID 不能用于下一步。核对账号作品的作者身份；数字 uid、用户名与 secUid 不能互换。

列表默认 20 条，`--limit` 范围 1–100；按实际 `page` 游标有界续读，不使用 --all。`call` 只允许 methods 列出的读取接口，不能借此发评论、私信、点赞或关注。会话缺失/明确过期返回 2，风控和网络故障保留独立错误，不触发盲重登。

作品搜索不支持 --sort/--type/--time。关注流只有首屏，user likes/followers/following 只支持 me。二级评论参数覆盖有限；notice count 只有总数。400002、验证码或风控应停止并报告，不能当空数据或登录失效。

视频先下载再交 `viral-chaser` 本地 analyzer，采用返回的实际视频路径；`--video-only` 在下载前拒绝图文。图文和文字采样在 `expert-kuaishou` 或调用方 workflow 回读原文与图片分析。创作/发布/本人数据走 `expert-kuaishou`；互动写接口目前未实现，公开直播读取走本 hunter，调研分析走 expert-osbi。下载依赖平台返回的实际可访问媒体 URL，失败不回报下载成功。

## 公开直播读取

房间、列表、分类、礼物、回放与有界监听使用 `kuaishou-hunter live`；[读取说明](tools/kuaishou-live/SKILL.md)。原 kuaishou-live wrapper 保留在 hunter 内，调用同一只读入口。竞对调研交 expert-osbi，快手互动写接口保持未实现。
