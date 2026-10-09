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


# 快手内容采集

首次登录：`kuaishou-hunter login`。
扫码登录返回二维码与下一步提示，交用户扫码后运行 `kuaishou-hunter login-confirm`。短信登录由 `login --method sms --phone <手机号>` 请求，用户给验证码后 `login-confirm --method sms --code <验证码>` 完成；手机与中间票据由脚本保存，不手工拼接。不要在非交互 Agent 环境等待终端输入。快手主站、创作者中心和直播站票据由运行库内同一登录流程管理。


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

视频先下载再交 `viral-chaser` 本地 analyzer，采用返回的实际视频路径；`--video-only` 在下载前拒绝图文。图文和文字采样在 `expert-kuaishou` 或调用方 workflow 回读原文与图片分析。创作/发布/本人数据走 `expert-kuaishou`；互动和直播走 expert-bd。下载依赖平台返回的实际可访问媒体 URL，失败不回报下载成功。
