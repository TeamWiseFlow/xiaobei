# Workspace Bootstrap 文件机制

版本基准：OpenClaw **2026.10.4**。文件列表和会话过滤以 `openclaw/src/agents/workspace-bootstrap-policy.ts`、`workspace.ts` 为准；本机实际配置可能限制注入大小或采用不同的 contextInjection 策略。

## 文件职责

| 文件或章节 | 职责 | 维护方式 |
|---|---|---|
| `AGENTS.md` | 工作流程、决策树、操作步骤、派工时必须生效的约束 | crew 模板提供默认值，实例保留用户定制 |
| `AGENTS.md` 的 `## Tools` 节 | 本机路径、环境变量名称、工具别名和本地约定 | 按实际部署维护，不保存密钥值，不重复 SKILL.md 手册 |
| `SOUL.md` | 角色、价值观、行为边界 | 不放工具路径和操作步骤 |
| `IDENTITY.md` | 名字、形象类型、性格基调、emoji、头像 | 不放职责和能力清单 |
| `USER.md` | 服务对象、称呼、偏好等用户信息 | 按授权维护，避免堆积长篇业务资料 |
| `BOOTSTRAP.md` | 一次性首次运行引导 | 有采集需求才创建，完成后删除 |
| `MEMORY.md` | 跨会话保留的背景事实、业务知识、历史决策 | 不写必须每次执行的流程或工具调用规范 |
| `memory/YYYY-MM-DD.md` | 当日日志和详细记录 | 按任务需要读取，不属于固定自动注入列表 |
| 各技能的 `SKILL.md` | 该技能的操作手册 | 由 agent 使用技能时按需读取 |

独立 **`TOOLS.md` 已退役**，不在自动加载列表中。模板和安装脚本不得重新生成它。旧版本遗留的 `TOOLS.md` / `HEARTBEAT.md` 由用户升级后手动删除；setup 不负责迁移、归档或清理。

`HEARTBEAT.md` 已退役，运行时不读取，仓内不再提供或部署该文件的模板。心跳频率、活跃时段与通知目标仍由 `agents.defaults.heartbeat` / `agents.entries.<id>.heartbeat` 定义，检查清单存入共享 SQLite 的 monitor scratch；独立周期业务通过原生 Automations 管理。

新安装配置模板不预置 main 的心跳任务，统一以 `agents.defaults.heartbeat.every="0m"` 关闭默认心跳，避免回退到上游的 30 分钟周期。需要启用时，由 IT Engineer 按用户需求配置指定 agent 的心跳频率、活跃时段和通知目标。

main 原心跳模板已移入 `content-calibrator/references/scheduled-review.md`，供用户开启定时取数时参考；main 交 IT 将用户选定的执行内容写入独立 Automation 或其显式引用的 workspace 任务说明。销售客服主动跟进按 `sales-cs-manager` 的 Follow-up Scheduling workflow 配置，不默认启用，也不重建 HEARTBEAT.md。

## 自动加载范围

普通会话的候选顺序为：AGENTS.md、SOUL.md、IDENTITY.md、USER.md、BOOTSTRAP.md、MEMORY.md。不存在的可选文件、隐私过滤、大小限制和 contextInjection 策略会影响最终上下文。

| 文件 | 私密主会话 | 群聊 / 频道 | 子 agent | Cron |
|---|---|---|---|---|
| AGENTS.md | ✓ | ✓ | ✓ | ✓ |
| SOUL.md | ✓ | ✓ | — | ✓ |
| IDENTITY.md | ✓ | ✓ | — | ✓ |
| USER.md | ✓ | ✓ | — | ✓ |
| BOOTSTRAP.md | 存在时 | 存在时 | — | — |
| MEMORY.md | ✓ | — | — | — |
| TOOLS.md / HEARTBEAT.md | — | — | — | — |

**子 agent 只自动加载 AGENTS.md。** 派工所需的工作流程和约束写在该文件或本次任务说明里；本机环境备忘放在其 Tools 节。需要角色信息、技能手册或部署路径时，在授权范围内显式读取对应文件，不假设 SOUL.md、OFB_ENV.md 或 MEMORY.md 已注入。

MEMORY.md 的“主会话”指本 agent 的私密主会话，不限于 agentId=main。不要为补充子 agent 上下文而自动读取其他 crew 的私人记忆。

## 大小与注入策略

| 限制 | 默认值 | 配置 |
|---|---|---|
| 单文件最大注入字符数 | 20,000 | `agents.entries.<id>.bootstrapMaxChars`，回退到 `agents.defaults.bootstrapMaxChars` |
| 总注入字符数 | 60,000 | `agents.entries.<id>.bootstrapTotalMaxChars`，回退到 defaults |
| USER.md 额外上限 | 4,000 | 不能通过提高通用限制突破 |

合并 Tools 后要检查 AGENTS.md 的总长度；不要把技能全文复制到其中，也不要盲目提高所有 agent 的预算。被截断的内容不能视为已加载。

`contextInjection` 支持 agent 覆盖 defaults；`always`、`continuation-skip`、`never` 的实际效果以当前配置为准。“文件存在”“属于候选列表”和“本轮确实注入”是不同事实。

## 首次引导与运行状态

BOOTSTRAP.md 只承担一次性用户信息采集。完成后将用户资料写入 USER.md、长期事实写入 MEMORY.md、本机环境备注写入 AGENTS.md 的 Tools 节，再删除 BOOTSTRAP.md。无需采集时不保留空占位文件。

工作区初始化状态在共享 SQLite 中；旧 workspace-state JSON、attestation sidecar 和会话 JSONL 是迁移输入，不应继续当作本版运行状态手工维护。

- 共享状态：`<stateDir>/state/openclaw.sqlite`。
- agent 持久化：`<stateDir>/agents/<agentId>/agent/openclaw-agent.sqlite`。
- 旧会话迁移归档：`<stateDir>/agents/<agentId>/session-sqlite-import-archive/`。

## setup-crew 的职责

`scripts/setup-crew.sh` 部署模板和技能、同步声明、生成配置及环境备忘；不执行引擎构建或重启 Gateway。

- 新模板直接包含 AGENTS.md 的 Tools 节，不携带 TOOLS.md 或 HEARTBEAT.md。
- internal crew 的文件编辑、exec、真实换行、会话文件约定及 Docker 运行约束写入 AGENTS.md。`workspace-guides.py` 生成的换行、exec 和 Python 提示每次按标题删除旧段落后重写，不检查标题存在就跳过，不做逐条对齐；段落外的用户正文保留。external crew 的回复、媒体发送、文件编辑、exec 和真实换行规范直接写在模板中，不由脚本追加，也不注入 Technical Issue Dispatch Protocol 或 sessions_spawn 规范。
- 已部署工作区不整文件覆盖；模板正文的更新不等于实例自定义正文已被替换。`--force` 是覆盖选项，不能用于日常迁移用户资料。
- setup 不迁移、归档或删除旧 TOOLS.md / HEARTBEAT.md，也不为它们触发 Doctor；旧文件由用户升级后手动删除。
- internal crew 模板不写 `### Python 环境`。每次 setup 由统一 internal workspace 入口清理旧标记区块及同名 Python 段落，再在 AGENTS.md 的 `## Tools` 节末尾生成唯一一份，填入实际自管路径；其他 Tools 备注保留，没有 Tools 节时自动补齐。该过程覆盖新建、既有及尚未注册的 internal 工作区；Python configure 使用同一生成器。需要独立依赖的临时任务 spawn IT Engineer 使用同一自管解释器准备任务环境。
- 提示生成器不处理 external crew；其完整规范直接由模板维护。sales-cs 等 external 模板明确禁止自行创建、修改或执行 Python 脚本，缺少能力时写 `feedback/YYYY-MM-DD.md`，不要求其创建 IT Engineer 子 agent。旧实例的提示由维护者按需调整，原有共享业务知识路径迁移与技能、命令白名单同步继续保留。
- 源码部署的 OFB_ENV.md 记录安装路径和 dotenv 位置；IT 从 AGENTS.md 获知该文件后按需读取。
- 业务知识正文为 main workspace 的 `business_knowledge/business_knowledge.md`，其他 crew 只共享 `business_knowledge/` 目录软链。setup 与 `sales-cs-enablement link` 共用迁移脚本：备份旧正文、修正迁移后的相对链接和工作区文档引用、移除指向旧正文的文件软链；新旧正文冲突或目标已有真实目录时保留原状并报错。

## 系统运维与渠道归属

IT Engineer 的日志审计、Automations、exec 审批、插件生效与会话维护手册在 `crews/it-engineer/skills/openclaw-maintenance/`。AGENTS.md 保留派工入口和必须生效的边界，具体步骤按该技能的参考表读取；MEMORY.md 不复制操作手册。该 crew 专属技能由现有 workspace 技能扫描加入可见列表，不放入只声明上游技能的 BUILTIN_SKILLS。

新安装的 config template 将 `agents.defaults.systemAgent.agentId` 指向 it-engineer；IT 的模板与 BUILTIN_SKILLS 声明包含四个 Custodian 运维技能。setup 仅在 owner 未指定时补 IT，不覆盖实例已有明确选择。systemAgent 选择系统推理使用的模型/凭据及 Custodian 技能库归属，不替代聊天 binding、heartbeat.agentId 或 talk.agentId。

该 pin 的 `tryResolveLegacyCompatibilityAgentId` 还会将显式 systemAgent 作为未匹配消息的兼容兜底；不能仅凭 ownership=explicit 就宣称所有未绑定请求都会拒绝。已有精确 binding 优先，工作渠道启用时必须明确账号归属。

微信 onboarding 在模板和 setup 中统一为一条 `openclaw-weixin + accountId="*" → main`，以接收插件登录生成的不同账号。飞书等工作渠道按启用流程写具体 accountId，不预置 `feishu + "*" → main`。已部署实例的 binding 不因 setup 被清理或改写；上游 Doctor 为保留旧 default agent 行为生成的兼容规则需按实例路由另行审阅。

## 项目扩展文件

以下属于 xiaobei 安装约定，不是原生自动 bootstrap 文件。

| 文件 | 用途 |
|---|---|
| `DECLARED_SKILLS` | 对外 crew 的技能白名单 |
| `BUILTIN_SKILLS` | 对内 crew 在公共基线之外声明的专属技能 |
| `DENIED_SKILLS` | 排除不适用的技能 |
| `ALLOWED_COMMANDS` | 对外 crew 在 deny 基础上通过 `+` 条目声明可执行脚本 |
| `OFB_ENV.md` | IT 的本机部署路径和环境文件备忘 |

技能列表最终写入 `agents.entries.<id>.skills`。内部 crew 通常使用 exec full，外部 crew 按声明采用 allowlist 或 deny；实际审批数据由原生存储管理，不手改运行数据库来扩大权限。公共技能基线以 `scripts/lib/agent-skills.sh` 为准，不能继续引用已移除的 session-logs。

## Crew 模板检查

- AGENTS.md 是否能独立表达子 agent 完成任务所需的工作流程与边界？
- 本机路径和工具别名是否收在其 Tools 节，工具操作是否仍指向具体 SKILL.md？
- 模板和生成器是否不再创建 TOOLS.md / HEARTBEAT.md，setup 是否不再承担旧文件迁移或清理？
- SOUL.md 的 crew-type、技能声明及执行命令声明是否与 crew 实际职责一致？
- MEMORY.md 是否只保留长期背景事实，私人记忆是否未被自动带入子 agent / Cron？
- BOOTSTRAP.md 是否确有一次性采集需求，完成后是否移除？
- 周期任务是否已在 Cron 中核验，合并后的 AGENTS.md 是否在实际注入预算内？
