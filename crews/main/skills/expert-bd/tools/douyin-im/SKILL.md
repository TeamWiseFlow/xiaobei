---
name: douyin-im
description: 抖音 API 私信会话、文本/媒体/分享卡片发送、实时消息监听及指定消息回复；发送状态可查询。
---

# 抖音私信

归 `expert-bd`，与 `douyin-hunter`、`expert-douyin` 共用 `douyin-hunter` 的 `douyin-login` API 登录态，不需要浏览器。协议配置从登录初始化取得。会话、身份令牌和私信回执按当前账号保存；票据、Cookie、令牌及媒体密钥不得贴入对话。

用户已授权目标和内容后才能执行发送。默认预览，实际创建/发送加 `--confirm`。每次授权任务选定一个稳定 `--request-id`，同一任务重试始终复用；不要为了绕过未知结果换编号重发。

```bash
douyin-im send-to --to-user-id 真实数字UID --text "已授权内容" --request-id bd-contact-001
douyin-im send-to --to-user-id 真实数字UID --text "已授权内容" --request-id bd-contact-001 --confirm
douyin-im status --request-id bd-contact-001
```

脚本核对当前账号，内部复用并刷新已有会话，没有本地会话时才创建；上传、身份安全令牌和发送由同一脚本完成。`send-to` 不要求 agent 保存和拼接中间票据。`status` 只读本地回执，不向平台查询送达状态；其退出码 0 表示查询完成，发送结果仍以 `status`、`accepted` 和 `evidence` 为准。

- `accepted`：平台给出成功回执；`evidence=platform-ack` 只有协议层确认，`business-response` 含业务成功及服务端消息 ID。两者均不代表送达或已读。
- `evidence=user-confirmed-app`：用户已从 App 核实发送后由维护者结案，不能当作工具从平台响应中解析出了消息 ID，也不要再次发送。
- `preparing` / `prepared`：尚未进入消息提交，可处理错误后按原参数、原编号续接。
- `submitting` / `unknown`：可能已发出；中断后的 `submitting` 自动记为 `unknown`，停止重发并向用户报告。`info` 无法确认某条消息是否已发出。
- `rejected`：平台明确拒绝，本任务不自动重试。同一编号修改目标或内容报 `REQUEST_ID_CONFLICT`。

提交响应在解析前保存到 0600 私有文件，回执返回 `response_file`、HTTP 状态和脱敏响应信息。原始内容可能含票据，不要贴入对话。解析业务状态、检查码与服务端消息 ID，并核对响应中的客户端消息 ID；空响应、缺少可确认字段或消息 ID 不匹配仍保留 `unknown`，不得为取回执而重新发送。

单条文本 ≤1000 字；本工具将本地图片、视频、文件限制为每个 ≤10MB。媒体、卡片和语音参数在预览阶段校验，未确认不会上传。

```bash
douyin-im send-to --to-user-id 真实数字UID --kind image --file /受控目录/image.jpg --request-id bd-image-001
douyin-im send-to --to-user-id 真实数字UID --kind video --file /受控目录/video.mp4 --thumb /受控目录/cover.jpg --request-id bd-video-001
douyin-im send-to --to-user-id 真实数字UID --kind file --file /受控目录/document.pdf --request-id bd-file-001
douyin-im send-to --to-user-id 真实数字UID --kind card-video --share "https://www.douyin.com/video/作品ID" --request-id bd-card-001
```

`card-photos`、`card-web`、`card-user`、`sticker` 接受兼容客户端的真实元数据 `--content-file`；JSON 文件须是当前用户所有、权限 0600 的普通文件。`audio` 只能传已有语音消息内容，`--encrypted` 选择加密消息类型；不支持将本地音频文件直接上传为语音。媒体上传完成后仍需平台发送确认。

实时收信和回复：

```bash
douyin-im listen --duration 60 --max-events 100 --output /受控目录/messages.jsonl
douyin-im reply --event-file /受控目录/messages.jsonl --message-id 真实服务端消息ID --text "已授权回复"
```

监听有时限、事件上限和有限重连，记录 `account_uid`、`direction`、`server_message_id`、会话 ID 和短 ID；消息 ID 保持字符串。工具按服务端消息 ID 去重，账号变化立即停止。读取到事件不等于登录认证已完成。不要自动回复收到的消息。

`reply` 仅选择明确指定的入站消息，并核对所属账号、发送者和会话；多条匹配时须加 `--conversation-id` 精确定位。确认后加 `--confirm`，工具内部刷新该会话票据，再向同一会话发送普通消息。缺省请求编号由该入站消息稳定生成；需要引用气泡的回复尚未实现。

兼容已保存会话的操作：

```bash
douyin-im create --my-user-id 本人ID --to-user-id 收件人ID
douyin-im info --conversation-file /受控目录/会话.json
douyin-im send --conversation-file /受控目录/会话.json --text "已授权内容" --request-id bd-existing-001
```

会话文件保存在 `~/.openclaw/douyin-im/`，权限 0600。旧会话在使用前重新取票据，不依赖旧票据继续发送。遇到登录失效、风控、身份令牌拒绝或媒体错误即停止，按 `douyin-hunter` 的 `douyin-login` 指导处理；不自动开启新登录。

平台完整会话列表、离线历史补拉、私信未读数、主动标记已读、撤回、删除及全自动回复未实现。监听仅处理实时推送；二进制业务回执无法确认时记录 `unknown`。不得用浏览器补造这些能力。
