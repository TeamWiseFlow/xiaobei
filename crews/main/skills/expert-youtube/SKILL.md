---
name: expert-youtube
description: YouTube 频道定位、视频和 Shorts 创作 Brief、本人已上传作品指标复盘与频道创建。搜索和下载使用 youtube-hunter，互动使用 expert-bd；暂不提供自动视频发布或删除。
metadata:
  openclaw:
    emoji: 🎬
---

# YouTube 频道运营

内容调研用 `youtube-hunter` 搜索视频、频道、评论与播放列表，视频拆解用 hunter 下载后交 `viral-chaser`。建立 `youtube/ref/`、`youtube/outputs/`、`youtube/calibration/` 保存原始样本、产出与真实指标；缺少频道定位、受众或发布目标时先根据已知业务整理草案，确认后再保存长期运营策略。

你负责选题、标题简介、结构与制作 Brief；视频全案交 content-producer。Brief 写清成片比例/时长、素材绝对路径、口播与视觉目标、授权范围和验收标准。Shorts 以实际内容形式识别，不只凭时长推断；标题、简介和封面分别准备。

本人作品取数与指标入库使用 [youtube-engagement](tools/youtube-engagement/SKILL.md)。已有 Google 账号需要开频道时用 [youtube-channel](tools/youtube-channel/SKILL.md)，不因 user get me 失败就自动开频道。登录由 `youtube-hunter login/export` 管理。

自动视频上传、发布、定时发布、封面设置和视频删除尚未接入。将已准备好的素材与文案交用户在 YouTube Studio 完成；拿到真实作品链接后使用 `published-track record --platform youtube` 记录，再由 youtube-engagement 取数。需要平台 AI 声明时在 Studio 完成，不宣称脚本已设置。收益、留存曲线、受众画像等缺少接口的数据明确留空。

评论/回复、点赞、稍后观看、订阅和直播文字互动使用 `expert-bd`；公开直播与聊天读取仍使用 `youtube-hunter live`，本包不收纳这些写操作。
