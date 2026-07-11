# openclaw/extensions/browser 替换接口/兼容层调研（spec §2.1）

> 2026-07-11 · 对应 [`browser-stack-replacement-spec-2026-07.md`](./browser-stack-replacement-spec-2026-07.md) §2.1 的 7 项调研。
> 调研范围：`/home/wukong/wiseflow/openclaw/extensions/browser/` + openclaw core 对它的依赖面。
> 原则：调研结论出来前不动 extension 代码——本文件只产出结论与方案，不落实改码。

---

## 0. 总结论（先读这段）

**spec §0 / §2「用 forked camoufox-cli 直接替换 `openclaw/extensions/browser` extension」的预设，与 extension 的真实规模和架构存在重大结构性张力，需在动工前修订 spec。**

三个关键事实，每一个都改变方案性质：

1. **extension 不是 camoufox-cli 的薄壳，而是一整套企业级浏览器控制平面。** 约 16000 行实现 + 125 个测试文件，包含：Chrome 进程生命周期、原生 CDP WebSocket 客户端、Playwright-core (connectOverCDP) 会话、Chrome-MCP 备用传输、HTTP/WS gateway server、sandbox/host/node 三态分发、SSRF 防护、navigation guard、session tab registry、自带 `browser` CLI。spec §2 当前的结构图（"browser-bridge/cdp/config/..." 十来个顶层文件）只看到 barrel，没看到 `src/browser/` 下 ~200 个实现文件。

2. **替换的真正边界不是 extension 包，而是 `src/plugin-sdk/browser-*.ts` 这组 core 公共契约面。** core 的 sandbox / doctor / gateway / agent / config 代码 **不直接 import extension 内部**，而是 import `openclaw/plugin-sdk/browser-*` facade（~20 个文件，由 openclaw 架构强制）。这些 facade **定义在 core 侧**（`src/plugin-sdk/`），是带 major-version 稳定性承诺的公共 API。extension 是它们的实现者。**因此替换的正确表述是：保持 `plugin-sdk/browser-*` 契约，替换其背后实现**——不是删 extension 重写。

3. **extension 的 browser tool 本身已有 `upload` 和 `act` action。** spec §1.1 称"fork 补 upload 命令（上游 camoufox-cli 无 upload）"——这是对的（指 camoufox-cli），但 spec 行文隐含 openclaw browser tool 也缺 upload，这是误读。openclaw 的 `browser` tool **已有** `upload` action（`src/browser-tool.ts:942`）。forked cli 补 upload 是为 camoufox-cli 侧的持久化 session 发布流，与 openclaw browser tool 的 upload 能力无关。spec §5 各 publish skill「依赖 forked cli 的 upload」需理清：**那些 publish skill 之前到底是调 openclaw browser tool 还是调 camoufox-cli？** 这决定了替换是否真有必要。

> ⚠️ **据此，spec §2 的落地顺序第 3 步"按调研结论替换 extension"在结论修订前不应启动。** 建议见 §9。

---

## 1. §2.1-1 · extension 接口契约

### 1.1 暴露给 openclaw core 的接口面

extension 通过 `definePluginEntry`（`index.ts`）+ `definePluginEntry` setup（`setup-api.ts`）双入口接入 core。注册体在 `plugin-registration.ts:200` `registerBrowserPlugin(api)`，调用 4 个 plugin API：

| 注册调用 | 注册的东西 | 落点 |
|---|---|---|
| `api.registerTool(factory)` | agent 工具 `browser`（名 `browser`，label `Browser`）→ `createLazyBrowserTool` → `browser-tool.ts` | `plugin-registration.ts:201` |
| `api.registerCli(registrar, {commands:["browser"]})` | CLI 命令 `browser`（子命令 open/snapshot/... ） | `plugin-registration.ts:203` → `src/cli/browser-cli.ts` |
| `api.registerGatewayMethod("browser.request", handler)` | gateway RPC 方法 `browser.request`（scope `operator.admin`） | `plugin-registration.ts:210` → `handleBrowserGatewayRequest` |
| `api.registerService(createLazyBrowserPluginService())` | 后台服务 `browser-control`（按 `OPENCLAW_*_EAGER` env 启停） | `plugin-registration.ts:220` → `control-service.ts` |

附加注册：
- `reload: browserPluginReload`（`restartPrefixes:["browser"]`，配置 browser.* 变更触发 plugin 热重载）— `plugin-registration.ts:148`
- `nodeHostCommands: [{command:"browser.proxy", cap:"browser", handle→runBrowserProxyCommand}]` — `plugin-registration.ts:151`（node-host 远程浏览器代理命令）
- `securityAuditCollectors` — `plugin-registration.ts:163`

### 1.2 manifest 契约（`openclaw.plugin.json`）

```json
{
  "id": "browser",
  "enabledByDefault": true,
  "activation": { "onStartup": true, "onConfigPaths": ["browser"] },
  "contracts": { "tools": ["browser"] },
  "commandAliases": [{ "name": "browser" }],
  "skills": ["./skills"],
  "configSchema": { "type":"object", "additionalProperties":false, "properties":{} }
}
```

- `contracts.tools:["browser"]` —— core 据此处把 `browser` 注册进 tool catalog（见 §2）。
- `activation.onConfigPaths:["browser"]` —— `config.browser.*` 一旦出现就激活 plugin。
- `commandAliases` —— `browser` 作为顶级 CLI 命令别名。

### 1.3 公共 runtime API 面（`runtime-api.ts`，~95 行 barrel）

re-export ~85 个符号，分类（节选）：
- 生命周期：`browserStart` / `browserStop` / `browserStatus` / `browserDoctor` / `stopBrowserRuntime`
- profile：`browserProfiles` / `browserCreateProfile` / `browserDeleteProfile` / `resolveBrowserConfig` / `resolveProfile` / `getBrowserProfileCapabilities`
- tab：`browserOpenTab` / `browserCloseTab` / `browserFocusTab` / `browserTabs`
- 截图/snapshot：`browserScreenshotAction` / `browserSnapshot`
- 导航：`browserNavigate`
- 维护：`closeTrackedBrowserTabsForSessions` / `movePathToTrash`
- bridge：`startBrowserBridgeServer` / `stopBrowserBridgeServer`
- gateway：`handleBrowserGatewayRequest` / `runBrowserProxyCommand`
- CDP 微助手：`redactCdpUrl`

顶层还有 8 个小 barrel（`browser-cdp.ts` / `browser-bridge.ts` / `browser-config.ts` / `browser-control-auth.ts` / `browser-doctor.ts` / `browser-maintenance.ts` / `browser-profiles.ts` / `cli-metadata.ts`），都是 5–21 行的 re-export，非实现。

### 1.4 core 侧调用点（grep `src/` 全量，排除测试）

core **不直接 import `extensions/browser/**`**（符合 openclaw extension boundary）。core 通过 `openclaw/plugin-sdk/browser-*` facade 依赖 browser 能力。核心调用点：

| core 文件 | 依赖的 facade | 用途 |
|---|---|---|
| `src/agents/sandbox/browser.ts` | `browser-bridge` / `browser-profiles` | 沙箱内浏览器桥接 + profile 解析 |
| `src/agents/sandbox/browser-bridges.ts` | `browser-bridge`（`BrowserBridge` 类型） | 沙箱浏览器桥注册 |
| `src/agents/sandbox/context.ts` | `browser-control-auth` / `browser-profiles` | 沙箱上下文注入 browser control auth |
| `src/agents/sandbox/prune.ts` / `manage.ts` | `browser-bridge`（`stopBrowserBridgeServer`） | 沙箱销毁时关桥 |
| `src/agents/sandbox/registry.ts` | `"browser"` registry kind（SQLite） | 沙箱注册表分类 |
| `src/browser-lifecycle-cleanup.ts` | `browser-maintenance`（`closeTrackedBrowserTabsForSessions`） | session 结束清 tab |
| `src/commands/doctor-browser.ts` | browser doctor facade | doctor 检查 + clawd 旧 profile 清理 |
| `src/gateway/server-methods/agents.ts` | `browser-maintenance`（`movePathToTrash`） | agent 删除时清理 profile |
| `src/agents/tool-catalog.ts:208` / `system-prompt.ts:810` / `tool-mutation.ts:427` / `sandbox/constants.ts:37` | 字面量 `"browser"` | tool 名 hardcode |
| `src/agents/embedded-agent-subscribe.tools.ts:434` | `"browser"` | 默认工具集 |
| `src/entry.ts:33,196,250` | `"browser"` CLI 命令名 | CLI 路由 |
| `src/config/plugin-auto-enable.shared.ts:392,434,476` | `"browser"` tool/profile 启用探测 | auto-enable |
| `src/plugins/sdk-alias.ts:501` | `bundledPluginId:"browser"` | bundled plugin 别名 |

> 还有一个独立的并行 agent 报告（core→browser coupling）正在进行，其结论与本节一致时以本节为准；如有补充会在落地阶段并入。

### 1.5 §2.1-1 结论

extension 暴露给 core 的**契约面 = `openclaw/plugin-sdk/browser-*` 这组 facade**（`browser-bridge` / `browser-cdp` / `browser-config` / `browser-control-auth` / `browser-host-inspection` / `browser-maintenance` / `browser-node-host` / `browser-profiles` / `browser-trash` / `browser-types`）+ manifest `contracts.tools` + 4 个 `api.registerXxx`。**替换必须保持这组 facade 的类型签名和行为契约不破**（见 §6 风险 R1）。

---

## 2. §2.1-2 · tool 名注册

### 2.1 tool 名与摘要来源

- **tool 名：`browser`**（单一 tool，非 `browser_do`）。`browser-tool.ts:492` `createBrowserTool()` 定义 `{ label:"Browser", name:"browser", ... }`。
- **schema**（`browser-tool.schema.ts`，165 行）：扁平 TypeBox 对象，`action` 必填 string enum = `doctor | status | start | stop | profiles | tabs | open | focus | close | snapshot | screenshot | navigate | console | pdf | upload | dialog | act`（17 个 action）。
- **system prompt 里 browser tool 摘要来源**：`src/agents/system-prompt.ts:810` 处理 tool 描述。tool 的 `description` 文本来自 `browser-tool.ts` 的 tool 定义字段（非独立注入点）。**patches/007 的注入点不在 core，而在 patch 007 改的是 extension 侧 browser tool 的 description 文本**（见下）。

### 2.2 patch 007 注入点（实测）

`patches/007-browser-prefer-camoufox-cli.patch` 内容（实测）：在 `extensions/browser/src/browser-tool.ts` 的 tool `description` 字符串里追加"优先使用 camoufox-cli"提示文本。**这是改 extension 源码（被 patch 系统在构建期应用），不是改 core。** spec §3 删 patch 007 的判断成立：替换后整个 tool 就是 camoufox-cli，描述里再写"优先 camoufox-cli"无意义。

> 纠正 spec §2.1-2 的措辞"原 patch 007 注入点"——注入点在 extension 的 tool description，不在 system-prompt.ts。

### 2.3 tool execute 的三态分发（关键，spec 未提及）

`browser-tool.ts:509` `execute` 按 `target` 分发，`target` 默认 `sandboxBridgeUrl ? "sandbox" : "host"`（`browser-tool.ts:399,489`）：

| target | 路径 | 后端 |
|---|---|---|
| `sandbox` | `browser-tool.ts:401` → sandbox bridge URL | 沙箱内浏览器（容器化） |
| `host` | → `local-dispatch.runtime.ts` → `routes/` → `server-context` → `pw-session` → CDP/playwright | 本机浏览器 |
| `node` | → `callGatewayTool("node.invoke", ...)` → gateway → 远程 node 的 `browser.proxy` 命令（`invoke-browser.ts` 372 行） | 远程节点浏览器 |

`callGatewayTool("node.invoke")` 走 gateway `browser.request` 方法（`browser-gateway-contract.ts`，scope `operator.admin`）。

### 2.4 §2.1-2 结论：tool 名是否保持兼容

**建议：tool 名 `browser` 保持不变，schema 17 个 action 名保持不变。** 理由：
- core 侧 `tool-catalog.ts` / `system-prompt.ts` / `tool-mutation.ts` / `sandbox/constants.ts` / `fast-openclaw-tools.ts` 全 hardcode `"browser"`；改名是 major-version 级破坏，得不偿失。
- agent 已习惯 `browser` tool + 这套 action 语义；改名等于重训所有 crew 的 skill 文档。
- spec 没有给出改名的产品理由。借机改名收益为零、成本极高。

执行层：保持 tool 名/schema 不变，只把 `execute` 的 **`host` 分支后端**从 CDP/playwright 换成 forked camoufox-cli 子进程调用。`sandbox` / `node` 分支的处置见 §6 R4。

---

## 3. §2.1-3 · CDP/Playwright 依赖耦合深度

### 3.1 依赖声明

`package.json`：`playwright-core: 1.60.0`、`ws: 8.21.0`、`express: 5.2.1`、`commander`、`@modelcontextprotocol/sdk`、`typebox`。**源码内不出现 `camoufox` / `patchright` 字样**（grep 零命中）——patchright 通过 `overrides.sh` 在构建期把 `playwright-core` 替换为 patchright-core，源码层不可见。

### 3.2 架构层次（自上而下，含行数估算）

| 层 | 代表文件 | 行数 | 角色 |
|---|---|---|---|
| Agent Tool | `src/browser-tool.ts` | 1034 | 17 action 路由，三态分发 |
| HTTP/进程内 Routes | `src/browser/routes/agent.*.ts` 等 | ~3000+ | dispatcher + 各 action handler |
| Playwright Session | `src/browser/pw-session.ts` | ~1700 | **`chromium.connectOverCDP(target)`**（pw-session.ts:947，唯一 PW↔Chrome 连接点） |
| Playwright Tools | `src/browser/pw-tools-core.*.ts` | ~2000+ | interactions/snapshot/downloads/storage/state/trace |
| Playwright AI | `src/browser/pw-ai.ts` + `pw-role-snapshot.ts` | ~800 | AI 驱动 snapshot 生成 |
| 原生 CDP | `src/browser/cdp.ts` + `cdp.helpers.ts` | ~800+ | 原始 WebSocket CDP，screenshot 等 |
| Chrome MCP | `src/browser/chrome-mcp.ts` | ~1400 | 备用非-CDP 传输 |
| Chrome 生命周期 | `src/browser/chrome.ts` + 子文件 | ~2500+ | spawn/launch args/CDP 探测/port 分配 |
| PW 加载器 | `src/browser/playwright-core.runtime.ts` | 13 | CJS `require("playwright-core")` |

### 3.3 CDP 连接流（实测）

1. `chrome.ts` 用 `--remote-debugging-port=<port>` 起 Chrome；
2. 轮询 `GET http://127.0.0.1:<port>/json/version` 拿 `webSocketDebuggerUrl`；
3. `cdp.ts:normalizeCdpWsUrl()` 归一化；
4. 要么 `cdp.ts:withCdpSocket()` 裸 WS，要么 `pw-session.ts:947` `chromium.connectOverCDP(target)` 给 Playwright。

### 3.4 §2.1-3 结论：全删 vs 薄壳转调 vs 重写

三分类清单：

**A. 全删（被 camoufox-cli daemon 取代，~6000+ 行 + 对应测试）**
- Chrome 生命周期：`chrome.ts` 全家 + `chrome.executables.ts` / `chrome.diagnostics.ts` / `chrome.profile-decoration.ts` / `chrome.version.ts` / `chrome.default-browser*`
- 原生 CDP：`cdp.ts` / `cdp.helpers.ts` / `cdp-timeouts.ts` / `cdp-target-filter.ts` / `cdp-proxy-bypass.ts` / `cdp-reachability-policy.ts` / `cdp.screenshot-params*`
- Chrome MCP：`chrome-mcp.ts` / `chrome-mcp.runtime.ts` / `chrome-mcp.snapshot.ts`
- PW Session：`pw-session.ts` 全家（含 `pw-session.page-cdp.ts` 等 ~12 文件）——前提是 camoufox-cli 自己管 page 生命周期
- `playwright-core.runtime.ts` + `package.json` 的 `playwright-core`/`ws` 依赖

**B. 重写适配（保留职责，换后端调用，~5000+ 行）**
- Playwright Tools 层 `pw-tools-core.*.ts`（interactions/snapshot/downloads/storage）：语义对齐 camoufox-cli 命令（snapshot→`snapshot`、click→`click`、fill→`fill`、upload→`upload`、eval→`eval`...），逐个改实现不破 action 契约
- PW AI `pw-ai.ts` / `pw-role-snapshot.ts`：camoufox-cli 的 snapshot 格式若与 PW accessibility snapshot 不同，需重写 role 解析
- Routes 层 `routes/agent.*.ts`：dispatcher 改成调 camoufox-cli 子进程
- `server-context.ts`：浏览器可用性探测改成探 camoufox-cli daemon
- `browser-tool.ts` 的 `host` 分支 execute

**C. 保留（与浏览器后端无关或 openclaw 专属策略）**
- SSRF 防护：`ssrf-policy-helpers.ts` / `cdp-reachability-policy.ts` 的策略逻辑（CDP 传输没了，但 SSRF 校验对 camoufox-cli 访问的 URL 仍需要——改为在调 cli 前校验目标 URL）
- `navigation-guard.ts`：导航安全策略
- `control-auth.ts` / `csrf.ts` / `http-auth.ts`：control server 鉴权
- `session-tab-registry.ts` / `session-tab-cleanup.ts`：tab 跟踪清理（正交于后端）
- `output-directories.ts` / `output-files.ts` / `paths.ts` / `safe-filename.ts` / `trash.ts`：输出与清理
- `rate-limit-message.ts` / `request-policy.ts` / `errors.ts`
- `vision.ts` / `screenshot-annotate.ts`：截图后处理
- `plugin-sdk/browser-*` facade 类型定义全部保留（契约）

> **关键判断：B 类的"重写适配"工作量 ≈ 重写半个 extension。** camoufox-cli 的命令集（open/snapshot/click/fill/select/check/hover/press/text/eval/screenshot/pdf/scroll/wait/tabs/switch/close/sessions/cookies/install）与 PW Tools 层的细粒度 action 不完全 1:1（如 PW 的 `setInputFiles` 多路径、`download` 事件流、`storageState`、`trace`），需逐个对账。

---

## 4. §2.1-4 · profile / session 管理

### 4.1 现状

- profile 目录：`~/.openclaw/browser/<profileName>/user-data/`（`chrome.ts:resolveOpenClawUserDataDir`）。
- 关键文件：`src/browser/profiles.ts`（`allocateCdpPort`/`allocateColor`/`getUsedPorts`）、`profiles-service.ts`（list/create/delete）、`config.ts`（`resolveBrowserConfig`/`resolveProfile`/`ResolvedBrowserProfile`）、`config-mutations.ts`、`trash.ts`。
- 默认 profile 名：`openclaw`（`plugin-sdk/browser-profiles.ts:DEFAULT_OPENCLAW_BROWSER_PROFILE_NAME`）。
- 配置字段：`cdpPort` / `cdpUrl` / `userDataDir` / `executable` / `proxy` 等（`plugin-sdk/browser-types.ts:ResolvedBrowserConfig`）。
- **无"持久化 vs 临时"显式区分**——profile 都是 user-data 目录，临时用就建一个命名 profile 再删。spec §0 补充 A 的"临时性 session 随机关纹关闭自清"是 camoufox-cli 模型，openclaw 当前没有。

### 4.2 与 camoufox-cli 模型对应

| openclaw 现状 | camoufox-cli | 对应方式 |
|---|---|---|
| `~/.openclaw/browser/<name>/user-data/` | `~/.camoufox-cli/profiles/<session>/` | 统一到 camoufox-cli 路径 |
| `ensureBrowserAvailable()` 探 Chrome | daemon 自动管 | 删，改探 daemon |
| `allocateCdpPort()` | cli 自管端口 | 删 |
| `resolveBrowserExecutableForPlatform()` | cli 自带二进制 | 删（但 `plugin-sdk/browser-host-inspection.ts` 暴露了同名契约 → 见 R2） |
| `userDataDir` 配置字段 | session 名 | 简化配置 |
| profile = 命名 user-data 目录 | session = 命名 profile dir + 冻结指纹 json | 概念对齐 |

### 4.3 §2.1-4 结论：D18 模板模式落点

**建议：D18 模板模式落在 `~/.camoufox-cli/profiles/<session>/`（camoufox-cli 原生路径），`~/.openclaw/logins/` 只放中央 cookie/UA JSON。** 理由：
- spec §1.3 D18 已写 `cp ~/.openclaw/logins/_template/camoufox-cli.json 进 ~/.camoufox-cli/profiles/<platform>/`，本就两处分工：`logins/` 放导出物（cookie+UA+模板 json 源），`profiles/` 放运行时 profile dir。调研确认这分工合理，不改。
- openclaw 的 `~/.openclaw/browser/` 旧 profile 目录随 Chrome 生命周期层一起删（§3.4-A），迁移期由 `doctor --fix` 归档（`doctor-browser.ts:95` 已有 trash 机制）。
- `profiles-service.ts` 的 list/create/delete 改成薄壳转调 `camoufox-cli sessions` 命令。
- `allocateCdpPort` / `getUsedPorts` 全删。

**spec §0 补充 A（持久化 vs 临时）的实现**：openclaw 侧加一个 profile 概念区分——持久化平台 session = 带 `--persistent` + cp 模板的 camoufox-cli session；临时 = 不 `--persistent` 的临时 session。这在 `resolveBrowserConfig` 里加一个 `persistent: boolean` 维度即可，不破 facade 类型（追加可选字段）。

---

## 5. §2.1-5 · browser-doctor / maintenance

### 5.1 现状

**doctor**（`src/browser/doctor.ts` 156 行 + `src/doctor-browser.ts`）检查：
1. plugin 启用 + profile 存在 + driver mode（cdp vs chrome-mcp）
2. Chrome MCP attach target 可达性
3. Chromium 二进制检测（`resolveBrowserExecutableForPlatform`）
4. Linux headed 模式 display 可用性
5. root sandbox 警告
6. CDP HTTP/WS 可达性
7. 旧 clawd profile 残留检测

doctor `--fix`：归档 `~/.openclaw/browser/clawd/` 旧 profile 到 trash（`doctor-browser.ts:95`）。

**maintenance**：
- `session-tab-cleanup.ts`（98 行）：`closeTrackedBrowserTabsForSessions` + 周期 sweep（5min 检查 / idle 120min / 每 session max 8 tab）。
- `trash.ts`：`movePathToTrash`（profile 删除时）。
- 孤儿进程清理：依赖 `chrome.ts:stopRunningBrowser`。

### 5.2 spec 提到的 profile 体积回收问题

spec §2.1-5 称"`~/.camoufox-cli/profiles/` 已 1.8GB / 22 dir，persistent 不自动清理"。这是 camoufox-cli 侧的运维问题，openclaw maintenance 需新增"camoufox-cli profile 体积回收"职责——但**注意**：原则 5 严禁浏览器方案导入 cookie、原则补充 D profile 丢失必须重建重登录。所以"体积回收"只能回收**临时性 session**的 profile（随机关纹关闭自清），持久化平台 profile **不能自动清**（清了等于丢登录态）。需在 maintenance 里区分两类 profile。

### 5.3 §2.1-5 结论

- doctor 检查 1/2/3/6/7 改写：Chrome 二进制 → camoufox-cli 二进制/daemon 探活；CDP 可达性 → daemon socket 可达性；Chrome-MCP attach → 删。检查 4/5（display/root）保留。
- doctor `--fix` clawd 归档逻辑保留一个迁移窗口后删。
- `session-tab-cleanup` 保留（正交于后端，但 camoufox-cli 的 tab 模型不同——`tabs`/`switch`/`close-tab` 命令 vs PW 的 targetId，需对账 tab registry 与 cli tab 概念是否一致）。
- 新增 maintenance：临时性 camoufox-cli profile 体积回收（只清临时，不碰持久化）。
- 孤儿进程清理：camoufox-cli daemon `close --all` 兜底，openclaw 侧 stop 时调它。

---

## 6. §2.1-6 · setup-api.ts

### 6.1 现状

`setup-api.ts`（58 行）**只做 `registerAutoEnableProbe`**——检测 config 里 `browser.*` / plugin entry / tool policy 引用 `browser`，命中则自动启用 plugin。**不安装任何浏览器二进制。**

二进制安装是**运行期懒触发**：`chrome.ts:ensureBrowserAvailable` → `resolveBrowserExecutableForPlatform` 在系统找 Chrome/Chromium/Brave/Edge；找不到则 doctor 报"Install Chrome/Chromium"。

### 6.2 §2.1-6 结论

- `autoEnableProbe` 保留（轻量配置检查，与浏览器后端无关）。
- 二进制安装从"运行期懒找系统 Chrome"改成"setup/doctor 期触发 `camoufox-cli install --with-deps`"。接入点：`plugin-sdk/browser-host-inspection.ts` 的 `resolveGoogleChromeExecutableForPlatform` / `readBrowserVersion` 契约改成探 camoufox-cli 二进制 + `camoufox-cli install` 状态（见 R2）。
- 首次无 camoufox-cli 时，doctor 给可执行安装提示，不静默失败。

---

## 7. §2.1-7 · 测试面替换范围

### 7.1 规模

extension 内 **125 个测试文件**（含 2 个 e2e）。`index.test.ts`（336 行）是顶层契约测试入口。`test-fetch.ts`（26 行）/`test-support.ts`（18 行）是测试辅助 barrel，re-export `plugin-sdk/test-fixtures` + `plugin-sdk/test-env`。

### 7.2 三分类（与 §3.4 对应）

**删（~55 文件）**：Chrome 生命周期 / CDP / PW session / PW tools / PW AI / Chrome-MCP 相关测试。被删的实现层对应的测试一律删（openclaw AGENTS.md 明确："Tests protect canonical behavior and migration boundaries, not obsolete internals. Delete tests for removed fallback paths"）。

**改适配（~50 文件）**：profile / config / doctor / CLI（~20 文件，大量可移植）/ browser-tool / maintenance / output / security-audit / gateway / agent route 契约测试——保留断言行为，改 mock 后端。

**加**：camoufox-cli 子进程适配层测试 + daemon 健康检查 + profile 管理（持久化/临时分流）+ fail-first 队列 + upload/identity export 命令。

### 7.3 §2.1-7 结论

测试面替换的核心是 **behavior-level 契约测试保留、transport-level 实现测试删除**。`browser-tool.test.ts` / `server.agent-contract-*.test.ts` 这类断言"action X 产生结果 Y"的留下；`pw-session.*.test.ts` / `cdp.*.test.ts` 这类绑死 PW/CDP 内部的删。`index.test.ts` 顶层契约需重写为 camoufox-cli 后端的等价契约。

---

## 8. 依赖图（一句话版）

```
agent → tool "browser"(browser-tool.ts) ─┬─ host ─→ local-dispatch → routes → server-context → [PW|CDP|Chrome-MCP] → Chrome
        ↑ schema 17 actions                ├─ sandbox ─→ BrowserBridge → sandbox 内浏览器
        │                                  └─ node ─→ gateway "browser.request" → node-host "browser.proxy" → invoke-browser.ts → 远程
core(sandbox/doctor/gateway/agent) ──import──→ plugin-sdk/browser-* facade ←──implements── extensions/browser
```

替换 = 把上图 `[PW|CDP|Chrome-MCP] → Chrome` 这一段换成 `camoufox-cli daemon`，保持左侧 tool 契约与右侧 facade 契约不破。

---

## 9. 风险点与 spec 修订建议

### R1 [CRITICAL] facade 契约不可破，但需逐个核对
`plugin-sdk/browser-*` 是 core 公共契约（带 major-version 承诺）。其中 `browser-host-inspection.ts` 暴露 `resolveGoogleChromeExecutableForPlatform` / `readBrowserVersion`——这俩名字绑死 Chrome。换 camoufox-cli 要么改契约名（破坏性，需 major + 迁移所有 caller）、要么保留名字但语义偷换成 camoufox-cli（误导）。**建议**：spec 增补一节「plugin-sdk/browser-* facade 改造清单」，逐个 facade 列出 保留/改名/新增/废弃。

### R2 [CRITICAL] sandbox/host/node 三态架构与 camoufox-cli daemon 的关系未定
spec 通篇假设"一个 camoufox-cli daemon"。但 openclaw 有 sandbox（容器内浏览器）和 node（远程节点浏览器）两套额外路径。forked camoufox-cli daemon 装在哪？sandbox 容器内要装 camoufox-cli 吗？远程 node 要装吗？**建议**：spec §2 增补「三态分发在新栈下的处置」——最小可行方案是**本次只替换 `host` 分支**，`sandbox`/`node` 分支保留旧 CDP/PW 后端或暂时禁用，分阶段推进。否则工作量翻倍且跨容器/远程验证成本极高。

### R3 [HIGH] 工作量级修正
spec §11 落地顺序第 3 步"替换 extension"被列为一项。实测这是 ~16000 行实现 + ~55 文件测试删除 + ~50 文件测试改写的工程，不是一步。**建议**：spec 把第 3 步拆成 3a（删 Chrome/CDP/Chrome-MCP/PW-session 层 + 依赖）、3b（PW-Tools/Routes 改写适配 camoufox-cli）、3c（facade 契约对账 + 测试重写）三个子阶段，每个子阶段独立可验证。

### R4 [HIGH] camoufox-cli 命令集与 PW action 不 1:1
spec §1.1 列的 camoufox-cli 命令集缺 download 事件流、storageState、trace、多文件 upload、role-based snapshot 等 PW 能力。forked cli 需补的不止 upload/identity-export，还有这些。**建议**：spec §1.1 增补「PW action ↔ camoufox-cli 命令对账表」，列出对不齐的能力及处置（补 cli / 降级 / 弃用该 action）。

### R5 [HIGH] spec §5 各 publish skill 的现状未理清
spec §5 假设各 publish skill「依赖 forked cli 的 upload」。但 openclaw browser tool 本身有 upload（§0 事实 3）。**这些 skill 现在到底调什么？** 需先排查 `crews/*/skills/*publish*/scripts/` 现状，确认它们是调 openclaw `browser` tool 还是已有 camoufox-cli 调用。这决定 §5 改造范围。**建议**：spec 落地前增补一步「§5 现状排查」，本轮调研未覆盖 crews/ 下脚本。

### R6 [MEDIUM] profile 体积回收与原则 5 的冲突
spec §2.1-5 担心 profile 1.8GB 不清理，但原则 5/补充 D 禁止丢登录态。自动清理只能清临时 session。**建议**：spec §2.1-5 明确「只回收临时性 session profile，持久化 session profile 仅 doctor 手动清理」。

### R7 [MEDIUM] patchright 整体去掉的连带
spec 补充 C「patchright 整体去掉，overrides.sh 不再注入 patchright-core」。但 patchright 是 `playwright-core` 的 drop-in 替换，去掉后 `playwright-core:1.60.0` 直接依赖原版 playwright。若 §3.4-A 全删 PW 层则无所谓；若 §3.4-B 保留部分 PW Tools 层（走 camoufox-cli 而非 PW），则 playwright-core 依赖应一起删。**建议**：spec §3 明确「playwright-core + ws 依赖随 PW 层一起从 package.json 移除」，与 patchright 去掉合并为一次。

### R8 [LOW] browser-guide skill 并入路径
spec §2.2 说并入 `extensions/browser/skill/`（单数）。实测当前是 `extensions/browser/skills/browser-automation/`（复数 skills）。manifest `skills:["./skills"]`。**建议**：并入路径用现有 `skills/browser-automation/`，不动 manifest 的 `./skills` 指向，避免改 manifest skills 字段触发 skill 加载逻辑变动。

---

## 10. 给 spec 的最小修订清单（落地前必做）

1. **§0 决策总览增补**：明确替换边界 = `plugin-sdk/browser-*` facade 契约保持 + facade 背后实现替换（不是删 extension 重写）。
2. **§2 增补 §2.0**：三态分发（sandbox/host/node）在新栈下的处置（建议本次只替换 host）。
3. **§2.1 调研结论并入**：本文件作为 §2.1 产出已就位，spec §2.1 标注"已调研 → 见 browser-extension-replacement-research.md"。
4. **§2 拆 §11 第 3 步为 3a/3b/3c**。
5. **§1.1 增补 PW action ↔ camoufox-cli 命令对账表** + forked cli 需补的 download/storageState/trace/多文件 upload/role-snapshot。
6. **§3 明确 playwright-core+ws 随 PW 层移除**，与 patchright 去掉合并。
7. **§5 增补前置排查**：各 publish skill 现状（调 browser tool 还是 camoufox-cli）。
8. **§2.2 并入路径**改成现有 `skills/browser-automation/`。
9. **§2.1-5 profile 体积回收**限定只清临时 session。

---

## 11. 下一步建议

调研结论已出。**在 spec 按 §10 修订前，不动 extension 代码**（遵循 spec §2.1 末尾的约束）。建议下一步：

1. 把本文件给用户确认 §0 总结论与 §10 修订清单；
2. 用户拍板后，更新 `browser-stack-replacement-spec-2026-07.md` §0/§2/§11；
3. 再按修订后 spec 的落地顺序，从 fork camoufox-cli（§1）开始。

> 本调研未覆盖：`crews/*/skills/` 下脚本现状（§5 改造范围前置排查）、camoufox-cli 0.6.2 源码细节（fork 改造点的精确行号，属 §1 fork 阶段任务）。这两项建议各自单独排期，不阻塞本调研结论。

---

## 12. 架构转向（2026-07-11 用户拍板，替代 spec §0「整体替换 extension」路线）

> 本节是用户在听完 §1-§9 调研后的决策。与 spec §0 的「整体替换 extension」预设存在重大张力（见 §0 总结论），用户选择了一条更小、更干净的路线。本节**优先级高于 §0-§11**，spec 落地以本节为准。

### 12.1 用户对 sandbox 的判断

OpenClaw 加 sandbox 是为了「无头模式跑有头浏览器」提升自动化能力。但实践发现：
- `camoufox-cli`（反指纹 Firefox）在反侦测上 **> CDP 直连本地真实 Chrome（有头）**，更别提 Docker 内 Chromium；
- `camoufox-cli` 比 CDP 稳得多，命令封装更完善；
- sandbox 实际暴露的是 CDP 鉴权端口——本质还是 CDP，反侦测优势并不来自 sandbox 本身。

结论：**sandbox 整条路删掉**，由 forked `camoufox-cli` 替代其角色。不是「改 sandbox 容器内容」，是「删 sandbox、camoufox-cli 走新旁路」。

### 12.2 关键代码事实：Browser Tool 层写死了 CDP + Chrome-MCP 两个后端，无抽象 seam

这是决定方案形态的硬事实，已在本次复核中用代码确认：

- `extensions/browser/src/browser/routes/agent.act.ts:733,784` 等每个 action handler 内部都有同一个二元 switch：
  ```ts
  if (getBrowserProfileCapabilities(profileCtx.profile).usesChromeMcp) {
    // → chrome-mcp.runtime（Chrome 扩展 relay，不走 CDP）
  } else {
    // → pw-session → chromium.connectOverCDP()（走 CDP）
  }
  ```
  逐个 action 重复，没有抽象。
- `grep -rn "interface.*Backend\|interface.*Driver\|type BrowserBackend\|abstract" src/browser/` **零结果**。不存在可插拔后端接口。把 camoufox-cli 塞进 routes 层当「第三后端」要逐个改 ~50 个 action handler——这就是 spec §0「整体替换 extension」代价的来源。
- **但上一层有干净 seam**：`browser-tool.schema.ts:52` `const BROWSER_TARGETS = ["sandbox","host","node"]`，`browser-tool.ts` 在此三态分发。其中 `sandbox` 分支**根本不进 routes/**——它走 Docker bridge。即 target 这层天然支持「绕开 routes/ 的旁路」。

### 12.3 落地形态：双线，改动比 spec §0 小一个数量级

```
browser tool execute(target)
├─ target="camoufox"   ← 新增（占被删的 sandbox 槽位）
│   └─ camoufox-cli.adapter.ts（新，~1 模块）→ forked camoufox-cli 子进程 + JSON-over-unix-socket
│      ※ 完全绕开 routes/、pw-session、chrome-mcp
│
├─ target="host"       ← 保留，patch 删 local-managed 分支
│   └─ local-dispatch.runtime → routes/ → (pw-session/CDP | chrome-mcp)
│      ├─ existing-session（真机 Chrome，走 chrome-mcp relay）
│      └─ remote-cdp（远端 Chrome，走 CDP）
│
└─ target="node"       ← 保留（Gateway 远程代理，走 host 同款 routes）
```

- **线 1（日常主力）**：`target=camoufox` → 新 adapter → forked camoufox-cli。camoufox-cli 是 Firefox 系，自带 JSON-over-unix-socket 协议，不讲 CDP。adapter 把 `browser` tool 的 17 个 action 翻译成 camoufox-cli 命令。持久 profile 落 host 文件系统（`~/.camoufox-cli/profiles/<platform>/` + 复用 `~/.openclaw/logins/`），**无容器、无持久 vs 临时的矛盾**——§8 R2 随 sandbox 一并消解。
- **线 2（特殊情况）**：`target=host`（existing-session 接登录态已就绪的真机 Chrome，或 relay）+ `target=node`（remote-cdp）。routes/ 层、pw-session、chrome-mcp **全部不动**。只 patch 掉 `local-managed` 分支（`chrome.ts` spawn + `ensureBrowserAvailable` 下载 Chromium 那条路），避免额外下 Chromium 干扰 sandbox / 浪费存储。

### 12.4 对 §8 风险的重评

| 风险 | 原评级 | 转向后 |
|-------|--------|--------|
| R1 sandbox=Chrome-in-container+CDP，camoufox=Firefox 不能直替 | CRITICAL | **消解**——不「替」sandbox 容器内容，删 sandbox 整条路、camoufox 走新旁路 |
| R2 持久会话 vs 临时容器 | CRITICAL | **消解**——sandbox 删了，camoufox profile 在 host |
| R3 plugin-sdk/browser-* facade 契约破坏 | HIGH | **降级**——facade 不动，只删 sandbox 实现 + 加 camoufox 新分支，facade 背后实现替换不破坏契约束缚（仍属 major-version 边界，需评审） |
| R4 camoufox-cli 命令集与 PW action 不 1:1 | HIGH | **保留**——adapter 翻译 17 action 时仍需对账表（§10 第 5 项），但范围从「全 extension」缩到「一个 adapter 模块」 |
| R5 各 publish skill 现状未理清 | HIGH | **保留**——仍需排查 `crews/*/skills/*publish*/scripts/` |
| R7 patchright 去掉连带 | MEDIUM | **简化**——线 2 的 existing-session 用真机 Chrome、remote-cdp 用远端 Chrome，都不需要 patchright；`overrides.sh` 去 patchright，playwright-core 留给 remote-cdp 用，不再被顶替 |
| 007 patch（system-prompt 加「prefer camoufox-cli」） | — | **保留并强化**——这是分流总开关，与双线形态一致 |

### 12.5 browser-guide skill 处置

- 实测 `extensions/browser/` 下**无 skills 目录**；openclaw skill 加载器只认 `skills/`（公共）和 `crews/<id>/skills/`（crew 专属），没有 `extensions/*/skills/` 加载路径。spec §2.2「并入 `extensions/browser/skill/`」**不可行**，应撤回。
- `browser-guide` 现位于 `skills/browser-guide/`（公共 skill），且其 §1 已写就是双线分流（「任何场景先 camoufox-cli，4 种兜底才用内置 browser tool」）。**位置不动，只更新内容**：§3「内置 browser tool fallback」明确成「target=host（existing-session/relay）或 target=node（remote-cdp）；sandbox 已删、local-managed 已 patch 掉」。
- spec §2.2 的「替代原版已有 skills」：原版 `extensions/browser` 不带 skill，只有 `docs/tools/browser.md`（文档）。那份文档由 `overrides.sh` sed 处理，本转向下更新其内容即可，不涉及 skill 替换。§8 R8 据此**撤销**。

### 12.6 修订后的落地顺序（替代 spec §11）

1. **fork camoufox-cli**（spec §1）——独立分支，不碰 extension。
2. **写 `camoufox-cli.adapter.ts`**：17 action → camoufox-cli 命令翻译 + JSON-over-unix-socket 通信。这是本路线唯一的新 extension 代码。
3. **patch extension**（一次性）：
   - `browser-tool.schema.ts`：`BROWSER_TARGETS` 删 `sandbox`、加 `camoufox`；
   - `browser-tool.ts`：删 sandbox 分发分支，加 camoufox 分支调 adapter；
   - `profile-capabilities.ts` / `chrome.ts` / `ensureBrowserAvailable`：删 `local-managed` 分支及 Chromium 下载逻辑；
   - 删 `openclaw/src/agents/sandbox/browser*.ts` + `bridge-server.ts` 的 sandbox 桥；
   - 删 `plugin-sdk/browser-bridge.*` facade（sandbox 桥契约）。
4. **`overrides.sh`**：去 patchright 注入；`docs/tools/browser.md` 文本更新成双线模型。
5. **`browser-guide` SKILL.md §3**：更新 fallback 描述。
6. **007 patch**：保留，视情强化措辞。
7. 验证：线 1 camoufox-cli 端到端 + 线 2 existing-session/remote-cdp 回归。

### 12.7 仍需用户确认的两点

1. **target 新值的命名**：`camoufox` 还是 `cli` 还是别的？（`sandbox` 槽位复用语义不清晰，建议新名字而非复用 `sandbox`。）
2. **线 2 的 remote-cdp 是否真保留**：如果有远端 Chrome 需求就留；若全场景都能被 camoufox-cli + existing-session 覆盖，remote-cdp 也可一并删，进一步收缩。本轮不预设，待用户定。
