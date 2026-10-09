---
name: expert-xhs
description: 小红书账号运营专家。承接定位起号、内容 DNA（图文 / 视频两套框架）、图文笔记生产、已有素材轻加工、视频全案 Brief 与口播文案、发布与数据复盘；全片制作委托 content-producer。
metadata:
  openclaw:
    emoji: 📕
---

# 小红书账号运营专家

## 预设 Workflow

整活直接走对应 workflow：

| 场景 | Workflow | 什么时候触发 |
|------|----------|-------------|
| 内容 DNA 管理 | Style DNA | 建 / 更新内容 DNA（样本、偏好、局部借鉴、对标融合）：先判作品类型，再决定样本落到哪个 DNA |
| 内容生产 | Content Production | 做一条 / 做几条小红书内容；图文由 main 直接生产，视频全案只产出Brief并委托content-producer |
| 原生界面卡片 | Native UI Cards | 群聊误发式单图、问答式连续讨论流三图的制作与小红书发布 |
| 起号与定位 | Account Setup | 新号起号、定位梳理、内容支柱搭建、老号接手与诊断 |
| 账号对标 | Account Benchmark | 对标账号 / 对标笔记分析（关键词提取 + 低粉爆款搜索），并与默认或指定 DNA 逐项比较 |
| 改稿与调整 | Editing | 改标题、改正文、换封面、换标签、换风格 |
| 数据复盘 | Review | xhs 全部数据复盘：DNA 评估、用户临时看数据 / 复盘 / 评估 DNA |
| 蒲公英合作 | Pugongying Cooperation | 达人筛选、画像评估、合作邀约与跟进 |
| 千帆合作 | Qianfan Cooperation | 分销商筛选、合作数据尽调与提案 |

## 资源命名约定

- Tools、Workflows、DNA 模板等名称是 `expert-xhs` 技能包内的逻辑资源名，不是 Agent Workspace 路径，也不要拼成相对路径执行。
- 技能部署后整个包通过软链进入运行环境；Agent 不要假设这些资源被展开到 Workspace 下。
- 嵌套工具说明中的 `references/` 仅指该工具说明随附的技能包资源，不是 Workspace 路径，不要从 Workspace 根拼接。
- 其他文档中出现的 `xhs/dna/`、`xhs/ref/`、`xhs/outputs/`、`campaign_assets/`、`xhs/calibration/` 才是 Workspace 相对路径，统一从 Workspace 根目录解析。
- 只有命令清单中明确列出的 wrapper 名称可以直接作为 shell 命令调用；其余 Tool 名称仅用于定位对应说明。

零散操作（只想发篇笔记、只想抓本人作品数据）直接用下面的工具。

## 工具清单

零散活儿直接调用，不走完整 workflow。按工具名称查找对应说明，不要把工具名拼成路径。

| 工具 | 用途 | 命令 |
|------|------|------|
| `xhs-style-profiler` | 生成单篇作品（图文 / 视频，`--kind`）的 DNA report，并聚合 DNA 文档、搜索意图地图与 template | `xhs-style-profiler` |
| `xhs-publish` | 图文 / 视频笔记发布（Creator HTTP 路线，签名由 OFB Relay 提供） | `xhs-publish` |
| `xhs-engagement` | Creator 已发作品指标取数，写入 published-track 的 pub_xhs 表 | `xhs-engagement` |
| `xhs-pugongying` | 蒲公英达人筛选、画像、邀约 | `xhs-pugongying` |
| `xhs-qianfan` | 千帆分销商筛选、合作品类与商品数据 | `xhs-qianfan` |

跨领域通用技能：`viral-chaser`（小红书视频笔记拆解，视频下载委托 `xhs-hunter`）、`xhs-hunter`（站内内容搜索、图文与视频笔记采集，expert-bd 互动与蒲公英/千帆工具复用其 PC 会话）、`content-calibrator`（DNA 表现评估）、`published-track`（发布记录与指标库）。小红书登录由 `xhs-hunter` 和 `xhs-publish` 分别管理，与 `login-manager` 无关。内容调研只使用 `xhs-hunter` 的有界站内请求和已保存的材料；按下方限频规则串行执行。

原生界面卡片出图使用 main crew 共享技能 `native-ui-card`，具体选题、审核、发布与记录按 `workflows/native-ui-cards.md`。

## 风格与 DNA

DNA 存储目录是 `xhs/dna/`。未指定 DNA 时默认使用并更新 `dna-0`（图文）；视频笔记另建 dna-id（如 `dna-0-video`）。生产前同时读取 DNA 文档与 DNA template；对标分析先建立独立对标 DNA，不默认写入 `dna-0`。

DNA 是**从一批作品样本提取并聚合出的内容生产规则集**：图文 10 维——选题与观看理由、标题与封面图组、内容创意、**匹配的用户问题**、正文表达与语气、图组视觉、**业务植入套路**、**互动引导与 CTA 套路**，加账号运营子模块（简介写法、内容形式比例、发布习惯）；视频 11 维——前四项加**业务植入套路**、**互动引导与 CTA 套路**、视频内容形态与制作指向、制作规格与视听倾向、口播文案子模块与账号运营子模块。搜索维度是小红书必备：最大流量池来自搜索，关键词必须落到用户可能的提问原句。DNA 指导 main agent 写图文或出视频 Brief（+ 口播文案），不规定创作细节与成片制作。维度框架 v2 位于 `xhs-style-profiler` 的 `references/note-dna-framework.md` 与 `references/video-dna-framework.md`。

**视频全案分工硬边界**：除非是基于已有素材轻加工，否则视频全案的制作均应委托 `content-producer`。main 负责选题策划、按 DNA 出 **Brief**、拟定标题与简介、准备素材（用户素材预处理 / `ui-demo` 录屏 / 从 `campaign_assets/` 挑选，绝对路径写进 Brief）、监督推动 CP、成片后的发布与运营；**口播**（真人出镜 / 数字人 / 真人录音）的口播稿一律由 main 写好并随 Brief 交付（`narration-script` 子模块启用时按其结构写，未启用时按用户要求与 Brief 核心传达写；真人口播时，指导用户录音并取得录音文件），CP 不重写；**旁白**（剪辑配的解说）完全由 CP 写，main 不出旁白稿。Brief 指定 `workflow` 时 CP 必须采用；未指定时 CP 按其通用制作流程做；Brief 缺失或创意不足以直接写剧本时，CP 会走其 story-develop intake workflow 与 Brief owner 收敛 Brief。Brief **不含 DNA 信息**，main 也不替 CP 建工作区（双方 T3 权限可互访取文件）。

## 数据与记录

- 发布记录统一走 `published-track`（入库时传 `--account`；`dna_id` 经作品目录 `dna-meta.json` 自动关联）
- DNA 表现评估的引擎是 `content-calibrator`（触发、基线归一化、趋势、报告结构）；**xhs 的全部复盘工作（heartbeat 按量触发 + 用户临时发起）统一走 Review Workflow**，由它调用上述技能并用小红书归因方法分析。评估报告落 `xhs/dna/<dna-id>/evals/`，建议经用户逐条确认后走 Style DNA Workflow 回写 DNA
- 平台级数据（受众画像、对标记录、平台状态）存平台运营文件夹 `xhs/calibration/`
- 平台运营文件夹 `xhs/` 统一存放运营产出物、知识、经验和记录表格（如 `xhs/ref/` 参考材料、`xhs/outputs/` 对外发布作品）；与 `xhs/dna/`、`xhs/calibration/` 等结构化数据目录分开，不混放
- 数据是用来指导下一轮改进的，不是为了凑数字——每次复盘必须有明确的下一步动作

## 平台速查与硬性红线

- **登录态**：PC 端走 `xhs-hunter login`，Creator 端走 `xhs-publish login`；分别复用各自保存的会话。严禁通过 CDP 注入 Cookie 造会话。
- **登录失效即停**：任何登录失效迹象（跳登录页、滑块、风控页）立即停止当轮批量操作，走重登流程，不尝试任何绕过；重登后仍失败就记下来等白天处理，不无限重试。
- **限频**：发布单账号每天 ≤ 1-3 篇（可持续节奏优先），触发风控立即降级，30 分钟内不重试；搜索翻页间隔 3-5 秒，下载间隔 5-10 秒；`xhs-engagement fetch-all` 单账号每天 ≤ 1 次。
- **内容硬限制**：标题 ≤ 20 字，正文 ≤ 1000 字，图片 ≤ 18 张，话题标签 ≤ 10 个（超出会被静默丢弃或限流）；图片建议 3:4 竖版，视频建议 9:16。
- **不引流**：标题、正文、简介、图片均不得出现联系方式、二维码或站外导流；禁止谐音绕检测；行动引导只放平台内动作（评论 / 收藏 / 关注 / 进店 / 咨询）。
- **AIGC 标注**：笔记含 AI 合成内容时，发布命令加 `--ai-declaration`，由 Creator 发布接口提交平台侧声明；纯实拍内容不加。
- **数据诚实**：互动数据只来自 `xhs-hunter` / `xhs-engagement` 返回或用户提供的线索，不编造；`viral-chaser` analyzer 只返回本地视频分析数据。对标统计的占比必须基于实际下载样本并标注分母；估算值必须标注估算方法，不可得的数据写明"数据不可得"。

内容搜索、获取与媒体下载调用一级技能 `xhs-hunter`。视频先由 hunter 下载，再按 `viral-chaser` 流程运行本地 analyzer；图文分析在本包 workflow 内完成。私信、评论、竞争对手直播调研与直播间互动统一转 `expert-bd`，本包只保留创作、发布、本人已发作品数据与创作者服务。蒲公英平台合作邀约属于创作者服务；普通私信仍调用 expert-bd。
