---
name: expert-kuaishou
description: 快手账号运营、起号定位、视频/图文内容 DNA、制作 Brief、发布与本人作品复盘；采集走 hunter，互动走 expert-bd。
metadata:
  openclaw:
    emoji: 🎬
---


# 快手账号运营

| 任务 | Workflow |
|---|---|
| 起号、定位、老号诊断 | [Account Setup](workflows/account-setup.md) |
| 样本风格、DNA 建立与更新 | [Style DNA](workflows/style-dna.md) |
| 内容生产与发布 | [Content Production](workflows/content-production.md) |
| 原生界面图组 | [Native UI Cards](workflows/native-ui-cards.md) |
| 账号/作品对标 | [Account Benchmark](workflows/account-benchmark.md) |
| 已有作品修改与再制作 | [Editing](workflows/editing.md) |
| 本人作品指标与复盘 | [Review](workflows/review.md) |

工具：`kuaishou-publish` 发布，`kuaishou-engagement` 本人取数回填，`kuaishou-style-profiler` 定性 DNA。读取本包 tools 下对应说明，通过 wrapper 调用，不拼工作区技能路径。内容搜索、账号与作品/评论读取、通知和媒体下载使用一级 `kuaishou-hunter`。私信、评论、点赞、收藏、关注与直播统一走 expert-bd；未实现的动作明确说明缺口。

视频接口仅覆盖空简介、私密、立即发布的测试分支，仍需本机实号验收；正式公开视频或带标题/正文/话题的视频交用户在原平台完成。图集可按发布工具的参数与授权执行。发布错误先看脱敏诊断，不能把裸 UPSTREAM 直接归因于新号风控或建议删除 unknown 收据重发。

登录由 kuaishou-hunter login 管理。视频样本先 hunter 下载，再运行 viral-chaser；文字和图文由本包回读正文与有序图组。作品搜索不支持 --sort/--type/--time。关注流只有首屏，user likes/followers/following 只支持 me。二级评论参数覆盖有限；notice count 只有总数。400002、验证码或风控应停止并报告，不能当空数据或登录失效。

运营资料存 `kuaishou/ref/`、`kuaishou/outputs/`、`kuaishou/calibration/`，DNA 存 `kuaishou/dna/`。默认 dna-0 为 视频，其他形态另建 ID。生产前读取 DNA 文档与 template；单篇借鉴按 focus 明确作用范围。未经用户确认不把对标规则写回默认 DNA。

视频全案由 content-producer 制作；main 负责选题、Brief、标题简介、素材与口播稿，CP 负责旁白与制作。已有素材轻加工可用 video-edit/talking-head-cut，完成后检查成品。Brief 不含 DNA 信息，写清素材绝对路径、授权范围、验收标准与闸门批准人。

所有发布返回真实作品 ID/URL 后记录 published-track，保留账号 alias 和 dna-meta.json。复盘只用实际指标，缺项不补零；没有创作者服务 API 时不宣称商业合作、收入、画像或后台管理能力。需要平台 AI 声明而接口未支持时交用户在原平台完成发布。
