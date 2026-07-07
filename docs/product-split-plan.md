# wiseflow-pro 产品拆分开发规划（基线 v1）

> 状态：**已启动实施**。Phase 0-2 + Phase 7 结构搬运 + D19 权限放开 + camoufox spike 完成；剩余见 `docs/DEVPLAN-REMAINING.md`。本文件是决策基线，结论有变再更新。
>
> 记忆索引：分仓后 client 侧记忆在 `client_memory/`（仓根），relay 侧在 `relay_memory/`。

## 一、总目标

把现 wiseflow-pro 单体仓的"综合最强功能"抽出来做成两个更轻量的独立产品，降低用户入手难度。**产品定位**：专为 OPC / 中小微企业老板量身打造的"AI 搞钱搭子"，中文名 **「小贝」**。

- **client 仓**：Docker 镜像部署态，用户拉取即用（免 install.sh）
- **server 仓**：服务器部署的统一中转服务（不用 Docker，普通部署）

**前置约束（用户明确）**：
- 现有 Pro 仓**不变**，继续按现状独立迭代
- 新建两个代码仓，从现 Pro 仓**当前 master** 切出
- 三仓各自独立维护
- 实施期间不碰现仓可运行状态

## 二、已确认的关键决策

| # | 决策项 | 最终定法 |
|---|---|---|
| D1 | 签名/发布凭据托管 | **全 proxy**：xhs/bilibili 服务器签名+代请求+返回解析结果；**抖音放弃官方 API，走浏览器模拟 / API 逆向**（同 xhs、微信视频号路子）。原因：抖音开放平台发布能力申请被驳回，要求公司主体注册资本 > 50 万且注册满 1 年，我方均不满足。新方案：① 浏览器模拟（D18 camoufox-cli/CDP attach 已登录抖音的 Chrome，直接发布页上传，免云存储）；② 可选 API 逆向（逆向抖音 web 发布接口，server 签名+代请求，同 xhs sign 服务）。不再需要 `h5.share`/`aweme.share`/`open.get.ticket` 三个 scope，不再需要 schema 跳转和 H5 中转页。详见 §十二 抖音发布流程 |
| D2 | awada 远程传输 | **HTTP/WS transport**：awada-server 加 HTTP 网关，客户端 extension 走 HTTP+OFB_KEY，不暴露 Redis |
| D3 | 容器内进程启动 | **entrypoint 直起 `node openclaw.mjs gateway`**，放弃容器内 systemd，`--restart=always` 保活 |
| D4 | 仓拆分 | 从现 Pro 仓当前 master 切出两个新仓；现仓不变 |
| D5 | 客户端内置 crew | 保留 **main(default) + content-producer + it-engineer + sales-cs(默认禁用)** 四个 |
| D6 | weixin 二维码首屏交付 | `docker logs` 终端二维码为主 + openclaw 控制台 UI(18789) 兜底 |
| D7 | agentId 命名 | main = `main`；content-producer = `content-producer`；sales-cs = `sales-cs`；it-engineer = `it-engineer` |
| D8 | 销毁 addon 结构 | client 仓扁平化：4 crew 直接放 `crews/`，公共技能(≥2 crew 用)放 `skills/`，非公共内化进各 crew 的 `skills/` |
| D9 | Docker 即部署态 | image 里直接是 `~/.openclaw/` 运行态目录，容器内不再跑 install/setup/apply-addons |
| D10 | sales-cs 定位 | 独立对外 crew，有自己 workspace + 绑 awada channel + **自有技能（同现仓 officials/crew/sales-cs）**，不从main agent继承；main agent充当其 HRBP 负责改善迭代 |
| D11 | business_knowledge | 放在main agent下 `crews/main/business_knowledge/`，启用 sales-cs 时在其 workspace 下软链 |
| D12 | video Key 归属 | **统购分销**：视频生成上游 key（百炼/火山视频）在 server，client 只见 OFB_KEY，用户向产品方计费 |
| D13 | img-gen Key 归属 | **用户自带**：用户已有 AWK_API_KEY，火山引擎同 key 覆盖语言/视觉/生图 → `siliconflow-img-gen` 改火山生图后**纯客户端技能，不进 server** |
| D14 | server 部署 | 不用 Docker，PM2/systemd 普通部署 |
| D15 | 内置 crew 去留 | 旧 openclaw 默认 main + hrbp + designer + ir + officials-selfmedia-operator 全删；**self-media-operator 整合 IR + BD 能力后改名为 `main` 作为新体系 default crew**；**video-producer 整合 designer 能力后改名为 `content-producer`**；`crews/shared/` 中 IT engineer 用得上的内容内化进 it-engineer，其余删 |
| D16 | main 定位 | **AI 搞钱搭子「小贝」**：专为 OPC / 中小微企业老板量身打造，对外定位/IDENTITY 写"AI 搞钱搭子"（中文名「小贝」），agentId = `main`；**SOUL/风格**：理性、高效、尽责的天才少女，带一点点傲娇和毒舌调皮；**对用户自称「小贝」** |
| D17 | IR 三模式→三 skill | 现仓 `addons/officials/crew/ir` 三模式抽成三个 skill 配给main agent（私有 skills）：`business-model-polish`(模式1商业模式打磨)、`project-application`(模式2项目申报)、`investor-pipeline`(模式3投资人发掘与跟进)。ir-record 作公共数据层 skill 保留(三 skill 委托它，DB 统一)；swcr-register/investor-hunting/investor-outreach/market-research 保留独立子 skill 被三 skill 委托；HEARTBEAT 留 crew 级，skill 只描述能力 |
| D18 | 浏览器方案（camoufox 主 + CDP fallback） | **主用 camoufox-cli 无头**（Node 版 v0.6.2，camoufox-js + playwright-core firefox 驱动 Camoufox/Firefox）做所有浏览器任务：获取/模拟登录/取cookie/上传。**fallback**：搞不定时 CDP attach 用户真实 Chrome + 直接用其 User Profile，或用户主动说"连我的浏览器"（应对已登录场景）。**保留** patchright override + patch 005/006 供 fallback 的 connectOverCDP 路径用，不删。**并发模型 = 每 agent 一个 session**（独立 daemon + 独立浏览器进程）+ 共享冻结指纹模板 + 每 session 独立 profile dir + cookie 中央存储(`~/.openclaw/logins/`)：登录一次→camoufox cookies export→中央存储→各 session `cookies import` 注入→下游 HTTP 脚本复用。**不 fork camoufox-cli**（其单全局 page 指针不支持一进程多 page 并发，B 路径零改动最稳）。**login-manager 重写**：无头截图 QR → cookie export → 中央存储（去掉 CDP WebSocket 抽 cookie）。**Dockerfile** bake camoufox Firefox 二进制 + camoufox-cli(npm 全局)，**不 bake chromium**（fallback attach 的是用户本机 Chrome，无需自带 chromium 二进制；patchright-core 仅作 npm 依赖留给 connectOverCDP 驱动）。**skill 改写**：browser-guide + 浏览器类 skill(xhs-interact/content-calibrator/viral-chaser/xhs-content-ops 等) 从 `browser act` 改为 camoufox-cli 调用 |
| D19 | Docker 内权限策略 | **对内 crew 全放开**：main、content-producer、it-engineer 的 `command-tier` 设为 `T3`（`security: full`），清空 ALLOWED_COMMANDS 增删项。**对外 crew 维持现状**：sales-cs 保持 `T0`（`security: deny`）不动。理由：Docker 已隔离宿主 OS，内 crew 放开消除 exec allowlist miss 摩擦（复合命令 `&&`、`cd`/`bash` 前缀、相对路径误拼，见 `docs/feedback/2026-04-18-exec-allowlist-compound-command.md`），不再需要 CLAUDE.md 里"必须绝对路径"那套绕坑规范；sales-cs 面对未受信外部输入，T0 是 prompt injection 防线（防外发凭据/乱发客户消息），与容器隔离正交，必须保留。落实点：Phase 7 crew 重构写 client 仓 SOUL.md 时 |
| D20 | Docker 内 skill 依赖策略 | **镜像预装 + 用户扩展装 volume**。① 镜像预装常用依赖：requests、Pillow、xhshow、python-pptx、reportlab、tccli、google-api-python-client、google-auth-oauthlib 等（Phase 6 Dockerfile 填实时按 skills/crews 实际 import 清单列全，pip 装进镜像 site-packages）。② 用户额外装 skill 时，pip/npm 依赖装到 volume 内 `~/.openclaw/skills/<skill>/vendor/`：pip 用 `--target` 装入 + entrypoint 注入 `PYTHONPATH` 指向各 skill vendor；npm 装到 skill 目录下局部 `node_modules`。重启不丢（在 volume）。③ 安装规则规范写入 it-engineer 的 AGENTS.md/MEMORY.md（何时装、装到哪、PYTHONPATH 注入、依赖冲突处理），Phase 8 记忆注入时落。理由：D9 镜像即部署态与"用户可扩展 skill"折中——常用依赖预 bake 免小白用户碰 pip，扩展能力又留给高级用户，且不破坏 D9（容器内不再跑 install 是指**镜像构建期**不跑，运行期用户主动装 skill 是用户显式行为，不冲突） |

## 三、Server 仓 `wiseflow-relay`（普通部署）

```
wiseflow-relay/
├─ services/
│  ├─ auth/              # OFB_KEY 网关：发放/校验/吊销/限流/配额
│  ├─ sign/              # xhs(xhshow) + douyin(douyin.js) 全proxy签名
│  ├─ publish-relay/     # bilibili全proxy；douyin token签发
│  ├─ video-relay/       # 包装gen.py → 百炼/火山（统购，server持上游key）
│  ├─ tx-relay/          # 迁入 wenyan-server + work-weixin-proxy
│  └─ awada-server/      # 迁入 + 新增 HTTP/WS transport 网关
├─ deploy/               # PM2/systemd 部署脚本、nginx、SSL
└─ docs/
```

**注意**：无 img-relay（D13），无 docker-compose（D14）。

## 四、Client 仓 `wiseflow-client`（部署态 source）

```
wiseflow-client/
├─ Dockerfile                    # 多阶段，bake出 ~/.openclaw 运行态
├─ docker-entrypoint.sh          # 填env→起gateway→弹weixin二维码
├─ .dockerignore
├─ openclaw/                     # 引擎源码（build期编译）
├─ patches/                      # 4个patch + overrides.sh
├─ openclaw-weixin.version.json  # 锁版本（现仓缺，client仓需补）
├─ openclaw.version              # 锁定 aa69b12d
├─ config/
│  ├─ openclaw.json              # 最终配置（list 含 main/content-producer/it-engineer 3 crew，sales-cs 不在 list，awada disabled）
│  ├─ daemon.env.template        # key占位（AWK_API_KEY/OFB_KEY/SMTP_*）
│  └─ workspace-skeleton/        # 通用骨架（credentials/空目录等）
├─ skills/                       # 公共技能（≥2 crew用）
│  ├─ browser-guide/
│  ├─ smart-search/
│  ├─ email-ops/
│  ├─ council/
│  ├─ pitch-deck/
│  ├─ rss-reader/
│  ├─ xhs-interact/
│  ├─ siliconflow-img-gen/       # 改火山生图（用户AWK_API_KEY，纯客户端，不入server）
│  ├─ login-manager/
│  ├─ wx-mp-hunter/
│  └─ wxwork-drive/
├─ crews/
│  ├─ main/        # DEFAULT，绑openclaw-weixin；对外定位=AI 搞钱搭子
│  │  ├─ AGENTS/SOUL/IDENTITY(AI 搞钱搭子)/MEMORY/USER/HEARTBEAT(含7天过期提醒)/HEARTBEAT_TEMPLATE/TOOLS/ALLOWED_COMMANDS/BUILTIN_SKILLS/DENIED_SKILLS
│  │  ├─ business_knowledge/     # 业务/品牌介绍/话术/FAQ，启用sales-cs时软链到其workspace
│  │  └─ skills/                 # 私有技能集：
│  │     ├─ [内容发布类·改relay] wx-mp-publisher, twitter-*, douyin-publish, kuaishou-publish, bilibili-publish, xhs-publish, xhs-content-ops, wxwork-moments
│  │     ├─ [素材运营类] pexels-footage, pixabay-footage, viral-chaser, published-track, content-calibrator, video-product
│  │     ├─ [IR三模式·迁自现仓ir crew] business-model-polish(模式1), project-application(模式2), investor-pipeline(模式3)
│  │     ├─ [IR数据层] ir-record(公共数据层，三IR skill委托，11脚本DB统一)
│  │     └─ [IR子skill·保留独立] swcr-register, investor-hunting, investor-outreach, market-research
│  ├─ content-producer/          # 内容制作 crew（原 video-producer 整合 designer 能力），main 的 sub-agent
│  │  └─ skills/                 # 视频生成/视觉设计/剪辑等制作类技能
│  ├─ it-engineer/               # sub-agent，无channel，删升级知识，强化运维
│  │  └─ skills/                 # session-logs/seo/tccli/icp* 等（shared内化）
│  └─ sales-cs/                  # 默认seed但不在openclaw.json，绑awada
│     ├─ AGENTS/SOUL/IDENTITY/MEMORY/USER/HEARTBEAT/ALLOWED_COMMANDS/BUILTIN_SKILLS
│     └─ skills/                 # sales-cs自有技能（同现仓officials/crew/sales-cs）
└─ scripts/
   └─ build-image.sh             # 仅构建辅助，无install.sh
```

**main 删除的 10 个海外/二次发布技能**：de-mouth、facebook-publish、highlight-clipper、instagram-publish、juejin-publish、pinterest-publish、threads-publish、tiktok-publish、toutiao-publish、youtube-publish。

**合入的 business-developer 三能力**（保留 heartbeat 写入模式）：Lead Hunting / Comment Engagement / Intel Gathering。

## 五、Server 接口契约

统一前缀 `/api/v1/`，统一 header `X-OFB-Key: <OFB_KEY>`，统一响应包络 `{success, data, error, meta}`。

- **auth**: `POST /auth/issue`（管理端发 key）+ `verifyOfbKey` 中间件注入所有 relay
- **sign**: `POST /sign/xhs`（cookie+params→代请求→返解析结果）、`POST /sign/douyin`
- **publish-relay**: `POST /publish/bilibili`（全proxy代发，server持APP_SECRET）、`POST /publish/douyin`（若走 API 逆向：server 签名+代请求+返回解析结果，同 xhs sign 模式；若走浏览器模拟：纯客户端操作，不经过 server）
- **video-relay**: `POST /video/generate`→`{task_id}`、`GET /video/task/:id`→`{status,videoUrl}`（server 轮询上游，client 只轮询 server；videoUrl 须为公开可访问 URL，server 转存到自有 CDN/OSS）
- **awada**: `POST /awada/inbound`、`GET /awada/outbound?lane=`（long-poll/WS，带 OFB_KEY）

## 六、Dockerfile 四阶段

1. **workspace-deps**: Node24 + pnpm + python3 + **camoufox Firefox 二进制 + camoufox-cli(npm 全局)**（不 bake chromium；patchright-core 仅作 npm 依赖留给 fallback connectOverCDP 驱动，attach 的是用户本机 Chrome）
2. **build**: COPY openclaw + apply patches(含 patchright override + 005/006，供 fallback) + pnpm install + pnpm build + ui:build
3. **wiseflow-layer**: COPY skills/crews/config → 组织成 `/root/.openclaw/` 运行态（skills→`/root/.openclaw/skills`；crews→`/root/.openclaw/workspace-*`；config/openclaw.json→`/root/.openclaw/openclaw.json`；daemon.env.template 占位）+ 统一 npm/pip install + 编译改火山的 img-gen gen.py + 生成 camoufox 冻结指纹模板(`~/.camoufox-cli/profiles/_template`)
4. **runtime**: 复制产物 + 装 openclaw-weixin 插件(tgz) + ENTRYPOINT

**entrypoint 运行期**：读 env 渲染 daemon.env → 注入 OFB_KEY/relay 端点到各 skill 配置 → `node openclaw.mjs gateway`（非 systemd）→ 检测 weixin 未绑 → `qrcode-terminal` 输出 stdout + UI 兜底。volume: `/root/.openclaw`。

## 七、crew 重构要点

- **main**（对外定位=AI 搞钱搭子「小贝」，专为 OPC / 中小微企业老板）：删 10 技能；保留技能全部改 relay 调用（带 OFB_KEY）；合入 business-developer 三能力(Lead Hunting/Comment Engagement/Intel Gathering，heartbeat 写入模式)；**合入 IR 三模式**抽成 business-model-polish / project-application / investor-pipeline 三 skill（ir-record 作公共数据层 skill 保留，swcr-register/investor-hunting/investor-outreach/market-research 保留为独立子 skill 供委托；HEARTBEAT 留 crew 级含 7 天投资人过期提醒，模式3 状态机 new→contacted→bp_sent→meeting→dd→ts→invested/passed）；weixin binding 指向它；MEMORY 写 sales-cs 启用/软链/HRBP 优化知识
- **content-producer**（原 video-producer 整合 designer 能力）：内容制作 crew，作为 main 的 sub-agent；持视频生成/视觉设计/剪辑等制作类技能，视频生成改调 relay video-relay（D12 统购）
- **it-engineer**: 删升级知识（MEMORY/AGENTS 中 install.sh 升级流程段落）；强化运维(env/relay/awada 启用/sales-cs 启用)；为 main + sales-cs 的 sub-agent，无 channel；shared 内化
- **sales-cs**: 默认 seed 不在 openclaw.json list；绑 awada（启用由 IT engineer 操作改 enabled + 软链 business_knowledge）；自有技能同现仓

## 八、用户体验闭环

拉镜像 → 配 key（AWK_API_KEY、OFB_KEY、可选 SMTP_*）→ 启动 Docker → entrypoint 判断 weixin 未绑 → 弹二维码（docker logs / UI）→ 用户微信扫码绑定 → 直接在微信使用。
（relay 端点固定，无需用户配 WENYAN_API_KEY/WENYAN_SERVER_URL/WXWORK_PROXY_URL；SMTP 可选；其余默认写好。所有 env 知识写入 it-engineer 预置记忆，后续可由 IT engineer 改/补。）

## 九、阶段与估时

| Phase | 内容 | 估时 |
|---|---|---|
| 0 | 两新仓骨架（从现仓 master 切，不碰现仓）+ OFB_KEY 框架 | 1-2d |
| 1 | auth 网关 + relay 框架 + tx-relay/awada 接入 OFB_KEY | 2-3d |
| 2 | sign 服务(xhs/douyin) + 改 xhs-publish/viral-chaser | 2-3d |
| 3 | publish-relay(bilibili全proxy/douyin token) + video-relay(统购) | 3-4d |
| 4 | awada HTTP transport + extension HTTP adapter | 2d |
| 4.5 | **camoufox 集成**：browser-guide 改写 + 浏览器类 skill 改 camoufox-cli 调用 + login-manager 重写(无头截图登录+cookie export) + 冻结指纹模板/每 session profile dir/cookie 中央存储 落地 + 2 个 spike 验证 | 2-3d |
| 5 | img-gen 改火山生图（fetch volcengine 文档确认接口）+ siliconflow-img-gen 落客户端 | 1-2d |
| 6 | client Dockerfile + entrypoint + weixin 二维码；**D20① 镜像预装常用 pip/npm 依赖**（按 skills/crews import 清单）；**D20② entrypoint 注入 PYTHONPATH 指向 skill vendor** | 3-4d |
| 7 | crew 重构：main 合体(AI 搞钱搭子「小贝」定位) + IR 三模式抽三 skill + business-developer 三能力合入；content-producer 合体(整合 designer)；it-engineer 瘦身；sales-cs sample+软链；**D19 落实权限**（内 crew T3 full + 清 ALLOWED_COMMANDS，sales-cs 维持 T0） | 3-4d |
| 8 | IT engineer 记忆注入 + 端到端走查 + 文档；**D20③ skill 依赖安装规范写入 it-engineer AGENTS.md/MEMORY.md** | 2d |

**总 21-27 天，复杂度 HIGH。**

## 十、待后续讨论/外部输入

- BD 市场调研结果（可能影响功能取舍、定价、relay 计费模型）
- 上游视频统购的计费模型细化（按量/包月/配额）
- sales-cs 增值服务的购买与启用流程（商务侧）
- 火山引擎生图 API 细节（Phase 5 时 fetch https://www.volcengine.com/docs/82379/1541523 确认）
- **camoufox spike（Phase 4.5 验证）**：✅ **2026-07-03 完成，两项均通过**，见 [`docs/camoufox-spike-2026-07.md`](camoufox-spike-2026-07.md)。① `cookies export` JSON 与 Playwright Python `add_cookies` 格式完全对齐（零转换），raw HTTP 3 行薄适配；② `camoufox-cli.json` 模板 cp 到新 profile dir + `--persistent` 启动可复用指纹（OS/platform/screen/canvas/fonts），rv 版本跟二进制（非指纹维度，预期）。D18 确认可行，无需 fork camoufox-cli。Phase 4.5 风险降级，可直接进入实现。
- **抖音发布 spike（Phase 3 验证）**：抖音官方 API 申请被驳回（主体资质不满足），已改走浏览器模拟 / API 逆向。spike 验证：① camoufox-cli 能否稳定完成抖音登录态下的发布页上传（视频+标题+话题）；② 抖音前端风控对无头浏览器的拦截程度，是否需 CDP attach 用户真实 Chrome 兜底；③ 若选 API 逆向路线，逆向 web 发布接口的签名机制可行性与维护成本。视频生成仍走火山/即梦（小云雀）上游（server video-relay 统购，D12），与发布是两个独立环节

## 十一、当前状态

- 2026-06-27/28 完成规划与技术评估，计划落盘
- 2026-07-03 启动实施：
  - **Phase 0 完成**：relay 仓骨架（独立仓 `git-server:repos/wiseflow-relay.git`）+ client 仓骨架（父仓 `product-split/client` 分支，Dockerfile/entrypoint/config/ 部署骨架就位）
  - **Phase 1 完成**（relay 侧）：auth 网关（签发/吊销/限流，16 测试）+ tx-relay 鉴权收敛到 OFB_KEY
  - **Phase 2 完成**（sign）：relay services/sign 实现 xhs(headers/proxy, GET+POST) + douyin(a_bogus，子进程隔离 vendor) + 6 测试 + smoke；client 侧 5 个调用点（viral-chaser/xhs-content-ops/xhs-publish/published-track）全部改走 relay，vendor/douyin.js 删并移至 relay
  - **Phase 4.5 spike 完成**：camoufox 两项验证通过，见 `docs/camoufox-spike-2026-07.md`
  - **awada-server 迁入**（Phase 4 部分）：整体迁入 relay/services/awada-server（99 文件），HTTP/WS 网关待 Phase 4
- 2026-07-04 client 仓完成主体改版（详见 `CHANGELOG.md` v5.5.3 Unreleased + `DEVPLAN.md`）：
  - **client 仓独立成仓**：`wiseflow`（远程 `bigbrother666sh/wiseflow.git`），发布仓 `TeamWiseFlow/xiaobei.git`
  - **D8 + D15 + awada 拍平 + D19 权限放开**（内 crew T3 full / sales-cs T0）
  - **Phase 4.5 全部完成**：login-manager 重写（25 单测）+ browser-guide §0 camoufox 主推 + 4 浏览器类 skill 收敛 + Dockerfile 指纹模板 bake
  - **Phase 4.6 骨架完成**（spike 待真机）：wx-mp-engagement skill + published-track 集成 + login-manager 加 `wx-mp` 平台
  - **Phase 5 完成**：siliconflow-img-gen → 火山方舟 Seedream 4.0（D13 客户端 key），28 单测全过
  - **Phase 8.1 / 8.2 完成**：it-engineer MEMORY 注入产品拆分后运维知识 + D20③ 依赖安装规范
  - **video relay 模式撤回**（2026-07-04 用户确认）：video-product / siliconflow-video-gen / html-video 维持本地凭据
  - **Phase 7 续·身份文件合写暂缓**（用户口头"先放一放"）
- **未动**：Phase 3（relay 侧 publish-relay/video-relay；video 撤回后仅 bilibili-publish 待拍板）/ Phase 4（awada HTTP transport + extension adapter 仍依赖 relay 端点）/ Phase 4.6 spike 待真机 / Phase 6（Dockerfile 阶段 3-4 填实 + entrypoint）/ Phase 8.3 端到端走查
- **部署路径修订（2026-07-04 中段）**：完成改版后**先源码部署本机**（不走 Docker；拉新仓代码 + copy openclaw + apply skill 替换 + 重启 Gateway），验证通过后再做 Phase 6 Dockerfile
- 阻塞项：配额计数上报待 BD 计费模型；抖音发布 spike 待有账号环境做；bilibili-publish 路线待拍板；relay Phase 3/4 端点（client Phase 3/4 直接挂起）

## 十二、抖音发布完整流程（H5 场景）

**背景**：抖音开放平台发布能力申请被驳回，要求公司主体注册资本 > 50 万且注册满 1 年，我方均不满足。故放弃官方 API 路线，改走浏览器模拟 / API 逆向，同 xhs、微信视频号一个路子。不再需要 `h5.share`/`aweme.share`/`open.get.ticket` 三个 scope，不再需要 schema 跳转、H5 中转页、公开 CDN。

**两条候选路线**（Phase 3 前定）：

1. **浏览器模拟（主推）**：D18 camoufox-cli 无头 / CDP attach 用户已登录抖音的 Chrome → 直接在抖音发布页上传发布。纯客户端操作，不经过 server。免 scope/签名/schema/H5/云存储（浏览器直接传本地视频文件）。代价：依赖用户抖音登录态（cookie 中央存储已有）、受抖音前端改版影响、速度较慢。
2. **API 逆向（备选）**：逆向抖音 web 发布接口，server 签名+代请求+返回解析结果，同 xhs sign 服务模式。代价：逆向维护成本、风控风险。

**用户侧闭环**（浏览器模拟路线，用户在微信里跟 Agent 对话）：

```
用户(微信)："帮我发个抖音视频，内容是 XXX"
        │
        ▼
Agent ──► server POST /video/generate (OFB_KEY)
        │   server 持统购上游 key 调 火山/即梦(小云雀) 生成视频
        │   返回 {task_id}
        ▼
Agent 轮询 GET /video/task/:id → 拿到 videoUrl（本地/临时 URL 即可，无需公开 CDN）
        │
        ▼
Agent 调 camoufox-cli / CDP attach 用户已登录抖音的 Chrome
        │   下载视频到本地 → 抖音发布页上传 → 填标题/话题 → 点发布
        ▼
Agent 回填发布结果到对话
```

**关键边界**：
- **视频生成**（火山/即梦上游，server 统购 key）与**抖音发布**（浏览器模拟 / API 逆向）是**两个独立环节**。抖音开放平台不提供视频生成 API。
- 浏览器模拟路线**不需要云存储**（视频本地传），省掉一块基础设施成本 + 运维——这是相比原 API 路线的最大收益。
- API 逆向路线若采用，则抖音发布进 server sign 服务（同 xhs），客户端只调 relay。
- xhs/bilibili 仍按 D1 全 proxy 不变。

---

关联前序调研：独立产品打包可行性（Docker 自部署方案已在此计划落地）。
