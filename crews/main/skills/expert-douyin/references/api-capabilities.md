# 抖音能力路由

| 业务 | 调用 |
|---|---|
| 创作者登录、发布前检查 | `douyin-publish login/check`，Camoufox 持久化 session `douyin` |
| 视频发布、分步取链 | `douyin-publish video`；分步工具 `douyin-video-publish` |
| 图文发布、配乐、取链 | `douyin-publish note`；分步工具 `douyin-note-publish` |
| 本人已发作品基础与深度指标 | `douyin-engagement check/list/fetch/daily`，HTTP 接口取数，临时复用发布 profile 的 cookie/UA |
| 内容 DNA、创作、对标、图文分析 | 本包对应 workflow |
| 账号、作品、评论、搜索、媒体下载 | 一级技能 `douyin-hunter` |
| 视频转写与拆解 | `viral-chaser`，抖音视频下载委托 `douyin-hunter` |
| 点赞、收藏、评论、回复、私信、直播与 PK | `expert-bd` 包内互动工具 |

hunter 与 expert-bd 使用 `douyin-hunter` 包内 `douyin-login` 的独立 API 会话，创作者发布/取数另用浏览器 profile。不能将两套登录互相覆盖，也不能使用已停用的 API 发布命令。
