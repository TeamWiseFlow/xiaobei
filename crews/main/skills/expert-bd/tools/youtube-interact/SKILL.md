---
name: youtube-interact
description: YouTube 视频点赞、稍后观看、频道订阅与评论发布、回复、删除、点赞。读取使用 youtube-hunter。
---

登录由 youtube-hunter login/export 完成。先确定真实目标、文案与用户授权；默认预览，已有动作授权时加 --confirm。结果未知先查评论或平台页面，不直接重发。

```bash
youtube-interact like '<视频链接>' --account default
youtube-interact like '<视频链接>' --account default --confirm
youtube-interact follow '@频道handle' --account default --confirm
youtube-interact comment '<视频链接>' --text '评论正文' --account default --confirm
youtube-interact call comment add '<视频链接>' '回复正文' --reply-to '<真实评论ID>' --account default --confirm
youtube-interact call comment delete '<视频链接>' '<本人评论ID>' --account default --confirm
```

like/unlike 点赞/取消；collect/uncollect 加入/移出稍后观看；follow/unfollow 订阅/取消；comment add/delete/like/unlike 的完整参数通过 methods 查看。发评论需要账号有频道；删除只针对本人评论。回复必须引用 hunter 读取的真实评论 ID，回复挂在根评论下。YouTube 不公开其他人的点赞、稍后观看和订阅列表；不提供私信、转发或送礼支付。将真实动作与结果记入 bd-record。
