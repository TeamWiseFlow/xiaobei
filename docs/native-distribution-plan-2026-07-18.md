# 原生分发方案（GitHub release tarball + 一键 install.sh）

> 2026-07-18 · 替代 Docker 作为主分发通道，降低用户上手难度。
> 与 `docs/docker-distribution.md` 并列：本方案为主通道，Docker 降级为可选（沙箱/隔离场景）。

## 一、背景与决策

### 1.1 痛点
用户装 wiseflow 最大的两个痛点：
1. **配环境**（Node / Python / camoufox / 浏览器二进制 / daemon）
2. **初始化配置**（wiseflow 加了大量 skill + crew，初始配置重）

### 1.2 已确认的事实（源码核实）
- **openclaw 原生 app 是壳，不内嵌运行时**：`apps/macos/Sources/OpenClaw/CommandResolver.swift` 在系统搜索路径（`$PATH` + `~/Library/pnpm` + `/opt/homebrew/bin` + `/usr/local/bin` + `~/.openclaw/bin` + `~/.openclaw/tools/node/bin` + `~/Projects/openclaw`）里找 `node` + openclaw 入口（`dist/index.js` / `openclaw.mjs` / `bin/openclaw.js`）。找不到就报错。
- **官方一键脚本帮你装 Node**：`openclaw/scripts/install.sh`（`curl ... openclaw.ai/install.sh | bash`）检测 Node ≥ 22.19，没有就装（mac `brew install node@24`、Alpine `apk add nodejs-current`、Linux 各包管理器、Windows `install.ps1`），再 `npm install -g openclaw` + `openclaw onboard --install-daemon`。
- **openclaw 自己开发/构建用 pnpm**（`pnpm-workspace.yaml` + `packageManager: pnpm@11.2.2`）。wiseflow 用 pnpm 构建引擎 + pnpm overrides 注入 patchright（`patches/overrides.sh`），与官方一致，**不是分叉**。差别只在终端用户安装层：官方给用户 `npm install -g openclaw`（发布包），wiseflow 现在是 Docker 里 pnpm 从源码 build。
- **wiseflow 相对 openclaw 的改动**：
  1. skills / crew / config / python deps —— 运行时从 `~/.openclaw/` 加载，不进二进制（文件 drop）。
  2. 浏览器 patch —— `patches/browser-camoufox-pivot/` 30+ patch 改 openclaw 源码，是 **fork 运行时**，不是运行时插件。
  3. camoufox-cli + Firefox 二进制 —— `npm install -g camoufox-cli && camoufox-cli install`，按 arch 自取。
  4. openclaw-weixin 插件 —— 在线 `plugins install`。
  5. crew 模板制 —— wiseflow 的核心差异化，agents list + 技能绑定可预填。

### 1.3 决策
| 项 | 决策 | 理由 |
|----|------|------|
| 分发载体 | **GitHub release tarball**（route B） | 不碰 npm registry、无账号、无认证、包体积宽裕（release asset 2GB/文件）、发版天然绑 GitHub release |
| 包名 / bin 名 | **保留 `openclaw`**（package `@wiseflow/openclaw`，bin `openclaw`） | 保留以后用官方 mac/Windows 原生 app GUI 的选项（resolver 找 `openclaw` 命令），成本为零 |
| 是否发 npm | **不发** | tarball 经 `npm install -g <url>` 本地安装，无需 registry |
| 认证 | **无** | npm 账号/Apple cert/Windows Authenticode/ICP 均不涉及；唯一资质相关是用户侧绑微信 channel，那是用户自己的事 |
| 多 arch 矩阵 | **不做** | Node / npm / camoufox-cli / uv 各自按 arch 自解决，不用 buildx |
| Docker | **降级可选** | 保留现有 `Dockerfile` 给要隔离/沙箱的用户，不再是主通道 |
| home 目录 | **`~/.openclaw`**（默认） | 保留 GUI 兼容（mac app 搜 `~/.openclaw/bin`）；代价是 wiseflow 与 stock openclaw 不应共存（文档注明） |
| 包管理器 | **构建期 pnpm（现状不变），用户期 npm 全局** | 与官方"开发 pnpm / 用户 npm"对齐 |
| 初始化 | **delegate 给 `openclaw onboard`** | 官方 onboard 已含模型供应商选择 + channel 初始化；wiseflow 预填 channel（微信→main），只让用户选模型 + 填 API key |

## 二、目标体验（用户视角）

```bash
# 一条命令，用户只需 curl
curl -fsSL https://raw.githubusercontent.com/wiseflow/wiseflow/main/scripts/install.sh | bash
```

脚本自动完成（用户只在前端被问"模型供应商 + API key"）：
1. 装 Node（≥ 24，复用 openclaw install_node 逻辑）
2. `npm install -g <tarball-url>` 装 forked `openclaw` CLI（带浏览器 patch）
3. `npm install -g camoufox-cli && camoufox-cli install`（按 arch 下 Firefox）
4. `uv` 装隔离 Python + `uv pip install -r requirements.txt`（wiseflow skill 的 python 依赖）
5. 落 wiseflow crew 模板 → `~/.openclaw/crews/`（agents + 技能绑定全预填，无交互）
6. 预写 channel config（微信→main）→ `~/.openclaw/`
7. `openclaw onboard`（channel 预填/跳过，只问模型供应商 + API key）
8. `openclaw onboard --install-daemon`（systemd/launchd 起 daemon）

**可选**：用户想要 GUI，另装 openclaw 官方 mac/Windows app——其 `CommandResolver` 在 PATH 找到 wiseflow 装的 `openclaw` bin，直接驱动 wiseflow 引擎 + 读 `~/.openclaw` 数据。

## 三、架构

### 3.1 forked CLI = openclaw + wiseflow 改动
```
@wiseflow/openclaw  (bin: openclaw)
  = openclaw@<OPENCLAW_COMMIT>            ← openclaw.version 锁定
  + patches/browser-camoufox-pivot/*.patch ← 30+ 浏览器 patch
  + patches/002,007 + overrides.sh         ← patchright override + 其他
  + openclaw-weixin 插件                   ← 在线 plugins install（build 期或首次启动）
  + wiseflow 专属 config 默认值             ← config-templates/openclaw.json 派生
```
构建方式：clone openclaw@commit → apply patches → `pnpm install --frozen-lockfile` → `pnpm build` → `npm pack` 出 tarball。与现有 Dockerfile 阶段 2 一致，只是产物从镜像变 tarball。

### 3.2 两个 release artifact（解耦发版节奏）
| artifact | 内容 | 何时重打 |
|----------|------|----------|
| `openclaw-<ver>-wiseflow.tgz` | forked 引擎 built dist（`npm pack` 产物） | openclaw 版本升级 / 浏览器 patch 变更 |
| `wiseflow-layer-<ver>.tar.gz` | `skills/` + `crews/` + `config-templates/` + `scripts/install.sh` + `requirements.txt`（原始文件） | crew 模板 / skill / config 变更 |

解耦理由：crew 模板演进频率高于引擎 patch 重放，分开避免每次改模板都重打引擎 tarball。v1 可先合并为一个 tarball，节奏痛了再拆。

### 3.3 install.sh（fork 自 `openclaw/scripts/install.sh`）
保留官方脚本的 Node 检测/安装、downloader、UI、daemon 安装逻辑，替换/追加：
- `npm install -g openclaw@latest` → `npm install -g <openclaw-<ver>-wiseflow.tgz URL>`
- 追加 camoufox-cli + uv + python deps 段
- 追加 wiseflow-layer 解包 → `~/.openclaw/`
- 追加 crew 模板渲染（见 3.4）
- 追加 channel 预填
- `openclaw onboard` 调用（预填 channel，见 3.5）
- Windows 走 fork 的 `install.ps1`

### 3.4 crew 模板渲染
crew 模板含占位符（用户名、API key 引用、路径等）。install.sh 渲染：
- 模板引擎：优先 `envsubst`（轻，无依赖）或仓内一个 node 渲染脚本（处理条件逻辑）
- 渲染输入：onboard 阶段拿到的模型供应商/key + 预填默认值
- 产物落 `~/.openclaw/crews/<crew-id>/`（AGENTS/SOUL/IDENTITY/TOOLS/MEMORY/HEARTBEAT 等，按 `docs/workspace-bootstrap-files.md` 职责划分）

### 3.5 onboard 预填 channel
- 预写 `~/.openclaw/` 下微信→main 的 channel config（来自 `config-templates/`）
- 调 `openclaw onboard` 时让其跳过 channel 步骤：
  - **P0 待验**：onboard 是否有 `--skip-channels` 类 flag。若有直接用；若无，靠"检测到已有 channel config 即跳过"的行为。
- 用户交互收敛到：选模型供应商 + 粘 API key（+ 0-2 项 wiseflow 专属，如微信 channel token）

### 3.6 home 目录与 GUI 兼容
- 默认 `~/.openclaw`（不设 `OPENCLAW_HOME`），mac/Windows 官方 app 的 `CommandResolver` 直接搜到。
- 文档注明：wiseflow 与 stock openclaw 不建议共存（共享 `~/.openclaw` 会互踩 config）。要隔离的用户可设 `OPENCLAW_HOME=~/.wiseflow`，但会失去 GUI 兼容（tradeoff，文档说明）。

## 四、实施阶段

### P0：可行性验证（动代码前，~2-4h）
- [ ] 确认 `openclaw onboard` 的 flag 集：有无 `--skip-channels` / 预填机制。读 `openclaw/src/commands/onboard*.ts`。
- [ ] 确认 `npm pack` 能产出可用的 forked 引擎 tarball：本地 `pnpm build` → `npm pack` → 另一台机 `npm install -g <tarball>` → `openclaw --version` 跑通。
- [ ] 确认 tarball 安装后 `openclaw` bin 在 PATH，且 mac app `CommandResolver` 能搜到（若有 mac 测试机）。
- [ ] 确认 `openclaw/scripts/install.sh` 可 fork：理清哪些段复用、哪些段替换。

### P1：forked 引擎 tarball 构建（~4-6h）
- [ ] 抽出 Dockerfile 阶段 2 的 build 逻辑为独立脚本 `scripts/build-engine.sh`：clone openclaw@commit → apply patches → pnpm install → pnpm build → npm pack → 产出 `openclaw-<ver>-wiseflow.tgz`。
- [ ] 本地跑通，tarball 在干净机器 `npm install -g` 后 `openclaw gateway` 能起。
- [ ] openclaw-weixin 插件：确认是 build 期 bake 进 tarball 还是首次启动在线装（倾向 bake，离线友好）。

### P2：wiseflow-layer 打包（~2-3h）
- [ ] `scripts/pack-layer.sh`：把 `skills/` + `crews/` + `config-templates/` + `requirements.txt` + install 脚本打成 `wiseflow-layer-<ver>.tar.gz`。
- [ ] 约定 layer 的目录结构（解包后直接对应 `~/.openclaw/` 子路径）。

### P3：install.sh（~6-8h，核心）
- [ ] fork `openclaw/scripts/install.sh` → `scripts/install.sh`，fork `install.ps1` → `scripts/install.ps1`。
- [ ] 替换引擎安装段为 tarball URL。
- [ ] 追加 camoufox-cli install 段（`npm install -g camoufox-cli@<ver> && camoufox-cli install`）。
- [ ] 追加 uv + python deps 段：`curl uv` → `uv venv ~/.openclaw/venv` → `uv pip install -r requirements.txt`；记 venv 路径到 config，skill 调 python 走 venv。
- [ ] 追加 layer 解包段：下载 `wiseflow-layer-<ver>.tar.gz` → 解到临时目录。
- [ ] 追加 crew 模板渲染段（3.4）。
- [ ] 追加 channel 预填段（3.5）。
- [ ] 调 `openclaw onboard`（预填 channel）+ `openclaw onboard --install-daemon`。
- [ ] 端到端在干净 Linux + mac + Windows(WSL) 各跑一次。

### P4：CI release 工序（~3-4h）
- [ ] `.github/workflows/release.yml` 加 `native` job（与现有 `docker` job 并列）：tag push → P1 build engine tarball → P2 pack layer → create GitHub release with 2 assets。
- [ ] install.sh 里 tarball URL 指向最新 release asset（用 `latest` 或版本号参数）。
- [ ] 复用现有版本 bump 机制。

### P5：crew 模板预填内容（~4-6h，产品向）
- [ ] 确定默认 agents 清单 + 每个 agent 的技能绑定（基于现有 `crews/` 模板）。
- [ ] 模板占位符化：把硬编码的用户名/key/路径改成占位符。
- [ ] 渲染默认值表（onboard 输出 → 模板变量）。
- [ ] channel 预填：微信→main 的 config 模板。

### P6：文档 + Docker 降级（~2h）
- [ ] 更新 README：主推一键脚本，Docker 移到"可选/沙箱"段。
- [ ] `docs/docker-distribution.md` 加头部注明"可选通道，主通道见 native-distribution-plan"。
- [ ] 写 `docs/install-troubleshooting.md`（`openclaw doctor` 类排障）。

## 五、风险与未决

| 级别 | 项 | 应对 |
|------|----|----|
| HIGH | `openclaw onboard` 是否支持跳过/预填 channel | P0 验证；若无 flag，靠预写 config + onboard 检测已有配置跳过 |
| HIGH | openclaw 版本升级时 30+ patch 重放 | 现有负担（[[03-openclaw-upgrade]] [[04-openclaw-patch-catchup]]），不新增；但发版 cadence 由 wiseflow 掌握 |
| MEDIUM | tarball 体积（openclaw 大 monorepo built dist） | openclaw 自己发 npm 同机制，已验证可行；GitHub asset 2GB 上限宽裕 |
| MEDIUM | Windows 上 uv + python + camoufox 边角 | P3 端到端覆盖 Windows；uv 跨平台是强项 |
| MEDIUM | crew 模板渲染的占位符与条件逻辑复杂度 | 简单的 envsubst 起步，复杂条件上 node 渲染脚本 |
| MEDIUM | wiseflow + stock openclaw 共存冲突 | 文档注明不共存；要隔离用 OPENCLAW_HOME（失 GUI） |
| LOW | mac app GUI 路径未端到端验 | 保留选项，非阻塞；有 mac 测试机时补验 |
| LOW | install.sh fork 后与上游 install.sh 同步 | 上游 install.sh 改动时手动 cherry-pick；低频 |

## 六、与现有方案的关系

- **`docs/docker-distribution.md`**：保留，降级为可选通道（沙箱/隔离）。`Dockerfile` 不删，CI 的 `docker` job 保留。
- **`docs/browser-stack-replacement-spec-2026-07.md`**：本方案是其分发侧的落地（camoufox-cli fork 替换 browser extension 的分发方式从 Docker 镜像改为 tarball + install.sh）。
- **`openclaw.version`**：继续锁定 `OPENCLAW_COMMIT`，tarball 构建基于此 commit。

## 七、成功标准

- 干净 Linux / mac / Windows 机器，一条 `curl | bash`，仅交互"模型供应商 + API key"，5 分钟内 daemon 起来、微信 channel 通、一个 crew agent 能跑。
- 无需用户装 Docker / Node / Python / 任何预依赖。
- 引擎 patch 升级 = 发新 release，用户 `wiseflow update` 拉新 tarball 重装。
