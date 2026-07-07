# IT Engineer Agent - Memory

## 内置运维知识

### 权限策略

- **内 crew（main / content-producer / it-engineer）**：`command-tier: T3` + 清空 `ALLOWED_COMMANDS` → `exec-approvals.json` 给 full allowlist。
- **对外 crew（sales-cs）**：`command-tier: T0` + 显式 `ALLOWED_COMMANDS` 白名单 → prompt injection 防线。

### skill 依赖策略

#### 镜像预装常用包

内置技能所需依赖已经在部署环境中。

#### awada 插件依赖（ws + zod）

- **Docker 部署**：Dockerfile wiseflow-layer 阶段 `COPY awada/ + npm install --omit=dev`，ws+zod 烘进 `/opt/openclaw/awada/node_modules`。
- **源码部署**：`apply-addons.sh` 自动 `cd awada && npm install --omit=dev`（哈希守卫 `.awada-pkg-hash`，幂等）。
- **关键点**：awada 插件运行时从自身 `awada/node_modules` 解析 ws/zod，**不**走 `~/.openclaw/node_modules`（不在向上解析链），故必须装在 awada 局部，不能靠统一依赖扫描。
- **Phase 4 已完成**（2026-07-07）：awada 改 HTTP/WS transport 调 relay 网关，ioredis 已从 deps 移除，预装步骤改装 ws+zod。proactive-send skill 同步迁 HTTP 网关，不再依赖 ioredis。
- **IT engineer 介入时机**：仅当日志报 `Cannot find module 'ws'`（plugin=awada）且上述预装漏跑时，按 `awada-channel-setup` SKILL 步骤 1 手动补装。

#### volume 扩展

- 用户额外装 skill 时的依赖路径：
  - **Python**：`pip install --target ~/.openclaw/skills/<skill>/vendor/ <pkg>`（PYTHONPATH 由 `docker-entrypoint.sh` 注入）
  - **Node**：`cd ~/.openclaw/skills/<skill> && npm install <pkg>`（局部 `node_modules`）
- 重启不丢（volume 持久化）

#### 依赖安装规范

- **何时装**：
  - skill 报错 `ModuleNotFoundError: No module named 'xxx'` → 装 xxx 到该 skill 的 vendor
  - skill 报错 `Cannot find module 'xxx'`（Node）→ 装 xxx 到该 skill 局部 node_modules
- **何时**不**装**：
  - skill 内 import 但镜像已预装（按镜像预装策略） → 检查 image 是否完整 / 用户是否漏装
  - 通用依赖（如 requests、Pillow）应已在镜像，不需用户装
- **依赖冲突处理**：
  - **Python**：vendor 目录是隔离的（每个 skill 独立），不冲突；如果跨 skill 同名不同版本需求 → 各自装各自的 vendor
  - **Node**：局部 node_modules 可能与全局 openclaw 依赖冲突 → 用 `npm install --save-prefix=~` 避免锁到特定 patch 版本
- **it-engineer 介入**：
  - 用户报告"skill 不能用" → 1）查 `~/.openclaw/logs/gateway-error.log` 2）确认 `pip list --target ~/.openclaw/skills/<skill>/vendor/` 或 `ls ~/.openclaw/skills/<skill>/node_modules/` 3）按需装
  - **不**主动更新 skill 自带的依赖版本（避免破坏 skill 兼容性）
- **特殊场景**：
  - **镜像重建后**（用户重 deploy Docker 镜像）→ 镜像预装的包恢复；vendor 目录在 volume 持久化不受影响
  - **本机源码部署**（非 Docker）→ 直接 `pip install <pkg>` 到系统 Python 即可（无 vendor 隔离需要），或者按 volume 扩展模式到 skill 子目录

### camoufox-cli 排故

- **指纹模板 bake**（Docker 镜像内）：`/root/.openclaw/logins/_template/camoufox-cli.json`，由 `Dockerfile wiseflow-layer` 阶段跑 `camoufox-cli --session _template --persistent --headless open about:blank` 生成。
- **运行时模板复用**：每个 agent session 启动前 `cp /root/.openclaw/logins/_template/camoufox-cli.json ~/.camoufox-cli/profiles/<session>/`。
- **约束**：不 fork camoufox-cli / 不 bake chromium / 每 agent 一 session / 独立 profile dir / 独立 cookie state。
- **常见问题**：
  - `camoufox-cli open` 超时 → `camoufox-cli close --all` 清残留 + 重试
  - `qr-confirm` 轮询不到成功 → 用户手机上确认后再说；不要盲等超过 `--timeout`（默认 180s）
  - `cookie-import` 后访问仍 401 → cookies 过期 / 域不匹配；重新走登录流
  - daemon 残留 → `camoufox-cli close --all` 兜底；每任务结束必须 `session-cleanup`

### 运行数据中openclaw.json中禁止更改的项目

如下`openclaw.json`中的项目严格禁止更改，如果如果用户明确要求更改，你也应向他解释理由，并再三征得确认：

- browser模块：本系统已经对浏览器的使用做过优化，默认会使用camoufox-cli，Browser tool是作为托底手段去处理反爬特别严格的站点，openclaw.json中整个browser部分的配置已经是针对这种场景下的最佳配置。

### LLM 模型参数约束(火山方舟 awk provider)

#### GLM 5.2 系列(模型 id `glm-latest` / 其他 GLM 5.2 变体)

- **Provider 端点**:`https://ark.cn-beijing.volces.com/api/coding/v3`(provider alias `awk`)
- **实际 max_tokens 上限**:**128000**
- **模型卡 / 官方文档标的**:131072(**这是 GLM 模型本身的能力上限**,但火山方舟 `coding/v3` 端点把它截到 128000)
- **错误症状**:所有请求 `400 The parameter 'max_tokens' specified in the request are not valid: integer above maximum value, expected a value <= 128000, but got 131072 instead`
- **openclaw.json 正确配置**:`maxTokens: 128000`

### 某个 agent 全报 "Something went wrong"处置方案

1. **看 gateway-error.log**(`/home/wukong/wiseflow-pro/logs/gateway-error.log`),找 `embedded run agent end: isError=true` + 紧跟的 `error=LLM request failed` 行。
2. **看 sessions.json 里那个 agent 的 modelOverride**(`~/.openclaw/agents/<agent>/sessions/sessions.json`,key 是 `agent:<agent>:feishu:direct:<user_ouid>`):
   - 如果有 `modelOverride` + `modelOverrideSource: "user"` → 说明之前 `/model <xx>` 把会话锁死在那个模型上了。
   - **修复**:用户在该 agent 对话里发 `/model <默认主模型>`,或 IT Engineer 删掉 sessions.json 里的 `modelOverride/providerOverride/modelOverrideSource` 三个字段(注意先 `cp` 备份 `.bak-<日期>`)。
   - **原因**:用户用 `/model` 切换是持久化的,`/new` 不会清。
3. **如果错误是 `max_tokens` 超过 provider 上限**:改 `openclaw.json` 里那个模型的 `maxTokens`。注意备份,hot-reload 通常生效。

### ⚠️ 重大警告：`pnpm openclaw <subcommand>` 会触发 build，在运行中的 Gateway 上使用会掏空系统

**防范规则（勿犯）**：

1. **永远不要在生产 Gateway 运行中调用 `pnpm openclaw <任何子命令>`**，包括看起来“只读”的 `cron list`、`cron show`、`cron runs`、`config get` 等。只要走 `pnpm openclaw` 入口，都会触发 build。
2. **查询/操作 cron、config、会话状态、系统状态都走 MCP 工具**：
   - cron 查询/增删改 → `cron` MCP 工具（不触发 build，不写 dist）
   - config 查询/修改 → `gateway` MCP 工具的 `config.get` / `config.patch` / `config.apply`
   - 会话状态 → `sessions_list` / `sessions_history` / `session_status`
3. **如果实在需要走 CLI**：优先看项目里的 `dist/` 是否已 build 过且是热的，可以直接 `node dist/index.js <subcommand>` 跳过 npm script 的 build wrapper；但在生产上也不推荐。
4. **对话里跟用户呈现任何 cron/config 信息**：走 MCP 工具拿到结果。

**反例（禁止）**：
```bash
cd /home/wukong/wiseflow-pro/openclaw && pnpm openclaw cron list
cd /home/wukong/wiseflow-pro/openclaw && pnpm openclaw config get
cd /home/wukong/wiseflow-pro/openclaw && pnpm openclaw doctor --fix
# 以上三条都会触发 build，都是雷区。
```

**正例（推荐）**：
```
MCP cron 工具调用，action="list" / "get" / "add" / "update" / "remove" / "run" / "runs"
MCP gateway 工具调用，action="config.get" / "config.patch" / "config.apply" / "restart"
```

| 需求 | 工具 |
|------|------|
| cron 查询 / 增删改 / 运行历史 / 手动触发 | `cron` MCP 工具 |
| config 查询 / 修改 / 应用 / 重启 Gateway | `gateway` MCP 工具 |
| 会话 查询 / 历史 / 状态 / 送信 / spawn | `sessions_list` / `sessions_history` / `session_status` / `sessions_send` / `sessions_spawn` |
| 节点 / 文件传输 / 调用 | `nodes` / `file_fetch` / `file_write` / `dir_list` / `dir_fetch` |
| 技能架库 增删改查 | `skill_workshop` |

### ⚠️ OpenClaw binding routing 的关键坑

**坑 1：binding 不写 `accountId` 时不会"通配所有 account"** — `src/routing/resolve-route.ts` 里的 `normalizeBindingMatch` 把没填的 `match.accountId` 视为 `""`（`DEFAULT_ACCOUNT_ID` = `"default"`），路由查找时只匹配 `accountId="default"` 的请求。**没有匹配的 binding 时回退到 `resolveDefaultAgentId` = default agent（main）**，看起来 binding 写了但消息还是去 default agent。

**正确做法**（任何 binding 改 channel 路由都要写 `accountId`）：
- 想通配所有 account：用 `"accountId": "*"`（会进 `byAnyAccount` 桶）
- 想精确匹配某个 account：用具体 account id

**坑 2：routing 缓存 `resolvedRouteCacheByCfg` 不会因 SIGUSR1 hot-reload 重置** — 它是 `WeakMap<OpenClawConfig, ...>`，基于 cfg 对象引用判断，hot-reload 不换 cfg 引用所以不重置。改 binding 后必须用 `systemctl --user restart openclaw-gateway.service` 完整重启（这会断所有 session，因此执行前必须告知用户并征得同意）。

**坑 3：sessions.json 中的旧 session entry 会"劫持"新消息** — openclaw 看到有 `(channel, peer) → sessionId` 的 entry 直接复用，agent 也按 entry 里绑的来，跟 binding 无关。改 binding 之前/之后都要查 `agents/<agent>/sessions/sessions.json` 把这个 entry 删掉，否则即使 binding 改对了，session 缓存仍把消息路由回旧 agent。

### 定时任务(Cron)维护方案

> **v2026.6.6 起**:cron 存储已从 JSON 文件迁移至 SQLite,**禁止再编辑任何 JSON 文件**。

#### 存储变更

| 项目 | 旧方案(已废弃) | 新方案(当前) |
|------|------------------|----------------|
| Job 定义 | `~/.openclaw/cron/jobs.json` | SQLite 表 `cron_jobs` |
| 运行时状态 | `~/.openclaw/cron/jobs-state.json` | SQLite 同表内字段 |
| 运行日志 | `~/.openclaw/cron/runs/*.jsonl` | SQLite 表 `cron_run_logs` |
| 数据库位置 | - | `~/.openclaw/state/openclaw.sqlite` |

旧文件已被 `doctor --fix`（上游升级后一次性迁移，由用户手动调用）重命名为 `.migrated` 后缀,数据已导入 SQLite。`.migrated` 文件可安全删除。

> ⚠️ **生产 Gateway 运行中，不得调用 `pnpm openclaw cron ...` / `node dist/index.js cron ...` 任何 CLI 入口**。它会触发重新 build 并写运行中 Gateway 共享的 `dist/`，多次连续调用可能导致系统崩溃。一律走 MCP `cron` 工具。

**正确姿势（MCP `cron` 工具，零 build、零 dist 写入）**：

```
# 查看所有定时任务
cron(action="list")

# 查看某个任务详情
cron(action="get", jobId="<job-id>")

# 新增定时任务（完整 schema 见工具描述：schedule 、payload、delivery、sessionTarget 等）
cron(action="add", job={
  "name": "任务名",
  "agentId": "<agent-id>",
  "schedule": {"kind": "cron", "expr": "0 8 * * *", "tz": "Asia/Shanghai"},
  "payload": {"kind": "agentTurn", "message": "任务描述"},
  "sessionTarget": "isolated",
  "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_xxx"}
})

# 启用 / 禁用
cron(action="update", jobId="<job-id>", patch={"enabled": true})
cron(action="update", jobId="<job-id>", patch={"enabled": false})

# 修改投递目标
cron(action="update", jobId="<job-id>", patch={
  "delivery": {"mode": "announce", "channel": "feishu", "to": "user:ou_xxx"}
})

# 修改模型覆盖
cron(action="update", jobId="<job-id>", patch={
  "payload": {"model": "provider/model"}
})

# 删除任务
cron(action="remove", jobId="<job-id>")

# 手动触发一次（默认仅在到期时走，加 runMode="force" 立刻触发）
cron(action="run", jobId="<job-id>", runMode="force")

# 查看运行历史
cron(action="runs", jobId="<job-id>", limit=20)
```

#### 直接查询 SQLite（只读排查用）

SQLite 只读查询不会触发 build，安全。但 **不得直接 UPDATE/INSERT/DELETE `cron_jobs` 表**，会跟 MCP 的状态机、`job_json` 冲突。

```bash
# 列出所有 job 及关键字段
sqlite3 ~/.openclaw/state/openclaw.sqlite \
  "SELECT job_id, name, schedule_expr, enabled, delivery_mode, delivery_channel, delivery_to FROM cron_jobs;"

# 查看最近运行记录
sqlite3 ~/.openclaw/state/openclaw.sqlite \
  "SELECT job_id, seq, datetime(ts/1000, 'unixepoch', 'localtime') as time, status, error FROM cron_run_logs ORDER BY ts DESC LIMIT 20;"
```

修改、增删都走 MCP `cron` 工具，**不允许手工 SQL 修改这些表**。

#### 迁移操作（如需要）

1. 读取`~/.openclaw/cron/job.json` 文件，获取目前的定时任务配置。
2. 按上使用`cron`MCP工具进行配置。

#### 重要提醒

1. **禁止手动编辑** `~/.openclaw/cron/` 下的任何 JSON 文件,它们已不再被运行时读取
2. **禁止手动 UPDATE/INSERT/DELETE** SQLite 中 `cron_jobs` / `cron_run_logs` 表；必须走 MCP `cron` 工具，CLI 会同时更新结构化列和概念上的 `job_json` 快照
3. cron 运行在 Gateway 进程内,修改后立即生效,无需重启

---

## 运行中持续积累的经验
