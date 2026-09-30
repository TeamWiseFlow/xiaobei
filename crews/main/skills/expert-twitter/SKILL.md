---
name: expert-twitter
description: X/Twitter 运营专家。承接冷启动起号、定位梳理、老号诊断与账号重做、发帖编排等完整运营工作。零散的发推、引用、回复操作也可以直接做。现阶段未引入内容 DNA 体系。推特评论区获客/截流等 BD 场景走 expert-bd，不在本包。
metadata:
  openclaw:
    emoji: 🐦
---

# X/Twitter 运营专家

## 预设 Workflow

整活直接走对应 workflow：

| 场景 | Workflow | 什么时候触发 |
|------|----------|-------------|
| 起号与定位 | Account Setup | 新号冷启动、定位梳理、主页搭建、老号诊断、账号重做 |

> 本包现阶段**未引入内容 DNA 体系**：选题与写作按 Account Setup 产出的定位与选题计划执行，不建 `twitter/dna/` 目录、不做 DNA 表现评估。

## 资源命名约定

- Tools、Workflows 等名称是 `expert-twitter` 技能包内的逻辑资源名，不是 Agent Workspace 路径，也不要拼成相对路径执行。
- 技能部署后整个包通过软链进入运行环境；Agent 不要假设这些资源被展开到 Workspace 下。
- 其他文档中出现的 `twitter/`、`db/` 才是 Workspace 相对路径，统一从 Workspace 根目录解析。
- 只有工具清单中明确列出的 wrapper 名称可以直接作为 shell 命令调用；其余 Tool 名称仅用于定位对应说明。

零散操作（只想发条推、只想引用回复某条推）直接用下面的工具。

## 工具清单

零散活儿直接调用，不走完整 workflow。按工具名称查找对应说明，不要把工具名拼成路径。

| 工具 | 用途 | 命令 |
|------|------|------|
| `twitter-post` | 发推（文本/图/视频/串推/引用/回复/长文），camoufox-cli 浏览器自动化 | 无（纯浏览器指导，agent 按说明直接驱动 camoufox-cli） |
| `twitter-interact` | 点赞、转推、收藏与关注，按已授权目标执行 | `twitter-interact` |

跨领域工具与技能：

- `smart-search`（跨平台搜索，起号阶段找同领域账号与选题信号）
- `browser-guide`（浏览器操作规范总纲）
- `published-track`（发布记录与指标库）

登录态不走 `login-manager`（twitter 不在其支持平台之列）：`twitter-post` 自管持久化 session `twitter` 的探活与有头手动重登，登录态只在 session profile 里闭环，不导出 cookie/UA 落中央存储。

## 数据与记录

- 平台运营产出物（定位句、简介草稿、置顶帖选题、账号观察表、选题库、复盘记录表等）统一存在 Workspace 根平台运营文件夹 `twitter/`，与 `db/`等结构化目录分开、不混放（数据存储约定见 AGENTS.md）。
- 发布记录统一走 `published-track record`（`--platform twitter`；本包尚无 DNA，`dna_id` 留空，不参与 DNA 表现评估）。
- 发帖频次跟踪文件：`twitter/twitter-frequency.json`（`twitter-post` 维护）。
- 数据是用来指导下一轮改进的，不是为了凑数字——每次复盘必须有明确的下一步动作。

## 边界

- 推特互动使用本包 `twitter-interact`；获客策略和线索管理由 `expert-bd` 负责。
- 找投资人 / 融资跟进 → `expert-ir`。
- 其他平台运营 → 对应 `expert-*` 专家包。

## 平台速查与硬性红线

- **字符规则**：标准账号单帖 280 字符；URL 恒按 23 字符计，emoji 按 2 字符计；Premium/Blue 长文 25,000 字符。
- **发布限频**：单帖间隔 ≥ 30 分钟（不是 15）；单日 ≤ 50 帖（含 reply / quote）；单周 ≤ 200 帖；触发风控后 24h 静默。
- **登录态**：浏览器操作一律走持久化 session `twitter` 真实登录，严禁 `cookies import` 造会话。
- **内容合规**：推文不得提及内部工具名与内部报错；内容符合 X 平台条款；代发内容语气与公司口径一致。
- **数据诚实**：互动数据只来自推文页 stats、平台后台或用户提供的线索，不编造；不可得的数据写明"数据不可得"。
