---
name: demo-send
description: >
  Send configured product visual material or customer feedback collages when
  customers ask about product competitiveness, real usage cases, or visual references.
---

# Demo material

## 1. 读取本实例素材

先读当前 agent 工作区下的 `media/demo-send.json`（相对于工作区，不是本技能的 realpath）。文件存在时以它为完整配置，不与共享配置混合；不存在才回退同级 `config.json`。实例素材、微盘文件名、账号不得写进共享技能配置，以免串到其他实例。

配置的 `media` 是本地绝对路径或 HTTPS 图片直链；可选 `awadaDrive` 为 `{"accountId":"default","fileName":"<微盘完整文件名>","kind":"image"}`。字段为空或缺少本渠道所需配置时，让 main agent配置实际素材，不猜路径、文件名或链接。完成标准：已读实际配置并确定发送分支。

## 2. 判断触发与边界

- 客户问产品竞争力、竞品比较或实际案例时，可发已配置的素材文件；先按既有产品卖点回答，不夸大图片中的反馈，不承诺客户也能取得同样收益。
- 仅发当前咨询所需素材，不群发、不主动触达其他客户；同一轮不重复发送。完成标准：当前问题符合触发条件，素材已获授权。

## 3. 按渠道发送（只选一条路径）

### Awada + 已配置 awadaDrive：微盘原图

使用企业微信微盘的图片文件名发图（type=208），目标必须是消息头里 Sender 的原始显示名，保留大小写；提交后必须核验执行回执。付款码脚本的默认成功文案是扫码付款文案，**案例图不能直接复用或转发该文案**。

本技能使用统一 Awada 工具完成实际发送；先用 `awada_api(action="schema", accountId="<配置账号>", operation="drive.send")` 核对当前接口，再调用：

```
awada_api(action="operation", accountId="<awadaDrive.accountId>", operation="drive.send", params={"targets":["<当前客户原始名称或备注名>"],"fileName":"<awadaDrive.fileName>","kind":"image"})
```

例如本实例配置为案例图 `vipclub-customer-feedback-20261118.jpg` 时，`fileName` 传该文件名；以实际配置为准。发送后按第 4 节查原回执，再决定后续回复。

- targets 必须取当前入站可核对的原始显示名/备注名，保留大小写；不能用已小写化的 CustomerDB peer、会话 key、fileid 或猜测的昵称。无法可靠确定目标时，先核对，不试发。
- 企业微盘 fileid、空间路径仅用于素材追溯，不属于 drive.send 参数。微盘分享网页不是图片直链，不塞入 media。文件名必须完全一致。
- 使用微盘按文件名发图能力实：际发送只能通过上面的统一 Awada 工具，不用 exec/curl/CLI 或内部动作绕过消息工具。工具不可用或权限拒绝时报告 main，不另找旁路。
- 此分支不得自动降级为本地路径或 URL 发送；失败/未知时也不得换通道再发一次。

### 其他渠道，或未配置 awadaDrive 的既有实例

沿用原标准媒体通路：

```
message(action="send", media="<配置中的 media>")
```

当前会话可省略 target；可用 message 参数附带说明。不得将本地路径、URL 或原始字节当作正文发给客户。完成标准：只提交了一次正确渠道的发送请求，保存原回执。

## 4. 核对结果与回复

Awada 的 queued / running / submitted 不是送达，使用同一 accountId 和返回的 operationId 调用 `awada_api(action="result", ...)` 查询原回执；仅 succeeded 才可说已发送。查询权限只限当前 agent/session 登记回执；拒绝时交 main/owner 核查，不绕过权限。

failed / unknown / 超时或查询受限：保留回执，不自动重发、不自动换路径；向 main agent报告具体阻碍，对客户可正常给官网案例页（如有），但不声称图片已送达、不透传内部错误。

调用工具的 turn 不输出面向客户的文本；完成后只给一份简短说明并结合客户场景继续，不重复附言。完成标准：已确认成功，或明确记录未确认/失败及原回执。
