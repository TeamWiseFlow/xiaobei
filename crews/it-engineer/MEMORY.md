# IT Engineer Agent - Memory

## 产品拆分后运维知识（Phase 8.1 注入，2026-07-04）

> 本节是产品拆分（client + relay 双仓）后的运维速查。运维通用经验（pnpm build 警告 / binding routing / cron SQLite / ALLOWED_COMMANDS 等）见下方各原章节，本节只覆盖**产品拆分引入的**新运维面。

### D19 权限策略（已落代码，2026-07-03）

- **内 crew（main / content-producer / it-engineer）**：`command-tier: T3` + 清空 `ALLOWED_COMMANDS` → `exec-approvals.json` 给 full allowlist。
- **对外 crew（sales-cs）**：`command-tier: T0` + 显式 `ALLOWED_COMMANDS` 白名单 → prompt injection 防线。
- **Docker 内对内全放开**（消除 allowlist miss 摩擦），**对外保留白名单**。
- 验证：`/usr/local/bin/wiseflow-crew T <agent-id>` → 应看到 T3 / T0 + 解析后的白名单。

### D20 skill 依赖策略

#### D20① 镜像预装常用包（Phase 6 落地）

- `Dockerfile wiseflow-layer` 阶段按 `skills/`+`crews/` 实际 import 清单 pip 装进镜像：
  - requests / Pillow / xhshow / python-pptx / reportlab / tccli / google-api-python-client / google-auth-oauthlib 等
- 避免小白用户运行期 pip（小白场景是 Docker 部署态；本机源码部署场景下用户已有 Python 环境，但 D20① 仍适用）

#### D20② volume 扩展（Phase 6 落地）

- 用户额外装 skill 时的依赖路径：
  - **Python**：`pip install --target ~/.openclaw/skills/<skill>/vendor/ <pkg>`（PYTHONPATH 由 `docker-entrypoint.sh` 注入）
  - **Node**：`cd ~/.openclaw/skills/<skill> && npm install <pkg>`（局部 `node_modules`）
- 重启不丢（volume 持久化）

#### D20③ 依赖安装规范（it-engineer 介入准则）

- **何时装**：
  - skill 报错 `ModuleNotFoundError: No module named 'xxx'` → 装 xxx 到该 skill 的 vendor
  - skill 报错 `Cannot find module 'xxx'`（Node）→ 装 xxx 到该 skill 局部 node_modules
- **何时**不**装**：
  - skill 内 import 但镜像已预装（按 D20①） → 检查 image 是否完整 / 用户是否漏装
  - 通用依赖（如 requests、Pillow）应已在镜像，不需用户装
- **依赖冲突处理**：
  - **Python**：vendor 目录是隔离的（每个 skill 独立），不冲突；如果跨 skill 同名不同版本需求 → 各自装各自的 vendor
  - **Node**：局部 node_modules 可能与全局 openclaw 依赖冲突 → 用 `npm install --save-prefix=~` 避免锁到特定 patch 版本
- **it-engineer 介入**：
  - 用户报告"skill 不能用" → 1）查 `~/.openclaw/logs/gateway-error.log` 2）确认 `pip list --target ~/.openclaw/skills/<skill>/vendor/` 或 `ls ~/.openclaw/skills/<skill>/node_modules/` 3）按需装
  - **不**主动更新 skill 自带的依赖版本（避免破坏 skill 兼容性）
- **特殊场景**：
  - **镜像重建后**（用户重 deploy Docker 镜像）→ 镜像预装的包恢复；vendor 目录在 volume 持久化不受影响
  - **本机源码部署**（非 Docker）→ 直接 `pip install <pkg>` 到系统 Python 即可（无 vendor 隔离需要），或者按 D20② 模式到 skill 子目录

### 部署期 OpenClaw 源码同步

- **开发期**：openclaw 源码读 `~/wiseflow-pro/openclaw/`（已 clone，v2026.6.10 / aa69b12d）。
- **部署时**：把 openclaw 源码 copy 到本仓 `openclaw/` 目录（`.gitignore` 排除，install.sh 会读 `openclaw.version` 检出）。
- **软链方案**（D21）：本机开发实例可软链 `~/.openclaw/skills/<name>` → `<repo>/skills/<name>`，改 repo 即时生效；Docker 镜像维持 COPY（重建即更新）。

### login-manager 状态机（Phase 4.5.2 重写，2026-07-04）

- **中央存储**：`~/.openclaw/logins/{platform}.json`（camoufox-cli 原生 JSON 格式 = Playwright `add_cookies` 期望格式）。
- **平台常量**：`douyin` / `bilibili` / `kuaishou` / `xhs-publish` / `xhs-browse` / `weibo` / `zhihu` / `wechat-channels` / `wx-mp`（Phase 4.6 加）。
- **9 个子命令**（兼容 + 新增）：
  - 兼容（维持原 CLI 语义）：`check` / `read` / `write` / `status-all`
  - Phase 4.5+ 新增：`qr-headless` / `qr-confirm` / `cookie-export` / `cookie-import` / `session-cleanup`
- **退出码**：`0` 成功 / `1` 通用错误 / `2` cookie 失效或扫码超时 → 触发重新登录流程。
- **登录两步式**：`qr-headless <platform>`（启 headless + 截 QR PNG）→ 用户扫码后 `qr-confirm <platform> --session <s> --timeout 180`（轮询成功 + cookies 落中央）。
- **cookie 跨 session 污染 pitfall**：每个 agent 任务用新 session name（`secrets.token_hex(4)` nonce 唯一），不要跨任务复用。

### awada 启用（Phase 4 HTTP/WS 待实施）

- **当前路径**（D8 拍平后）：`<WISEFLOW_PROJECT_ROOT>/awada/`，**单层**结构（非 `awada/awada-extension/`）。通过 ioredis 直连 Redis。
- **目标路径**（Phase 4）：改 HTTP/WS transport + `X-OFB-Key` header：
  - `GET /api/v1/awada/outbound?lane=`（long-poll / WS 拉回复）
  - `POST /api/v1/awada/inbound`（agent 回复入）
  - relay 端点 = `RELAY_BASE_URL`（默认 `https://relay.wiseflow.example.com`）
- **运维动作**：
  - 启用：`awada-channel-setup` 技能（装依赖 → 写 openclaw.json → 重启 Gateway → 验证）
  - 排障：见 `crews/it-engineer/skills/awada-channel-setup/SKILL.md` 排障检查单

### camoufox-cli 排故（Phase 4.5 已落地）

- **指纹模板 bake**（Docker 镜像内）：`/root/.openclaw/logins/_template/camoufox-cli.json`，由 `Dockerfile wiseflow-layer` 阶段跑 `camoufox-cli --session _template --persistent --headless open about:blank` 生成。
- **运行时模板复用**：每个 agent session 启动前 `cp /root/.openclaw/logins/_template/camoufox-cli.json ~/.camoufox-cli/profiles/<session>/`。
- **D18 约束**：不 fork camoufox-cli / 不 bake chromium / 每 agent 一 session / 独立 profile dir / 独立 cookie state。
- **常见问题**：
  - `camoufox-cli open` 超时 → `camoufox-cli close --all` 清残留 + 重试
  - `qr-confirm` 轮询不到成功 → 用户手机上确认后再说；不要盲等超过 `--timeout`（默认 180s）
  - `cookie-import` 后访问仍 401 → cookies 过期 / 域不匹配；重新走登录流
  - daemon 残留 → `camoufox-cli close --all` 兜底；每任务结束必须 `session-cleanup`
- **资源**：`docs/camoufox-spike-2026-07.md`（spike 报告）/ `docs/phase-4.5-design.md`（设计骨架）/ `skills/browser-guide/SKILL.md` §0（主推章节）。

### 微信公众号 engagement 排故（Phase 4.6 方案 A 骨架，待 spike 验证）

- **新 skill**：`crews/main/skills/wx-mp-engagement/`（fetch_engagement.py + SKILL.md）。
- **新平台**：`login-manager` 加 `wx-mp`（中央存储 `~/.openclaw/logins/wx-mp.json`，登录页 `https://mp.weixin.qq.com/`，探活首页）。
- **集成点**：`published-track/fetch-and-update-metrics.sh` 加 `wx_mp` 平台路由（直接 exec `wx-mp-engagement.sh fetch --row-id $ROW_ID`），`MANUAL_PLATFORMS` 移除 `wx_mp`。
- **限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录），竞品号拿不到。
- **spike 验证**：等真机部署后由用户跑 `docs/wechat-mp-engagement-design.md` §七 的 10 项 checklist。
- **失败回退**：方案 A → B（容器内 mitmproxy + camoufox）→ C（维持 manual update）。

### 部署路径（2026-07-04 修订）

- **本机开发实例**：`~/wiseflow-pro` 仓 + `~/.openclaw/`（Pro 仓实例，仍在跑）。
- **本轮新仓**：`~/wiseflow`（client 仓，master 分支，D8 扁平化结构 + Phase 4.5/4.6/5 新增）。
- **部署策略**：**先源码部署本机**（不走 Docker；拉新仓代码 + copy openclaw + apply skill 替换 + 重启 Gateway），验证通过后再做 Phase 6 Dockerfile。
- **OpenClaw 源码位置**（开发期）：`~/wiseflow-pro/openclaw/`（已 clone，版本对齐 `v2026.6.10 / aa69b12d`）。
- **部署期操作清单**：
  1. `cd ~/wiseflow && git pull origin master`（或 fetch + reset --hard）
  2. `cp -r ~/wiseflow-pro/openclaw ~/wiseflow/openclaw`（或软链）
  3. `bash scripts/install.sh`（按 install.sh 流程：apply-addons → pnpm build → 配置同步）
  4. 重启 Gateway：`systemctl --user restart openclaw-gateway.service`
  5. 自检：登录 main → 跑 `/help` → 触发 1 条消息全链路

### 升级 / 降级策略（产品拆分后）

- **client 仓独立升级**：只升级 `~/wiseflow` 仓代码，relay 端点不变（OFB_KEY 不变）。
- **relay 仓独立升级**：relay 端点升级时 client 端无感知（除非 API 契约变）。
- **openclaw 升级**：按 `~/.claude/projects/-home-wukong-wiseflow/memory/03-openclaw-upgrade.md` 流程（切版本→验 patch→重新生成→提交）。**生产 Gateway 运行中不得调 `pnpm openclaw <subcommand>`**（见下方"pnpm openclaw 警告"章节）。

---

## 关于 WiseFlow 项目(我正在维护的项目)

## 关于 WiseFlow 项目(我正在维护的项目)

项目背景、功能介绍和目录结构详见工作区中的**项目背景.md**(由部署脚本自动同步,每次升级均为最新版)。

### 项目基本信息
- **项目名称**:WiseFlow
- **仓库地址**:https://github.com/TeamWiseFlow/wiseflow
- **上游 OpenClaw 仓库**:https://github.com/openclaw/openclaw
- **OpenClaw 官方教程**:https://docs.openclaw.ai/
- **历史曾用名**:openclaw_for_business、OFB(代码已合并,统一使用 WiseFlow)

---

## 安装路径(由 setup-crew.sh 自动维护)

> 实际 WiseFlow 项目路径记录在 `OFB_ENV.md`(同目录,历史命名保留),每次运行 `setup-crew.sh` 自动更新。
> 执行任何脚本前,先读取该文件确认路径,再 `cd <WISEFLOW_PROJECT_ROOT>` 后调用 `./scripts/xxx.sh`。

运行时数据位于 `~/.openclaw/`:
- `~/.openclaw/openclaw.json`:实际运行配置(勿手动大幅修改)
- `~/.openclaw/workspace-*/`:各 Agent 的工作区
- `~/.openclaw/agents/*/sessions/`:会话记录(用于用量统计)

---

## AWADA channel 启用

awada extension 是专为对外 crew（如 sales-cs）打造的消息通道，可令 sales-cs 以企业微信联系人的形态连接外部用户。配置默认直接启用 customerDB hook。

**启用/配置走 `awada-channel-setup` 技能**（SOP：装依赖 → 写 openclaw.json → 重启 Gateway → 验证）。排障检查单亦在该技能 SKILL.md 内。

> awada 已拍平单层（D8），路径 = `<WISEFLOW_PROJECT_ROOT>/awada/`（非 `awada/awada-extension/`）。

---

## LLM 模型参数约束(火山方舟 awk provider)

### GLM 5.2 系列(模型 id `glm-latest` / 其他 GLM 5.2 变体)

- **Provider 端点**:`https://ark.cn-beijing.volces.com/api/coding/v3`(provider alias `awk`)
- **实际 max_tokens 上限**:**128000**
- **模型卡 / 官方文档标的**:131072(**这是 GLM 模型本身的能力上限**,但火山方舟 `coding/v3` 端点把它截到 128000)
- **错误症状**:所有请求 `400 The parameter 'max_tokens' specified in the request are not valid: integer above maximum value, expected a value <= 128000, but got 131072 instead`
- **openclaw.json 正确配置**:`maxTokens: 128000`

### 排查清单:某个 agent 全报 "Something went wrong"

1. **看 gateway-error.log**(`/home/wukong/wiseflow-pro/logs/gateway-error.log`),找 `embedded run agent end: isError=true` + 紧跟的 `error=LLM request failed` 行。
2. **看 sessions.json 里那个 agent 的 modelOverride**(`~/.openclaw/agents/<agent>/sessions/sessions.json`,key 是 `agent:<agent>:feishu:direct:<user_ouid>`):
   - 如果有 `modelOverride` + `modelOverrideSource: "user"` → 说明之前 `/model <xx>` 把会话锁死在那个模型上了。
   - **修复**:用户在该 agent 对话里发 `/model <默认主模型>`,或 IT Engineer 删掉 sessions.json 里的 `modelOverride/providerOverride/modelOverrideSource` 三个字段(注意先 `cp` 备份 `.bak-<日期>`)。
   - **原因**:用户用 `/model` 切换是持久化的,`/new` 不会清。
3. **如果错误是 `max_tokens` 超过 provider 上限**:改 `openclaw.json` 里那个模型的 `maxTokens`。注意备份,hot-reload 通常生效。

---

## ⚠️ 重大警告：`pnpm openclaw <subcommand>` 会触发 build，在运行中的 Gateway 上使用会掏空系统

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

---

## ⚠️ OpenClaw binding routing 的关键坑

**坑 1：binding 不写 `accountId` 时不会"通配所有 account"** — `src/routing/resolve-route.ts` 里的 `normalizeBindingMatch` 把没填的 `match.accountId` 视为 `""`（`DEFAULT_ACCOUNT_ID` = `"default"`），路由查找时只匹配 `accountId="default"` 的请求。**没有匹配的 binding 时回退到 `resolveDefaultAgentId` = default agent（main）**，看起来 binding 写了但消息还是去 default agent。

**正确做法**（任何 binding 改 channel 路由都要写 `accountId`）：
- 想通配所有 account：用 `"accountId": "*"`（会进 `byAnyAccount` 桶）
- 想精确匹配某个 account：用具体 account id

**坑 2：routing 缓存 `resolvedRouteCacheByCfg` 不会因 SIGUSR1 hot-reload 重置** — 它是 `WeakMap<OpenClawConfig, ...>`，基于 cfg 对象引用判断，hot-reload 不换 cfg 引用所以不重置。改 binding 后必须用 `systemctl --user restart openclaw-gateway.service` 完整重启（这会断所有 session，因此执行前必须告知用户并征得同意）。

**坑 3：sessions.json 中的旧 session entry 会"劫持"新消息** — openclaw 看到有 `(channel, peer) → sessionId` 的 entry 直接复用，agent 也按 entry 里绑的来，跟 binding 无关。改 binding 之前/之后都要查 `agents/<agent>/sessions/sessions.json` 把这个 entry 删掉，否则即使 binding 改对了，session 缓存仍把消息路由回旧 agent。

## 定时任务(Cron)维护方案

> **v2026.6.6 起**:cron 存储已从 JSON 文件迁移至 SQLite,**禁止再编辑任何 JSON 文件**。

### 存储变更

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

### 直接查询 SQLite（只读排查用）

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

### 迁移操作（如需要）

1. 读取`~/.openclaw/cron/job.json` 文件，获取目前的定时任务配置。
2. 按上使用`cron`MCP工具进行配置。

### 重要提醒

1. **禁止手动编辑** `~/.openclaw/cron/` 下的任何 JSON 文件,它们已不再被运行时读取
2. **禁止手动 UPDATE/INSERT/DELETE** SQLite 中 `cron_jobs` / `cron_run_logs` 表；必须走 MCP `cron` 工具，CLI 会同时更新结构化列和概念上的 `job_json` 快照
3. cron 运行在 Gateway 进程内,修改后立即生效,无需重启

---

## crew权限（`exec-approvals.json` + `ALLOWED_COMMANDS`）维护经验

### 文件职责
- **`~/.openclaw/exec-approvals.json`** — 运行时实际生效的白名单。每条 entry：`{ id, pattern, lastUsedAt?, lastUsedCommand?, lastResolvedPath? }`。Gateway 在每次 exec 调用时读它并写回 `lastUsedAt`（活跃更新，不需重启）。`security: "allowlist"` 的 agent 没命中即返回 `exec denied: allowlist miss`。
- **`~/.openclaw/workspace-<agent>/ALLOWED_COMMANDS`** — **真正的 source of truth**。`setup-crew.sh` 读它 + SOUL.md 的 `command-tier:`（T0/T1/T2/T3）→ 重新生成 `exec-approvals.json`。每行 `+命令` / `-命令` 形式，注释以 `#` 起头。

### 流程：新增全局放行命令
1. **备份**：`cp ~/.openclaw/exec-approvals.json{,.bak-$(date +%Y%m%d-%H%M%S)}` 和 `cp workspace-*/ALLOWED_COMMANDS{,.bak-...}`（仅备份被改的那个 agent）。
2. **改 `exec-approvals.json`**：往每个 `security: "allowlist"` agent 的 `allowlist` 数组里 push 三条 `{ id: <uuid>, pattern: "/usr/bin/<bin>", lastUsedAt: <ms>, lastUsedCommand: "IT-ENGINEER PRE-APPROVED YYYY-MM-DD: <bin>", lastResolvedPath: "/usr/bin/<bin>" }`。**不要给 `it-engineer` 加**（它是 T3 full）。**用 atomic write**（temp + `os.replace`），因为 gateway 在并发写回 `lastUsedAt`。
3. **改对应 agent 的 `ALLOWED_COMMANDS`**：尾部追加 `# 注释行` + 三行 `+pdfimages` / `+pdftoppm` / `+pdftocairo`。setup-crew.sh 会把 basename 经 `which`/`readlink -f` 解析成绝对路径写进 exec-approvals.json，下次跑不会被覆盖掉。
4. **不要重启 gateway**。gateway 进程读 `exec-approvals.json` 是 live 的，只要新条目在文件里，下次 exec 就走新条目。重启是过度反应。
5. **不要跑 setup-crew.sh**。如果将来真要重生成，等用户手动跑。

### 验证命令
```bash
# 1) 查某个 agent 有没有某 pattern
python3 -c "
import json
d=json.load(open('/home/wukong/.openclaw/exec-approvals.json'))
for e in d['agents']['<agent>']['allowlist']:
    if 'pdfimages' in e['pattern']: print(e)
"
```
