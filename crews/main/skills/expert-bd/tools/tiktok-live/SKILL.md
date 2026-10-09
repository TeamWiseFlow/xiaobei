---
name: tiktok-live
description: TikTok公开直播调研与互动，支持范围以工具能力表为准。
---

# TikTok live

公开直播查询、搜索、分类、短时事件、进房历史、排行、礼物列表、实际流地址，以及已授权文字 send 与 like。list 只显示关注账号中在播的；history 只覆盖进房消息，流地址不保证每场都有。不支持送礼、商品查询或主播后台管理。

```bash
tiktok-live get "<直播间>"
tiktok-live listen "<直播间>" --duration 1m
tiktok-live send "<直播间>" "弹幕文案" --confirm
tiktok-live like "<直播间>" --confirm
tiktok-live call <resource> <action> [平台选项]
tiktok-live --help
```

写操作默认预览，已有授权时加 --confirm。查询通过 --account 指定同一个真实账号，完整ID作为字符串传递。列表默认20条、最多100条；监听 --duration 为1s–10m，默认1m，输出JSONL。不无限监听，不把样本当完整历史。

登录使用 `tiktok-hunter login/export`，写材料准备按 hunter 说明执行。TikTok 写操作缺少同次 ticket-guard 材料时脚本在请求前阻止。只执行真实接口已支持的动作，仍须本地实号验证响应、送达与权限。超时/断连先核对结果，不换通道重发；风控不当作登出。

内容搜索、作品、用户和评论采集使用 `tiktok-hunter`。直播工具按 expert-bd 的 live-research/live-interaction workflow 操作，观察竞对公开房间，不执行主播后台管理。记录真实目标、动作、时间和结果，区分已提交与已核实送达。
