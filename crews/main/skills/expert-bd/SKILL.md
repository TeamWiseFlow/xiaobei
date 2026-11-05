---
name: expert-bd
description: 商务拓展与联络专家。承接潜客探索筛选、客户与合作方背景核验、评论回复、私信、邮件、点赞收藏关注、直播间互动、客户触达与联络记录。商业情报、竞对监控、直播调研及市场研究走 expert-osbi；公开资料按平台使用文中列出的采集技能或公共 smart-search，融资推进走 expert-ir。
metadata:
  openclaw:
    emoji: 💼
---

# 商务拓展与联络（BD）

## Workflow 路由

| 场景 | Workflow |
|---|---|
| 找客户、发布者画像匹配与评论区潜客筛选 | [Lead Hunting](workflows/lead-hunting.md) |
| 评论、私信、邮件与线索联络 | [Interaction](workflows/interaction.md) |
| 在指定公开直播间提问、答疑或拓展合作 | [Live Interaction](workflows/live-interaction.md) |

找客户和筛选潜客按本包 Lead Hunting 执行；已有目标时直接核对语境、授权和实际能力。商业情报、竞对调研和市场研究转 `expert-osbi`，研究结论用于本包后续拓展与联络。

## 工具清单

执行互动写操作前，先读 [互动能力表](references/interaction-capabilities.md) 与目标工具说明，以已实现接口为准。

| 工具 | 用途 |
|---|---|
| `email-ops`（公共技能） | 邮件起草、回复/跟进、会前会后沟通、合作提案与发送；先读取该技能 SKILL.md |
| 天眼查 CLI（外部可选工具，命令 `tyc`） | 企业工商、股权及风险查询，用于客户/合作方尽调和交易对手核验；先遵循下文安装与授权规则 |
| [bd-record](tools/bd-record/SKILL.md) | 线索与联络记录、帖子互动去重 |
| [douyin-interact](tools/douyin-interact/SKILL.md) | 抖音作品点赞、收藏、评论/回复及已支持的收藏夹操作 |
| [douyin-im](tools/douyin-im/SKILL.md) | 抖音文本、媒体和分享卡片私信及收信 |
| [douyin-live](tools/douyin-live/SKILL.md) | 抖音直播弹幕与点赞 |
| [xhs-im](tools/xhs-im/SKILL.md) | 小红书会话/历史、单聊文本、已读、撤回与删除 |
| [xhs-live](tools/xhs-live/SKILL.md) | 小红书直播文字评论与文字帧发送 |
| [twitter-interact](tools/twitter-interact/SKILL.md) | X 评论回复、点赞、转发、收藏与关注 |
| [twitter-im](tools/twitter-im/SKILL.md) | X 首页会话与加密占位历史查询；不支持发送 |
| [tiktok-interact](tools/tiktok-interact/SKILL.md) | TikTok 已支持的作品、评论、关注和收藏夹操作 |
| [tiktok-im](tools/tiktok-im/SKILL.md) | TikTok 已有会话文本私信、历史和监听 |
| [tiktok-live](tools/tiktok-live/SKILL.md) | TikTok 直播文字与点赞 |

`email-ops` 保持公共技能位置，按其 SKILL.md 规定的流程与脚本调用，不复制进本包。包内工具通过已列出的 wrapper 调用；包内资源按 SKILL.md 的位置定位，不拼 Workspace 技能路径。

## 企业背景核验：天眼查 CLI

需要查询客户、供应商、合作方或交易对手的企业背景时，可按需使用官方 `tyc-cli`，命令为 `tyc`。本项目通过 CLI 接入，不配置 MCP。CLI 默认不随项目安装，也不是本包其他能力的前置依赖。

### 安装与授权规则

1. **先检查本机**：执行 `command -v tyc`。已安装时直接复用现有 CLI 和登录配置执行查询，跳过安装问询，不重复展示额度、计费或安装提示。
2. **仅在未安装时，先展示额度与计费**：先阅读并向用户展示[免费额度与计费规则](https://www.tianyancha.com/ai/developer-docs#faq-quota)，说明当前免费日/月额度、不同会员的数据权益，以及额度用完后等待重置、升级会员或增购的方式。数值与权益以官方当前说明和账号实际配置为准；无法读取时提供该链接并说明无法确认最新额度，不编造价格或额度。完成上述说明后，再提供[官方 CLI 安装文档](https://www.tianyancha.com/ai/developer-docs#cli)，询问用户是否同意安装。
3. **得到明确同意后才安装**：执行 `npm install -g tyc-cli`。用户未同意或拒绝时不安装，也不通过 `npx` 临时下载执行；将企业背景核验标为未完成，继续任务中不依赖它的部分。安装同意不代表同意升级会员或购买额度。
4. **按实际需要登录**：查询返回未登录或认证失效时，用 `tyc login --no-open --no-block` 发起授权，向用户展示 CLI 返回的授权链接和验证码；用户在网页完成授权后，运行 `tyc login --resume`。登录中间状态由 CLI 自行保存，不手工复制 token 或拼接会话文件；不因认证失败重装 CLI。
5. **按需查询并记录结果**：只查任务需要的维度，优先复用本轮已有结果。额度不足或无对应数据权限时如实说明，按官方规则提示处理方式，不自动升级或购买；不要把无数据、无权限或查询失败写成“核验通过”。

具体查询示例见 [Lead Hunting](workflows/lead-hunting.md) 与 [Interaction](workflows/interaction.md)。输入使用已确认的企业全称或统一社会信用代码，不凭品牌名、账号昵称推断法律主体；主体无法确认时标为待核实。`tyc --help` 可查看命令；需要完整留存时，在同一次查询中加 `--output-file <Workspace内本次输出文件路径>`，先确保目标目录存在，避免为保存结果重复消耗查询额度。

## 获取互动语境

公开作品、评论、账号、提醒与媒体按平台使用：抖音 `douyin-hunter`、小红书 `xhs-hunter`、TikTok `tiktok-hunter`、快手 `kuaishou-hunter`、X `x-hunter`、微博 `weibo-hunter`、微信公众号 `wx-mp-hunter`。其他网页用 `smart-search` / `browser-guide`。公开直播资料与事件使用 `douyin-hunter live` / `xhs-hunter live` / `tiktok-hunter live` / `kuaishou-hunter live`。私信会话、历史及私信未读仍由本包 IM 工具读取，它们服务于会话联络。

抖音互动使用 `douyin-login` 独立 API 会话；小红书复用 `xhs-hunter` PC 会话，不混用 Creator 登录。TikTok 写入材料按 `tiktok-hunter` 登录说明核验。快手普通互动、私信与直播写操作未实现；微博互动写操作未实现。不要以浏览器操作补造未实现能力。

## 数据与边界

- 潜客画像、线索与帖子互动记录保留在 Workspace `db/bd_record.db`，通过本包 `bd-record` 初始化和去重；未联系的记录不能标为已联系。
- 联络草稿、结果与中间产物存 Workspace `bd/`；直播互动日志存 `bd/live/`。情报条目、研究报告与监控配置由 OSBI 管理。
- 每次写操作核对真实目标和既有授权；预览后仅执行已授权动作。接口提交、实际送达与对方回应分别记录；结果不明时先核实，不自动重发或换通道补发。
- 公开直播调研转 `expert-osbi`。本包不提供赠礼支付、主播后台开关播、禁言/踢人和商品管理。
- 内容创作、发布和本人作品数据转平台专家包；投资人关系、融资材料和项目申报转 `expert-ir`。
