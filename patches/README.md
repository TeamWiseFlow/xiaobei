# Wiseflow Patches

wiseflow 针对原版 openclaw 提供的非侵入式补丁与依赖覆盖，由 `apply-addons.sh` 自动应用。

### 1. 代码补丁（*.patch）

对 OpenClaw 打的 git patch，按序号命名，顺序应用：

| 补丁 | 功能 |
|------|------|
| `002-disable-web-search-env-var.patch` | 添加 `OPENCLAW_DISABLE_WEB_SEARCH` 环境变量，可按需禁用内置 web_search（由 smart-search skill 通过浏览器替代） |
| `007-prefer-camoufox-cli.patch` | system-prompt 引导：`browser` tool 描述改成 "Prefer camoufox-cli for browser automation; use this tool only when camoufox-cli cannot handle the task or the user explicitly requests it"（§12.6 step 6，分流总开关）。改 `src/agents/system-prompt.ts`（core `coreToolSummaries["browser"]`，渲染进 agent 工具列表摘要），与 001 改的 extension 侧 `browser-tool.ts` 是不同文件、不同消息，不冗余 |

> 浏览器转向详见 `docs/browser-stack-replacement-spec-2026-07.md` + `docs/browser-extension-replacement-research.md` §12。

### 1a. forked camoufox-cli（`camoufox-cli/`）

`camoufox-cli/` 是上游 [`Bin-Huang/camoufox-cli`](https://github.com/Bin-Huang/camoufox-cli) @ 0.6.2 的 vendored fork，浏览器栈转向的线 1 后端。在上游基础上加了三件事（spec §1.1）：`upload` 命令、daemon fail-first 队列、`identity export` 命令。构建+全局安装：`patches/camoufox-cli/build.sh`（替换 `$PATH` 上的上游 `camoufox-cli`）。详见 `camoufox-cli/README.md`。

### 1b. browser-camoufox-pivot per-file 补丁（`browser-camoufox-pivot/patches/`）

浏览器栈转向 step 3（3a 增量 + 3b 减法 + doc）的 35 个**单文件 patch**，按「一个 patch 只改一个上游文件」拆分（原 001 monolith 35 文件合一失效面太大，上游漂一个文件就挂整条）。命名 `NN-{mod|del}-<path--with--dashes>.patch`，按文件名 sort 顺序应用；各 patch 改不同文件、彼此独立。内容：3a 加 `camoufox` target + adapter 早返回 + **default 改成 camoufox**（`browser-tool.ts`：无 target 无 node 无 existing-session profile 时走 camoufox，3b 删了 local-managed 故旧默认路径已死；description 同步成 `Default: camoufox`；upload 路径校验前置到 camoufox 早返回前，闭合 camoufox+upload 绕过 `resolveExistingUploadPaths` 的安全缺口）；3b 删 sandbox target + 删 host `local-managed` 分支 + 删 `src/agents/sandbox/browser*.ts` + bridge-server sandbox 桥 + `plugin-sdk/browser-bridge.*` facade + `--browser` CLI flag + `/sandbox/novnc` route；`docs/tools/browser.md` 改双线模型。线 2（host/node + existing-session/remote-cdp）保留，测试里测 host 行为的 case 显式 `target: "host"`。`apply-addons.sh` 在基础 patch 循环后应用此子目录。

### 1c. browser-camoufox-pivot 新增文件（`browser-camoufox-pivot/files/`）

`browser-camoufox-pivot/files/` 下是转向要**新增**进 openclaw extension 的整文件：`camoufox-cli.adapter.ts`（17 action → forked cli 翻译 + unix-socket 通信）+ `camoufox-cli.adapter.test.ts`（33 单测）。`apply-addons.sh` 在 patch 循环后 `cp` 进 `openclaw/extensions/browser/src/`（`git clean -fd` 会清 untracked，故新文件必须走 patches/ 而非直接写 openclaw）。per-file patch 只改**现有**文件接 adapter。详见 `browser-camoufox-pivot/README.md`。

### 2. 依赖覆盖（overrides.sh）

`overrides.sh` 在 openclaw 恢复干净状态后最先执行。浏览器转向后**去掉 patchright-core 注入**（`PATCHRIGHT_VERSION` 相关逻辑删除）：线 2 的 existing-session 用真机 Chrome、remote-cdp 用远端 Chrome，都不需要 patchright；playwright-core 保留给 remote-cdp 用，不再被 patchright 顶替。

### 辅助工具

- `generate-patch.sh`：从当前 openclaw 工作区生成 patch 文件的辅助脚本，在项目根目录运行。

### 已删除补丁历史

| 补丁 | 删除时间 | 原因 |
|------|---------|------|
| `001-relax-exec-allowlist-shell-syntax.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游 exec 审批重构为 risk-based，`&&`/`\|\|`/`;` 复合命令已原生支持逐段匹配 allowlist；wiseflow 已改走 `.sh` 脚本不再直接 exec。原目标代码 `splitShellPipeline` 已删，无法 re-port |
| `001-browser-camoufox-pivot.patch`（monolith） | 2026-07-11（拆分） | 35 文件合一失效面太大，按「一个 patch 只改一个上游文件」拆成 35 个单文件 patch，移至 `browser-camoufox-pivot/patches/`（见 §1b）。内容不变，干净上游逐个 `git apply --3way` 验证通过 |
| `004-chrome-port-grace-retry.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游新增 `ensureManagedChromePortAvailable` + `recoverOwnedStaleManagedChromeCdpListener`，完全覆盖 |
| `003-act-field-validation.patch` | 2026-07-11（浏览器转向） | 默认走 camoufox-cli（不经 browser tool 的 act 路由），fallback 路径偶尔用，前置校验价值有限；先拿掉，后面有需求再加 |
| `005-browser-timeout-env-var.patch` | 2026-07-11（浏览器转向） | 基于 patchright/browser tool 的超时调优，camoufox-cli 走旁路不受影响，fallback 路径偶尔用；先拿掉，后面有需求再加 |
| `006-connectovercdp-no-defaults.patch` | 2026-07-11（浏览器转向） | `noDefaults` 是 patchright 1.60+ 专属选项，patchright 整体去掉后原版 playwright-core 的 `connectOverCDP` 不支持该参数；remote-cdp 保留但走原版 PW 即可 |

> 注：`007` 曾于 2026-07-11 计划"并入 001"并记入删除历史，后改为**保留为独立 patch**（system-prompt 引导与架构 patch 解耦，便于单独 revert/调序），见上 §1 active 表。
