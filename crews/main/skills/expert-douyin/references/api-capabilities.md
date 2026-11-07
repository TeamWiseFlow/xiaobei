# 抖音能力路由

| 业务 | 调用 |
|---|---|
| 创作者登录、发布前检查 | `douyin-publish login/check`，复用统一 API 会话 |
| 视频发布、请求准备、验证续接与取链 | `douyin-publish video`，分步操作见发布工具的 `references/video.md` |
| 原声图文发布、验证续接与取链 | `douyin-publish note`，分步操作见发布工具的 `references/note.md` |
| 本人已发作品基础与深度指标 | `douyin-engagement check/list/fetch/daily`，HTTP 接口取数，复用统一 API 账号 |
| 内容 DNA、创作、对标、图文分析 | 本包对应 workflow |
| 账号、作品、评论、搜索、媒体下载 | 一级技能 `douyin-hunter` |
| 视频转写与拆解 | `viral-chaser`，抖音视频下载委托 `douyin-hunter` |
| 点赞、收藏、评论、回复、私信、直播与 PK | `expert-bd` 包内互动工具 |

采集、expert-bd 互动、创作者发布和本人取数共用 douyin-login 的 API 会话；主站与创作者分别维护通道 token 和证书，不从浏览器 profile 拼接凭据。HTTP 入口不提供浏览器填表、草稿编辑或配乐选择。
