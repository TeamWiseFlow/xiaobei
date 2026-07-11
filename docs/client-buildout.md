# wiseflow-client buildout

> 本仓为wiseflow-pro拆分后的 **wiseflow-client（Docker 部署态）** 代码仓，将作为 Teamwiseflow/xiaobei 开源项目。
> 本文记录 client 侧 buildout 状态与待办。当前活跃规划见 [`browser-stack-replacement-spec-2026-07.md`](browser-stack-replacement-spec-2026-07.md)（浏览器栈转向）；产品拆分决策已落地，历史规划可从 git 历史恢复。
>
> 中转服务（relay）已拆为独立仓 `git-server:repos/wiseflow-relay.git`，交接文档在其仓内 `docs/HANDOVER.md`。

## 产品定位

专为 OPC / 中小微企业老板量身打造的 **"AI 搞钱搭子"**，中文名 **「小贝」**。四个 crew：**main**（原 self-media-operator 整合 IR + BD 能力，default，对外对接用户）/ **content-producer**（原 video-producer 整合 designer 能力，内容制作）/ **it-engineer**（运维 sub-agent）/ **sales-cs**（对外客服，默认禁用）。

**main 的 SOUL/风格**：理性、高效、尽责的天才少女，带一点点傲娇和毒舌调皮；对用户自称「小贝」。

## 用户使用流程

用户拉镜像 → 配 `AWK_API_KEY` + `OFB_KEY` → `docker run` → entrypoint 弹微信二维码 → 扫码绑定 → 在微信里用 Agent。零 install.sh，零平台凭据，relay 端点固定。

## 当前状态（Phase 7 结构搬运完成，2026-07-03）

分支 `product-split/client`（已 push origin）。在 `product-split/relay-server` 基础上切出（tx-relay 已迁走、relay/ 已 untrack、plan + spike 文档在）。

### 已就位

| 件 | 说明 |
|----|------|
| `Dockerfile` | 4 阶段骨架（plan §六）：workspace-deps / build / wiseflow-layer / runtime。阶段 1-2 基本可构建，3-4 含 TODO |
| `docker-entrypoint.sh` | 入口流程：渲染 daemon.env → 注入 OFB_KEY/relay 端点 → `node openclaw.mjs gateway` → weixin QR。步骤 1/2/4 渲染待 Phase 6 |
| `.dockerignore` | 排除 relay/、docs、node_modules、openclaw/.git 等 |
| `scripts/build-image.sh` | 按 `openclaw.version` 检出引擎 → docker build |
| `config-templates/openclaw.json` | 单源主配置（Docker 与源码部署同源）：default = main + it-engineer + content-producer；sales-cs 不在 list（D5）；binding → main |
| `config/daemon.env.template` | key 占位（AWK_API_KEY / OFB_KEY / RELAY_BASE_URL / SMTP_*） |
| `config/workspace-skeleton/` | credentials/ + business_knowledge/ + logins/ 骨架 |
| `openclaw.version` / `openclaw-weixin.version.json` / `patches/` | 已存在，client 直接用 |
| `awada/` | 已拍平单层（awada/awada-extension → awada/），channel 插件，待 Phase 4 改 HTTP/WS |
| `crews/` | **Phase 7 结构搬运完成**：扁平 4 crew（main / content-producer / sales-cs / it-engineer）+ _template + shared；addons/ 销毁（D8）；main/hrbp/designer/ir/旧selfmedia 删（D15）；10 海外技能删 |
| `skills/` | 公共技能顶层化：smart-search/browser-guide/complex-task/email-ops/council/pitch-deck/rss-reader/xhs-interact/siliconflow-img-gen/login-manager/wx-mp-hunter/wxwork-drive |
| `tests/crew-architecture-regression.sh` | 改写为新结构回归（addons 销毁 / 4 crew / 公共 skill / seed default / awada 拍平），通过 |

### 未动（Phase 7 续 + Phase 6/4.5/5）

- **crew 内容合写**（Phase 7 续）：main 身份文件仍是原 self-media-operator 原样，未合入 AI 搞钱搭子「小贝」定位（SOUL/IDENTITY/MEMORY/HEARTBEAT）；IR 三模式未抽成 business-model-polish/project-application/investor-pipeline 三 skill（源 AGENTS 在 git 历史 `97bad4d^` 可恢复）；business-developer 三能力（lead-hunting/comment-engagement/intel-gathering）已搬入 main/skills 但未写入 AGENTS/HEARTBEAT；content-producer 未合入 designer 能力；it-engineer 未瘦身/强化运维；sales-cs 未做 sample + 软链；shared/ 未内化进 it-engineer。
- **apply-addons.sh 精简**（Phase 6/7 续）：addons 扫描循环（~260 行起）现为死代码，待整体删除；crew 安装已由 setup-crew.sh 单独负责。
- **skill 改 relay 调用**（Phase 2-3）：**sign 已完成**（viral-chaser/xhs-content-ops/xhs-publish/published-track 全部改走 relay services/sign，D1 落地）；publish-relay / video-relay 改造待 Phase 3（relay 侧服务未实现）。
- **awada 改 HTTP/WS transport**（Phase 4 ✅）：awada-server 已迁出至 relay（D4），awada-extension 走 relay 网关 `WS /inbound` + `POST /outbound`（relayBaseUrl+ofbKey+lane），不再直连 Redis；ioredis 已从 deps 移除，预装步骤改装 ws+zod。proactive-send skill 同步迁 HTTP 网关。
- **camoufox 集成**（Phase 4.5）：调研已完成（见 `browser-extension-replacement-research.md` §12），双线转向已定（删 sandbox + fork camoufox-cli 走 `target=camoufox` 旁路 + 保留 host/node fallback），落地顺序见 `browser-stack-replacement-spec-2026-07.md` §11。
- **img-gen 改火山**（Phase 5）：未做。
- **Dockerfile 阶段 3-4 填实**（Phase 6）：wiseflow-layer 组织 / img-gen 编译 / 指纹模板 bake / openclaw-weixin 插件安装 / entrypoint 渲染逻辑。
- **文档收尾**：docs/workspace-bootstrap-files.md 的 skill 表、CHANGELOG 旧条目仍含旧 crew 名，待内容合写时一并更新。

## 与 relay 的边界

- client 不持任何平台凭据，所有 relay 调用带 `X-OFB-Key`。
- relay 端点由 `RELAY_BASE_URL` 派生（见 `config/daemon.env.template`），entrypoint 注入各 skill 配置，**用户无需配**。
- 接口契约见 relay 仓 `docs/API-CONTRACT.md`。改接口先改那边并通知本仓。
- 本仓 `relay/` 目录是本地独立仓（gitignored，父仓不跟踪），仅供本轮开发期参考/同步，移交时删除。

## 后续 Phase 落地顺序（client 侧）

| Phase | 内容 | 依赖 |
|-------|------|------|
| 4.5 | camoufox 集成（browser-guide + login-manager + 浏览器类 skill 改写 + 模板/中央存储） | spike ✅ |
| 5 | img-gen 改火山生图（fetch volcengine 文档确认接口） | — |
| 6 | Dockerfile 阶段 3-4 填实 + entrypoint 渲染 + weixin 二维码 | 4.5, 5, 7 |
| 7 | crew 重构（main 合体 / IR 三模式 / business-developer 三能力 / it-engineer 瘦身 / sales-cs sample + 软链） | — |
| 8 | IT engineer 记忆注入 + 端到端走查 | 6, 7 |

Phase 2-3（sign / publish-relay / video-relay）是 relay 侧工作，不在本仓。

## 远程仓安排

待定。当前 client 工作在父仓 `product-split/client` 分支。是否像 relay 一样拆为独立仓推到 git-server（或 GitHub），等用户定。
