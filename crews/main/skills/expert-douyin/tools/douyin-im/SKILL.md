---
name: douyin-im
description: 抖音 API 私信会话、文本/媒体/分享卡片发送与实时消息监听。
---

# 抖音私信

使用 `douyin-login` 的独立 API 会话。协议版本由受控环境 `DOUYIN_IM_SDK_VERSION`、`DOUYIN_IM_BUILD_NUMBER` 提供，取值不写入仓库。会话文件位于 `~/.openclaw/douyin-im/`、权限 0600，包含本人/收件人 ID 与票据。操作前核对目标，文件必须属于当前 API 账号。

```bash
douyin-im create --my-user-id 本人ID --to-user-id 收件人ID
douyin-im info --conversation-file /受控目录/会话.json
douyin-im send --conversation-file /受控目录/会话.json --text "消息内容"
douyin-im send --conversation-file /受控目录/会话.json --kind image --file /绝对路径/image.jpg
douyin-im send --conversation-file /受控目录/会话.json --kind video --file /绝对路径/video.mp4 --thumb /绝对路径/cover.jpg
douyin-im send --conversation-file /受控目录/会话.json --kind file --file /绝对路径/document.pdf
douyin-im send --conversation-file /受控目录/会话.json --kind card-video --share "https://www.douyin.com/video/作品ID"
douyin-im listen --duration 60 --max-events 100 --output /受控目录/messages.jsonl
```

创建与发送默认预览；用户已授权目标和内容时加 `--confirm`。单条文本 ≤1000 字，附件 ≤10MB。`card-photos`、`card-web`、`card-user`、`sticker` 接受真实平台元数据 `--content-file`。图片/视频/文件在本机上传；私信先获取身份安全 token，再发送协议封包。票据、上传凭据与 token 不输出。

语音消息只能传兼容客户端已形成的 `--content-file`，`--kind audio`（加 `--encrypted` 使用对应消息类型）；当前网页协议没有本地音频录制/上传能力，不将普通音频文件伪装成语音。监听支持文本、图片、语音、分享与已读通知；有时限、事件上限、心跳及有限重连，不自动回复收到的消息。

创建会话先向 Relay 请求封包扩展，再以最终封包和一次性 context 签请求；不得重用 context。请求结果未知时先查会话，不自动重发私信。操作成功仅表示平台接受请求，不承诺对方已收到或已读。
