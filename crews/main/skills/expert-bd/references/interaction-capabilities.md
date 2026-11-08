# 平台互动能力

本表汇总仓内已实现的 BD 能力；执行前先确认当前 crew 已配置入口，再读取对应工具的 SKILL.md。表中有实现不代表已完成本账号、媒体类型或业务动作的实号验收。

公开账号、作品、评论、提醒和媒体按平台调用 `douyin-hunter` / `xhs-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter` / `youtube-hunter` / `wx-mp-hunter`，只读各自已支持的资料。创作、发布、本人作品指标与创作者服务转平台专家包，普通互动写操作仍归 `expert-bd`。

| 平台 | 能力 | 工具 / 入口 | 当前范围与限制 |
|---|---|---|---|
| 抖音 | 作品与评论互动 | `douyin-interact like/unlike/favorite/unfavorite/comment/reply` | 点赞、收藏及取消，评论与回复；评论删除/点赞、关注/取消未实现。受理不等于最终账号状态或公开可见性已核验 |
| 抖音 | 主动私信与媒体发送 | `douyin-im send-to/send` | 文本、图片、视频、附件、视频分享卡片；其他卡片/贴纸/已有语音需真实内容对象。本地音频直接上传为语音未实现；同任务使用稳定 request-id，脚本内部维护会话与上传中间态 |
| 抖音 | 实时收信与指定消息回复 | `douyin-im listen/reply` | 有界监听、去重、账号与入站消息校验；按真实消息 ID 向同一会话回复普通消息。引用气泡及全自动回复未实现，不补拉离线历史 |
| 抖音 | 会话创建与请求回执 | `douyin-im create/info/status` | 创建会话、核对本地已保存会话；status 只查本地回执。平台完整会话列表、历史、未读数、主动标已读、撤回、删除未实现；可监听到已读事件不等于主动标已读 |
| 抖音 | 公开直播读取与互动 | 读取 `douyin-hunter live`；写入 `douyin-live chat/like` | 房间/商品/流地址、PK/榜单、近期消息与事件；history 仅进房快照最近15条。发言与点赞按真实 room_id，不把网页 web_rid 当 room_id |
| 小红书 | 笔记互动 | 读取 `xhs-hunter`；无笔记写工具 | 可读笔记评论、评论/@、赞藏和新增关注提醒；笔记评论/回复、点赞收藏关注及取消未实现，直播发送不能代替笔记评论 |
| 小红书 | 私信读取与监听 | `xhs-im list/groups/history/unread/listen` | 单聊会话/历史/未读、有界实时消息；群聊仅列表和历史，按真实返回核对字段与游标 |
| 小红书 | 私信发送与管理 | `xhs-im send/read/revoke/delete` | 仅单聊文本、标已读、撤回指定消息与删除本账号会话；拒绝群聊写操作。计数与游标由工具校验，submitted/mid 不表示送达或已读 |
| 小红书 | 公开直播读取与互动 | 读取 `xhs-hunter live`；写入 `xhs-live send/room-text` | 房间、商品、事件与有界监听；文字发送需真实房间与目标主播 ID。无历史查询、直播点赞或主播后台能力；捕获文字帧仅按工具说明使用 |
| TikTok | 作品、评论、关注与收藏夹 | `tiktok-interact` | 点赞/收藏/关注及取消、评论与真实父评论回复；folder create/update/add，add 只加入已收藏作品。评论删除/点赞、转发写操作未实现 |
| TikTok | 私信读取、发送与监听 | `tiktok-im list/history/send/listen` | 查询真实会话与历史、有界监听；只向已有会话发文本。不能新建会话、发媒体、标已读、撤回或删除 |
| TikTok | 公开直播读取与互动 | 读取 `tiktok-hunter live`；写入 `tiktok-live send/like` | 公开房间、近期消息/事件等按采集工具范围读取；写入仅文字与点赞，须同次 ticket-guard 材料 |
| X / Twitter | 作品与账号互动 | `twitter-interact` | 点赞、书签、转发、关注及取消；评论/回复推文、删除本人评论、评论点赞及取消。回复受权重与长推权限限制，文章/帖串创作走 expert-twitter |
| X / Twitter | 私信查询 | `twitter-im list/history` | 仅最近20个会话首页，历史是端到端加密占位消息；不支持正文解密、发送、标已读、撤回、删除或实时监听 |
| X / Twitter | 直播 | 无已接入工具 | 不支持公开直播读取、监听或写入，不用普通推文互动替代 |
| 快手 | 公开采集与直播观察 | `kuaishou-hunter` / `kuaishou-hunter live` | 可读作品、账号、评论及支持的提醒/直播资料、事件和回放；普通评论、点赞收藏关注、私信与直播写操作均未实现 |
| 微博 | 公开采集 | `weibo-hunter` | 可读账号、作品、搜索、一级评论及媒体；通知、普通互动写操作、私信和直播均未接入。内容发布另走 weibo-publish |
| YouTube | 视频、评论与频道互动 | `youtube-interact` | 视频点赞/取消、稍后观看/移出、订阅/取消，评论/回复/删除本人评论与评论点赞/取消。发评论需要已有频道，不支持私信 |
| YouTube | 公开采集、个人列表与提醒 | `youtube-hunter` | 公开视频、频道、评论、播放列表和分轨下载可用游客态；个人列表、历史、推荐/订阅流及通知需登录。不能查看其他人的点赞、稍后观看和订阅列表 |
| YouTube | 公开直播读取与文字互动 | 读取 `youtube-hunter live`；写入 `youtube-live send` | 直播状态、近期聊天与有界轮询监听；发文字需账号有频道，遵守会员/慢速模式。无直播点赞、Super Chat/礼物支付或私信 |
| 微信公众号 | 公开资料 | `wx-mp-hunter` | 只使用已实现的文章/账号资料读取；本包无公众号评论发布或私信工具，不从其他平台私信接口代发 |
| 邮件 | 邮件联络与跟进 | 公共 `email-ops` | 按其实际账号、功能与发送授权执行；社交平台授权不自动覆盖邮件，不伪造来源帖子入库 |

## 共用条件

- 抖音共用 `douyin-login` API 会话与同次安全材料；小红书复用 `xhs-hunter` PC 会话，不混用 Creator 登录。TikTok、X、微博、YouTube 与快手分别按 `tiktok-hunter` / `x-hunter` / `weibo-hunter` / `youtube-hunter` / `kuaishou-hunter` 管理会话，TikTok 写入还需同次 ticket-guard 材料。
- 默认先预览，已有动作授权时按工具加 `--confirm`；邮件按 `email-ops` 自身流程执行。平台受理、公开可见、送达、已读与实际回应分开记录；抖音私信按 `status/accepted/evidence` 判断，`submitting/unknown` 不重发，不换请求编号绕过保护。具体执行见 [Interaction](../workflows/interaction.md)。
- 公开直播调研使用 `expert-osbi`，仅观察不触发互动。直播写操作见 [Live Interaction](../workflows/live-interaction.md)；所有平台均不提供礼物支付、主播后台开关播、禁言/踢人或商品管理。
- Relay 只计算签名。验证码、平台风控、Relay 配额/故障与平台会话失效分别处理；不自动求解验证码、切换本地签名、无限重试或用浏览器补造缺失接口。失败/未知只保留真实诊断，不当作空结果或成功。
