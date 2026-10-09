---
name: expert-twitter
description: X/Twitter账号运营、起号定位、视频/图文内容 DNA、制作 Brief、发布与本人作品复盘；采集走 hunter，互动走 expert-bd。
metadata:
  openclaw:
    emoji: 🐦
---


# X/Twitter账号运营

| 任务 | Workflow |
|---|---|
| 起号、定位、老号诊断 | [Account Setup](workflows/account-setup.md) |
| 样本风格、DNA 建立与更新 | [Style DNA](workflows/style-dna.md) |
| 内容生产与发布 | [Content Production](workflows/content-production.md) |
| 原生界面图组 | [Native UI Cards](workflows/native-ui-cards.md) |
| 账号/作品对标 | [Account Benchmark](workflows/account-benchmark.md) |
| 已有作品修改与再制作 | [Editing](workflows/editing.md) |
| 本人作品指标与复盘 | [Review](workflows/review.md) |

工具：`twitter-post` 发布，`twitter-engagement` 本人取数回填，`twitter-style-profiler` 定性 DNA。读取本包 tools 下对应说明，通过 wrapper 调用，不拼工作区技能路径。内容搜索、账号与作品/评论读取和媒体下载使用一级 `x-hunter`。私信查询、评论、点赞、收藏与关注统一走 expert-bd；通知与直播未实现。

未订阅或未确认 X Premium 长推权限时，每条正文保持在280权重内（纯中文约140字，还需计入标点、链接等）。发布前检查 twitter-post 预览中的逐条权重和 warnings；超限先精简，不直接提交。帖串每条分别检查，不能自动拆帖；登录校验成功不等于有长推权限。

登录使用 `x-hunter login/export`，会话由共享运行库管理。视频样本先 hunter 下载，再运行 viral-chaser；文字和图文由本包回读正文与有序图组。只读与写接口仍需真实账号验收。媒体搜索 --type video/image 不支持 --sort latest；推荐流可读，关注流未实现。通知、粉丝/关注列表和收藏列表尚不支持。

运营资料存 `twitter/ref/`、`twitter/outputs/`、`twitter/calibration/`，DNA 存 `twitter/dna/`。默认 dna-0 为 文字/图文，其他形态另建 ID。生产前读取 DNA 文档与 template；单篇借鉴按 focus 明确作用范围。未经用户确认不把对标规则写回默认 DNA。

视频全案由 content-producer 制作；main 负责选题、Brief、标题简介、素材与口播稿，CP 负责旁白与制作。已有素材轻加工可用 video-edit/talking-head-cut，完成后检查成品。Brief 不含 DNA 信息，写清素材绝对路径、授权范围、验收标准与闸门批准人。

所有发布返回真实作品 ID/URL 后记录 published-track，保留账号 alias 和 dna-meta.json。复盘只用实际指标，缺项不补零；没有创作者服务 API 时不宣称商业合作、收入、画像或后台管理能力。需要平台 AI 声明而接口未支持时交用户在原平台完成发布。
