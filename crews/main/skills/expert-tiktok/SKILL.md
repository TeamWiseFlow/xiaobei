---
name: expert-tiktok
description: TikTok账号运营、起号定位、视频/图文内容 DNA、制作 Brief、发布与本人作品复盘；采集走 hunter，互动走 expert-bd。
metadata:
  openclaw:
    emoji: 🎬
---


# TikTok账号运营

| 任务 | Workflow |
|---|---|
| 起号、定位、老号诊断 | [Account Setup](workflows/account-setup.md) |
| 样本风格、DNA 建立与更新 | [Style DNA](workflows/style-dna.md) |
| 内容生产与发布 | [Content Production](workflows/content-production.md) |
| 原生界面图组 | [Native UI Cards](workflows/native-ui-cards.md) |
| 账号/作品对标 | [Account Benchmark](workflows/account-benchmark.md) |
| 已有作品修改与再制作 | [Editing](workflows/editing.md) |
| 本人作品指标与复盘 | [Review](workflows/review.md) |

工具：`tiktok-publish` 发布，`tiktok-engagement` 本人取数回填，`tiktok-style-profiler` 定性 DNA。读取本包 tools 下对应说明，通过 wrapper 调用，不拼工作区技能路径。内容搜索、账号与作品/评论读取、通知和媒体下载使用一级 `tiktok-hunter`。私信、评论、点赞、收藏、关注与直播统一走 expert-bd；未实现的动作明确说明缺口。

登录使用 `tiktok-hunter login/export`，会话由共享运行库管理。写会话准备与 `--require-write` 导出按 hunter 说明执行。视频样本先 hunter 下载，再运行 viral-chaser；文字和图文由本包回读正文与有序图组。读取与写入均需真实账号验收。用户搜索未实现；user get 仅给 secUid 时不能取得完整资料。notice list/count、收藏夹、合集、推荐与关注流可读。本人已发作品指标通过专家 engagement 获取。写操作需要同次 ticket-guard 材料。

运营资料存 `tiktok/ref/`、`tiktok/outputs/`、`tiktok/calibration/`，DNA 存 `tiktok/dna/`。默认 dna-0 为 视频，其他形态另建 ID。生产前读取 DNA 文档与 template；单篇借鉴按 focus 明确作用范围。未经用户确认不把对标规则写回默认 DNA。

视频全案由 content-producer 制作；main 负责选题、Brief、标题简介、素材与口播稿，CP 负责旁白与制作。已有素材轻加工可用 video-edit/talking-head-cut，完成后检查成品。Brief 不含 DNA 信息，写清素材绝对路径、授权范围、验收标准与闸门批准人。

所有发布返回真实作品 ID/URL 后记录 published-track，保留账号 alias 和 dna-meta.json。复盘只用实际指标，缺项不补零；没有创作者服务 API 时不宣称商业合作、收入、画像或后台管理能力。需要平台 AI 声明而接口未支持时交用户在原平台完成发布。
