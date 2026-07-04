# wiseflow-client 开发计划（剩余）

> 本仓 = 产品拆分后的**客户端仓**（Docker 部署态，分支 `product-split/client`）。
> 已完成：Phase 0 骨架 / Phase 1 鉴权收敛（client 侧） / Phase 2 sign（client 5 调用点改 relay） / Phase 7 结构搬运（D8 扁平化 + D15 删减 + addons 销毁 + awada 拍平） / **D19 权限放开（内 crew T3 + 清 ALLOWED_COMMANDS，sales-cs 维持 T0）**。
> 全局规划见 `docs/product-split-plan.md`；client buildout 状态见 `docs/client-buildout.md`；relay 侧剩余见 relay 仓 `DEVPLAN.md`。
> 本文档只列**剩余开发内容**，按 Phase 排，每项含验收标准与依赖。

最后更新：2026-07-04

## 本轮开发约束（2026-07-04 启，阶段内有效）

- **本机部署实例不动**：`~/wiseflow-pro` 仓 + `~/.openclaw/` 是当前在线实例，本轮不触碰、不重部署、不读其 logs。
- **OpenClaw 源码位置**：本仓不 clone openclaw（与 `.gitignore` 一致）；开发期读源码去 `~/wiseflow-pro/openclaw/`，版本对齐 `v2026.6.10 / aa69b12d`（与本仓 `openclaw.version` 一致）。
- **bilibili-publish 路线**：与 video relay 撤回**独立判断**，待用户拍板（视频相关已撤回，见 Phase 3 顶部）。
- **Phase 7 续·身份文件合写**：用户标记为"后续探索"，**本轮暂缓**，不在本阶段排期。
- **统一部署**：本阶段开发完成后，再统一重新部署本机实例（届时再 copy openclaw 到本仓）。

---

## Phase 3 — publish/video skill 改调 relay（依赖 relay Phase 3）

> **2026-07-04 撤回**：video relay 模式取消。`crews/main/skills/video-product/`、`crews/content-producer/skills/siliconflow-video-gen/`、`html-video/` 维持现状（视频生成走本地凭据，不入 relay）。本节剩余仅 bilibili-publish + douyin-publish 路线讨论。

- [ ] **bilibili-publish 改调 relay**
  - 依赖：relay `publish-relay/bilibili` 端点就绪；用户拍板走 relay vs 维持现状。
  - 做：`crews/content-producer/skills/bilibili-publish/` 去掉本地持 SESSDATA/APP_SECRET，改 `POST /api/v1/publish/bilibili/*` 带 OFB_KEY。
  - 验收：发一条真实动态成功；skill 内无 BILI 凭据。

- [ ] ~~**video-product / content-producer 改调 relay**~~ → **撤回**（2026-07-04，视频技能维持本地凭据）

- [ ] **douyin-publish 路线对齐**
  - 依赖：relay 3.1 抖音路线定。
  - 做：若 API 逆向 → 改调 relay；若浏览器模拟 → 走 camoufox-cli（Phase 4.5）纯 client 操作。**定之前不动**。

## Phase 4 — awada extension 改 HTTP/WS（依赖 relay Phase 4）

- [ ] **awada extension 改 HTTP/WS transport**
  - 依赖：relay awada-server HTTP/WS 网关就绪。
  - 做：`awada/src/` 去掉 `ioredis` 直连，改 `relayBaseUrl` + `ofbKey`：
    - `GET /api/v1/awada/outbound?lane=`（long-poll/WS 拉回复）
    - `POST /api/v1/awada/inbound`（agent 回复入）
    - 带 `X-OFB-Key` header。
  - 改 `awada/src/config-schema.ts`：`redisUrl` 字段作废，换 `relayBaseUrl` + `ofbKey`。
  - 验收：微信消息双向闭环；`grep -r "ioredis\|redisUrl" awada/src/` 仅剩类型残留或空。

## Phase 4.5 — camoufox 集成（spike 已过，见 `docs/camoufox-spike-2026-07.md`）

- [ ] **browser-guide 改写**：`browser act` → camoufox-cli 调用指导。
- [ ] **login-manager 重写**：无头截图 QR → camoufox cookies export → 中央存储 `~/.openclaw/logins/`（去掉 CDP WebSocket 抽 cookie）。
- [ ] **浏览器类 skill 改 camoufox-cli**：xhs-interact / content-calibrator / viral-chaser / xhs-content-ops 等。
- [ ] **指纹模板 bake**：Dockerfile 生成 `~/.camoufox-cli/profiles/_template` 冻结指纹。
- 验收：xhs-browse 登录走 camoufox 跑通；cookie 入中央存储；下游 HTTP skill 复用 cookie 成功。
- 约束：保留 patchright override + patch 005/006 供 fallback connectOverCDP；**不 fork camoufox-cli**（D18）；并发 = 每 agent 一个 session（独立 daemon + 独立浏览器进程 + 独立 profile dir）。

## Phase 4.6 — 微信公众号 engagement 数据接入 published-track

> **背景**：微信公众号是 published-track + 复盘的唯一 engagement 缺口（小红书/抖音等已接）。目标：拿到阅读数/评论数，纳入统一复盘流。
> **依赖**：Phase 4.5 camoufox 集成 ✅。
> **切分**：整块 client 容器内闭环，**不碰 relay**（credential 是会话 token，relay 持有无益且有风险）。
> **设计**：`docs/wechat-mp-engagement-design.md`（方案 A 全量设计）
> **骨架实现**（2026-07-04）：`crews/main/skills/wx-mp-engagement/`（SKILL.md + 脚本 + 15 单测） + `published-track/fetch-and-update-metrics.sh` 路由加 wx_mp 分支 + `login-manager` 加 `wx-mp` 平台
> **状态**：⚠️ **待真机 spike 验证**。本轮仅交付骨架，不实施真机验证（无公众号账号环境）。

### 方案优先级

| 优先级 | 方案 | 状态 |
|---|---|---|
| A（首选） | 公众号后台 + camoufox | 骨架已交付，spike 待真机 |
| B（兜底） | wxdown-service 抓包（容器内 mitmproxy） | 待 spike A 失败后启 |
| C（兜底） | 维持现状 | A+B 都失败时启用 |

**方案 A（优先）：公众号后台 + camoufox** — 骨架已交付：
- camoufox 打开 `mp.weixin.qq.com` 公众号后台，通过创作者列表/内容管理页拿阅读数/评论数
- 每次需用户扫码登录后台（后台有网页登录入口，D18 camoufox 适用）
- 限制：仅能拿**用户自己有后台权限的号**，竞品号拿不到
- spike：camoufox 能否稳定登录后台 + 抓到内容管理页数据

**方案 B（次选）：wxdown-service 抓包方案（容器内闭环）** — 待 spike A 失败后启：
- 上游 `wechat-article/wxdown-service` 实证了**桌面浏览器 + 无微信登录**架构
- 把"桌面浏览器"换成**容器内 camoufox**，mitmproxy 也在容器内 → mitmproxy CA 只在容器内
- 复杂度：mitmproxy 进镜像（~50MB）+ camoufox 注入 mitmproxy CA + credential 解析 + API 移植

**方案 C（兜底）**：维持现状。

### Spike 验证 checklist（部署后由用户真账号跑）

> 详见 `docs/wechat-mp-engagement-design.md` §七

| # | 验证项 | 期望 |
|---|---|---|
| 1 | camoufox-cli 启 headless 打开 `mp.weixin.qq.com` 创作者中心 | 页面正常加载，无风控拦截 |
| 2 | 触发扫码登录，PC 端微信扫描 | 30s 内登录成功，cookie 落 `~/.openclaw/logins/wx-mp.json` |
| 3 | 内容管理列表页 DOM 含阅读数/点赞数/评论数 | selector 命中 |
| 4 | 单篇分析页 DOM 含精确阅读数 | selector 命中 |
| 5 | 评论管理 API 返回 JSON 列表 | 字段对齐 |
| 6 | 抓取频率（每篇 1 次）不触发风控 | 验证通过 |
| 7 | 批量抓最近 7 天文章 | 7 篇 ≤ 5 分钟，无封号 |
| 8 | 凌晨复盘心跳集成 | 自动跑通 |
| 9 | 竞品号（无后台权限） | 方案 A 自然失败（产品约束，接受） |
| 10 | cookie 失效兜底 | 触发 qr-headless + qr-confirm |

**失败回退**：
- 1-5 任一失败 → 走方案 B
- 6-7 失败 → 限频 + 错峰跑
- 8 失败 → 保留 manual update 作为兜底

### 落实步骤

1. ~~设计 doc~~ ✅ `docs/wechat-mp-engagement-design.md`
2. ~~skill 骨架~~ ✅ `crews/main/skills/wx-mp-engagement/`
3. ~~login-manager 加 `wx-mp` 平台~~ ✅
4. ~~published-track 集成点~~ ✅ `fetch-and-update-metrics.sh` 加 wx_mp 路由
5. **spike 验证**：等统一部署后由用户真账号跑
6. 根据 spike 结果决定走方案 A 完整化 / 回退到 B / 维持 C

## Phase 5 — img-gen 改火山

- [ ] **siliconflow-img-gen → 火山生图**
  - 做：`skills/siliconflow-img-gen/` 改调火山引擎生图 API；用用户 `AWK_API_KEY`（纯客户端，不入 server，D13）。
  - 验收：生成一张图成功；skill 内无 siliconflow key。
  - 依赖：fetch 火山 volcengine 文档确认接口（plan §九 Phase 5）。

## Phase 6 — Dockerfile 阶段 3-4 填实 + entrypoint

- [ ] **wiseflow-layer 阶段组织**
  - 做：COPY `skills/` → `/root/.openclaw/skills`；COPY `crews/` → `/root/.openclaw/workspace-*`；COPY `config/openclaw.json` → `/root/.openclaw/openclaw.json`；`daemon.env.template` 占位。
- [ ] **依赖统一装**：`requirements.txt` / `package.json` 一次性 npm/pip install。
- [ ] **D20① 镜像预装常用依赖**：按 `skills/`+`crews/` 实际 import 清单（requests/Pillow/xhshow/python-pptx/reportlab/tccli/google-api-python-client/google-auth-oauthlib 等）pip 装进镜像 site-packages，免小白用户运行期 pip。
- [ ] **img-gen 编译**：火山 gen.py 编译/打包。
- [ ] **camoufox Firefox 二进制 bake**（不 bake chromium，D18）。
- [ ] **openclaw-weixin 插件安装**（tgz）。
- [ ] **entrypoint 渲染逻辑**：读 env 渲染 daemon.env → 注入 OFB_KEY/RELAY_BASE_URL 到各 skill 配置 → `node openclaw.mjs gateway` → 检测 weixin 未绑 → `qrcode-terminal` 输出 + UI 兜底。
- [ ] **D20② entrypoint 注入 PYTHONPATH**：指向 `~/.openclaw/skills/*/vendor/`，使用户额外装 skill 的 pip 依赖（`pip --target` 装入）可被 import；npm 依赖装 skill 目录下局部 `node_modules`。重启不丢（在 volume）。
- 验收：`docker build` 出镜像；`docker run` 弹微信二维码；扫码绑定后 agent 响应。

## Phase 7 续 — crew 内容合写

> **2026-07-04 暂缓**：用户标记为"后续探索"，本轮不在排期。等下一阶段再启动。
> 以下为暂缓期间保留的需求清单（仅作存档，不推进）。

~~> 结构搬运已完成（`97bad4d`）；以下为身份文件 / AGENTS / HEARTBEAT 内容合写。源 AGENTS 在 git 历史 `97bad4d^` 可恢复。
>
> **D19 已落（2026-07-03）**：内 crew（main/content-producer/it-engineer）SOUL.md `command-tier=T3` + 清空 ALLOWED_COMMANDS；sales-cs 维持 `T0` 不动。Docker 内对内全放开（消除 allowlist miss 摩擦），对外保留 prompt injection 防线。~~

- [ ] **main 身份合体**（AI 搞钱搭子「小贝」定位）
  - 做：写 SOUL.md / IDENTITY.md / MEMORY.md / HEARTBEAT.md，定位 = AI 搞钱搭子（中文名「小贝」，专为 OPC / 中小微企业老板）；**SOUL/风格**：理性、高效、尽责的天才少女，带一点点傲娇和毒舌调皮；**对用户自称「小贝」**；weixin binding 指向它；MEMORY 写 sales-cs 启用/软链/HRBP 优化知识。
  - 源：原 self-media-operator crew（已整合 IR + BD 能力，改名为 main）+ plan §七。
- [ ] **IR 三模式抽三 skill**
  - 做：从旧 ir crew AGENTS（git 历史 `97bad4d^:addons/officials/crew/ir/AGENTS.md`）抽三模式，写成 `crews/main/skills/` 下 `business-model-polish`（模式1商业模式打磨）/ `project-application`（模式2项目申报）/ `investor-pipeline`（模式3投资人发掘与跟进）三个 skill。
  - `ir-record` 作公共数据层 skill（三 skill 委托，DB 统一，已搬入）；`swcr-register` / `investor-hunting` / `investor-outreach` / `market-research` 保留独立子 skill 供委托（已搬入）。
  - HEARTBEAT 留 crew 级含 7 天投资人过期提醒；模式3 状态机 new→contacted→bp_sent→meeting→dd→ts→invested/passed。
- [ ] **business-developer 三能力合入**
  - 做：`lead-hunting` / `comment-engagement` / `intel-gathering`（已搬入 main/skills）写入 main AGENTS + HEARTBEAT（保留 heartbeat 写入模式）；`bd-record` / `info-record` 作数据层。
- [ ] **it-engineer 瘦身 + 强化运维**
  - 做：删升级知识（MEMORY/AGENTS 中 install.sh 升级流程段落）；强化 env/relay/awada 启用/sales-cs 启用运维；定位为 main + sales-cs 的 sub-agent，无 channel。
- [ ] **sales-cs sample + 软链**
  - 做：默认 seed 不在 openclaw.json；绑 awada；启用由 IT engineer 操作改 `enabled: true` + 软链 `business_knowledge/`；自有技能同现仓（已搬入）。
- [ ] **shared/ 内化进 it-engineer**
  - 做：`crews/shared/` 中 IT engineer 用得上的内容（COMMAND_TIERS / CREW_TYPES）内化进 it-engineer，其余删。
- [ ] **apply-addons.sh 死代码精简**
  - 做：删 addons 扫描循环（~260 行起）；保留补丁 + 全局技能 + awada 注入 + 配置同步；crew 安装由 setup-crew.sh 单独负责。
- [ ] **全局技能软链化 + wrapper 覆盖审计**（D21）
  - 背景：当前 `~/.openclaw/skills/` 是拷贝（改 repo 要 reinstall）；弱模型路径拼接错主要来自 baseDir 拼接 + allowlist miss。D19 已消掉 allowlist miss（内 crew T3 full），剩"拼错绝对路径"靠 wrapper 上 PATH 解。
  - 做（本地开发实例）：`~/.openclaw/skills/<name>` 由拷贝改软链 → `<repo>/skills/<name>`（指向本仓 repo，**不**软链到 `openclaw/skills` bundled 层——那会降优先级 + 耦合版本树 + 不治路径错）。
  - 做（Docker 镜像）：维持 COPY 拷贝到 `/root/.openclaw/skills/`（镜像重建即更新，软链无额外收益）。
  - 做（wrapper 审计）：审计各 skill 的 wrapper 覆盖率，常用 skill 没 wrapper 的加上（`wx-mp-hunter.sh` 已有范例），让 agent 调 `<skill> <cmd>` 零路径拼接。
  - 不做：软链到 `openclaw/skills`（bundled）——见上理由。
  - 验收：本地实例改 repo skill 即时生效；常用 skill 均有 wrapper；弱模型路径相关 exec 失败近零。
- 验收：各 crew AGENTS/SOUL/IDENTITY 自洽；`tests/crew-architecture-regression.sh` 仍过；openclaw.json 3-crew 目标态跑通。

## Phase 8 — IT engineer 记忆注入 + 端到端走查

- [ ] **IT engineer 记忆注入**：把产品拆分后的运维知识（relay 端点 / awada 启用 / sales-cs 启用 / camoufox 排障）写入 it-engineer MEMORY。
- [ ] **D20③ skill 依赖安装规范写入 it-engineer**：在 AGENTS.md/MEMORY.md 写明用户额外装 skill 时的依赖安装规则（pip `--target ~/.openclaw/skills/<skill>/vendor/` + PYTHONPATH 已由 entrypoint 注入；npm 局部 `node_modules`；何时装、依赖冲突处理）。
- [ ] **端到端走查**：docker run → 扫码 → 用户在微信发消息 → main 响应 → 调 relay sign/publish/video → 回复。全链路绿。
- 验收：一条用户消息走完全链路无人工干预。

## 文档收尾

- [ ] `docs/workspace-bootstrap-files.md` skill 表更新为新 crew + 新 skill 归属。
- [ ] `CHANGELOG.md` 补产品拆分条目。
- [ ] `docs/product-split-plan.md` §十一状态段同步至 Phase 7 结构搬运完成。

---

## 阻塞项（待外部输入）

- **抖音发布路线**：见 Phase 3 douyin-publish，relay 3.1 定之前不动。
- **relay Phase 3/4 端点**：client Phase 3/4 依赖 relay 侧先就绪。
- **配额计数上报**：待 BD 计费模型（relay 侧）。

## 与 relay 仓的边界

- client 不持任何平台凭据，所有 relay 调用带 `X-OFB-Key`。
- relay 端点由 `RELAY_BASE_URL` 派生，entrypoint 注入各 skill 配置，**用户无需配**。
- 接口契约见 relay 仓 `docs/API-CONTRACT.md`。改接口先改那边并通知本仓。
- 本仓 `relay/` 目录是本地独立仓（gitignored，父仓不跟踪），仅供本轮开发期参考/同步，移交时删除。
