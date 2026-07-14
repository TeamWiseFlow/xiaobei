# Workspace Bootstrap 文件机制

> 版本基准：openclaw v2026.4.11

每个 crew 的 workspace 目录（`~/.openclaw/workspace-<id>/`）下存放着一系列 Markdown 文件，openclaw 在每次 agent 运行时将它们注入系统提示，从而影响 agent 的行为、人格和记忆。本文档说明各文件的作用、加载时机，以及 wiseflow 在标准机制之上做的扩展约定。

---

## 一、标准 Bootstrap 文件（openclaw 原生）

openclaw 共识别 8 个标准文件，**按以下顺序依次注入系统提示**：

| # | 文件名 | 作用摘要 | 内容来源 |
|---|--------|----------|----------|
| 1 | `AGENTS.md` | 工作区总规则：会话启动流程、记忆管理策略、安全红线、平台格式规范、心跳行为等 | 框架自动生成模板，**用户（或 crew template）定制** |
| 2 | `SOUL.md` | Agent 核心人格：价值观、行为准则、工作风格、边界定义 | 框架生成模板，**用户（或 crew template）定制** |
| 3 | `TOOLS.md` | 本地工具配置备忘：摄像头别名、SSH 主机名、TTS 偏好音色等——技能（SKILL.md）定义"怎么用"，TOOLS.md 记录"你的环境具体是什么" | 框架生成空白模板，**用户在运行中维护** |
| 4 | `IDENTITY.md` | Agent 身份名片：名字、形象（AI/机器人/other）、性格基调、专属 emoji、头像路径 | 框架生成模板，**首次 bootstrap 时由 agent 与用户共同确认** |
| 5 | `USER.md` | 用户信息：姓名/称呼、时区、偏好、背景笔记 | 框架生成模板，**首次 bootstrap 时由 agent 填写** |
| 6 | `HEARTBEAT.md` | 心跳轮询任务清单：agent 在 heartbeat 时依照此文件执行周期性检查 | 框架生成空白模板，**agent 运行中自主维护** |
| 7 | `BOOTSTRAP.md` | 首次运行仪式：引导 agent 确定身份、了解用户、选择接入渠道（**一次性文件**） | 框架自动生成，**agent 首次运行完成后自动删除** |
| 8 | `MEMORY.md` | 长期记忆：跨会话保留的精华信息（仅在主会话加载，防止隐私泄露到群聊/子 agent） | **用户/agent 自主创建和维护**，初始不存在 |

> `memory.md`（小写）为 `MEMORY.md` 的备用名，两者同时存在时优先加载 `MEMORY.md`。

---

## 二、加载时机与过滤规则

### 2.1 主会话（用户直接发起的对话）

加载**全部 8 个文件**（存在时）。

### 2.2 子 agent 会话（`sessions_spawn` 唤起的 subagent）和 Cron 会话

只加载**最小集合**，以减少 token 消耗：

| 文件 | 是否加载 |
|------|---------|
| AGENTS.md | ✓ |
| SOUL.md | ✓ |
| TOOLS.md | ✓ |
| IDENTITY.md | ✓ |
| USER.md | ✓ |
| HEARTBEAT.md | ✗（排除） |
| BOOTSTRAP.md | ✗（排除） |
| MEMORY.md | ✗（排除，防隐私泄露） |

### 2.3 Heartbeat 会话（周期性心跳轮询）

在最小集合基础上**额外加载 HEARTBEAT.md**，但仅当该 agent 是配置了心跳的默认 agent 时生效。

若开启了 `heartbeat.lightContext: true`，则心跳会话只加载 `HEARTBEAT.md`，其余文件全部排除（极致节省 token）。

### 2.4 Continuation-skip 优化

当 `agents.defaults.contextInjection = "continuation-skip"`（非默认）时，首轮 bootstrap 完成后的后续 turn 跳过文件注入，减少 prompt 缓存失效。默认值 `"always"` 表示每次 turn 都注入。

---

## 三、大小限制

| 限制项 | 默认值 | 配置键 |
|--------|--------|--------|
| 单文件最大磁盘读取 | 2 MB | 硬编码 |
| 单文件注入最大字符数 | 20,000 字符 | `agents.defaults.bootstrapMaxChars` |
| 所有文件合计最大字符数 | 150,000 字符 | `agents.defaults.bootstrapTotalMaxChars` |

超出单文件限制时内容被截断，并根据 `bootstrapPromptTruncationWarning` 配置决定是否向 agent 发出警告。

---

## 四、BOOTSTRAP.md 生命周期

1. **首次部署时**：框架自动创建 `BOOTSTRAP.md`，记录状态到 `.openclaw/workspace-state.json`
2. **首次对话**：agent 读取 `BOOTSTRAP.md`，与用户完成身份确认（名字、性格、渠道接入等），更新 `IDENTITY.md`、`USER.md`、`SOUL.md`
3. **仪式完成后**：agent **删除** `BOOTSTRAP.md`，框架将 `workspace-state.json` 中的 `setupCompletedAt` 置为当前时间
4. **后续运行**：`BOOTSTRAP.md` 不再存在，框架不会重新生成

---

## 五、MEMORY.md 安全约定

`MEMORY.md` 仅在主会话（用户直接一对一对话）中加载，**不会**注入群聊会话、子 agent 会话或 cron 会话。这是为了防止包含敏感个人信息的长期记忆在开放环境（如 Discord 群组、多人 Telegram 群）中泄露。

agent 应在 `AGENTS.md` 中明确记录此约定：

```markdown
### 🧠 MEMORY.md - 长期记忆
- **仅在主会话（与用户直接一对一）加载**
- **不在群聊、子 agent、外部对话中加载**（安全隔离）
```

---

## 六、xiaobei 扩展文件（非 openclaw 原生）

以下文件是 xiaobei 的约定扩展，**openclaw 框架不会自动处理**，由脚本或 agent 按需读取后写入 `openclaw.json`。

### 6.1 DECLARED_SKILLS — 外部 crew 技能白名单

| 属性 | 说明 |
|------|------|
| 适用 crew 类型 | 对外 crew（T0，如 sales-cs） |
| 作用 | 声明该 crew 被允许使用的技能，**只有声明的技能才可使用** |
| 使用方 | `add-agent.sh`（`hrbp-recruit` 脚本底层）读取，写入该 agent 的 `openclaw.json` `agents.list[].skills` |
| 格式 | 每行一个技能名，`#` 开头为注释 |

外部 crew 采用**最小权限原则**：不继承全局技能基线，只能使用 `DECLARED_SKILLS` 中明确列出的技能。这防止对外服务的 agent 意外访问内部工具。

### 6.2 BUILTIN_SKILLS — 内部 crew 扩展技能

| 属性 | 说明 |
|------|------|
| 适用 crew 类型 | 对内 crew（T1/T2，如 selfmedia-operator、business-developer、designer） |
| 作用 | 列出该 crew 在公共基线之上额外需要的专属技能 |
| 使用方 | `setup-crew.sh`（初始安装/升级）或 `recruit-internal-crew.sh`（Main Agent 招募新内部 crew）读取，合并到公共基线后写入 `agents.list[].skills` |
| 格式 | 每行一个技能名，无需重复列入公共基线中已有的技能 |

**公共基线**（所有内部 crew 都有的技能）由 `config-templates/openclaw.json` 中各 agent 配置定义，通常包括：`nano-pdf`、`skill-creator`、`session-logs`、`tmux`、`weather`、`summarize`、`self-improving` 等。

### 6.3 DENIED_SKILLS — 显式排除技能

| 属性 | 说明 |
|------|------|
| 适用 | 所有 crew |
| 作用 | 从候选技能列表中强制排除某些技能，防止误配置 |
| 使用方 | `add-agent.sh` 在构建 `agents.list[].skills` 时移除此列表中的技能 |
| 典型用途 | 排除 `github`/`gh-issues`/`coding-agent`（IT 专用）、商务拓展专属技能（非 BD crew）等 |

### 6.4 ALLOWED_COMMANDS — 精确命令放行

| 属性 | 说明 |
|------|------|
| 适用 | 对外 crew（T0） |
| 作用 | 在 T0（默认拒绝所有 shell 命令）基础上，精确允许特定脚本路径 |
| 格式 | `+<相对于 workspace 的路径>` |
| 典型用途 | 放行 `./skills/customer-db/scripts/*.sh`、`./skills/payment_send/scripts/*.sh` 等声明式技能脚本 |

---

## 七、各 Crew 文件配置速查

> **2026-07-04 修订（D8 扁平化 + D19 权限放开）**：从 Pro 仓 addons 层级结构改为 client 仓扁平结构。原 `hrbp` / `selfmedia-operator` / `business-developer` / `designer` 全部合入 `main`（AI 搞钱搭子「小贝」）。`main` / `content-producer` / `it-engineer` 升为 T3 full，`sales-cs` 维持 T0。（产品拆分决策已落地，历史规划文档已清理，可从 git 历史恢复。）

### 内置 Crew（对内，T3 full — D19 已落）

| Crew | 角色 | 特殊文件 | 备注 |
|------|------|---------|------|
| `main` | DEFAULT — AI 搞钱搭子「小贝」（OPC / 中小微企业老板） | 标准 8 个文件 | 整合原 selfmedia-operator + business-developer + IR 三模式；绑 openclaw-weixin |
| `content-producer` | 内容制作（视频 / 图像） | 标准 8 个文件 | 整合原 video-producer + designer |
| `it-engineer` | sub-agent，无 channel | 标准 8 个文件 + D19/D20/部署运维知识（注入到 MEMORY 顶部） | Phase 8.1 记忆注入已完成（2026-07-04） |
| `_template` | crew 创建模板 | 标准 8 个文件 | D8 扁平化时搬入 |

### 外部 Crew（对外，T0 — D19 维持）

| Crew | 角色 | 特殊文件 | 备注 |
|------|------|---------|------|
| `sales-cs` | 销售客服 | 标准 8 个文件 + `DECLARED_SKILLS` + `ALLOWED_COMMANDS` | 默认 seed 不在 openclaw.json；绑 awada（启用时由 IT 改 enabled+软链 `business_knowledge/`） |

---

## 八、Crew 自查清单

在实例化或调试 crew 时，可以按以下清单检查：

- [ ] `AGENTS.md` 是否有明确的 Session Startup 流程（读取 SOUL.md、USER.md、MEMORY.md 等）？
- [ ] `SOUL.md` 是否设置了正确的 `crew-type`（`internal` 或 `external`）？
- [ ] `IDENTITY.md` 是否已填写（或留有填写指引）？
- [ ] `HEARTBEAT.md` 是否只包含必要的周期性任务（保持小而精，避免 token 浪费）？
- [ ] `BOOTSTRAP.md` 是否是一次性文件，首次运行后是否删除？
- [ ] 对外 crew：`DECLARED_SKILLS` 是否存在且内容完整？
- [ ] 对内 crew：`BUILTIN_SKILLS` 是否列出了所有专属技能（不包含公共基线已有的技能）？
- [ ] `DENIED_SKILLS` 是否排除了不适合此 crew 的全局技能？
- [ ] 对外 crew：`ALLOWED_COMMANDS` 是否只放行了声明式技能所需的脚本？
