# config/ — wiseflow-client 运行态配置（Docker 专用辅助文件）

> **openclaw.json 已单源化**：Docker 与源码部署均从 `config-templates/openclaw.json` 派生
> （Dockerfile 阶段 3 直接 COPY 该文件）。本目录不再放 `openclaw.json`，避免双份漂移。
> 源码部署由 `setup-crew.sh §4` 在模板基础上合并 skills 过滤 / 路径规范化；
> Docker 不跑 setup-crew.sh，直接用模板（content-producer 已在模板 agents.list 预注册）。

build 期由 Dockerfile 阶段 3（wiseflow-layer）把 `config-templates/openclaw.json` 放到
`/root/.openclaw/openclaw.json`，`daemon.env.template` 由 entrypoint 渲染成
`/root/.openclaw/daemon.env`，`workspace-skeleton/` 复制到各 crew workspace。

## 文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `daemon.env.template` | daemon 环境变量模板，entrypoint 渲染 | ✅ 占位就位（AWK_API_KEY / OFB_KEY / RELAY_BASE_URL / SMTP_*） |
| `workspace-skeleton/` | 通用 workspace 骨架 | ✅ 结构就位，运行期内容不进镜像 |

## openclaw.json 目标态（Phase 7）

`config-templates/openclaw.json` 是现仓的全量配置，Docker 与源码部署共用。Phase 7 改成 client 目标：

- **crew list**：`main`（DEFAULT，绑 openclaw-weixin）+ `it-engineer` + `content-producer`；`sales-cs` 默认 seed 但**不在 list**（D10，启用由 IT engineer 操作）
- **addons**：删 `officials` / `official-plus`（D8 扁平化后无 addon 结构）；保留 `openclaw-weixin`
- **awada**：`enabled: false`（D10）
- **models**：保留 awk provider（用户 AWK_API_KEY）；视频生成模型走 relay（不直配上游 key，D12）
- **browser**：`headless=true`（D18 camoufox 主力无头省资源，这是浏览器栈转向的主因）；需手动登录/过风控（滑块等）的平台由 login-manager 指导显式 `camoufox-cli --headed`（走直接 exec，不经 browser tool，不受此全局开关约束）；patchright 已整体去掉（补充 C），线 2 fallback（host existing-session 真机 Chrome / node remote-cdp）走原版 playwright-core，不预设，按需启用

## relay 端点注入

entrypoint 把 `RELAY_BASE_URL` 派生成各子端点写入 skill 配置（见 `daemon.env.template` 注释）。用户只需配 `AWK_API_KEY` + `OFB_KEY`，relay 端点固定。
