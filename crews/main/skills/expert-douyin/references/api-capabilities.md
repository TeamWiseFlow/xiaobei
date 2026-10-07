# API 能力入口

先验证 `douyin-login status`、`douyin-hunter check`。发布核查与本人播放量使用创作者本人作品列表，不要求主站身份响应含 `sec_uid`。所有平台请求使用同一独立 API 会话。缺材料时修复会话配置，不能启动旧浏览器补操作。

| 任务 | 入口 |
| --- | --- |
| 初始化、重新登录、二维码、短信、两种登录 MFA、有效期与登录确认 | `douyin-login` |
| 本人、用户资料、用户作品、点赞作品、收藏夹 | `douyin-hunter call/collect` |
| 综合、视频、用户和直播搜索 | `douyin-hunter search` |
| 外层评论与回复 | `douyin-hunter comments`，回复传 `--comment-id` |
| 粉丝、关注、通知与推荐流 | `douyin-hunter call/collect` |
| 作品及本地媒体下载 | `douyin-hunter fetch --download-media` |
| 本人已发作品播放量、公开互动量及发布记录更新 | `douyin-engagement list/fetch/daily` |
| 图文和视频上传、检测、封面及作品提交 | `douyin-publish note/video` |
| 创作者预览、封面引用与生成、声明建议、媒体 URL | `douyin-publish call`；生成任务用 `cover-generate` |
| 提交结果未知的核查与人工结案 | `douyin-publish status/resolve` |
| 点赞与取消、收藏与取消、评论与回复、收藏夹迁移 | `douyin-interact` |
| 私信会话建立、信息刷新 | `douyin-im create/info` |
| 文本、图片、视频、文件、语音内容、贴纸及分享卡片 | `douyin-im send` |
| 私信实时消息与已读通知 | `douyin-im listen` |
| 直播房间、连麦、PK、双方贡献及千票榜 | `douyin-live room/pk/pk-rank/rank/ticket-rank` |
| 直播商品与详情 | `douyin-live products/call product_detail` |
| 商品评论及数量 | `douyin-hunter call product_reviews/product_review_counts` |
| 直播 HTTP 消息快照 | `douyin-live call live_fetch` |
| 直播消息、礼物、PK 状态及 ACK | `douyin-live listen` |
| 直播弹幕与点赞 | `douyin-live chat/like` |

`methods` 或对应 `call --help` 给出方法名，业务字段以实际响应为准。采集分批、有分页上限；媒体下载限制来源域与文件大小。设备 ID、作品 ID、账号 ID 始终保留字符串。

自动取数覆盖本人作品播放量，以及公开详情实际返回的点赞、评论、分享和收藏。播放量来自创作者作品列表，须核对当前账号 UID 与完整作品 ID；其他账号或列表未返回的作品不补播放量。完播、跳出、平均观看、曝光、点击率、画像及留存等后台深指标不列为自动取数能力。

创建会话、发送消息、互动、生成封面、上传发布均需用户授权，默认预览。网络错误后先核查业务状态，不自动重新写入。语音只能使用已形成的兼容消息内容；不要把本地音频文件伪装成语音。直播控场限于观察消息和 PK、授权弹幕与点赞；不得虚构后台禁言、踢人或送礼能力。
