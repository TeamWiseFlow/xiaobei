---
name: youtube-channel
description: 为已登录且尚无 YouTube 频道的 Google 账号创建频道，默认预览，已有创建授权时执行。
---

先通过 youtube-hunter login/export 登录，确认用户需要创建频道以及名字/handle。本命令不修改已有频道资料，不因查询失败自动创建。

```bash
youtube-channel call channel create --name '频道名' --handle 'channel-handle' --account default
youtube-channel call channel create --name '频道名' --handle 'channel-handle' --account default --confirm
```

已有创建授权时加 --confirm，不重复询问。创建后可能等待约20秒才出现；超时先用 youtube-hunter user me 核查，不自动重复创建。账号已有频道时返回错误。
