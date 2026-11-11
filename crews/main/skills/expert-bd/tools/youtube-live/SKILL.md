---
name: youtube-live
description: 在 YouTube 直播间发送文字聊天；直播资料、历史和持续观察使用 youtube-hunter live。
---

先用 youtube-hunter 登录并读取真实直播视频 ID；账号需要有频道。确认目标、文字和授权，默认预览，已有授权时加 --confirm。

```bash
youtube-live send '<直播视频ID或链接>' --text '聊天正文' --account default
youtube-live send '<直播视频ID或链接>' --text '聊天正文' --account default --confirm
```

慢速模式、会员限制或平台拒绝按实际错误处理；超时不直接重发。只支持文字，不提供 Super Chat、礼物支付、直播点赞或主播后台操作。
