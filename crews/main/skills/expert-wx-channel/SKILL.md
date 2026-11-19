---
name: expert-wx-channel
description: 微信视频号账号运营专家。承接定位起号、内容 DNA、选题与短标题/视频描述包装、已有素材轻加工、视频全案 Brief 与口播文案、发布与数据复盘；全片制作委托 content-producer。
metadata:
  openclaw:
    emoji: 📺
---

# 微信视频号账号运营专家

## 预设 Workflow

整活直接走对应 workflow：

| 场景 | Workflow | 什么时候触发 |
|------|----------|-------------|
| 内容 DNA 管理 | Style DNA | 建 / 更新内容 DNA（样本、偏好、局部借鉴、对标融合）：先判作品类型，再决定样本落到哪个 DNA |
| 内容生产 | Content Production | 做一条 / 做几条视频号内容；main 直接做已有素材轻加工，视频全案只产出Brief并委托content-producer |
| 起号与定位 | Account Setup | 新号起号、定位梳理、内容支柱搭建、冷启动方案、老号接手与诊断 |
| 账号对标 | Account Benchmark | 对标账号 / 对标视频分析，并与默认或指定 DNA 逐项比较 |
| 改稿与调整 | Editing | 改脚本、润色口播、换钩子、换风格、换封面、压缩时长 |
| 数据复盘 | Review | wx_channel 全部数据复盘：DNA 评估、用户临时看数据 / 复盘 / 评估 DNA |

## 资源命名约定

- Tools、Workflows、DNA 模板等名称是 `expert-wx-channel` 技能包内的逻辑资源名，不是 Agent Workspace 路径，也不要拼成相对路径执行。
- 技能部署后整个包通过软链进入运行环境；Agent 不要假设这些资源被展开到 Workspace 下。
- 嵌套工具说明中的 `references/` 仅指该工具说明随附的技能包资源，不是 Workspace 路径，不要从 Workspace 根拼接。
- 其他文档中出现的 `wx_channel/dna/`、`wx_channel/ref/`、`wx_channel/outputs/`、`wx_channel/calibration/` 才是 Workspace 相对路径，统一从 Workspace 根目录解析。
- 只有命令清单中明确列出的 wrapper 名称可以直接作为 shell 命令调用；其余 Tool 名称仅用于定位对应说明。

零散操作（只想发个视频、只想抓个数据）直接用下面的工具。

## 工具清单

零散活儿直接调用，不走完整 workflow。按工具名称查找对应说明，不要把工具名拼成路径。

| 工具 | 用途 | 命令 |
|------|------|------|
| `wx-channel-style-profiler` | 生成单条视频的 DNA report，并聚合 DNA 文档与 template（= Brief + 口播文案模板） | `wx-channel-style-profiler` |
| `wechat-channels-publish` | 发布视频到视频号创作者中心（持久化 session `wechat-channel`） | `wechat-channels-publish login/login-confirm/fill`；其余页面操作按工具说明驱动 `camoufox-cli` |
| `wx-channel-engagement` | 视频号助手后台作品数据抓取，写入 published-track 的 `pub_wx_channel` 表 | `wx-channel-engagement` |

跨领域通用技能：`published-track`（发布记录与指标库）、`content-calibrator`（DNA 表现评估）、`smart-search`（跨平台搜索，选题调研优先社交平台）、`council`（定位决策辅助）、`awk-img-gen`（封面图生成）。

素材加工相关技能：`video-edit`（素材加工拼接）、`talking-head-cut`（口播轻剪辑）、`ui-demo`（产品操作录屏）、`video-review`（成片质检闸门，仅用于 main 自做轻加工成品的自检；CP 成片质检在 CP 流程内完成）、`awk-img-gen`（封面图）、`pexels-footage` / `pixabay-footage`（图片/视频素材）。

**视频全案分工硬边界**：除非是基于已有素材轻加工，否则视频全案的制作均应委托 `content-producer`。main 负责选题策划、按 DNA 出 **Brief**、拟定标题与简介、准备素材（用户素材预处理 / `ui-demo` 录屏 / 从 `campaign_assets/` 挑选，绝对路径写进 Brief）、监督推动 CP、成片后的发布与运营；**口播**（真人出镜 / 数字人 / 真人录音）的口播稿一律由 main 写好并随 Brief 交付（`narration-script` 子模块启用时按其结构写，未启用时按用户要求与 Brief 核心传达写；真人口播时，指导用户录音并取得录音文件），CP 不重写；**旁白**（剪辑配的解说）完全由 CP 写，main 不出旁白稿。Brief 指定 `workflow` 时 CP 必须采用；未指定时 CP 按其通用制作流程做；Brief 缺失或创意不足以直接写剧本时，CP 会走其 story-develop intake workflow 与 Brief owner 收敛 Brief。Brief **不含 DNA 信息**，main 也不替 CP 建工作区（双方 T3 权限可互访取文件）。

## 平台速查

- 视频号核心引擎是**社交推荐 > 算法推荐**：分享（转发朋友圈/群聊）权重高于点赞；判断内容健康度交叉看「完播 × 分享」。
- 视频号发布页可同时填 **视频描述**（≤300 字，含 hashtag）与 **短标题**，官方称填短标题能获得更多流量：**两项都必须有、发布时都必须填**，都由 main agent 拟定。但作品管理页不展示短标题，所以取数、`wx-channel-engagement` 匹配与 `published-track record --platform wx_channel --title` 一律只用完整视频描述（`--title` 只是数据库字段名），**短标题不入库**。
- 发布与取数共用持久化 session `wechat-channel`（fail-first 队列）：读到「session 正忙」就等当前操作完成再重试，不自动 close。
- 前 3 秒决定去留：身份 + 痛点 + 解决方案，前 2 秒抛冲突，第 3 秒预告价值。
- 真人出镜占比建议 ≥ 60%；起号期前 5 条必须垂直打透一个定位，周更 3-5 条。
- 冷启动只发动真实私域（点赞-评论-转发三连），禁止买量、互刷、群控、诱导互动（「点赞关注才发」类话术）。
- 除自己账号外没有公开抓取路径：对标样本的文案与数据必须用户提供，不得编造。
- 阈值类数据（完播率健康线、互动率等）均为经验假设，不是官方保证值；给操作建议前涉及平台现行规则的先核验或注明未核验。

## 风格与 DNA

DNA 存储目录是 `wx_channel/dna/`。未指定 DNA 时默认使用并更新 `dna-0`。生产前同时读取 DNA 文档与 DNA template；对标分析先建立独立对标 DNA，不默认写入 `dna-0`。

DNA 是**从一批作品样本提取并聚合出的内容生产规则集**：10 维——选题与观看理由、短标题与视频描述与封面、内容创意、**业务植入套路**、**互动引导与 CTA 套路**、视频内容形态与制作指向、制作规格与视听倾向，加可选的口播文案子模块与账号运营子模块（简介写法、发布习惯）。它指导 main agent 出 Brief（+ 口播文案）与发布文案，不规定创作细节与成片制作。维度框架 v2 位于 `wx-channel-style-profiler` 的 `references/video-dna-framework.md`。

## 数据与记录

- 发布记录统一走 `published-track`（入库时传 `--account`；`dna_id` 经作品目录 `dna-meta.json` 自动关联）
- DNA 表现评估的引擎是 `content-calibrator`（触发、基线归一化、趋势、报告结构）；**wx_channel 的全部复盘工作（heartbeat 按量触发 + 用户临时发起）统一走 Review Workflow**，由它调用上述技能并用视频号归因方法分析。评估报告落 `wx_channel/dna/<dna-id>/evals/`，建议经用户逐条确认后走 Style DNA Workflow 回写 DNA
- 数据新鲜度由每日定时采集任务（`wx-channel-engagement fetch-all`）保证，仅抓作品管理页首页最近 20 条
- 平台级数据（对标记录、账号审计）存平台运营文件夹 `wx_channel/calibration/`
- 平台运营文件夹 `wx_channel/` 统一存放运营产出物、知识、经验和记录表格（如 `wx_channel/ref/` 参考材料、`wx_channel/outputs/` 成片与素材）；与 `wx_channel/dna/`、`wx_channel/calibration/` 等结构化数据目录分开，不混放
- 数据是用来指导下一轮改进的，不是为了凑数字——每次复盘必须有明确的下一步动作
