---
name: kuaishou-live
description: 快手公开直播资料、回放与有界事件监听；不支持发言或点赞。
---


# 快手 live

只读公开房间、列表、分类、礼物、回放与有界事件监听。get 的直播主播ID与用户主页ID是两套；replays 传主页ID，不混用。没有直播评论、点赞、私信或主播后台接口。快手普通评论、点赞、收藏与关注写操作也未实现。

```bash
kuaishou-live get "<直播间>"
kuaishou-live listen "<直播间>" --duration 1m
kuaishou-live call <resource> <action> [平台选项]
kuaishou-live --help
```

查询通过 --account 指定同一个真实账号，完整ID作为字符串传递。列表默认20条、最多100条；监听 --duration 为1s–10m，默认1m，输出JSONL。不无限监听，不把样本当完整历史。

登录使用 kuaishou-hunter login。只执行真实接口已支持的动作，仍须本地实号验证响应、送达与权限。超时/断连先核对结果，不换通道重发；风控不当作登出。

内容搜索、作品、用户和评论采集使用 `kuaishou-hunter`。直播工具按 expert-bd 的 live-research/live-interaction workflow 操作，观察竞对公开房间，不执行主播后台管理。记录真实目标、动作、时间和结果，区分已提交与已核实送达。
