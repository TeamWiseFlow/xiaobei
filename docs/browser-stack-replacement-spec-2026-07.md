# 浏览器栈整体替换 spec（v5.6.0 重磅）

> 2026-07-11 落盘，2026-07-11 按 research §12 转向修订。本 spec 供新开对话执行。
> 执行顺序：**先做 §1 fork camoufox-cli**，再按 §11 落地顺序施工。
> 调研结论见 [`browser-extension-replacement-research.md`](./browser-extension-replacement-research.md) §12（架构转向，优先级最高）；可复用调研方法论见 [`browser-investigation-methodology.md`](./browser-investigation-methodology.md)。

---

## 0. 决策总览

维持 OpenClaw 架构，**双线浏览器栈**（research §12 拍板，替代原"整体替换 extension"路线）：

- **线 1（日常主力）**：新增 `target=camoufox` → forked camoufox-cli（vendor 进 `patches/camoufox-cli/`）走旁路，绕开 routes/、pw-session、chrome-mcp。反指纹 Firefox + JSON-over-unix-socket，不讲 CDP。
- **线 2（特殊情况 fallback）**：保留 `target=host`（existing-session 真机 Chrome + chrome-mcp relay）+ `target=node`（remote-cdp 远端 Chrome）。routes/ 层不动。
- **删 sandbox 整条路**（容器 + bridge + facade + `agents.defaults.sandbox.browser` 配置），由线 1 替代。
- **patch 删 host `local-managed` 分支**（`chrome.ts` spawn + `ensureBrowserAvailable` 下载 Chromium），避免额外下 Chromium 干扰、浪费存储。
- **patchright 整体去掉**（`overrides.sh` 不再注入 patchright-core）；playwright-core 保留给 remote-cdp 用，不再被顶替。
- **browser-guide skill 留 `skills/browser-guide/`**（公共 skill，位置不动），只更新 §3 fallback 描述。原 §2.2"并入 extensions/browser/skill"撤回（加载器不认该路径）。

### 核心原则（用户拍板的 8 点 + 补充）

| # | 原则 |
|---|------|
| 0 | **全线使用 forked camoufox-cli**，放弃 patchright 的 patch |
| 1 | 涉及登录的自媒体平台，**每平台一个且只一个持久化 session**，必须顺次使用（fail-first 队列，见 §fork 改造清单） |
| 2 | browser-guide 约定：需要用户配合过验证码的，**必须用 camoufox-cli 有头模式** |
| 3 | login-manager 约定：wechat-channel / wx-mp 登录可无头启动截图发 QR；**douyin / twitter / xhs（xhs-publish \| xhs-browse）/ weibo / zhihu / xianyu 登录必须 有头模式** |
| 4 | login-manager 导出 cookie **同时导出 UA**；所有用中央 cookie 的脚本导入 cookie 同时导入 UA |
| 5 | **严禁浏览器方案导入 cookie**（登录失效必须重新登录流程，见 §profile 丢失处理） |
| 6 | 恢复 twitter-interact 脚本操作模式（参考 AiToEarn 上游，见 §twitter-interact） |
| 7 | wx-mp-hunter 改造纳入上述体系，不再保留单独登录流程 |
| 补充 A | 持久化 vs 临时 session：**涉及登录的站点 → 持久化**（指纹稳定 + cookie 留 profile）；**不涉及登录的站点（新闻等）→ 临时性 session**（每次随机指纹，关闭自清） |
| 补充 B | reddit / youtube 等也是自媒体平台，涉及登录走持久化 |
| 补充 C | patchright 整体去掉（overrides.sh 不再注入 patchright-core） |
| 补充 D | profile 丢失：**重建 + 重登录，绝对不允许导入** |

### 涉及的持久化平台（每平台一个 session）

`douyin` · `twitter` · `xhs`（浏览器操作一套，cookie 分两套见 §login-manager）· `weibo` · `zhihu` · `xianyu` · `wechat-channel`（视频号）· `wx-mp`（公众号）· `reddit` · `youtube`

> xhs 例外：login-manager 导出 cookie **分两套**（xhs-publish creator 域 / xhs-browse 浏览域），对应不同技能脚本；但**浏览器操作部分一套**（一个持久化 session）。

---

## 1. fork camoufox-cli 改造清单

**vendoring 方式**：直接进代码仓 `patches/camoufox-cli/`（不另起 repo，不 npm 发布）。fork 基线 = `camoufox-cli@0.6.2`（本机当前全局版本）。

### 1.1 必改

| 项 | 说明 |
|----|------|
| **upload 命令** | 上游无 upload 命令（命令集：open/back/forward/reload/url/title/close/snapshot/click/fill/type/select/check/hover/press/text/eval/screenshot/pdf/scroll/wait/tabs/switch/close-tab/sessions/cookies/install）。fork 补 `upload <selector> <filepath>`，走 Playwright `setInputFiles`。发布类技能（douyin-publish / xhs-publish / weibo-publish / zhihu-publish / wechat-channels-publish / youtube-publish）依赖此 |
| **fail-first 队列** | 同 session 并发不是良性失败而是互相踩（`server.js:71` 无锁 + `commands.js:24` 共享 page.goto）。fork 内置 **fail-first 队列**：同 session 已有命令在跑时，新命令直接 fail，**失败返回文本写清原因和指导**（"session <name> 正忙，请等待当前操作完成后再试"）。agent 读到 fail 文本知道发生了什么、该干什么（等待重试）。不自动排队、不自动等待——避免隐藏排队语义 |
| **identity export 命令** | fork 加 `identity export` 命令，导出当前 session 的 UA / 指纹摘要（供脚本侧导入 UA，对应原则 4）。与 `cookies export` 对称使用 |

### 1.2 不改（沿用上游）

- `--persistent` 指纹冻结机制（`camoufox-cli.json` 首次生成后冻结，spike ② 已证）
- `cookies export/import` JSON 格式（= Playwright `add_cookies` 格式，spike ① 已证零转换）
- daemon 模型 / `--session` 隔离 / `--json` 信封 / `--headed`/`--headless`

### 1.3 D18 共享模板模式（持久化 session 落地方式）

spike 文档 L30-33 已设计：
1. 一次性 bootstrap：`camoufox-cli --session _template --persistent open about:blank` → 生成冻结 `camoufox-cli.json` → close。
2. 每个持久化平台 session：`mkdir ~/.camoufox-cli/profiles/<platform>` → `cp ~/.openclaw/logins/_template/camoufox-cli.json` 进去 → `camoufox-cli --session <platform> --persistent ...`。
3. 各平台 session 共享指纹，独立 `cookies.sqlite`/state。

> 临时性 session（新闻等不登录站点）不 cp 模板，走默认临时 profile（每次随机指纹，关闭自清）。

---

## 2. openclaw/extensions/browser 改造（双线旁路，调研已完成）

**目标**：不整体替换 extension，而是**删 sandbox + patch 删 local-managed + 新增 camoufox 旁路**。调研结论见 `browser-extension-replacement-research.md` §12，关键事实：

- routes 层（`agent.act.ts:733,784` 等）每个 action handler 重复 `if (usesChromeMcp) → chrome-mcp else → pw-session/CDP` 二元 switch，**无抽象 backend seam**（grep `interface Backend/Driver/abstract` 零结果）。塞第三后端要改 ~50 handler。
- 上一层 `browser-tool.schema.ts:52` 的 `BROWSER_TARGETS=["sandbox","host","node"]` 是干净 seam，`sandbox` 分支本就不进 routes/（走 Docker bridge）。故新增 `target=camoufox` 走旁路、绕开 routes/，改动比整体替换小一个数量级。

### 2.1 调研结论（已就位，见 research §12）

7 项调研全完成，结论在 `browser-extension-replacement-research.md` §1-§9 + §12 转向。本节不再重复，落地以 research §12.6 的 7 步为准。

### 2.2 browser-guide skill 处置（撤回原"并入 extension"）

- openclaw skill 加载器只认 `skills/`（公共）和 `crews/<id>/skills/`（crew 专属），**不认 `extensions/*/skills/`**。原 §2.2"并入 `extensions/browser/skill/`"**撤回**。
- `browser-guide` 留 `skills/browser-guide/`（公共 skill，全员共用），只更新 §3 fallback 描述：`target=host`（existing-session/relay）或 `target=node`（remote-cdp）；`sandbox` 已删、`local-managed` 已 patch 掉。
- 原版 `extensions/browser` 不带 skill（只有 `docs/tools/browser.md` 文档），无"替代原版 skill"一说。那份文档由 `overrides.sh` sed 处理。

---

## 3. patch 重组

`patches/` 转向后：`001`（新架构）+ `002`（保留）+ `overrides.sh`（去 patchright）+ `generate-patch.sh`。

| patch | 处置 | 原因 |
|-------|------|------|
| `001-browser-camoufox-pivot.patch` | **新增**（待 fork camoufox-cli 后编写） | 浏览器架构转向：删 sandbox target + 删 host `local-managed` 分支 + 新增 `target=camoufox` 旁路调 forked camoufox-cli adapter + system-prompt browser 工具摘要注入"优先 camoufox-cli"。含原 007 内容 |
| `002-disable-web-search-env-var.patch` | **留** | 与浏览器无关，web_search 禁用仍需要（由 smart-search 替代） |
| `003-act-field-validation.patch` | **删** | 默认走 camoufox-cli（不经 browser tool 的 act 路由），fallback 偶尔用，前置校验价值有限；先拿掉，后面有需求再加 |
| `005-browser-timeout-env-var.patch` | **删** | 基于 patchright/browser tool 的超时调优，camoufox-cli 走旁路不受影响；先拿掉，后面有需求再加 |
| `006-connectovercdp-no-defaults.patch` | **删** | `noDefaults` 是 patchright 1.60+ 专属，patchright 整体去掉后原版 playwright-core 的 `connectOverCDP` 不支持该参数；remote-cdp 走原版 PW 即可 |
| `007-browser-prefer-camoufox-cli.patch` | **删** | 并入新 `001`（system-prompt 引导与架构改动合并为一条） |

`overrides.sh`：去掉 patchright-core 注入逻辑（`PATCHRIGHT_VERSION` 相关），playwright-core 保留给 remote-cdp 用。`patches/README.md` 已同步更新。

---

## 4. login-manager 改造为纯指导文件

**职责边界**：forked camoufox-cli 加了 `identity export` 命令后，cookie/UA 导出由 forked cli 干。**login-manager 不再有脚本**，变成纯 SKILL.md 指导文件（告诉 agent 各平台登录流程：何时有头 / 何时无头截图 QR / 探活规则 / 中央存储路径约定）。

### 4.1 删除

- `crews/main/skills/login-manager/scripts/login_manager.py`
- `crews/main/skills/login-manager/scripts/login-manager.sh`
- `tests/`

### 4.2 SKILL.md 保留并改写的内容

- 各平台登录模式约定（原则 3）：
  - 无头截图 QR：`wechat-channel` / `wx-mp`
  - 有头手动：`douyin` / `twitter` / `xhs-publish` / `xhs-browse` / `weibo` / `zhihu` / `xianyu` / `reddit` / `youtube`
- 探活规则（各平台登录态检测，参考 `wiseflow-pro/wiseflow4-pro/core/wis/nodriver_helper.py` 的规则：xhs=web_session / wb=SUB+SCF / dy=sessionid+sid_tt+uid_tt / bili=SESSDATA / ks=passToken / zhihu=z_c0 / mp=URL token= / twitter=auth_token 等）
- 中央存储路径约定：`~/.openclaw/logins/<platform>.json`（cookie）+ `~/.openclaw/logins/<platform>.ua.json`（UA，新增）
- xhs 两套 cookie 约定：`xhs-publish.json`（creator 域）/ `xhs-browse.json`（浏览域）
- 流程模板：探活失败 → forked cli 有头/无头启动 → 用户扫码/登录 → `cookies export` + `identity export` → 落盘中央存储 → close session

### 4.3 待同步的 4 个 camoufox-cli 适配 bug fix

上一轮发现的 login-manager 4 个适配 bug，方案确认后随改造一起做（低风险）。具体 bug 清单在上一轮对话中，新对话开始时从 transcript 取或重新排查 `login_manager.py` 对 camoufox-cli 的调用点。

---

## 5. 9+ 平台 skill 逐个改造点

每个涉及浏览器的 skill：把对 patchright / browser tool / 旧 login-manager 脚本的调用，改为调 forked camoufox-cli（绝对路径，遵循 CLAUDE.md「crew 专属 skill 脚本调用必须绝对路径」）+ 读中央 cookie/UA 文件。

| skill | 改造点 |
|-------|--------|
| `xhs-content-ops` | 浏览器取数走 forked cli 持久化 session `xhs`；脚本侧从 `xhs-browse.json` + `.ua.json` 导入 cookie+UA |
| `xhs-publish` | 发布走 forked cli 持久化 session `xhs` + upload 命令；cookie 从 `xhs-publish.json` 导入 |
| `xhs-interact` | 同 xhs-content-ops，浏览域 cookie |
| `douyin-publish` | forked cli 持久化 session `douyin` + upload；有头登录 |
| `weibo-publish` | forked cli 持久化 session `weibo` + upload；有头登录 |
| `zhihu-publish` | forked cli 持久化 session `zhihu` + upload；有头登录 |
| `wechat-channels-publish` | forked cli 持久化 session `wechat-channel` + upload；无头截图 QR 登录 |
| `youtube-publish`（全局 skill） | forked cli 持久化 session `youtube` + upload |
| `wx-mp-hunter` | 见 §6 收编 |
| `wx-mp-publisher` / `wx-mp-engagement` | wx-mp 域，无头截图 QR 登录；engagement 已同步（commit cab3fb3） |
| `xianyu-ops` | forked cli 持久化 session `xianyu`；有头登录 |
| `published-track` | `fetch-and-update-metrics.sh` 内部 login-manager 探活调用改为读新中央存储；浏览器获取流程（zhihu/toutiao/juejin/twitter/youtube/FB/IG/TikTok/Pinterest/Threads）改 forked cli |
| `twitter-interact` | 见 §7 恢复脚本模式 |
| `twitter-post` | forked cli 持久化 session `twitter` + upload（Quote/Reply） |

> 临时性 session（不登录站点）：`rss-reader` / 新闻抓取 / `intel-gathering` 等纯浏览取数，走 forked cli 默认临时 profile，不 cp 模板、不持久化。

---

## 6. wx-mp-hunter 收编

当前 wx-mp-hunter 有单独登录流程（`wx_mp_hunter.ts` 的 `login-qr` / `login-confirm` 两步，cookie 自管，见记忆 `11-heartbeat-isolated-session-gotcha.md`）。

改造：登录走 login-manager 统一流程（wx-mp 无头截图 QR），cookie 落 `~/.openclaw/logins/wx_mp.json`。wx-mp-hunter 只保留抓公众号文章的核心逻辑（搜索/文章列表/正文，参考上游 `wechat-article/wechat-article-exporter`），不再自管登录。

心跳里的 wx_mp 登录死锁问题（记忆 11）随此改造一并消解——login-manager 统一流程 + 心跳约束 4（登录失效跳过等白天处理）。

---

## 7. twitter-interact 恢复脚本模式

**参考项目**：`yikart/AiToEarn`（记忆 `02-upstream-sources.md` 第 4 行，"twitter 互动操作模式"）。

**任务**（下个对话做，本轮不动）：
1. 看 AiToEarn 上游当前 twitter 互动这块的进展（catchup commit `74e884f0` v2.4.0 之后的 HEAD 差异）
2. 照搬其操作模式到 twitter-interact（脚本操作模式，camoufox-cli 持久化 session `twitter` + 中央 cookie/UA）
3. 登录对齐原则 3（twitter 有头登录）

当前 twitter-interact 已经是 camoufox-cli + login-manager 中央 cookie 架构（SKILL.md 已写），主要是对齐 forked cli 的 upload/identity export 新命令 + 跟上游模式。

---

## 8. smart-search 适配

smart-search 是全局 skill（`skills/smart-search/`），针对所有站点。全量切换 forked camoufox-cli 后：
- 涉及登录的站点（自媒体平台）→ 持久化 session（§0 平台列表）
- 不涉及登录的站点（新闻等）→ 临时性 session

smart-search 内部按站点是否需要登录分流到上述两种 session 模式。具体适配范围在调研阶段确认（smart-search 当前对 browser tool / CDP 的依赖面）。

---

## 9. setup-crew.sh 改造

**现状（用户 2026-07-11 确认）**：`scripts/setup-crew.sh` 每次只**同步全局 skill**（`skills/` → `~/.openclaw/skills/`，由 `apply-addons.sh` 做），**不同步 crew 专属 skill**（`crews/<id>/skills/` 不 copy 到部署实例 workspace）。crew 专属 skill 的同步是**待实现改造**：

- ✅ 待加：`crews/<crew-id>/skills/` → `~/.openclaw/workspace-<crew-id>/skills/`（覆盖）
- ❌ 不动：本地 `Agents.md` / `Tools.md` / `Memory`（这些本地有自定义内容）
- ❌ 不动：本地部署实例里的自定义 skill（Chrome 的 skill 等本地私货）

> 遵循记忆铁律 `50-code-repo-only-no-touch-local-instance`：setup-crew.sh 的 crew skill 同步是用户明确要求的同步通道，属于"明确要求同步"的例外，但只同步 skill，不碰其他。
> **注意**：`browser-guide` 是公共 skill（`skills/`），走 `apply-addons.sh` 全局 skill 通道部署，**不归 setup-crew 管**。

---

## 10. profile 丢失处理

profile 丢失 / 损坏 / 指纹错配 → **重建 + 重登录，绝对不允许导入**（补充 D，强化原则 5）。

理由：xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹会错配 → 被风控检测（见上一轮分析）。任何"用 cookie 造一个登录会话"的动作都禁止（HEARTBEAT.md 约束 4 已写，2026-06-29 CDP 注入 22 cookie 触发风控的教训）。

---

## 11. 落地顺序

**阶段一：浏览器栈转向（research §12.6 的 7 步）**

1. **fork camoufox-cli**（§1）：vendor 进 `patches/camoufox-cli/`，补 upload / fail-first 队列 / identity export
2. **写 `camoufox-cli.adapter.ts`**：17 action → camoufox-cli 命令翻译 + JSON-over-unix-socket 通信（extension 唯一新代码）
3. **一次性 patch extension**（新 `001`）：`browser-tool.schema.ts` 的 `BROWSER_TARGETS` 删 `sandbox` 加 `camoufox`；`browser-tool.ts` 删 sandbox 分发分支、加 camoufox 分支调 adapter；`profile-capabilities.ts`/`chrome.ts`/`ensureBrowserAvailable` 删 `local-managed` 分支；删 `openclaw/src/agents/sandbox/browser*.ts` + `bridge-server.ts` sandbox 桥；删 `plugin-sdk/browser-bridge.*` facade
4. **`overrides.sh` 去 patchright** + `docs/tools/browser.md` 文本更新成双线模型
5. **`browser-guide` SKILL.md §3 更新**（已完成）+ `apply-addons.sh` 加 `camoufox-cli install`（已完成，幂等）
6. **patch 收缩**：删 003/005/006/007（已完成），002 保留，001 占位（已完成）
7. **验证**：线 1 camoufox-cli 端到端 + 线 2 existing-session/remote-cdp 回归

**阶段二：平台 skill 适配（forked cli 就绪后）**

8. **login-manager 改纯指导**（§4）：删脚本，改写 SKILL.md，同步 4 个 bug fix
9. **平台 skill 逐个改造**（§5）：按表格逐个改
10. **wx-mp-hunter 收编**（§6）
11. **twitter-interact 恢复**（§7）：跟 AiToEarn 上游
12. **smart-search 适配**（§8）
13. **setup-crew.sh 加 crew skill 同步**（§9）
14. **README / CHANGELOG / 致谢**：v5.6.0 重磅说明，致谢 Bin-Huang / camoufox-cli（fork 基线）

---

## 12. 未定点（执行时再决）

- twitter-interact op 级 script/browser 取舍细节（跟上游 AiToEarn 后定）
- smart-search 适配的具体范围（调研阶段定）
- forked cli fail-first 队列的超时 / 重试上限（先无超时，agent 自行决策重试）
- 版本号：v5.6.0（CHANGELOG 已记 2026-07-12）vs v6.0（重磅可冲 6.0）——执行时跟用户定
- 上一轮用户被中断的句子"然后目前的patched…"——可能指当前 patchright patched 状态的收尾，已在 §3 patch 重组 + 补充 C 覆盖

---

## 13. 致谢

- **Bin-Huang / camoufox-cli**：fork 基线，本栈整体替换的核心依赖
- AiToEarn（twitter 互动模式）、wechat-article-exporter（wx-mp-hunter）、Spider_XHS（xhs-content-ops）——见记忆 `02-upstream-sources.md`
