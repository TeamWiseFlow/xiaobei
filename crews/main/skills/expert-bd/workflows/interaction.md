# 评论与私信互动 Workflow

适用：用户要求在抖音或小红书互动、回复评论、发送私信或进行线索触达。创作、发布与本人作品数据转对应平台专家包。

1. 确定平台、真实目标、互动目的、确切文案与授权范围。没有发布/发送授权时只整理草稿；既有授权覆盖的动作无需重复确认。
2. 用一级 `douyin-hunter` / `xhs-hunter` 获取真实作品、评论和账号资料，保留完整 ID、链接及小红书 xsec_token。用 bd-record 查重；错误与样本不足如实标注。
3. 读 `references/interaction-capabilities.md` 与目标工具说明。未实现的写操作报告缺口，不能将模拟预览当成功。
4. 生成预览，核对目标和文案后执行已授权动作。抖音文本直达使用 `douyin-im send-to --to-user-id <真实数字UID> --text "文案"`，脚本内部建立和保存会话；小红书使用 `xhs-im send <用户ID> "文案"`。预览后实际执行加 `--confirm`，不让 agent 手工拼接中间会话文件。
5. 抖音公开评论使用 `douyin-interact comment --url <作品链接> --text "文案"`；回复使用 `reply --comment-id <真实评论ID>`。小红书笔记评论接口尚未实现；不要调用直播评论命令代替笔记评论。
6. 小红书私信查询用 `xhs-im list/history/unread`，需要标记已读、撤回或删除时用 `read/revoke/delete` 先预览；群聊只查询。结果不明先核对历史或平台页面，不自动重发。
7. 用 bd-record 记录真实目标、动作、时间和结果。区分已提交、已核实送达和失败；汇总真实回复、待跟进及能力缺口。没有用户要求不建立周期任务。

直播间提问、答疑与合作互动按 [Live Interaction](live-interaction.md) 执行；竞争对手直播调研按 [Live Research](live-research.md) 执行。取数、登录失效或风控不触发重新发布内容。

TikTok 互动通过 tiktok-interact/tiktok-im/tiktok-live，写操作需要同次 ticket-guard 材料。X 评论、回复、点赞、转发、收藏与关注使用 twitter-interact；twitter-im 只查询首页会话及加密占位历史。所有写操作先预览，已有授权时 --confirm；快手只支持直播观察，没有评论、点赞、关注、私信或直播发言接口。
