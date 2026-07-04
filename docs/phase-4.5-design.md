# Phase 4.5 — camoufox-cli 集成设计骨架

> 2026-07-04 起，状态：设计阶段，4 子任务骨架未定稿。Spike 已过（见 [camoufox-spike-2026-07.md](./camoufox-spike-2026-07.md)），技术风险降级，本阶段可直接进入实现。
>
> **本轮开发约束**（见 [[30-client-dev-session-2026-07-04]]）：本机实例不动；openclaw 源码读 `~/wiseflow-pro/openclaw/`；阶段完成统一部署。

## 总目标

把 openclaw 内置 `browser` tool + CDP WebSocket 抽 cookie 的旧路径，替换为 camoufox-cli 主推路径。保留 patchright override + patch 005/006 作为 fallback（CDP attach 用户本机 Chrome）。

## 子任务地图

### 4.5.2 login-manager 重写 — 核心枢纽

**当前**：依赖 CDP WebSocket 抽 cookie（`export-cookies.sh <wsUrl> <domain> <platform>`），需要用户介入的 browser tool 操作。

**目标**：用 camoufox-cli 替 CDP 抽 cookie 流程，登录态管理闭环。

**接口契约（保持兼容 + 新增）**：

```
login-manager.sh check <platform>            # 维持（探活）
login-manager.sh read  <platform>            # 维持（读中央存储 JSON）
login-manager.sh write <platform>            # 维持（写中央存储，从 stdin 读 JSON）
login-manager.sh status-all                  # 维持（批量探活）

# 新增：camoufox 会话管理
login-manager.sh qr-headless <platform> [url]   # 启 headless 会话 + 截图 QR + 输出文件路径
login-manager.sh qr-confirm <platform>          # 轮询 QR 扫码状态，成功 → cookies export 落盘
login-manager.sh cookie-export <platform> <session> # 手动 export（从已登录 camoufox session 落中央存储）
login-manager.sh cookie-import <platform> <session> # 手动 import（中央存储 → 新 camoufox session）
login-manager.sh session-cleanup <platform>     # 关闭该平台对应的 camoufox session
```

**中央存储路径**：维持 `~/.openclaw/logins/{platform}.json`，camoufox-cli 原生 JSON 格式（= Playwright `add_cookies` 期望格式）。

**camoufox 会话命名**：`~/.camoufox-cli/profiles/{platform}-{purpose}-{nonce}/`，如 `xhs-browse-login`、`xhs-browse-agent-abc123`。

**核心约束**：
- 每 agent 一 session（独立 daemon + 独立 profile dir + 独立 cookie state）— spike 已验证
- 不 bake chromium（D18），只 bake Firefox
- 不 fork camoufox-cli（D18）
- 保留 patchright fallback（patch 005/006）— 用户 Chrome attach 路径

**验收**：xhs-browse 登录走 camoufox 跑通；cookie 入中央存储；下游 HTTP skill 复用 cookie 成功。

### 4.5.3 browser-guide 改写 — 入口约定

**当前**：openclaw 内置 browser tool 最佳实践（登录 / CAPTCHA / lazy-load / 表达式约束 / 付费墙）。

**目标**：加 camoufox-cli 调用模式，作为主推；保留 browser tool 最佳实践作为 fallback 章节。

**新增章节**：
1. **camoufox-cli 登录流程（主推）**：qr-headless → 用户扫码 → qr-confirm → cookie-export
2. **camoufox-cli 取数 / 抓取**：临时 session + cookies import + eval/snapshot
3. **session 隔离与并发**：每 agent 一 session，禁止跨 session 共享 profile
4. **fallback（patchright + CDP attach）**：保留原 browser tool 章节

### 4.5.4 浏览器类 skill 改调用模式 — 收敛

**目标**：dev plan 列出 xhs-interact / content-calibrator / viral-chaser / xhs-content-ops 等，本轮统一收敛调用模式。

**改写范围**：
- `crews/main/skills/xhs-interact/SKILL.md`（仅 SKILL.md，无 scripts）
- `crews/main/skills/viral-chaser/SKILL.md` + `scripts/`（已有，需补充 camoufox 模式）
- `crews/main/skills/content-calibrator/SKILL.md` + `scripts/`（同上）
- `crews/main/skills/xhs-content-ops/SKILL.md` + `scripts/`（已搬入，需补 camoufox 模式）

**统一模式**：
1. 先调 `login-manager.sh check <platform>` 拿 cookie + UA
2. HTTP 取数（requests/httpx）走中央存储 JSON，薄适配 3 行
3. 必须用 browser 时：`login-manager.sh cookie-import <platform> <session>` → `camoufox-cli --session <session> --persistent ...` → close

**不动 scripts 实现**：本轮只改 SKILL.md 指引；scripts 内部细节（如 fetch_note_content.ts 用 patchright 还是 raw HTTP）由各 skill owner 自己后续迁移。

### 4.5.5 指纹模板 bake — 镜像构建期

**当前 Dockerfile**（wiseflow-layer 阶段）：
```dockerfile
# TODO(Phase 4.5): 生成 camoufox 冻结指纹模板
#   RUN camoufox-cli --session _template --persistent open about:blank && \
#       camoufox-cli --session _template close && \
#       cp -r ~/.camoufox-cli/profiles/_template /root/.openclaw/logins/_template
```

**目标**：把 TODO 转成真活儿。

**bootstrap 流程**（spike §"D18 落地方式" 已验证）：
1. 清空 `~/.camoufox-cli/profiles/_template/`（避免污染）
2. `camoufox-cli --session _template --persistent --json open about:blank` → 生成冻结 `camoufox-cli.json`
3. `camoufox-cli --session _template close` → 关闭
4. `cp -r ~/.camoufox-cli/profiles/_template /root/.openclaw/logins/_template` → 落到运行态

**运行时使用**（各 agent session）：
1. `mkdir ~/.camoufox-cli/profiles/<session>` → 独立 profile dir
2. `cp /root/.openclaw/logins/_template/camoufox-cli.json ~/.camoufox-cli/profiles/<session>/` → 套用冻结指纹
3. `camoufox-cli --session <session> --persistent ...` → 启动

**注意**：Firefox rv 版本跟 camoufox 二进制版本，**不是指纹维度**——不要在 bake 时锁 rv。

## D18 约束清单（实施期 review 项）

- [ ] 不 fork camoufox-cli（spike 已证无需）
- [ ] 不 bake chromium
- [ ] 保留 patchright override + patch 005/006
- [ ] 每 agent 一 session（独立 daemon + 独立 profile dir + 独立 cookie state）
- [ ] 指纹模板通过 cp camoufox-cli.json 复用，不在运行时重生成
- [ ] 中央存储维持 `~/.openclaw/logins/{platform}.json`，camoufox-cli 原生 JSON 格式
- [ ] login-manager 保留 check/read/write/status-all CLI 接口兼容

## 阶段验收

- [ ] xhs-browse 登录走 camoufox 跑通（集成测试，本轮跳过，等统一部署后）
- [ ] cookie 入中央存储
- [ ] 下游 HTTP skill 复用 cookie 成功（published-track 单元测试覆盖 cookie 加载路径）
- [ ] browser-guide 文档明确 camoufox-cli 主推 + browser tool fallback
- [ ] 浏览器类 skill SKILL.md 收敛到统一模式

## 与本轮其他阶段的关系

- **Phase 4.6（公众号 engagement）**：方案 A 依赖 camoufox-cli 跑后台（4.5.2 落地后即可启）
- **Phase 6（Dockerfile 阶段 3-4）**：4.5.5 是 Phase 6 的一部分，会在 Dockerfile 阶段填实时一并落地
- **D20 skill 依赖**：login-manager 重写后，camoufox-cli 已通过 Dockerfile 阶段 1 全局安装，无需 D20 处理
- **D21 软链化**：4.5.x 改完后，本地实例部署时通过 D21 软链到本仓，即时生效

## 实施顺序（推荐）

1. 4.5.1（本 doc）— ✅
2. 4.5.2 login-manager 重写（核心，先做）
3. 4.5.3 browser-guide 改写（依赖 4.5.2 接口定）
4. 4.5.4 浏览器类 skill 收敛（依赖 4.5.3 文档模板）
5. 4.5.5 指纹模板 bake（独立，可在 4.5.2 完成后并行）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| camoufox-cli 版本升级导致命令格式变 | 锁版本（Dockerfile 阶段 1 锁 `camoufox-cli@0.6.2`）；spike 报告中命令是稳定的 |
| login-manager 重写影响下游 skill（viral-chaser / xhs-publish 等）| CLI 接口保持兼容（check/read/write/status-all 不变）；新增子命令 |
| 单元测试无法覆盖真实 camoufox-cli 行为 | mock camoufox-cli；集成测试等统一部署后做 |
| Docker 镜像内 camoufox-cli 需要 Xvfb 等依赖 | Dockerfile 阶段 1 已 `camoufox-cli install --with-deps`（含 Xvfb），无需额外 |

---

关联：[camoufox-spike-2026-07.md](./camoufox-spike-2026-07.md) · [[30-client-dev-session-2026-07-04]] · DEVPLAN.md Phase 4.5