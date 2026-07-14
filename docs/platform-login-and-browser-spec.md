# 平台登录态与浏览器统一规范（2026-07-12）

本文档定义 wiseflow 仓下所有涉及自媒体/社交平台发布的技能，如何统一管理浏览器 session、登录态、Cookie 与 UA。后续所有相关技能的开发与重构均以此为准。

## 1. 两层概念（不能混淆）

**层 1 — 持久化 session**：**每一个**自媒体/社交平台都需要一个独立的 camoufox 持久化 session，登录态直接在 session profile 里。技能和脚本都通过 `camoufox-cli --session <name> --persistent` 直接复用该 session，不需要每次重建登录。

**层 2 — Cookie 导出**：其中只有 **5 个平台**每次登录后还需要额外把 Cookie + UA 导出到中央存储，供非浏览器类脚本（纯 HTTP 抓取）消费。导出与管理由 `login-manager` 技能负责。

一句话：**所有平台都要 session；只有 5 个还要导出 Cookie。**

## 2. login-manager 管理范围（仅 5 个平台）

login-manager 只管以下 5 个平台，**其他平台完全不涉及**：

| 平台 key | session 名 | 登录模式 | 中央存储文件 |
|----------|-----------|---------|------------|
| `douyin` | `douyin` | **有头手动** | `~/.openclaw/logins/douyin.json` + `~/.openclaw/logins/douyin.ua.json` |
| `kuaishou` | `kuaishou` | **有头手动** | `~/.openclaw/logins/kuaishou.json` + `~/.openclaw/logins/kuaishou.ua.json` |
| `bilibili` | `bilibili` | **有头手动** | `~/.openclaw/logins/bilibili.json` + `~/.openclaw/logins/bilibili.ua.json` |
| `xhs-publish` | `xhs-publish` | **有头手动**（创作者域 `creator.xiaohongshu.com`） | `~/.openclaw/logins/xhs-publish.json` + `~/.openclaw/logins/xhs-publish.ua.json` |
| `xhs-browse` | `xhs-browse` | **有头手动**（消费者域 `www.xiaohongshu.com`） | `~/.openclaw/logins/xhs-browse.json` + `~/.openclaw/logins/xhs-browse.ua.json` |

**登录模式强制统一为有头**——不再有 wx_mp 无头特例。用户在浏览器窗口里手动扫码 / 短信 / 账号密码完成登录，agent 不主动触发登录动作，只开浏览器等用户。

**wx_mp 已从 login-manager 移除**。理由：移除后 login-manager 不再有无头特例，强制统一有头，实现简化。wx_mp 走自己的体系（见 §4）——但导出的 `wx_mp.json` + `wx_mp.ua.json` **依然落 `~/.openclaw/logins/` 中央目录**，与 login-manager 5 平台放同一文件夹，只是管理自管、login-manager 不沾。

## 3. 持久化 session 全清单（所有平台）

每个平台一个独立 session，登录态在 session 里。共享 session 的组用「共用」标注：

| session 名 | 服务技能 | 共用 | 说明 |
|-----------|---------|------|------|
| `xhs-publish` | `xhs-publish` | — | 创作者域，导出 Cookie 供自己消费 |
| `xhs-browse` | `xhs-content-ops`、`xhs-interact`、`viral-chaser`、`published-track` | — | 消费者域，导出 Cookie 供多方消费 |
| `zhihu` | `zhihu-publish` | — | 不导出 Cookie |
| `xianyu` | `xianyu-ops` | — | 不导出 Cookie |
| `wx_mp` | `wx-mp-hunter`、`wx-mp-engagement` | **共用** | 公众号；自己一套探活/登录/导出（见 §4） |
| `weixin-channel` | `wechat-channels-publish` | — | 视频号，与公众号独立；不导出 Cookie |
| `weibo` | `weibo-publish` | — | 不导出 Cookie |
| `twitter` | `twitter-post`、`twitter-interact` | **共用** | 不导出 Cookie |
| `douyin` | `douyin-publish`、`viral-chaser`、`published-track` | — | login-manager 导出 Cookie 供脚本类下游（viral-chaser / published-track）消费；`douyin-publish` 自身不吃 Cookie，纯浏览器操作 |
| `bilibili` | `viral-chaser`、`published-track` | — | 导出 Cookie（目前无发布/浏览/互动技能） |
| `kuaishou` | `published-track` | — | 导出 Cookie（目前无发布/浏览/互动技能） |

**共享 session 机制**：session 名字符串约定——两个技能用同一个 `--session <name>` 即共享同一个 profile 目录与登录态。无需 patches/camoufox-cli 里加任何标记或额外机制，**只是 session 名相同**。twitter 组两技能都 `--session twitter`；wx-mp 组两技能都 `--session wx_mp`。

**不在这套体系内**：
- `wx-mp-publisher` 和 wxwork 相关技能走中转站，**完全不归本规范管**，完全用不到浏览器\camoufox-cli\login-manager。

## 4. wx_mp 特例（公众号，不走 login-manager，自己一套）

wx_mp **不归 login-manager 管**，但也不是「不导出 Cookie 的简单话术纠正」那一档——它有自己一套独立的探活/登录/导出体系，由 `wx-mp-hunter` + `wx-mp-engagement` 两技能**共用**。

**共用一套**：
- 同一个 camoufox 持久化 session `wx_mp`（两技能都 `--session wx_mp --persistent`）
- 同一套探活 + 登录流程（都走 camoufox-cli）
- **两个都可以导出** Cookie + UA（登录后导出）
- **但 Cookie 消费只发生在 `wx-mp-hunter`**——它的抓取走脚本，脚本吃导出的 Cookie + UA
- `wx-mp-engagement` 只走 camoufox-cli 操作浏览器，**不吃 Cookie**

**wx-mp-hunter 改造点**（现状走的是自建 `wx-mp-hunter.sh check-session / login-qr / login-confirm` 那套，session 存 `~/.openclaw/logins/wx_mp.json` TTL 4 天，**不走 camoufox-cli**）：
1. 探活/登录机制**统一改走 camoufox-cli**——废除 `wx-mp-hunter.sh` 的 `check-session` / `login-qr` / `login-confirm` 子命令与 `wx_mp_hunter.ts` 里自建的那套登录逻辑。
2. 理由：避免同机两套登录机制（自建 HTTP + camoufox-cli）触发平台风控。
3. 登录走 **camoufox-cli + 无头模式**：启 `--session wx_mp --persistent`（默认 headless）打开 `https://mp.weixin.qq.com/`，`screenshot` 截登录页上半部含二维码那块图发给用户，用户扫码登录。
4. 登录就位后**同时导出 Cookie + UA**到 `~/.openclaw/logins/wx_mp.json` + `~/.openclaw/logins/wx_mp.ua.json`，供 `wx-mp-hunter` 自己的脚本消费。
5. `wx-mp-engagement` 也用同一个 `wx_mp` session，探活/登录失败就让它失效（不要去 login-manager 找）。

**无头截图 QR 流程**（wx_mp 唯一允许的无头场景）：
```bash
camoufox-cli --session wx_mp --persistent --json open "https://mp.weixin.qq.com/"
sleep 3
camoufox-cli --session wx_mp --json screenshot /tmp/qr-wx-mp.png
# 把 /tmp/qr-wx-mp.png 用 image 工具加载发用户（不要发本地路径），告知扫码
# 等用户回复「已扫码」后 snapshot �验登录态就位
camoufox-cli --session wx_mp --persistent --json cookies export ~/.openclaw/logins/wx_mp.json
camoufox-cli --session wx_mp --persistent --json identity export ~/.openclaw/logins/wx_mp.ua.json
```

**wx-mp-engagementr 改造点** Description中要明确这个技能只抓取自己账号已发布内容的数据。一般仅用于定时任务、 Heartbeat或者publish-track。其他场景，比如说公众号搜索、公众号文章获取等，应该使用`wx-mp-hunter`

## 5. Cookie 消费方完整清单

只有以下技能会消费 login-manager 导出的中央存储 Cookie：

| 消费技能 | 吃哪个 Cookie 文件 | 适用平台 | 说明 |
|---------|------------------|---------|------|
| `published-track`（流程 2A·自动更新） | `douyin.json` / `xhs-browse.json` / `bilibili.json` / `kuaishou.json` | douyin、xhs-browse、bilibili、kuaishou | 定时任务用，凌晨复盘心跳 |
| `viral-chaser`（Step 3 analyzer 下载） | `douyin.json` / `xhs-browse.json` / `bilibili.json` | douyin、xhs-browse、bilibili | 不含 kuaishou |
| `xhs-content-ops` | `xhs-browse.json` + `xhs-browse.ua.json` | xhs | 纯脚本操作 |
| `xhs-publish` | `xhs-publish.json` + `xhs-publish.ua.json` | xhs | 导出自己吃模式 |
| `wx-mp-hunter` | `wx_mp.json` + `wx_mp.ua.json` | wx_mp | 自己导出自己吃，不走 login-manager |

**关键**：所有消费方**同时导入 Cookie 和 UA**——同一指纹下的 Cookie 才不会被风控错配（spec §8，2026-06-29 CDP 注入 22 cookie 触发风控的教训）。

> **`douyin-publish` 不在本表**——它是**纯浏览器操作**技能（形态仿 `wechat-channels-publish`），自身不吃中央 Cookie。它的探活/有头登录/导出 Cookie+UA 全交 `login-manager` 负责，导出的 `douyin.json` + `douyin.ua.json` 仅供本表中的脚本类下游（`viral-chaser` / `published-track`）消费。`douyin-publish` 自身复用 login-manager 留下的持久化 session `douyin` 做浏览器发布操作，**严禁 `cookies import`**。

**xhs 双 Cookie 流向值得专门留意**：
- `xhs-browse.json` 被 `xhs-content-ops` + `published-track` + `viral-chaser` **三方**消费
- `xhs-publish.json` 只被 `xhs-publish` 自己消费
- 取数/调研/互动只走 `xhs-browse`；**禁止**探测或使用 `xhs-publish` creator 域 Cookie 做取数（给 creator 域增加风控概率且与取数无关）

## 6. 不导出 Cookie 的技能话术纠正要点

下列技能**自身不导出 Cookie / 不吃 Cookie**，登录态直接在持久化 session 里闭环。其 SKILL.md 须按以下要点纠正：

**话术纠正清单**：
- `twitter-interact` + `twitter-post`（共享 session `twitter`）
- `wechat-channels-publish`（session `weixin-channel`，与公众号独立）
- `weibo-publish`（session `weibo`）
- `zhihu-publish`（session `zhihu`）
- `douyin-publish`（session `douyin`，**特档**：见下方专门说明）

**纠正要点**（每个技能 SKILL.md 都要写明）：
1. **优先使用 camoufox-cli �持久化 session**，登录态在 session profile 里，**除非用户有明确要求别的**才走其他方案。
2. **探活 + 登录流程写在自己的 SKILL.md 里**，与 login-manager **完全无关**——SKILL.md 里不提 login-manager、不调用 login-manager。
3. **取消 Cookie 导出步骤**——本来如果有 `cookies export` / `identity export` 这类导出动作要删掉；登录只验 session 内页面状态，不落中央存储。
4. 共享 session 的两组（twitter、wx-mp-wx-mp）**必须保证两技能用同一个 session 名**——只靠 session 名字符串约定即可，无需别的机制。

注：`wx-mp-hunter` + `wx-mp-engagement` 虽然也共用 session + 部分导出 Cookie，但归 §4 wx_mp 特例管，不在本节简单话术纠正清单里。

### 6.1 douyin-publish 特档（需要 login-manager 探活/有头登录/导出，但自身不吃 Cookie）

`douyin-publish` 与上面 5 个不导出 Cookie 的技能**同构**——纯浏览器操作，自身不吃 Cookie、严禁 `cookies import`，形态仿 `wechat-channels-publish`。但有一个关键差异让它单独成档：

| 维度 | 不导出 Cookie 的 5 技能（§6 主清单） | `douyin-publish` |
|------|----------------------------------|------------------|
| 自身吃 Cookie | 否 | 否 |
| 自管探活 + 登录 | 是（写在 SKILL.md 里，与 login-manager 无关） | **否——探活/有头登录/导出全交 login-manager** |
| 导出 Cookie+UA | 不导出 | **由 login-manager 导出**，落 `~/.openclaw/logins/douyin.json` + `~/.openclaw/logins/douyin.ua.json` |
| 导出的用途 | — | 供**脚本类下游**消费（`viral-chaser` / `published-track`）；**douyin-publish 自身不用** |
| 登录模式 | 各自有头/无头 QR | **强制有头手动**（手机号+验证码 / 抖音 APP 扫码，login-manager §2 5 平台统一有头） |

**为什么 douyin-publish 不归 §6 主清单的「与 login-manager 完全无关」一档**：它需要 login-manager 帮它准备持久化 session（探活 + 有头登录 + 导出 Cookie+UA），自己**没有** login 子命令、**不**自管探活。但导出的 Cookie 它自己也不读——浏览器操作严禁 `cookies import`，session 内的登录态 + 指纹冻结就位即可做发布操作。

**douyin-publish SKILL.md 必须写明**：
1. **形态仿 `wechat-channels-publish`**：纯浏览器操作方案，走 camoufox-cli 持久化 session `douyin`（一个且只有一个持久化 session，fail-first 队列）。
2. **探活 / 有头登录 / 导出 Cookie+UA 全交 login-manager**——本 skill 不自管，不调用 `cookies export` / `identity export` / `cookies import`。
3. **自身不吃 Cookie**：发布脚本直接复用 login-manager 准备好的持久化 session `douyin`（`--session douyin --persistent`），不开临时 session、不 import cookie。
4. **导出的 Cookie+UA 落中央存储仅供脚本类下游消费**（`viral-chaser` / `published-track`）——douyin-publish 自身不读这两个文件。
5. **发布任务跑完不主动 close 持久化 session `douyin`**——登录态留着下次用；只在 session 卡死时 `camoufox-cli --session douyin --json close` teardown。
6. 子命令清单**无 `login`**：`upload` / `fill` / `publish` / `get-link` / `cleanup` / `run`（run 一键跑 upload → fill → publish → get-link，**不**自管探活）。

## 7. 显式有头/无头模式的场景规则（browser-guide 澄清点）

只有以下两种场景需要**显式**指定 `camoufox-cli` 的有头/无头模式参数：

| 场景 | 显式指定 | 说明 |
|------|---------|------|
| login-manager 登录（5 平台） | `--headed` | 强制统一有头，用户在浏览器手动扫码/短信/账号密码 |
| 需要用户手动过验证（captcha/滑块/短信） | `--headed` | 用户才能在浏览器里手动操作 |

**其他场景默认走 camoufox 持久化 session，不显式指定有头/无头**——camoufox-cli 默认行为即可（headless 是默认）。

**browser-guide §1-B 那句「wechat-channel / wx-mp 可无头启动截图发 QR；douyin / twitter / xhs / weibo / zhihu / xianyu / reddit / youtube 登录必须有头模式」要改**：
- wx-mp 那个无头特例只属于 wx-mp-hunter/engagement 的自有体系，不属于 login-manager 体系，不应在 browser-guide 里和 wechat-channel 并列提。
- wechat-channel（视频号）按现行 wechat-channels-publish 技能自有 SKILL.md 走，不在 browser-guide 里集中下结论。

## 8. published-track 流程 2A·自动更新（定时任务用）取数方案

凌晨复盘心跳调 `fetch-and-update-metrics.sh` 取互动数据。按平台分**三种**取数情况：

### 情况 1 — 脚本自动化取数（douyin / kuaishou / xhs / bilibili）

走 `fetch-and-update-metrics.sh` → `fetch-retro-data.ts` 纯 HTTP + 中央存储 cookie + UA。

- douyin / kuaishou / bilibili：直接脚本抓
- **xhs 需重构**（见 §9）：取 `note_id → xsec_token` 映射这步目前靠 `crews/main/HEARTBEAT.md` 描述的浏览器 evaluate 流程手动做，要整合进脚本

### 情况 2 — 微信公众号（wx_mp）

`fetch-and-update-metrics.sh --platform wx_mp --id <rowid>` 内部 exec `wx-mp-engagement.sh fetch --row-id <rowid>`——已实现这条路径（fetch-and-update-metrics.sh 现状已对），不动。但 wx-mp-engagement 内部要改：现状调的是不存在的 `login-manager.sh check wx-mp`（login-manager 是纯指导文件无脚本），要改成走 wx-mp-hunter 那套共用 camoufox-cli session + 无头 QR 流程（§4）。

### 情况 3 — 直接使用浏览器（其他平台）

对没有脚本支持的平台，明确讲：**应用对应平台的持久化 session 进入创作者列表页面即可**——browser 导航到创作者中心列表页 → snapshot 读行内互动指标 → 调 `update-metrics.sh` 写库。

涉及平台（后续会不断优化积累）：twitter、zhihu、weibo、wechat-channels（视频号）、youtube、facebook、instagram、tiktok、pinterest、threads 等。

`fetch-and-update-metrics.sh` 对这些平台现状会返回 `{"ok":false,"method":"browser","hint":"..."}` JSON 让 agent 走浏览器流程，**已对**，不动。

## 9. published-track 中 xhs 取数方案重构

**现状**：xhs feed API 强制要求 `xsec_token`，而 xsec_token 不能纯 API 拿（`user_posted` 端点已 406），只能从浏览器 DOM 取。`crews/main/HEARTBEAT.md` 里写了一段 CDP 思路的描述——`get-xhs-user-id.sh` 拿 self user_id，再**手动**用 browser evaluate 跑一段 JS 从 `__INITIAL_STATE__.user.notes` flatten 出 `note_id → xsec_token` 映射，再回脚本调 feed。

**问题**：这段流程散在 HEARTBEAT.md 描述里，agent 要手动编排多步，易出错。CDP 时代只能描述；现在用 camoufox-cli（本身是命令），取映射过程就是一步 eval 操作，**可整合进一个脚本**。

**重构目标**：做一个脚本（TS / Gas / Shell 都行，建议 TS 跟 `fetch-retro-data.ts` 同栈），把「拿 user_id + 浏 navigate profile 页 + eval �段 JS 取映射 + 调 feed 抓数」整段封进去。脚本内部走 `camoufox-cli --session xhs-browse --persistent`，不靠 agent 手动编排浏览器步骤。

**调用形态**（建议）：
```bash
./skills/published-track/scripts/fetch-xhs-with-xsec.ts \
  --id <rowid>            # pub_xhs 行主键，脚本内部查 publish_url 提 note_id
  # 脚本内部：
  #   1. camoufox-cli open xhs-browse session 探活，失效返回 exit 2
  #   2. 调 get-xhs-user-id.sh 拿 self user_id（或内部并）
  #   3. camoufox-cli open profile 页 + eval 那段 flatten JS 拿映射
  #   4. 按行 note_id 查映射拿 xsec_token/xsec_source
  #   5. 调 fetch-retro-data.ts 抓 feed → update-metrics.sh 写库
  #   6. 输出统一 JSON {ok, method, platform, content_id, metrics_params}
```

**HEARTBEAT.md 那段 xhs CDP 描述简化**：重构后那段「小红书 xsec_token 获取流程」整段删掉，改成一行指向脚本：「xhs 取数走 `fetch-xhs-with-xsec.ts`，脚本内闭环拿映射+抓数；失效返 exit 2 由心跳跳过」。

## 10. viral-chaser 改造点

`crews/main/skills/viral-chaser/scripts/session.ts` 现状已对齐「同时读 cookie + ua」，但需核实：

1. `Platform` 类型只列 `"douyin" | "bilibili" | "xhs" | "xhs-browse"`——按 §5 viral-chaser 只吃 douyin / xhs-browse / bili，不含 kuaishou，**不算 bug 但不完整**。重构时补上缺的类型注解，避免后续误用。
2. `viral_chaser.ts` / `downloader.ts` 抓取流程是否真同步导入 UA（不只是 session.ts 单点）——核实并补齐。
3. SKILL.md Step 2 文字现状已对齐新体系（同时导出 cookie + UA），但 SKILL.md 写的「exit 2 触发 login-manager 重登」要把 login-manager 改成只针对 5 平台的新描述（douyin / xhs-browse / bili 都在 5 平台里，对得上）。

## 11. 改造路线优先级

按依赖关系排：

1. **login-manager/SKILL.md**：删 wx_mp、改 6→5 平台、删 wx_mp 那行中央存储路径、删「无头截图 QR」段（§3 原则 3 的无头特例段），其他文字基本不动。（独立改，无依赖）
2. **browser-guide/SKILL.md §1-B**：删「wx-mp 可无头启动截图发 QR」并列句；澄清只有 login-manager 登录 + 用户过验证 + wx_mp 自己那套（§4）才显式指定有头/无头。（独立改，无依赖）
3. **不导出 Cookie 的话术纠正**（§6 清单）：twitter-interact / twitter-post / wechat-channels-publish / weibo-publish / zhihu-publish 五个 SKILL.md 改话术。（独立改，无依赖，可批量）
4. **wx-mp-hunter 重构**（§4）：探活/登录改走 camoufox-cli + 无头截 QR；废除 wx-mp-hunter.sh 的 check-session/login-qr/login-confirm；保留 search/account-posts/fetch 业务命令。
5. **wx-mp-engagement 改**（§4）：删所有 `login-manager.sh check wx-mp` / `login-manager.sh qr-headless` / `login-manager.sh cookie-import` 调用，改走 wx-mp-hunter 那套共用 session wx_mp + 无头 QR + 导出 cookie+ua。
6. **published-track/scripts 适配新 login-manager 中央存储格式 + UA 同步导入**：核实 fetch-retro-data.ts 是否同步读 ua.json；探活方式按 login-manager SKILL.md 步骤 0 改（snapshot 看跳登录页，不是 eval window.location.href）。
7. **published-track 中 xhs 取数重构**（§9）：做 fetch-xhs-with-xsec.ts，整合拿映射+抓数。
8. **HEARTBEAT.md 简化**：删 xhs 那段 CDP 描述，指向新脚本。
9. **viral-chaser/scripts 核实+补齐**（§10）：UA 同步导入全链路核实 + Platform 类型补齐。
10. **douyin-publish 重构**（§6.1）：之前误把它定位为「导出 Cookie 自己吃」一档（同 xhs-publish 模式），导致昨天改造走错。实际它**与 wechat-channels-publish 同构**——纯浏览器操作，自身不吃 Cookie、严禁 `cookies import`。差别在于：探活/有头登录/导出 Cookie+UA 全交 login-manager（供脚本类下游 viral-chaser / published-track 消费，douyin-publish 自身不读）。脚本删 `login` 子命令 + `login_manager_check` 自管探活；SKILL.md 重写职责划分。
11. **xhs-publish / xhs-content-ops 复核**：现状已对齐新体系，最后扫一遍确认话术与 login-manager SKILL.md 新版一致。

## 12. 附：核实清单（重构时必查）

- [ ] login-manager SKILL.md：5 平台、无 wx_mp、强制有头、无「无头截图 QR」段
- [ ] browser-guide §1-B：无 wx-mp 无头句；显式有头/无头场景规则按 §7 写清
- [ ] wx-mp-hunter：camoufox-cli + 无头 QR；无 check-session/login-qr/login-confirm 子命令；导出 cookie+ua 到 `wx_mp.json` + `wx_mp.ua.json`
- [ ] wx-mp-engagement：无 `login-manager.sh` 调用；走 wx_mp session；不导入 cookie（只走浏览器操作）
- [ ] published-track/scripts：探活按 snapshot 方式；fetch-retro-data.ts 同步读 ua.json
- [ ] fetch-xhs-with-xsec.ts：脚本内闭环拿映射+抓数；exit 2 = SESSION_EXPIRED
- [ ] HEARTBEAT.md：xhs CDP 段删，指向新脚本
- [ ] viral-chaser/scripts：UA 同步导入全链路；Platform 类型补齐
- [ ] 不导出 Cookie 的 5 技能：话术按 §6 改；共享 session 名约定（twitter / weixin-channel 等）写清
- [ ] douyin-publish（§6.1）：纯浏览器操作话术（仿 wechat-channels-publish）；探活/有头登录/导出交 login-manager；脚本无 `login` 子命令、无 `login_manager_check`；自身不吃 Cookie 严禁 `cookies import`
- [ ] xhs-publish / xhs-content-ops：话术复核与新版 login-manager 一致
