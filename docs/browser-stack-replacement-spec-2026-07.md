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
- **browser-guide skill 留 `skills/browser-guide/`**（公共 skill，位置不动），依然定位在浏览器使用的最佳实践指导，但是因为现在主力是使用`target=camoufox`，要基于`patches/camoufox-cli/`的命令改写。

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

## 2. openclaw/extensions/browser 改造（双线旁路，调研已完成）/ patches 重组

**目标**：不整体替换 extension，而是**删 sandbox + patch 删 local-managed + 新增 camoufox 旁路**。调研结论见 `browser-extension-replacement-research.md` §12，关键事实：

- routes 层（`agent.act.ts:733,784` 等）每个 action handler 重复 `if (usesChromeMcp) → chrome-mcp else → pw-session/CDP` 二元 switch，**无抽象 backend seam**（grep `interface Backend/Driver/abstract` 零结果）。塞第三后端要改 ~50 handler。
- 上一层 `browser-tool.schema.ts:52` 的 `BROWSER_TARGETS=["sandbox","host","node"]` 是干净 seam，`sandbox` 分支本就不进 routes/（走 Docker bridge）。故新增 `target=camoufox` 走旁路、绕开 routes/，改动比整体替换小一个数量级。

### 2.1 调研结论（已就位，见 research §12）

7 项调研全完成，结论在 `browser-extension-replacement-research.md` §1-§9 + §12 转向。本节不再重复，落地以 research §12.6 的 7 步为准。

### 2.2 patch 重组

`patches/` 转向后：`001`（新架构）+ `002`（保留）+ `overrides.sh`（去 patchright）+ `generate-patch.sh`。

| patch | 处置 | 原因 |
|-------|------|------|
| `001-browser-camoufox-pivot.patch` | **拆成 35 个单文件 patch**（`browser-camoufox-pivot/patches/`，见 §1b） | 原 monolith 35 文件合一失效面太大，按「一个 patch 只改一个上游文件」拆分，降低上游漂移失效面 |
| `002-disable-web-search-env-var.patch` | **留** | 与浏览器无关，web_search 禁用仍需要（由 smart-search 替代） |
| `003-act-field-validation.patch` | **删** | 默认走 camoufox-cli（不经 browser tool 的 act 路由），fallback 偶尔用，前置校验价值有限；先拿掉，后面有需求再加 |
| `005-browser-timeout-env-var.patch` | **删** | 基于 patchright/browser tool 的超时调优，camoufox-cli 走旁路不受影响；先拿掉，后面有需求再加 |
| `006-connectovercdp-no-defaults.patch` | **删** | `noDefaults` 是 patchright 1.60+ 专属，patchright 整体去掉后原版 playwright-core 的 `connectOverCDP` 不支持该参数；remote-cdp 走原版 PW 即可 |
| `007-browser-prefer-camoufox-cli.patch` | **留**（改名 `007-prefer-camoufox-cli.patch`） | system-prompt 引导与架构 patch 解耦，便于单独 revert/调序；原计划并入 001 已撤回 |

`overrides.sh`：去掉 patchright-core 注入逻辑（`PATCHRIGHT_VERSION` 相关），playwright-core 保留给 remote-cdp 用。`patches/README.md` 已同步更新。

### 2.3. setup-crew.sh 改造

**现状（用户 2026-07-11 确认）**：`scripts/setup-crew.sh` 每次只**同步全局 skill**（`skills/` → `~/.openclaw/skills/`，由 `apply-addons.sh` 做），**不同步 crew 专属 skill**（`crews/<id>/skills/` 不 copy 到部署实例 workspace）。crew 专属 skill 的同步是**待实现改造**：

- ✅ 待加：`crews/<crew-id>/skills/` → `~/.openclaw/workspace-<crew-id>/skills/`（覆盖）
- ❌ 不动：本地 `Agents.md` / `Tools.md` / `Memory`（这些本地有自定义内容）
- ❌ 不动：本地部署实例里的自定义 skill

**落地（2026-07-12）**：`scripts/lib/crew-workspaces.sh` 加 `sync_crew_skills` 函数（按 skill 粒度 `rm -rf + cp -R` 覆盖，不删部署实例独有 skill，带 package.json 的 skill 跑 `npm install --production`）；`setup-crew.sh` §1 部署循环 fresh + exists 两个分支都调它，exists 分支不再只做 guide 注入。沙箱验证：自定义 skill 保留、同名 skill 被覆盖、npm 依赖装好。

---

## 3. skills下的browser-guide/smart-search/web-form-fill 三技能适配

这三个技能都是全局技能，用于指导Agent如何最佳实践使用浏览器工具。但是他们给出的操作方法和示例，都是基于原来的CDP方案。现在因为默认使用 fork camoufox-cli，所以要进行适配，只针对camoufox-cli来写就行，并说明操作命令和指令示例都只是针对target=camoufox，如果是 target=host 或者 target=node 的情况，只按照技能要求的流程和步骤并提示事项即可，不必参考具体操作和示例。

---

## 4. crews/main/skills下的login-manager 改造为纯指导文件

**职责边界**：forked camoufox-cli 加了 `identity export` 命令后，cookie/UA 导出由 forked cli 干。**login-manager 不再有脚本**，变成纯 SKILL.md 指导文件（告诉 agent 各平台登录流程：何时有头 / 何时无头截图 QR / 探活规则 / 中央存储路径约定）。

确认仅支持这些平台：`douyin` | `bilibili` | `kuaishou` | `xhs-publish` | `xhs-browse` | `wx-mp`

同样login-manager只针对camoufox-cli来写就行，并说明操作命令和指令示例都只是针对target=camoufox，如果是 target=host 或者 target=node 的情况，只按照技能要求的流程和步骤并提示事项即可，不必参考具体操作和示例。

### 4.1 删除

- `crews/main/skills/login-manager/scripts/login_manager.py`
- `crews/main/skills/login-manager/scripts/login-manager.sh`
- `tests/`

### 4.2 SKILL.md 保留并改写的内容

- 各平台登录模式约定（原则 3）：
  - 无头截图 QR：`wechat-channel` / `wx-mp`
  - 有头手动：`douyin` / `twitter` / `xhs-publish` / `xhs-browse` / `weibo` / `zhihu` / `xianyu` / `reddit` / `youtube`
- 中央存储路径约定：`~/.openclaw/logins/<platform>.json`（cookie）+ `~/.openclaw/logins/<platform>.ua.json`（UA，新增）
- xhs 两套 cookie 约定：`xhs-publish.json`（creator 域）/ `xhs-browse.json`（浏览域）
- 探活方案可以参考 `docs/nodriver_helper_reference.py`

---

## 5. crews/main/skills下的 9+ 平台 skill 逐个改造点

如下技能也需要改造，适配上述改动。

同样，具体的操作指导和示例以及脚本程序只针对camoufox-cli来写就行，并说明操作命令和指令示例都只是针对target=camoufox，如果是 target=host 或者 target=node 的情况，只按照技能要求的流程和步骤并提示事项即可，不必参考具体操作和示例。

| skill | 改造点 |
|-------|--------|
| `xhs-content-ops` | 适配修改后的login-manager中央cookie格式（`xhs-browse`），尤其是导入Cookie的时候，要同时导入UA。|
| `xhs-publish` | 适配修改后的login-manager中央cookie格式（`xhs-publish`），尤其是导入Cookie的时候，要同时导入UA。 |
| `xhs-interact` | forked cli 持久化 session `xhs` + upload；有头登录 |
| `douyin-publish` | 由脚本方案改为浏览器自动化方案：forked cli 持久化 session `douyin` + upload；有头登录 |
| `weibo-publish` | forked cli 持久化 session `weibo` + upload；有头登录 |
| `zhihu-publish` | forked cli 持久化 session `zhihu` + upload；有头登录 |
| `wechat-channels-publish` | forked cli 持久化 session `wechat-channel` + upload；无头截图 QR 登录 |
| `viral-chaser` | 适配修改后的login-manager中央cookie格式，尤其是导入Cookie的时候，要同时导入UA。 |
| `wx-mp-hunter` | 见 §6 收编 |
| `xianyu-ops` | forked cli 持久化 session `xianyu`；有头登录 |
| `published-track` | `fetch-and-update-metrics.sh` 适配修改后的login-manager中央cookie格式，尤其是导入Cookie的时候，要同时导入UA；自动化取数明确仅限这些平台：xhs、bilibili、douyin、kuaishou、wx_mp，其中wx_mp取数能力整理同目录下的`wx-mp-engagement`, wx-mp-engagement 里边的流程已经经过实际验证, 可以直接用, 但是它不再作为单独技能。 |
| `twitter-interact` | 见 §7 恢复脚本模式 |
| `twitter-post` | forked cli 持久化 session `twitter` + upload（Quote/Reply） |

> 临时性 session（不登录站点）：`rss-reader` / 新闻抓取 / `intel-gathering` 等纯浏览取数，走 forked cli 默认临时 profile，不 cp 模板、不持久化。

---

## 6. wx-mp-hunter 收编

当前 wx-mp-hunter 有单独登录流程（`wx_mp_hunter.ts` 的 `login-qr` / `login-confirm` 两步，cookie 自管）。

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

**落地（2026-07-12）**：
1. AiToEarn clone 正好在 catchup commit `74e884f0`（v2.4.0），之后无新提交，无 HEAD 差异要追。上游 twitter 互动走 **Twitter API v2 + OAuth**（`POST /users/{id}/likes` 等），按记忆「AiToEarn 只吸收知识不搬架构」+ spec 要求 camoufox-cli，吸收操作语义（子命令结构 + 频率纪律），执行仍走 camoufox-cli。
2. `twitter_interact.py` 改造：单一持久化 session `twitter`（原则 1，去掉 per-task nonce）+ fail-first 队列检测（`SessionBusyError` → exit 3，busy 时不 close 避免 tear down 正在跑的操作）+ 登录错误消息改成有头（原则 3）。
3. SKILL.md 同步：前置条件改有头登录、并发约束改 fail-first、Pitfalls 更新、Notes 记 forked cli 新命令 + AiToEarn 参考。
4. 测试：`TestSessionNaming` 改断言常量 `twitter`，加 `TestFailFirstQueue` 验证 busy → exit 3 + 不 close。28/28 通过。

---

## 8. profile 丢失处理

profile 丢失 / 损坏 / 指纹错配 → **重建 + 重登录，绝对不允许导入**（补充 D，强化原则 5）。

理由：xhs `a1`/`websectiga` 等设备指纹 cookie 导入到不同指纹会错配 → 被风控检测（见上一轮分析）。任何"用 cookie 造一个登录会话"的动作都禁止（HEARTBEAT.md 约束 4 已写，2026-06-29 CDP 注入 22 cookie 触发风控的教训）。

---

## 9. README.md 更新

- `**v5.6.0 更新**` 中要体现本次对浏览器架构的重新设计，并且CHANGELOG.md 详细记录
- `## 🔧 比原版更强、更适合国内网络环境的浏览器方案` 段落更新
- `## 🤝 xiaobei 基于如下优秀的开源项目` 去掉Patchright，增加camoufox（🦊 Anti-detect browser）  https://github.com/daijro/camoufox 
