# Wiseflow Patches

wiseflow 针对原版 openclaw 提供的非侵入式补丁与依赖覆盖，由 `apply-addons.sh` 自动应用。

### 1. 代码补丁（*.patch）

对 OpenClaw 打的 git patch，按序号命名，顺序应用：

| 补丁 | 功能 |
|------|------|
| `001-browser-camoufox-pivot.patch` | 浏览器栈转向：删 sandbox target + 删 host `local-managed` 分支 + 新增 `target=camoufox` 旁路（调 forked camoufox-cli adapter）+ system-prompt 的 browser 工具摘要注入"优先 camoufox-cli"引导。**待 fork camoufox-cli（§1）完成后编写**，含原 007 内容 |
| `002-disable-web-search-env-var.patch` | 添加 `OPENCLAW_DISABLE_WEB_SEARCH` 环境变量，可按需禁用内置 web_search（由 smart-search skill 通过浏览器替代） |

> 浏览器转向详见 `docs/browser-stack-replacement-spec-2026-07.md` + `docs/browser-extension-replacement-research.md` §12。

### 2. 依赖覆盖（overrides.sh）

`overrides.sh` 在 openclaw 恢复干净状态后最先执行。浏览器转向后**去掉 patchright-core 注入**（`PATCHRIGHT_VERSION` 相关逻辑删除）：线 2 的 existing-session 用真机 Chrome、remote-cdp 用远端 Chrome，都不需要 patchright；playwright-core 保留给 remote-cdp 用，不再被 patchright 顶替。

### 辅助工具

- `generate-patch.sh`：从当前 openclaw 工作区生成 patch 文件的辅助脚本，在项目根目录运行。

### 已删除补丁历史

| 补丁 | 删除时间 | 原因 |
|------|---------|------|
| `001-relax-exec-allowlist-shell-syntax.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游 exec 审批重构为 risk-based，`&&`/`\|\|`/`;` 复合命令已原生支持逐段匹配 allowlist；wiseflow 已改走 `.sh` 脚本不再直接 exec。原目标代码 `splitShellPipeline` 已删，无法 re-port |
| `004-chrome-port-grace-retry.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游新增 `ensureManagedChromePortAvailable` + `recoverOwnedStaleManagedChromeCdpListener`，完全覆盖 |
| `003-act-field-validation.patch` | 2026-07-11（浏览器转向） | 默认走 camoufox-cli（不经 browser tool 的 act 路由），fallback 路径偶尔用，前置校验价值有限；先拿掉，后面有需求再加 |
| `005-browser-timeout-env-var.patch` | 2026-07-11（浏览器转向） | 基于 patchright/browser tool 的超时调优，camoufox-cli 走旁路不受影响，fallback 路径偶尔用；先拿掉，后面有需求再加 |
| `006-connectovercdp-no-defaults.patch` | 2026-07-11（浏览器转向） | `noDefaults` 是 patchright 1.60+ 专属选项，patchright 整体去掉后原版 playwright-core 的 `connectOverCDP` 不支持该参数；remote-cdp 保留但走原版 PW 即可 |
| `007-browser-prefer-camoufox-cli.patch` | 2026-07-11（浏览器转向） | 并入新 `001-browser-camoufox-pivot.patch`（system-prompt 引导与架构改动合并为一条） |
