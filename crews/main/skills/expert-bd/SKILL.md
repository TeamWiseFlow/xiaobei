---
name: expert-bd
description: 商务拓展（BD）专家。承接找客户、评论区拓展、商业情报、竞对监控、竞争对手直播调研，以及抖音/小红书/TikTok/X评论、私信和公开直播调研互动、快手直播观察；内容采集调用一级 hunter，平台创作发布与本人作品数据走平台专家包。不涉及投资人关系。
metadata:
  openclaw:
    emoji: 💼
---

# 商务拓展（BD）专家

## 预设 Workflow

整活直接走对应 workflow：

| 场景 | Workflow | 什么时候触发 |
|------|----------|-------------|
| 潜在客户探索 | Lead Hunting | 按关键词搜索平台内容，策略 A 分析发布者画像 / 策略 B 评论区挖掘潜客，去重记录，可选触达 |
| 信息搜集/竞对监控/每日简报 | Intel Gathering | 监控指定信源（自媒体账号 / 网页），按预设标准提取商业情报，生成简报 / 报告 / 监控表格 |
| 竞争对手 / 重点客户动向监控 | Competitor Watch | 以对象为中心采集账号、网页与直播信源，识别动向并交付告警或简报 |
| 评论、私信与线索触达 | Interaction | 根据真实内容拟定互动、预览、执行已授权动作并记录结果 |
| 竞争对手直播调研 | [Live Research](workflows/live-research.md) | 观察竞品公开直播间的商品、促销、话术与观众反馈，形成有时间与来源的调研报告 |
| 直播间互动 | [Live Interaction](workflows/live-interaction.md) | 在指定公开直播间参与讨论、答疑或拓展合作，执行已授权的评论与点赞 |

## 执行方式与定时任务

所有 workflow 默认按**一次性任务**执行。**仅当用户明确希望周期性执行**时，才落为定时任务：写入模板、启用 / 停用流程与心跳批跑约束见包内 `scheduling.md`。不要主动建议或预填定时任务。

## 资源命名约定

- Tools、Workflows、`scheduling.md` 等名称是 `expert-bd` 技能包内的逻辑资源名，不是 Agent Workspace 路径，也不要拼成相对路径执行。
- 技能部署后整个包通过软链进入运行环境；Agent 不要假设这些资源被展开到 Workspace 下。
- 其他文档中出现的 `db/` 才是 Workspace 相对路径，统一从 Workspace 根目录解析。
- 只有工具清单中明确列出的 wrapper 名称可以直接作为 shell 命令调用；其余 Tool 名称仅用于定位对应说明。

零散操作（只想采个 RSS、只想搜个闲鱼商品、只想点赞关注）直接用下面的工具。

## 工具清单

零散活儿直接调用，不走完整 workflow。按工具名称查找对应说明，不要把工具名拼成路径。

| 工具 | 用途 | 命令 |
|------|------|------|
| `bd-record` | BD 线索 / 互动记录数据库（创作者探索 + 帖子互动去重） | `bd-record` |
| `info-record` | 情报条目数据库（采集去重 + 按日查询） | `info-record` |
| `rss-reader` | 发现并抓取网页 RSS/Atom feed | `rss-reader` |
| `xianyu-ops` | 闲鱼商品搜索 / 详情 / 私信 | `xianyu-ops` |
| `douyin-interact` | 抖音点赞/取消、收藏/取消、评论/回复及收藏夹迁移 | `douyin-interact` |
| `douyin-im` | 抖音私信会话、文本/媒体/分享卡片发送和收信 | `douyin-im` |
| `douyin-live` | 抖音公开直播调研与互动：事件、商品、榜单、PK、弹幕及点赞 | `douyin-live` |
| `xhs-im` | 小红书单聊/群聊查询、文本私信、已读、撤回与删除会话 | `xhs-im` |
| `xhs-live` | 小红书公开直播调研与互动：房间、商品、事件监听与文字评论 | `xhs-live` |
| `twitter-interact` | X点赞、转发、收藏、关注与评论回复 | `twitter-interact` |
| `twitter-im` | X最近20个会话与加密占位历史；不能发送 | `twitter-im` |
| `tiktok-interact` | TikTok点赞、收藏、关注、评论与收藏夹管理 | `tiktok-interact` |
| `tiktok-im` | TikTok已有会话文本私信、历史和监听 | `tiktok-im` |
| `tiktok-live` | TikTok公开直播调研与已授权文字/点赞 | `tiktok-live` |
| `kuaishou-live` | 快手公开直播、回放与事件观察；写操作未实现 | `kuaishou-live` |

内容搜索、详情、评论采集和下载统一调用一级技能 `xhs-hunter` / `douyin-hunter` / `tiktok-hunter` / `kuaishou-hunter` / `x-hunter` / `weibo-hunter` / `wx-mp-hunter`。小红书/抖音评论与 @ 提醒、点赞收藏提醒和新增关注通知也调用对应 hunter；私信会话、私信历史及私信未读查询仍使用本包 IM 工具。`smart-search` 只处理支持的其他平台；微信视频号目前没有内容获取方案。抖音互动使用 hunter 包内 `douyin-login` 的独立 API 会话，小红书互动复用 `xhs-hunter` PC 会话。创作、发布、本人作品数据与创作者服务分别走对应 `expert-xhs` / `expert-douyin` / `expert-tiktok` / `expert-kuaishou` / `expert-twitter`；微博发布走 weibo-publish。

跨领域通用技能：`browser-guide`（其他平台浏览器规范）、`email-ops`（邮件发送）。操作前读同包 `references/interaction-capabilities.md`，确认哪些可执行、哪些有条件、哪些尚不支持；不能把尚未真机验证当作已验收。

## 数据与记录

- BD 数据层只有两个库，都在 Workspace `db/` 下：`db/bd_record.db`（线索与互动）、`db/info_record.db`（情报条目），使用前如果数据库文件不存在，先调对应工具 `init-db`（幂等）初始化。
- 去重检查（`check-*`）必须在打开详情页 / 执行互动之前做。
- 定时批跑（仅用户启用后）只按用户已配置的策略执行并写入记录，不修改用户已建档的条目、不主动发起配置外的接触（完整约束见 `scheduling.md`）。
- 未有明确约定的文件、产出物以及中间产物，统一存放在 Workspace 根目录下的 `bd/` 文件夹下，不要散落在 Workspace 下。

## 边界

- 找投资人 / 融资材料 / 投资人跟进 → `expert-ir`。
- 项目申报 / 补贴 / 创业大赛 → `expert-ir` 专家包（Project Application Workflow）。
- X/Twitter 起号、定位、发帖编排走 `expert-twitter`，评论、回复、点赞、转发、收藏、关注和私信查询统一使用本包 twitter-interact/twitter-im。
- 抖音/小红书/TikTok/快手/X互动和直播工具统一归本包；没有实现的写操作明确说明能力缺口，不将网页读取或预览标为互动成功。
- 直播能力主要用于竞争对手调研与直播间互动；目标可以是自己的房间或他人的公开房间，以实际访问和发言权限为准。主播后台开关播、禁言/踢人和商品管理不在本包能力范围内。
