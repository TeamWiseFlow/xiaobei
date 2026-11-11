---
name: expert-osbi
description: 开源商业智能（OSBI）专家。从公开信源提取、跟踪和分析商业信息，承接信源情报、竞对动向、公开直播调研及市场/基金/技术研究。原始搜索与内容获取按平台使用文中列出的采集技能和公共 smart-search；潜客探索、互动与联络交 expert-bd，融资推进交 expert-ir。
metadata:
  openclaw:
    emoji: 🔎
---

# 开源商业智能（OSBI）

这里的“开源”指公开信息源。先明确研究问题、对象、范围与交付形式，再取证、提取、交叉核实和分析；已有任务说明充分时直接执行。

## Workflow 路由

| 任务 | Workflow |
|---|---|
| 按账号、网页或订阅源提取情报、生成简报 | [Intel Gathering](workflows/intel-gathering.md) |
| 跟踪竞品、重点客户或其他对象的公开动向 | [Competitor Watch](workflows/competitor-watch.md) |
| 研究公开直播的商品、促销、话术证据和观众反馈 | [Live Research](workflows/live-research.md) |
| 市场规模、竞品比较、基金尽调、技术与供应商研究 | [Market Research](workflows/market-research.md) |

默认执行一次性任务。用户明确要求周期执行时才按 [scheduling.md](scheduling.md) 配置监控；不因“跟踪”一词自动建定时任务。

## 原始资料获取

- 平台搜索、账号、作品、评论、提醒和下载按平台调用：抖音 `douyin-hunter`、小红书 `xhs-hunter`、TikTok `tiktok-hunter`、快手 `kuaishou-hunter`、X `x-hunter`、微博 `weibo-hunter`、微信公众号 `wx-mp-hunter`。以各技能实际能力为准；不在本包重复实现平台请求或浏览器回退。
- YouTube 公开视频、频道、评论、播放列表、媒体下载和直播聊天用 `youtube-hunter`，公开读取免登录；通知与个人列表按其登录说明执行。
- 其他网页与站点搜索调用公共 `smart-search`，页面操作遵循 `browser-guide`。微信视频号目前没有搜索与内容获取方案。
- 公开直播读取与有界监听使用 `douyin-hunter live` / `xhs-hunter live` / `tiktok-hunter live` / `kuaishou-hunter live` / `youtube-hunter live`。事件样本不等于口播转写或完整直播历史。
- 通用 RSS/Atom 订阅解析使用本包 `rss-reader`；它只处理公开 feed，不替代 `douyin-hunter` / `xhs-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter` / `wx-mp-hunter`，不向其拼入平台 Cookie。

## 工具与数据

| 工具 | 用途 | 说明 |
|---|---|---|
| `info-record` | 情报去重、记录、按日查询 | [工具说明](tools/info-record/SKILL.md)；保留 Workspace `db/info_record.db` |
| `rss-reader` | 解析公开 RSS/Atom 订阅源 | [工具说明](tools/rss-reader/SKILL.md)；依赖由统一安装器安装 |

潜客探索与筛选转 `expert-bd` 的 Lead Hunting workflow；画像、线索档案、互动去重、发送记录和后续跟进由 BD 管理。

报告、证据索引和中间产物保存到 Workspace `osbi/`，直播证据保存到 `osbi/live/<platform>/<日期时间>-<room_id>/`。数据库路径不随技能迁移改变，既有记录按原库读取。

包内资源通过本 SKILL.md 所在目录定位；只把已列出的 wrapper 名称作为命令，不拼 Workspace 技能路径。数据库不存在时调用对应 wrapper `init-db`，不要直接执行 sqlite3。

## 分析与交接

- 每个重要论断附原始链接和证据；记录发布日期、采集时间和样本范围。缺失、截断、过时或无法核实的信息明确标注。
- 需交付真实原帖/网页截图、可读裁切或供创作引用的证据包时，读取 `browser-guide` 的 `references/source-evidence.md`；保留未改动原件与来源，平台原始资料仍按上述采集技能获取。
- 分开写事实、推断和建议。平台宣传、个别评论和短时直播样本不直接代表实际功能、整体需求或长期表现；冲突来源与反面证据一并保留。
- 研究发现需联络时，将目标完整 ID/链接、相关原文、判定理由和建议话题交 `expert-bd` 的 Interaction workflow。发现潜客、读取评论或收到事件均不授权发送。
- 基金尽调和融资研究交 `expert-ir` 用于材料与融资推进；本包不推进融资状态、不代发邮件。
- 内容创作、发布、本人已发作品指标及 DNA 复盘仍走对应平台专家包；本包不改用户业务知识或平台 DNA。
