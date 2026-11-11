---
name: youtube-engagement
description: 获取当前 YouTube 账号的 Studio 视频列表及播放、点赞、评论指标，按真实作品链接回填 published-track。
---

登录使用 youtube-hunter login/export。本工具访问自己频道的 Studio 视频列表（含私享和草稿），不能用来抓其他频道。

```bash
youtube-engagement check --account default
youtube-engagement list --account default --limit 20
youtube-engagement fetch --account default --record-id 123 --limit 100
youtube-engagement daily --account default --limit 100
```

record-id 是 published-track 的数据库行 ID。只匹配本页真实视频 ID、记录账号 alias 与当前频道作者；翻页用返回的 cursor，未在本页或无指标的记录返回 skipped。指标缺失不补零，不将全部频道视频自动建发布记录。记录使用平台代号 youtube，视频链接支持 watch、youtu.be、shorts/live/embed；不同账号不得相互回填。没有频道时先核实需求，频道创建另用 youtube-channel。
