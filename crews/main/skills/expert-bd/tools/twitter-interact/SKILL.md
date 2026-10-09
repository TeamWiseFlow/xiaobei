---
name: twitter-interact
description: X/Twitter作品互动，支持范围以工具能力表为准。
---


# X/Twitter interact

点赞/取消、收藏/取消、转发/取消、关注/取消、评论回复、评论删除与评论点赞。兼容 retweet/bookmark 等旧动作别名。评论以回复推文发送，线程内容创作仍走 twitter-post。

评论回复同样按推文权重选择普通回复或长推。未订阅或未确认 X Premium 长推权限时，回复控制在280权重内（纯中文约140字，还需计入标点、链接等）；超限先精简，不能以提交探测权限。`Blue claim is not enabled for note tweet` 表示长推权限不足，不当作登录失效。

```bash
twitter-interact like "<作品链接>"
twitter-interact comment "<作品链接>" --text "真实讨论内容"
twitter-interact follow "<账号>" --confirm
twitter-interact call <resource> <action> [平台选项]
twitter-interact --help
```

写操作默认预览，已有授权时加 --confirm。查询通过 --account 指定同一个真实账号，完整ID作为字符串传递。列表默认20条、最多100条；监听 --duration 为1s–10m，默认1m，输出JSONL。不无限监听，不把样本当完整历史。

登录使用 `x-hunter login/export`。只执行真实接口已支持的动作，仍须本地实号验证响应、送达与权限。超时/断连先核对结果，不换通道重发；风控不当作登出。

内容搜索、作品、用户和评论采集使用 `x-hunter`。直播工具按 expert-bd 的 live-research/live-interaction workflow 操作，观察竞对公开房间，不执行主播后台管理。记录真实目标、动作、时间和结果，区分已提交与已核实送达。
