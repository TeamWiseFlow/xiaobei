# v5.6.0 (2026-07-12)

### 浏览器栈整体替换（双线栈，spec `docs/browser-stack-replacement-spec-2026-07.md`）

> 2026-07-11 ~ 07-12 落地。调研结论见 `docs/browser-extension-replacement-research.md` §12（架构转向，优先级最高）。

**双线浏览器栈**（替代原"整体替换 extension"路线）：

- **线 1（日常主力）**：新增 `target=camoufox`（默认）→ forked camoufox-cli 走旁路，绕开 routes/、pw-session、chrome-mcp。反指纹 Firefox + JSON-over-unix-socket。
- **线 2（特殊情况 fallback）**：保留 `target=host`（existing-session 真机 Chrome + chrome-mcp relay）+ `target=node`（remote-cdp 远端 Chrome）。routes/ 层不动。
- **删 sandbox 整条路**（容器 + bridge + facade + `agents.defaults.sandbox.browser` 配置）+ **删 host `local-managed` 分支**（不再额外下 Chromium）+ **patchright 整体去掉**（`overrides.sh` 不再注入 patchright-core，playwright-core 保留给 remote-cdp 用）。

**§1 fork camoufox-cli**（commit `24c1bf1`）：

- vendored 进 `patches/camoufox-cli/`（flat layout，基线上游 `Bin-Huang/camoufox-cli@0.6.2`），不另起 repo、不 npm 发布。`build.sh` 全局安装（`npm install -g .` link，bin → `dist/cli.js`），全局版本 `0.6.2-wiseflow.1`。
- **三个新功能**（spec §1.1 必改）：
  - `upload @ref|selector <file> [more files...]` — Playwright `setInputFiles`，variadic，缺文件 fail-fast。发布类技能依赖。
  - daemon **fail-first 队列** — 同 session 并发命令直接 fail 返回 `session <name> 正忙，请等待当前操作完成后再试`，`close` bypass（recovery）。不排队不等待，agent 读到 fail 文本知道发生了什么。
  - `identity [export <f>]` — 导出有效 UA + 指纹摘要（fingerprintHash），与 `cookies export` 对称（对应原则 4 cookie+UA 双导出）。
- code-review 后两处修复：HIGH 测试隔离（`server-queue.test.ts` 的 `queueState.calls` + firstGate 在 `beforeEach` 重置）+ MEDIUM daemon 挂起（`activeConnections` Set + `forceExit` 构造选项，`wait 999999999` + `close` 不再 linger）。
- 测试：`cli.test.ts` 加 upload/identity 解析 + `server-queue.test.ts` 新文件（fail-first + close bypass）。`npm test` 非 e2e 全过（173 passed）。`tests/e2e.test.ts` 1 失败（沙箱无 camoufox 浏览器二进制，557MB，`camoufox-cli install` 下，deferred 到 §11 step 7 真机验证）。

**§2 extension 改造 + patches 重组**：

- **001 monolith 拆成 35 个单文件 patch**（commit `c3fb7f9`）移至 `patches/browser-camoufox-pivot/patches/`，命名 `NN-{mod|del}-<path>.patch`，按文件名 sort 顺序应用。各 patch 改不同文件、彼此独立，上游漂一个文件只挂那一个 patch。干净上游逐个 `git apply --3way` + 全量端到端 dry-run 验证通过。
- **adapter + 测试 ship 在 `patches/browser-camoufox-pivot/files/`**（`camoufox-cli.adapter.ts` 的 `executeCamoufoxCliAction` 翻译 17 action → forked cli daemon 命令，JSON-over-unix-socket 通信，daemon 生命周期 `ensureDaemon` 探活 + `spawn detached unref`，DI 注入便于测试，33 测试过）。
- **default 改成 camoufox + upload 校验前置**（commit `b0fe815`）：`browser-tool.ts` 无 target 无 node 无 existing-session profile 时走 camoufox（description 同步 `Default: camoufox`）；`resolveExistingUploadPaths` 前置到 camoufox 早返回前，闭合 explicit target=camoufox+upload 绕过路径校验的 pre-existing 安全缺口。
- **patch 处置**：002 留 / 003 删 / 005 删 / 006 删（`noDefaults` 是 patchright 1.60+ 专属，patchright 去掉后原版 playwright-core `connectOverCDP` 不支持）/ 007 留并改名 `007-prefer-camoufox-cli.patch`（system-prompt 引导与架构 patch 解耦，便于单独 revert/调序）。
- **`overrides.sh`**：删 patchright-core 注入（pnpm override + doc sed 都删），保留 web_search disable。
- **`docs/tools/browser.md`** 改成双线模型（`target` 枚举段：`camoufox|host|node`，sandbox/local-managed 标已删，camoufox 为默认日常主力）。

**§2.3 setup-crew.sh 改造**（commit `ce28c38`）：

- `scripts/lib/crew-workspaces.sh` 加 `sync_crew_skills` 函数（按 skill 粒度 `rm -rf + cp -R` 覆盖，不删部署实例独有 skill，带 package.json 的 skill 跑 `npm install --production`）。
- `setup-crew.sh` §1 部署循环 fresh + exists 两个分支都调它，exists 分支不再只做 guide 注入。沙箱验证：自定义 skill 保留、同名 skill 被覆盖、npm 依赖装好。crew 专属 skill 更新现可传播到已部署 workspace。

**§7 twitter-interact 恢复脚本模式**（commit `0c2e962`）：

- AiToEarn clone 正好在 catchup commit `74e884f0`（v2.4.0），无 HEAD 差异要追。上游走 Twitter API v2 + OAuth，按「只吸收知识不搬架构」+ spec 要求 camoufox-cli，吸收操作语义（子命令结构 + 频率纪律），执行仍走 camoufox-cli。
- `twitter_interact.py` 改造：单一持久化 session `twitter`（原则 1，去掉 per-task nonce）+ fail-first 队列检测（`SessionBusyError` → exit 3，busy 时不 close 避免 tear down 正在跑的操作）+ 登录错误消息改成有头（原则 3）。
- 测试：`TestSessionNaming` 改断言常量 `twitter`，加 `TestFailFirstQueue` 验证 busy → exit 3 + 不 close。28/28 通过。

**§8 profile 丢失处理**：

- 新增 `docs/profile-loss-handling.md` canonical 程序：profile 丢失 / 损坏 / 指纹错配 → 重建 + 重登录，**绝对不允许导入 cookie 造会话**（补充 D，强化原则 5）。
- 理由：xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹会错配 → 被风控检测。2026-06-29 教训：凌晨心跳里 xhs-browse 无登录态，Agent 用 CDP `Network.setCookies` 注入 22 个 cookie 强造会话后批量抓取，当日触发小红书风控、账号被处罚。
- camoufox-cli `cookies import` 合法用途仅限同指纹 profile 的 cookie 备份/恢复 + 跨设备迁移同一指纹（profile 整体搬，不是只搬 cookie）。
- HEARTBEAT.md 约束 4 已落地「凌晨心跳跳过 + 等白天」策略，本文档补白天恢复流程。

**§9 README.md / CHANGELOG.md 更新**：本条目 + README `**v5.6.0 更新**` 浏览器架构重新设计段 + `## 🔧 比原版更强、更适合国内网络环境的浏览器方案` patch 表更新 + `## 🤝 xiaobei 基于如下优秀的开源项目` 去掉 Patchright 加 camoufox（🦊 https://github.com/daijro/camoufox）。

**§3-§6 并行中**（另一 agent）：browser-guide/smart-search/web-form-fill 三技能适配 + login-manager 纯指导化 + 9+ 平台 skill 改造 + wx-mp-hunter 收编。

**核心原则**（用户拍板的 8 点 + 补充，详见 spec §0）：每平台一个且只一个持久化 session（原则 1）/ 需验证码必须 camoufox-cli 有头（原则 2）/ douyin·twitter·xhs·weibo·zhihu·xianyu·reddit·youtube 有头登录 + wechat-channel·wx-mp 无头截图 QR（原则 3）/ cookie+UA 双导出（原则 4）/ 严禁浏览器方案导入 cookie（原则 5）/ profile 丢失重建+重登录绝不导入（补充 D）/ 涉及登录持久化 + 不登录临时性 session（补充 A）。

### 产品拆分（client 仓）

- **client 仓独立成仓**：从 Pro 仓 `product-split/client` 分支切出独立仓 `wiseflow`（远程 `git@github.com:bigbrother666sh/wiseflow.git`），发布仓 `TeamWiseFlow/xiaobei.git`。
- **relay 仓独立**：auth / sign / publish-relay / video-relay / tx-relay / awada-server 等服务搬到独立 PM2 仓 `wiseflow-relay`（`git-server:repos/wiseflow-relay.git`）。client 不持任何平台凭据，所有 relay 调用带 `X-OFB-Key` header。
- **openclaw 版本锁定**：本仓 `openclaw.version` 锁 `v2026.6.10 / aa69b12d`，CI/release 按此 clone + checkout。
- **patches 精简**：001（relax exec allowlist）+ 004（chrome port grace retry）已删，上游 6.10 已吸收或风险降级；保留 002/003/005/006。

### D8 扁平化 + D15 删减 + addons 销毁 + awada 拍平

- **D8**：原 `addons/officials/crew/{main,content-producer,it-engineer,sales-cs}` 拍平到 `crews/<crew-id>/`；公共技能统一在 `skills/`。
- **D15**：删除所有不用的 addons 模板与脚本。
- **awada 拍平**：原 `awada/awada-extension/` 改为 `awada/`（D8 一并）。
- **D19 权限放开**（2026-07-03）：内 crew（main / content-producer / it-engineer）SOUL.md `command-tier: T3` + 清空 `ALLOWED_COMMANDS`；sales-cs 维持 `T0`。Docker 内对内全放开（消除 allowlist miss 摩擦），对外保留 prompt injection 防线。
- **权限模型简化**（2026-07-07）：删 `command-tier`（T0~T3 四档抽象）字段，T1/T2 死代码清除。权限改由 `crew-type` + `ALLOWED_COMMANDS` 两源决定：`internal` → `full`；`external` → `deny`，有 `+` 条目则升级 `allowlist`。SOUL.md ×5 删 `command-tier` 行；`exec-tiers.sh` 重写；`inject_exec_guide` 改读 `crew-type`；内 crew 空 `ALLOWED_COMMANDS` 删除。

### Phase 4.5 — camoufox-cli 集成

- **login-manager 重写**：从 CDP WebSocket 抽 cookie 路径 → camoufox-cli cookies export。保留中央存储 `~/.openclaw/logins/{platform}.json`；新增 5 个子命令（`qr-headless` / `qr-confirm` / `cookie-export` / `cookie-import` / `session-cleanup`），加 `wx-mp` 平台（Phase 4.6）。25 单元测试全过。
- **browser-guide 改写**：加 §0 camoufox-cli 主推章节（5 小节），§1-6 标 fallback。
- **浏览器类 skill 收敛**：viral-chaser / content-calibrator / xhs-content-ops / xhs-interact 4 个 skill SKILL.md 改用 camoufox-cli 主推路径（修过期引用 + xhs-interact 全文重写 161+ 行）。
- **指纹模板 bake**：Dockerfile `wiseflow-layer` 阶段加 camoufox-cli 指纹模板 bake，产物 `/root/.openclaw/logins/_template/camoufox-cli.json`。
- **D18 约束**：不 fork camoufox-cli / 不 bake chromium / 每 agent 一 session。
- **设计骨架**：`docs/phase-4.5-design.md`（4 子任务地图 + 接口契约 + D18 约束清单）。
- **spike 报告**：`docs/camoufox-spike-2026-07.md`（指纹复用 + cookies export 验证通过）。

### Phase 4.6 — 微信公众号 engagement 接入（方案 A 骨架）

- **wx-mp-engagement skill 新建**：`crews/main/skills/wx-mp-engagement/`（SKILL.md + fetch_engagement.py + 15 单元测试）。camoufox 跑创作者中心抓阅读数/点赞数/评论数/分享数/收藏数 → 写 `pub_wx_mp`。
- **published-track 集成**：`fetch-and-update-metrics.sh` 加 `wx_mp` 平台路由（直接 exec `wx-mp-engagement.sh fetch --row-id $ROW_ID`），`MANUAL_PLATFORMS` 移除 `wx_mp`。
- **登录复用**：走 login-manager `wx-mp` 平台（中央 cookie）+ camoufox 扫码流程。
- **限制**：仅支持用户**自己有后台权限的号**（创作者中心用公众号账号登录），竞品号拿不到。
- **spike 验证待真机**：10 项 checklist 见 `docs/wechat-mp-engagement-design.md` §七，等统一部署后由用户跑。
- **失败回退**：方案 A → B（容器内 mitmproxy + camoufox）→ C（维持 manual update）。

### Phase 5 — img-gen 改火山方舟 Seedream 4.0（D13 决策）

- **siliconflow-img-gen 改调火山方舟**：`/api/v3/images/generations`（非 `/coding/v3`）。默认 model `doubao-seedream-4-0-250828`，可选 5.0 lite / 3.0 t2i。
- **API key 改 AWK_API_KEY**（D13 决策：img-gen Key 用户自带，纯客户端不入 server）。Skill 内全部 SiliconFlow / Qwen 引用清除。
- **size 校验**：按火山文档（方式 1: 2K/3K/4K；方式 2: WxH，总像素 [2560×1440, 4096×4096]，宽高比 [1/16, 16]）。
- **28 单元测试全过**：常量 / size 校验 / payload 构造 / API 请求 / env 校验 / CLI smoke。
- **SKILL.md 全文重写**：火山方舟专属文档，保留与 SiliconFlow 路径对比表。

### Phase 8.1 / 8.2 — IT engineer 记忆注入

- **产品拆分后运维知识集中注入**：`crews/it-engineer/MEMORY.md` 顶部加 116 行新章节（D19 / D20 / login-manager / awada / camoufox 排故 / 4.6 engagement / 部署路径 / 升级策略）。
- **D20③ 依赖安装规范**（pip `--target vendor` / npm 局部 / 冲突处理 / it-engineer 介入准则）。
- **未动**：SOUL / IDENTITY / AGENTS（属 Phase 7 续暂缓部分，待下一阶段）。

### 默认配置精简（开箱即用）

- **记忆默认 fts-only**：`config-templates/openclaw.json` 与 `openclaw-aihubmix.json` 均加 `agents.defaults.memorySearch.provider = "none"`，新用户**无需开向量/embedding 模型**即可用记忆（走 FTS 全文检索）。
- **dream 默认关闭**：`plugins.entries.memory-core.config.dreaming.enabled` 改 `false`，避免 3am 烧 token 和噪声日志；进阶用户可自行开启（README 有指引）。
- **主力模型统一走 AWK**：`install.sh` 不再收集 `SILICONFLOW_API_KEY`，`_USER_PROMPT_KEYS="AWK_API_KEY"`；视觉/替补也走火山方舟 Coding Plan，一个 key 即可。

### 脚本注入精简

- **Python 调用规范挪进 `inject_exec_guide` 的 external-allowlist 分支**：原独立 `inject_python_exec_guide()` 删除，`setup-crew.sh` 4 处调用移除。内 crew 无 allowlist，该规范对内不成立，不再注入。
- **`inject_env_file_guide()` 删除**：与 main / it-engineer AGENTS.md 已建立的"main 不直接写 env，spawn IT engineer；IT engineer 按 OFB_ENV.md 规范写入"约定重复，`setup-crew.sh` 中调用与 `_OFB_ENV_FILE` 计算块一并移除。

---

# v5.5.2

### Selfmedia Operator 视频制作与分发能力

- **一站式短视频制作**：`video-product` 技能支持文章链接、追爆报告、文字主题、本地文件等多种输入，自动生成脚本 → 逐段生成视频素材（声画同出）→ FFmpeg 合成成片。直连火山引擎 Seedance（doubao-seedance-2.0 系列）与阿里云百炼 Wan2.7-HappyHorse（happyhorse-1.1 系列）端点，按平台自动 fallback
- **视频分发**：新增微信视频号发布（`wechat-channels-publish`，处理 wujie shadow DOM），结合既有的小红书、抖音、Twitter/X、B站、快手等平台，实现短视频制作 → 多平台分发的闭环
- **两个剪辑辅助技能**：
  - `de-mouth`：口播视频去口误，自动识别并删除静音、语气词、卡顿词、重复句、残句，输出干净视频 + 字幕 + 剪映草稿
  - `highlight-clipper`：从本地视频中通过 ASR 转录 + 文本分析自动提取高光片段，剪辑输出多段短视频
- Selfmedia Operator引入科学的评估方案和自动复盘方案（发布前预测打分 -> 每日数据复盘 -> 根据复盘调整打分量表 -> 不断优化预测准确性)。以上已内置到所有平台的发布流程中，让运营工作不再“凭感觉”。

### 主力模型切换为 GLM-5.2，推荐火山方舟 Coding Plan

- `config-templates/openclaw.json` 主力模型由 DeepSeek V4 Pro 切换为 **GLM-5.2**（经火山引擎方舟 Coding Plan 接入，`awk/glm-latest`），fallback 为 siliconflow provider
- `install.sh` 交互式收集的 key 由 `DEEPSEEK_API_KEY` 改为 `AWK_API_KEY`
- 大模型推荐主推**火山方舟 Coding Plan**：支持 GLM-5.2、Kimi-K2.7、MiniMax-M3、DeepSeek-V4 系列、Doubao-Seed-2.0 系列等模型，工具不限；通过 xiaobei 邀请链接订阅叠加 9.5 折，首月尝鲜低至 9.4 元。邀请链接 https://volcengine.com/L/dx-wt80li-I/ ，邀请码 `5Y5A6L86`
- siliconflow、aihubmix 推荐不变（siliconflow 仍需申请，作为视觉/替补模型）

> 想使用 5.5.2 的视频生成能力，需额外开通火山方舟 doubao-seedance-2.0 系列或阿里云百炼 happyhorse-1.1 系列模型，并将对应 key（`AWK_GEN_KEY` 或 `MODELSTUDIO_API_KEY`）配置到 `daemon.env`。

### openclaw 上游同步至 v2026.6.10

- 从 v2026.6.6 升级到 v2026.6.10
- **删除 patch 001**（relax exec allowlist shell syntax）：上游 exec 审批重构为 risk-based（`command-explainer` + `exec-authorization-plan`），`&&`/`||`/`;` 复合命令已原生逐段匹配 allowlist；`$()`/反引号/重定向上游仍拒但 wiseflow 已改走 `.sh` 脚本。原目标代码 `splitShellPipeline` 已删，无法 re-port
- **删除 patch 004**（chrome port grace retry）：上游新增 `ensureManagedChromePortAvailable` + `recoverOwnedStaleManagedChromeCdpListener`，命中 EADDRINUSE 时主动杀掉占用端口的陈旧 Chrome 进程并清 singleton lock 再重探，比 3×500ms 轮询更强
- 保留 patch 002/003/005/006（验证 apply 通过，上游无等价改动）

### 上游关键变更摘要（与 xiaobei 相关）

- **GLM-5.2（6.10）**：暴露 reasoning levels、GLM overload failover、Zai 合成模型回退 manifest baseUrl
- **心跳（6.9）**：修复 5.20 及所有 5.x 上心跳 scheduler 不触发的回归（#88970）
- **sessions_yield over MCP（6.9，#90861）**：修复 MCP 下 sessions_yield 保留
- **安全（6.9）**：secrets redaction、阻断内部 HTTP session overrides、审计 open-DM tool exposure、plugin write owner check
- **存储（6.9）**：NFS 上禁用 SQLite WAL、reindex temp 清理、setup state 移出 workspace dot-dir
- **web search（6.9）**：Codex Hosted Search、key-free provider 保持 opt-in
- **6.10**：fast talks auto mode、channel switch reset 陈旧 origin 字段、hook registry 组合保留 trusted policies

# v5.5.1

### openclaw 上游同步至 v2026.6.6

- 从 v2026.5.28 升级到 v2026.6.6（4253 commits，跨越 6.1→6.2→6.5→6.6 四个稳定版）
- 重新生成 patch 004（chrome-port-grace-retry）和 patch 005（browser-timeout-env-var）以适配上游文件重构
- patch 001–003 验证通过，无需修改

### 上游关键变更摘要

- **安全加固**：exec 审批超时默认拒绝（fail-closed）、sandbox binds 收紧、MCP stdio 继承收紧、Codex HTTP 私有目标阻断、loopback tools 权限隔离
- **OpenRouter 一等公民**：模型设置流程原生支持 OpenRouter OAuth/API-key
- **Parallel Search (Free)**：零配置内置 web search（无需 API key），作为 DuckDuckGo 之前的默认 fallback
- **移动端**：iPad 侧边栏 + iPhone Control Hub，Workboard/Skill Workshop 连接 Gateway
- **Telegram/iMessage**：account-scoped topic 路由、always-on inbound restart、durable echo markers
- **Browser/MCP**：existing-session CDP 支持、WebSocket validation、Streamable HTTP loopback、OAuth/SSE auth 修正
- **Provider**：Claude Fable 5 adaptive thinking、Gemma 4 reasoning replay、本地模型跳过 guardian review、gpt-5.3-codex 恢复
- **Cron**：wake 保留 originating session/agent、impossible cron 表达式拒绝创建
- **启动提速**：cached model metadata、移除 startup catalog wait、lazy slash-command loading
- **QoL**：`openclaw update repair` 恢复路径、compaction timeout 默认降至 180s

# v5.5.0

### 完全重新设计的部署与渠道绑定流程

- 初次安装时默认安装官方微信插件，用户使用个人微信扫码后即可启动第一个crew——main agent，直接在微信上就能使用
- 后续的设定、更多crew的启用、渠道绑定等均可通过main agent完成（直接在微信上与它对话）
- 如果仅需要一个“个人助理”，或者不需要更大的AI crew团队（crew数量小于3），可以一直使用微信渠道，无需额外的操作
- 工作渠道除支持飞书外，额外增加企业微信
- 新增 WeCom channel 插件自动安装脚本（`install-wecom-channel.sh`），支持 pin 版本 + SHA-512 完整性校验，Main Agent 直接执行无需用户手动运行 `npx`
- main agent可以完整操作feishu、企业微信的配置（应用创建、凭据获取、权限配置、事件订阅、crew绑定全流程）

### Designer + IT Engineer 全链路升级

**Designer 与 IT Engineer 的技能组合现已覆盖网页（官网 / 产品 Landing Page）的完整开发与生命周期管理：**

> **设计** → **开发**（IT Engineer 通过 coding-agent）→ **部署**（云计算资源）→ **备案**（ICP）→ **SEO**

#### Designer 升级

- Designer 从"配图+海报生成"重新定位为**系统性视觉设计体系构建者**，负责从零构建完整网页、APP 界面、品牌视觉体系
- 新增 `design-system-picker` 技能：内置 15 套知名品牌设计系统（Stripe / Vercel / Linear / Notion / Apple / Supabase / Shopify / Figma / Spotify / Tesla / Framer / Airbnb / BMW / IBM / Starbucks），覆盖 fintech / devtools / productivity / consumer / luxury / enterprise / ecommerce / creative / media / automotive / lifestyle 全品类
- 设计系统包含完整的 8 段规范（色彩、字体、组件、布局、层级、响应式等），所有 HTML/CSS 产出严格遵循选定设计系统的 token
- 支持从 [awesome-design-md](https://github.com/VoltAgent/awesome-design-md) 上游仓库查找并导入更多设计系统
- Designer 改为纯 binding 模式运行，用户直接使用，其他 crew 不再 spawn Designer
- 简单出图需求（视频封面、海报等）统一使用 `siliconflow-img-gen`，无需启动 Designer
- 新增三大工作流：完整网页/落地页设计（A）、APP/产品界面设计（B）、品牌视觉体系构建（C）

#### IT Engineer 升级

- 新增 `seo` 技能：技术 SEO 审计与优化（爬取、索引、结构化数据、Core Web Vitals、关键词映射）
- 新增 `icp-filing` 技能：ICP 备案全流程指导（材料清单、流程步骤、域名查询、备案号生成）
- 新增 `icp-exemption` 技能：Apple 国区 ICP 豁免申请附件 PDF 生成
- 新增 `tccli` 技能：腾讯云 CLI 速查手册（CVM / Lighthouse / DNSPod / SSL / VPC 等 200+ 服务）
- 新增 `alicloud-find-skills` 技能：阿里云 Agent Skills 搜索、发现与安装

### Selfmedia Operator 增强

- 新增 `wx-mp-publish` 技能：**支持将微信公众号文章自动排版并直接推送至草稿箱**，实现从内容生产到公众号发布的一站式闭环
- 新增 `t2video`（简单视频制作）技能：一站式短视频生产，整合 TTS 语音合成 + 素材搜集 + FFmpeg 组装
- 新增 `highlight-clipper`（高光时刻视频制作）技能：支持从给定视频文件（录屏）中按语音自动剪辑高光时刻短视频
- 大幅完善多平台发布技能，新增/增强支持：小红书（API 方式）、抖音、B站、快手、YouTube、TikTok、Instagram、Facebook、Threads、Pinterest 等

### Officials Addon 新crew 

- **business-developer**（商务拓展）正式发布：4.x版本的功能现在可以完全通过business-developer实现
- **investor-relationship**（投资人关系）预发布

### crew 机制改进

- 启用 BOOTSTRAP.md 机制，每个crew根据自己职责设定，在启动初期会主动向用户搜集必要信息，如Selfmedia Operator搜集账号矩阵信息、IR和BD主动搜集公司、产品信息
- skill 路径解析修复与加载机制优化

#### OpenClaw 升级至 v2026.5.28

- 基于 OpenClaw v2026.5.28（从 v2026.5.7 升级，跨越 6424 commits）
- Patches 004/005 针对 v2026.5.28 新文件结构重新生成，全部 5 个 patch 验证通过
- awada extension 适配升级

### Bug 修复与改进

- `scripts` 脚本中诸多不当处修复与改进
- `crew-recruit` / `crew-dismiss` SKILL.md 澄清 TEAM_DIRECTORY.md 由脚本内部自动同步，无需 agent 手动更新
- HRBP `add-agent.sh` 新增 business-context symlink 和 crew MEMORY.md 背景说明自动注入

---

# v5.4.9

### 升级 openclaw 至 v2026.5.7

- v2026.5.7 被标记为 stable，是近期最稳版本；所有 4 个 patch 均干净应用，无冲突

### install.sh 大幅优化 & DeepSeek + SiliconFlow 最佳实践落地

- 大幅简化新用户 onboard 流程，交互式引导输入 API Key，同时完整支持 macOS 安装部署
- 经过对多个 provider、多个主流 LLM 的实战测试，总结最佳实践为 DeepSeek（主力）+ SiliconFlow（替补 & 视觉模型）组合，已内置到 config-template 和 install 脚本中
- agents.defaults.subagents.announceTimeoutMs 提高至 3600000（1 小时），避免长时间 subagent 任务意外超时

### Bug 修复

- 修复了 v5.4.8 中存在的诸多 bug（涉及 scripts、skills、crew 配置等模块）

### Officials Addon 预发布

- 预发布 **business-developer**（商务拓展）和 **investor-relations**（投资人关系）两个新 crew 模板

---

# v5.4.5～5.4.8

### 升级 openclaw 至 v2026.5.6

- 同步上游 hotfix（OpenAI Codex OAuth 路由修复回滚、plugin/runtime fetch header、debug proxy header replay、web_fetch timeout 后 tool lane 卡住等修复）
- 当前升级原因：v2026.4.24 已知运行问题较多，直接追到 2026.5.6 稳定修复版本
- 诸多 bug 修复（scripts）
- 技能优化

### 升级 openclaw 至 v2026.4.24

**Browser Extensions 重要变更（v2026.4.22 → v2026.4.24）：**

- **新增坐标点击动作**：`act kind="coordinateClick"` 支持通过 x/y 坐标点击，补充 aria ref 定位之外的场景
- **默认 act 超时预算**：修复了 act 操作的默认超时时间设定，避免长时间 act 任务意外被截断（与 patch 005 env var 支持互补）
- **per-profile headless 配置**：每个浏览器 profile 可独立配置 headless/有头模式，不再全局统一
- **稳定 tab 句柄 + 自动化技能**：新增 tab handle 机制，跨多步操作可稳定引用同一标签页；新增 `automation skill` 供 agent 调用
- **Doctor 诊断工具**：新增 `browser doctor` 命令，agent 可直接调用浏览器诊断，并向用户展示结构化诊断信息
- **已有 session 附加修复**：修复 existing-session 附加时的端口冲突、超时判定、WS 状态探测等多个问题（#57245）
- **Chrome profile 锁恢复**：自动检测并恢复 Chromium profile 锁文件异常，减少需手动清理的情况（#62935）
- **空闲 tab 自动关闭**：`/new`、`/reset` 或会话归档时自动关闭已跟踪的浏览器标签，防止跨 session 泄漏
- **Linux 可执行文件路径扩展**：新增 `/opt/google`、`/opt/brave.com`、`/usr/lib/chromium*` 等检测路径（#48563）
- **Browser Realtime Talk**：Talk/Voice Call/Google Meet 可通过 realtime voice loop 调用完整 agent 能力

**Google Meet 首次作为内置 plugin 发布**（bundled participant plugin，含个人 Google 认证、Chrome/Twilio 实时会话、会议记录/出席名单导出、已开启 Meet 标签的恢复工具）

**其他变更：**
- DeepSeek V4 Flash/Pro 加入内置 catalog，V4 Flash 成为新用户默认模型
- 多项安全修复（跨 bot token replay、sandbox browser SSRF、secrets BOM 清理等）
- Plugin 启动性能优化：静态 model catalog、按需加载 provider 依赖

**patch 状态：**
- patch 002、005 无需调整，直接通过
- patch 003（act-field-validation）因 `executeActAction` 函数签名新增 `onTabActivity` 参数导致上下文行号偏移，已重新生成



### 升级 openclaw 至 v2026.4.22

- 同步上游变更（2298 commits，含 telegram/discord 优化、thinking 模型默认级别修复、session 路由保持、wecom/azure openai 等改进）
- patch 001（suppress-stale-reply context）针对新版上下文行偏��重新生成，`--check` 直接通过

# v5.5

### 架构调整

- **patches 与 addon 分离**：将代码补丁（`patches/*.patch`）、插件（`patches/suppress-stale-reply`）和依赖覆盖（`patches/overrides.sh`）从 `addons/officials/` 迁移至项目根目录 `patches/`，作为 xiaobei 的共性基础能力，对所有 addon 生效。addon 不再支持 patches 层，仅提供额外全局技能和 Crew 模板。

- **默认全局技能重新划分**：`smart-search`、`browser-guide` 从 addon 专属技能迁移至 `skills/`（项目根目录），成为 xiaobei 所有 crew 默认可用的内置技能，无需依赖 official addon 即可生效。

- **`apply-addons.sh` 重构**：先应用 `patches/` 下的基础补丁和覆盖，再安装默认全局技能（`skills/`），最后逐 addon 安装额外技能和 Crew 模板。addon 加载流程简化为两层（skills → crew），移除原有的 overrides 和 patches 层。

### 升级 openclaw 至 v2026.4.15

- 同步上游变更（详见 openclaw release notes）
- patch 001（suppress-stale-reply context）针对 `deliver.ts` 重构（OutboundPayloadPlan 架构调整）重新生成
- patch 005（codex apiKey）已被上游原生集成，移除

# v5.4

### 新增

- **suppress-stale-reply 插件 + patch 001**：用户连续快速发送多条消息时，agent 对被超越消息的回复不再发送给用户，但仍写入对话历史供下一轮上下文使用，最终用户只看到对最新消息的回复。所有走标准 inbound/outbound 路径的 channel（feishu / awada / wecom / cli 等）自动获得该能力。`/`-前缀的指令型回复（如 `/kb`、`/cc`）放行，不参与抑制。可通过 `OPENCLAW_SUPPRESS_STALE_REPLY=0` 关闭

# v5.3

### 新增

- **新媒体运营 Crew 模板（selfmedia-operator）**：内置文生图（siliconflow-img-gen）技能，文生视频（siliconflow-video-gen）已迁移至 video-producer crew；提供完整的选题研究→图文输出、草稿扩写→完整文章两套工作流；配图优先策略（用户素材 > 免版权图片 > AI 生成 > 历史复用），素材统一归档至 `campaign_assets/`

- **smart-search 新增平台**：百度贴吧（全局搜索 + 指定吧搜索）、Amazon（含分类/排序过滤），YouTube 新增类型过滤（shorts/video/channel）及"最近1小时"时间过滤

### 改进

- **升级 OpenClaw 至 v2026.4.11**：同步上游安全加固（Browser/security SSRF 防御增强、exec 沙箱安全、媒体访问鉴权）、Dreaming/Active Memory 功能（内存子智能体、日记视图、REM 回���）、Ollama/vLLM/Feishu/Teams 若干 bug 修复；原 patch 004（web_fetch RFC2544 支持）已被上游原生集成，改为配置项并同步到 `config-templates/openclaw.json`

- **sales-cs 数据库访问重构**：将所有客户数据库操作改为命名脚本（`skills/customer-db/scripts/`），禁止直接执行 SQL，增强安全性和可维护性

- **sales-cs 消息防重**：修复工具调用轮次中输出面向客户文本导致重复消息的问题；统一 customerdb hook 与命令路径的 peer 规范化逻辑

- **smart-search 搜索引擎策略调整**：主推 Bing（国内网络稳定可用），百度降为 backup，Quark 降为 fallback，移除 Google（国内经常不可用）

- **系统配置**：修复 setup-crew 中所有 agent 的 reasoningDefault 未正确关闭的问题

### 文档

- `docs/quick_start.md` 新增"推荐上手三步走"：含招募对内/对外 crew、注入业务背景、IT Engineer 运维的完整对话示例

- README 完善：补充 openclaw clone 步骤；新增 opencli 致谢

# v5.2

- combine ofb and wiseflow
- publish sales-db and self-media operator

# v5.0

upgrage workflow to Agent!

# v4.32
- bug fix；

- import error\can not work when use rss souces only.

- update patchright to 1.57.2

- clean useless code

# v4.3.1

- 后端新增 info_stat 统计接口，并补齐 user_notify、user_prompt、ws_ping 等前端交互相关接口。

  Added info_stat statistics endpoint and completed frontend interaction endpoints such as user_notify, user_prompt, and ws_ping.

- read_info 参数与 task time_slots 枚举同步为当前实现。

  Synced read_info parameters and task time_slots enum with the current implementation.

- 后端接口文档更新，移除已弃用的 mc_backup_accounts CRUD 说明。

  Updated backend API docs and removed deprecated mc_backup_accounts CRUD descriptions.

# v4.30

- 升级为与 pro 版本一样的架构，同时具有一样的 api，可无缝共享 [wiseflow+](https://github.com/TeamWiseFlow/wiseflow-plus) 生态！

  Upgraded to the same architecture as the pro version, with the same api, seamlessly sharing the [wiseflow+](https://github.com/TeamWiseFlow/wiseflow-plus) ecosystem!

# v4.2

- 全新的网页爬取方案，使用 patchright 直连本地用户真实浏览器，从而实现更加强大的反爬虫伪装能力，以及提供用户数据持久化留存等特性；

  Brand new web crawling solution: uses patchright to directly connect to the user's real local browser, providing much stronger anti-crawling disguise capabilities and features like persistent user data storage.

- 配套提供预登录、清除、深度清除脚本

  Provided supporting scripts for pre-login, cleanup, and deep cleanup.

- 大幅简化 web crawler相关的 config

  Greatly simplified web crawler-related configuration.

- 新增了proxy方案（支持直连提供商服务器，动态获取，本地缓存）

  Added a new proxy solution (supports direct connection to provider servers, dynamic acquisition, and local caching).

- 整合 Crawler4ai script 方案，提供网页操作能力

  Integrated Crawler4ai script solution, enabling web page operation capabilities.

- 重构搜索引擎方案，适配新的爬取方案并修复一些累积问题

  Refactored search engine solution to adapt to the new crawling approach and fixed some accumulated issues.

- 升级 docker 部署方案，适配全新的打包 work flow。

  Upgraded Docker deployment solution to fit the brand new packaging workflow.


# v4.1

- 通用llm提取支持设定 role 和 purpose，从而实现更加精准的提取

  Universal LLM extraction supports setting role and purpose, enabling more precise extraction

- 社交平台信源增加查找创作者详情的功能

  Added functionality to search for creator details in social media platform sources

- 增加自定义精准搜索功能（自定义 info 提取字段）

  Added custom precision search functionality (custom info extraction fields)

- 可以为关注点指定搜索源，目前支持 bing、github、arxiv、ebay 四个源，并且全部使用平台原生接口，无需额外申请并配置第三方 key

  Can specify search sources for focus points, currently supporting four sources: bing, github, arxiv, ebay, all using platform native interfaces without requiring additional third-party key applications and configurations

- 优化的缓存以及缓存遗忘机制

  Optimized caching and cache forgetting mechanisms

- 修复快手平台搜索结果为空时的错误处理

  Fixed error handling when Kuaishou platform search results are empty

# v4.0

- 深度重构 Crawl4ai（0.6.3）和 MediaCrawler， 并整合引入 Nodriver，大幅提升获取能力，支持社交平台内容获取（4.0版本提供对微博和快手平台的支持）；

  Deeply refactored Crawl4ai (0.6.3) and MediaCrawler, integrated Nodriver, significantly enhanced content acquisition capabilities, supporting social media platform content retrieval (version 4.0 provides support for Weibo and Kuaishou platforms);

- 全新的架构，混合使用异步和线程池，大大提升处理效率（同时降低内存消耗）；

  New architecture utilizing a hybrid approach of async and thread pools, greatly improving processing efficiency (while reducing memory consumption);

- 继承了 Crawl4ai 0.6.3 版本的 dispacher 能力，提供更精细的内存管理能力；

  Inherited the dispatcher capabilities from Crawl4ai 0.6.3 version, providing more refined memory management capabilities;

- 深度整合了 3.9 版本中的 Pre-Process 和 Crawl4ai 的 Markdown Generation流程， 规避了重复处理；

  Deeply integrated the Pre-Process from version 3.9 and Crawl4ai's Markdown Generation process, avoiding duplicate processing;

- 放弃了通过 pocketbase 的api 进行数据库操作，改为直接读写 sqlite 数据库，因此无需用户在 .env 中提供pocketbase的账密，也规避了登录过期导致数据库无法读写，从而产生大量日志的隐患；

  Abandoned database operations through PocketBase API, switched to direct SQLite database read/write, eliminating the need for users to provide PocketBase credentials in .env, and avoiding the risk of database read/write failures due to login expiration that could generate excessive logs;

- 优化 llm 处理策略，更加符合思考模型的特性；

  Optimized LLM processing strategy to better align with the characteristics of thinking models;

- 优化了对 RSS 信源的支持；

  Enhanced support for RSS sources;

- 优化了代码仓文件结构，更加清晰且符合当代 python 项目规范；

  Optimized repository file structure, making it clearer and more compliant with contemporary Python project standards;

- 改为使用 uv 进行依赖管理，并优化了 requirement.txt 文件；

  Switched to using uv for dependency management and optimized the requirement.txt file;

- 优化了启动脚本（提供提供 windows 版本），真正做到"一键启动"；

  Optimized startup scripts (including Windows version), achieving true "one-click startup";

- 优化了日志输出，增加 recorder 总结，并提供更精细化的日志输出控制。

  Enhanced log output, added recorder summaries, and provided more granular log output control.


# v3.9-patch3

- 更改版本号命名规则

  Change version number naming rules

- 诸多累积修复

  Numerous cumulative fixes

# v0.3.9-patch2

- 定制更改 crawl4ai 0.4.30 版本，以取得更好的性能

  Modified crawl4ai version 0.4.30 for better performance

- 相应的更改 core/requirements.txt

  Corresponding changes to core/requirements.txt

- 更改 prompt，但未在 qwen2.5-14b 模型上发现改进

  Modified the prompt, but no improvements were found on the qwen2.5-14b model


# V0.3.9

- 适配 Crawl4ai 0.4.248 版本，优化了性能

  Adapt to Crawl4ai 0.4.248 version, optimized performance

- 累积 bug 修复

  Cumulative bug fixes

- 增加 docker 运行方案（感谢 @braumye 贡献）

  Added docker running solution (thanks to @braumye for contributing)


# V0.3.8

- 增加对 RSS 信源的支持

  add support for RSS source

- 支持为关注点指定信源，并且可以为每个关注点增加搜索引擎作为信源

  support to specify source for each focus point, and add search engine as source

- 进一步优化信息提取策略（每次只处理一个关注点）

  Further optimized information extraction strategy (processing one focus point at a time)

- 优化入口逻辑，简化并合并启动方案 （感谢 @c469591 贡献windows版本启动脚本）

  Optimized entry logic, simplified and merged startup solutions (thanks to @c469591 for contributing Windows startup script)


# V0.3.7

- 新增通过wxbot方案获取微信公众号订阅消息信源（不是很优雅，但已是目前能找到的最佳方案）
  
  Added WeChat Official Account subscription message source acquisition through wxbot solution (not very elegant, but currently the best solution available)

- 升级适配 Crawl4ai 0.4.247 版本，

  Upgraded to fit Crawl4ai 0.4.247 version,

- 通过新增预处理流程以及全新设计的推荐链接提取策略，大幅提升信息抓取效果，现在7b 这样的小模型也能比较好的完成复杂关注点（explanation中包含时间、指标限制这种）的提取了。

  Through the addition of a new pre-processing process and a completely redesigned recommended link extraction strategy, the information capture effect has been significantly improved, and now even small models like 7b can better complete the extraction of complex focus points (such as time and index limits in the explanation).

- 提供自定义提取器接口，方便用户根据实际需求进行定制。

  Provided a custom extractor interface to allow users to customize according to actual needs.

- bug 修复以及其他改进（crawl4ai浏览器生命周期管理，异步 llm wrapper 等）（感谢 @tusik 贡献）

  Bug fixes and other improvements (crawl4ai browser lifecycle management, asynchronous llm wrapper, etc.)

  Thanks to @tusik for contributing

# V0.3.6
- 改用 Crawl4ai 作为底层爬虫框架，其实Crawl4ai 和 Crawlee 的获取效果差别不大，二者也都是基于 Playwright ，但 Crawl4ai 的 html2markdown 功能很实用，而这对llm 信息提取作用很大，另外 Crawl4ai 的架构也更加符合我的思路；

  Switched to Crawl4ai as the underlying web crawling framework. Although Crawl4ai and Crawlee both rely on Playwright with similar fetching results, Crawl4ai's html2markdown feature is quite practical for LLM information extraction. Additionally, Crawl4ai's architecture better aligns with my design philosophy.

- 在 Crawl4ai 的 html2markdown 基础上，增加了 deep scraper，进一步把页面的独立链接与正文进行区分，便于后一步 llm 的精准提取。由于html2markdown和deep scraper已经将原始网页数据做了很好的清理，极大降低了llm所受的干扰和误导，保证了最终结果的质量，同时也减少了不必要的 token 消耗；

  Built upon Crawl4ai's html2markdown, we added a deep scraper to further differentiate standalone links from the main content, facilitating more precise LLM extraction. The preprocessing done by html2markdown and deep scraper significantly cleans up raw web data, minimizing interference and misleading information for LLMs, ensuring higher quality outcomes while reducing unnecessary token consumption.

   *列表页面和文章页面的区分是所有爬虫类项目都头痛的地方，尤其是现代网页往往习惯在文章页面的侧边栏和底部增加大量推荐阅读，使得二者几乎不存在文本统计上的特征差异。*
   *这一块我本来想用视觉大模型进行 layout 分析，但最终实现起来发现获取不受干扰的网页截图是一件会极大增加程序复杂度并降低处理效率的事情……*

  *Distinguishing between list pages and article pages is a common challenge in web scraping projects, especially when modern webpages often include extensive recommended readings in sidebars and footers of articles, making it difficult to differentiate them through text statistics.*

  *Initially, I considered using large visual models for layout analysis, but found that obtaining undistorted webpage screenshots greatly increases program complexity and reduces processing efficiency...*
  
- 重构了提取策略、llm 的 prompt 等；

  Restructured extraction strategies and LLM prompts;

  *有关 prompt 我想说的是，我理解好的 prompt 是清晰的工作流指导，每一步都足够明确，明确到很难犯错。但我不太相信过于复杂的 prompt 的价值，这个很难评估，如果你有更好的方案，欢迎提供 PR*

   *Regarding prompts, I believe that a good prompt serves as clear workflow guidance, with each step being explicit enough to minimize errors. However, I am skeptical about the value of overly complex prompts, which are hard to evaluate. If you have better solutions, feel free to submit a PR.*

- 引入视觉大模型，自动在提取前对高权重（目前由 Crawl4ai 评估权重）图片进行识别，并补充相关信息到页面文本中；

  Introduced large visual models to automatically recognize high-weight images (currently evaluated by Crawl4ai) before extraction and append relevant information to the page text;

- 继续减少 requirement.txt 的依赖项，目前不需要 json_repair了（实践中也发现让 llm 按 json 格式生成，还是会明显增加处理时间和失败率，因此我现在采用更简单的方式，同时增加对处理结果的后处理）

  Continued to reduce dependencies in requirement.txt; json_repair is no longer needed (in practice, having LLMs generate JSON format still noticeably increases processing time and failure rates, so I now adopt a simpler approach with additional post-processing of results)

- pb info 表单的结构做了小调整，增加了 web_title 和 reference 两项。

  Made minor adjustments to the pb info form structure, adding web_title and reference fields.

- @ourines 贡献了 install_pocketbase.sh 脚本

  @ourines contributed the install_pocketbase.sh script

- @ibaoger 贡献了 windows 下的pocketbase 安装脚本

  @ibaoger contributed the pocketbase installation script for Windows

- docker运行方案被暂时移除了，感觉大家用起来也不是很方便……

  Docker running solution has been temporarily removed as it wasn't very convenient for users...

# V0.3.5
- 引入 Crawlee(playwrigt模块)，大幅提升通用爬取能力，适配实际项目场景；
  
  Introduce Crawlee (playwright module), significantly enhancing general crawling capabilities and adapting to real-world task;

- 完全重写了信息提取模块，引入"爬-查一体"策略，你关注的才是你想要的；

  Completely rewrote the information extraction module, introducing an "integrated crawl-search" strategy, focusing on what you care about;

- 新策略下放弃了 gne、jieba 等模块，去除了安装包；

  Under the new strategy, modules such as gne and jieba have been abandoned, reducing the installation package size;

- 重写了 pocketbase 的表单结构；
  
  Rewrote the PocketBase form structure;

- llm wrapper引入异步架构、自定义页面提取器规范优化（含 微信公众号文章提取优化）；

  llm wrapper introduces asynchronous architecture, customized page extractor specifications optimization (including WeChat official account article extraction optimization);

- 进一步简化部署操作步骤。

  Further simplified deployment steps.
