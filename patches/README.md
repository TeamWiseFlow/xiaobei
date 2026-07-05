# Wiseflow Patches

xiaobei 针对原版 openclaw 提供的非侵入式补丁与依赖覆盖，作为 xiaobei 的共性基础能力，由 `apply-addons.sh` 自动应用。

### 1. 代码补丁（*.patch）

对 OpenClaw 打的 git patch，按序号命名，顺序应用：

| 补丁 | 功能 |
|------|------|
| `002-disable-web-search-env-var.patch` | 添加 `OPENCLAW_DISABLE_WEB_SEARCH` 环境变量，可按需禁用内置 web_search |
| `003-act-field-validation.patch` | 强化浏览器工具的 act 字段校验，防止幻觉动作 |
| `005-browser-timeout-env-var.patch` | 添加 `OPENCLAW_BROWSER_TIMEOUT_MS` 环境变量，支持自定义浏览器超时 |
| `006-connectovercdp-no-defaults.patch` | `connectOverCDP` 调用时启用 `noDefaults: true`（Patchright 1.60+），避免修改用户浏览器状态（下载行为、焦点模拟、媒体模拟等） |
| `007-browser-prefer-camoufox-cli.patch` | 在 system-prompt 的 browser 工具摘要里注入"优先 camoufox-cli，仅当 camoufox-cli 处理不了或用户明确要求时才用 browser 工具"的引导 |

### 3. Patchright 版本（overrides.sh 默认）

`overrides.sh` 默认 `PATCHRIGHT_VERSION=1.61.1`（2026-07-05 升自 1.60.2，跟 Playwright 1.61 同步）。可通过环境变量覆盖：

```bash
PATCHRIGHT_VERSION=1.60.2 bash overrides.sh  # 锁定旧版
```

> **注**：原 `001-suppress-stale-reply-context.patch` 已于 2026-04-25 移除，awada channel 改用 per-peer inbound debouncer 在入口层合并连发消息，无需 openclaw 核心补丁即可解决历史污染问题。

### 2. 依赖覆盖（overrides.sh）

`overrides.sh` 在 openclaw 恢复干净状态后最先执行，用于注入 pnpm 依赖覆盖（如 patchright 替换 playwright）。

### 辅助工具

- `generate-patch.sh`：从当前 openclaw 工作区生成 patch 文件的辅助脚本，在项目根目录运行。

### 已删除补丁历史

| 补丁 | 删除时间 | 原因 |
|------|---------|------|
| `001-relax-exec-allowlist-shell-syntax.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游 exec 审批重构为 risk-based（`command-explainer` + `exec-authorization-plan`），`&&`/`\|\|`/`;` 复合命令已原生支持逐段匹配 allowlist；`$()`/反引号/重定向仍被拒但 wiseflow 已改走 `.sh` 脚本不再直接 exec。原 patch 目标代码 `splitShellPipeline` 已删，无法 re-port。日后若再被 deny，按新架构重写最小 patch |
| `004-chrome-port-grace-retry.patch` | 2026-06-25（升级至 openclaw v2026.6.10） | 上游新增 `ensureManagedChromePortAvailable` + `recoverOwnedStaleManagedChromeCdpListener`：命中 EADDRINUSE 时主动杀掉占用端口的陈旧 managed Chrome 进程并清 singleton lock 再重探，比我们的 3×500ms 轮询更强，完全覆盖 |
