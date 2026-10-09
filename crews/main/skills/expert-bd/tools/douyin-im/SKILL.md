---
name: douyin-im
description: 抖音 API 私信会话、文本/媒体/分享卡片发送与实时消息监听。
---

# 抖音私信

归 expert-bd，使用一级技能 douyin-hunter 包内 `douyin-login` 的独立 API 会话；与创作者 Camoufox profile 独立。协议版本由登录初始化自动取得并保存在 API 会话中，无需人工配置。会话文件位于 `~/.openclaw/douyin-im/`、权限 0600，包含本人/收件人 ID 与票据。操作前核对目标，文件必须属于当前 API 账号。

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

创建会话先向 Relay 请求封包扩展，再以最终封包和一次性 context 签请求；不得重用 context。工具处理平台的 JSON 或 protobuf 响应，并校验业务状态及返回会话。创建成功后复用返回的 `conversation_file`，后续先用 `info` 查询，不重复创建。`PLATFORM_IM_INVALID_RESPONSE` 表示响应无法解析，不代表票据失效；请求结果未知时先查会话并报告，不自动重发私信。操作成功仅表示平台接受请求，不承诺对方已收到或已读。


## 直接发送到用户

```bash
douyin-im send-to --to-user-id 真实数字UID --text "已授权文本"
douyin-im send-to --to-user-id 真实数字UID --kind image --file /绝对路径/image.jpg
```

默认预览，实际执行加 `--confirm`。脚本核对当前 API 账号，内部建立并保存会话，再发送一条消息；不让 agent 自行拼接上一步返回的会话文件。媒体、附件和卡片选项与 `send` 一致。

平台会话列表、历史查询、主动标记已读、撤回及删除仍未实现。`info` 只刷新已保存的会话，不等于平台列表；`listen` 的已读事件不等于主动发送已读回执。私信提交响应与实际送达分开记录，未知结果不自动重发；媒体与实时收发需真实账号验收。
