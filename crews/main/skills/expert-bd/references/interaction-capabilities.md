# 抖音与小红书互动能力

内容搜索、用户资料、作品与评论采集、评论/@提醒、点赞收藏提醒及新增关注通知调用一级 hunter；私信和互动写操作在 expert-bd 内执行。创作、发布、本人已发作品数据和创作者服务仍转平台专家包。表内尚不支持的能力保留为空缺。

| 能力 | 抖音 | 小红书 |
|---|---|---|
| 作品点赞/取消、收藏/取消 | `douyin-interact like/unlike/favorite/unfavorite` | 尚无已实现的接口工具 |
| 评论与回复 | `douyin-interact comment/reply` | 笔记评论发布尚无已实现接口；读取用 xhs-hunter |
| 评论删除/点赞、关注/取消关注 | 尚不支持 | 尚不支持 |
| 单聊会话/历史 | 本地已建立会话 `douyin-im info`；平台列表/历史尚不支持 | `xhs-im list/history` |
| 群聊会话/历史 | 尚不支持 | `xhs-im groups` / `history --conversation group:<ID>`，响应字段需实测核对 |
| 私信发送 | `douyin-im send-to/send`：文本、图片、视频、附件与分享卡片；语音/贴纸需要真实内容对象 | `xhs-im send`：仅单聊文本 |
| 实时私信 | `douyin-im listen` | `xhs-im listen` |
| 标记已读 | 可监听已读通知，主动标记尚不支持 | `xhs-im read`：从真实会话列表取得 store_id/未读数，缺字段即停 |
| 撤回/删除会话 | 尚不支持 | `xhs-im revoke/delete`，预览后加 `--confirm` |
| 直播文字互动 | `douyin-live chat/like` | `xhs-live send`；不支持直播点赞 |
| 直播事件 | `douyin-live listen`，含礼物、PK 与 ACK | `xhs-live listen` |
| 最近直播消息 | `douyin-live history`，只到进房快照最近 15 条 | 尚不支持历史查询 |
| 直播资料与商品 | `douyin-live room/products/media`，PK/榜单能力保留 | `xhs-live call` 房间/频道/广场/礼物与商品信息 |
| 礼物支付、主播后台开关播、禁言/踢人 | 不提供 | 不提供 |

小红书的「获取笔记评论」「获取点赞/收藏提醒」「获取新增关注」均为读取能力，可通过 xhs-hunter 调用现有 PC 方法；这些方法不能发布笔记评论、点赞、收藏或关注。直播 `send_comment` 只发直播弹幕，也不能用于笔记评论。

直播工具面向指定的公开直播间，不限自有房间，按实际访问与发言权限工作。主要场景为竞争对手直播调研（`workflows/live-research.md`）与直播间互动（`workflows/live-interaction.md`）；仅调研时不自动发送。小红书 host_id 指目标主播，抖音 web_rid 是网页房间号，均不表示必须使用主播账号。当前能力不包括主播后台管理。

## 使用条件与验收范围

- 抖音使用 `douyin-login` 独立 API 会话。写操作必须有同次登录绑定的安全材料，缺失即停；仅 cookie 或创作者浏览器登录不能替代互动登录。扫码入口可取得写操作所需材料，短信链有额外限制，以工具检查结果为准。
- 小红书使用 `xhs-hunter login` 的 PC 会话，不能混用 Creator 登录。私信只支持单聊文本；群聊只支持查询，已读/撤回/删除/发送拒绝 group: 目标。
- 小红书私信发送、已读、撤回、删除、实时监听和直播发送/监听仍需要真实账号验收。抖音评论、私信与直播写操作也不能因离线测试通过而宣称已送达；先以单条已授权任务核对响应与平台实际结果。
- 评论采集可能触发验证码或限频，小红书扫码可能触发人机验证。停止并报告实际错误，不无限重试，不当作零结果或自动登出。
- 所有写操作先预览，已有用户授权时加 `--confirm`；提交成功与实际送达/对方已读分开记录。超时或连接中断先查结果，禁止直接换通道重发。
