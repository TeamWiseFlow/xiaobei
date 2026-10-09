---
name: tiktok-interact
description: TikTok作品互动，支持范围以工具能力表为准。
---

# TikTok interact

点赞/取消、收藏/取消、关注/取消、评论发布；用 call folder create/update/add 管理收藏夹（add 只能加入已收藏作品）。没有评论点赞、删除或转发写接口。

```bash
tiktok-interact like "<作品链接>"
tiktok-interact comment "<作品链接>" --text "真实讨论内容"
tiktok-interact reply "<作品链接>" --reply-to "<真实评论ID>" --text "回复内容"
tiktok-interact follow "<账号>" --confirm
tiktok-interact call <resource> <action> [平台选项]
tiktok-interact --help
```

写操作默认预览，已有授权时加 --confirm。查询通过 --account 指定同一个真实账号，完整ID作为字符串传递。列表默认20条、最多100条；监听 --duration 为1s–10m，默认1m，输出JSONL。不无限监听，不把样本当完整历史。

登录使用 `tiktok-hunter login/export`，写材料准备按 hunter 说明执行。TikTok 写操作缺少同次 ticket-guard 材料时脚本在请求前阻止。只执行真实接口已支持的动作，仍须本地实号验证响应、送达与权限。超时/断连先核对结果，不换通道重发；风控不当作登出。

内容搜索、作品、用户和评论采集使用 `tiktok-hunter`。直播工具按 expert-bd 的 live-research/live-interaction workflow 操作，观察竞对公开房间，不执行主播后台管理。记录真实目标、动作、时间和结果，区分已提交与已核实送达。
