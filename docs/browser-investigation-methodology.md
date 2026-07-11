# OpenClaw Extension 调查方法论

> 2026-07-11 落盘。从 `browser-extension-replacement-research.md` 提炼的可复用调研框架，便于日后对 openclaw 其他 extension（telegram / canvas / nodes …）或大规模替换做同类调查。

## 0. 适用场景

- 要替换/改造一个 openclaw extension，但不清楚接口面、依赖耦合、测试范围
- 要判断"整体替换"vs"旁路新增"vs"patch 微改"哪种路线代价最小
- 要确认某层是否硬编码某协议/后端（决定单线 vs 双线）

## 1. 调研 7 步（按序，每步产出清单）

### 1.1 extension 接口契约
- 读 `openclaw.plugin.json`（`contracts.tools` / `activation` / `commandAliases`）+ `plugin-registration.ts` + `register.runtime.ts`
- grep core 侧调用点：`grep -rn "extensions/<ext>" openclaw/src/`
- 产出：extension 暴露给 core 的接口面清单 + core 调用点清单

### 1.2 tool 名注册 + system-prompt 摘要
- 找 extension 向 agent 注册的 tool 名（`contracts.tools` 值 + `definePluginEntry` 的 tool 定义）
- 找 system-prompt 里 tool 摘要生成点（grep `buildAgentSystemPrompt` / tool description）
- 产出：tool 名 + 摘要注入点（决定改名是否波及 system-prompt）

### 1.3 依赖耦合（协议/后端是否硬编码）
- grep `interface Backend|interface Driver|type .*Backend|abstract` 在 extension src/ —— 判断有无可插拔 seam
- grep 每个路由 handler 的后端 switch（如 `if (usesChromeMcp) ... else ...`）—— 看是否逐个重复二元/三元 switch
- 找上一层 enum（如 `BROWSER_TARGETS`）—— target/dispatch 层是否有干净 seam
- 产出：**后端是否硬编码** + **干净 seam 在哪一层**（决定单线 vs 双线、塞进 routes 还是走旁路）

### 1.4 profile / session 管理
- 读 profile 管理模块（如 `browser-profiles.ts`）+ profile 目录布局
- 对比替换方案的 session 模型（如 camoufox-cli 的 `~/.camoufox-cli/profiles/<session>`）
- 产出：profile 统一方案（落 `~/.openclaw/logins/` 还是别处）+ 持久 vs 临时分流

### 1.5 doctor / maintenance
- 读 `*-doctor.ts` / `*-maintenance.ts` 的健康检查 + 清理职责
- 对比替换方案侧的对应能力（daemon 超时 / profile 体积回收）
- 产出：doctor 职责迁移清单 + profile 回收策略（只清临时、持久 doctor 手动）

### 1.6 setup-api / 安装期动作
- 读 `setup-api.ts` 的安装期动作（二进制下载、系统依赖）
- 产出：安装期动作接入点（`apply-addons.sh` / `install.sh` / Dockerfile）+ 幂等性守卫

### 1.7 测试面
- 列测试文件（`*.test.ts` / `*.e2e.test.ts` / `index.test.ts`）
- 产出：测试替换范围（哪些测目标代码随替换消失、哪些保留）

## 2. 代码证据模式（结论必须挂行号）

- 每个结论 cite `file:line`，如 `agent.act.ts:733` 的 `if (usesChromeMcp)` switch
- 判断"无抽象 seam"用 grep 零结果 + 路由 handler 逐个重复 switch 佐证
- 判断"有干净 seam"指出 enum 定义行 + 旁路分支先例（如 sandbox 分支不进 routes/）

## 3. 风险评估（R 表）

每条风险标：
- 评级：CRITICAL / HIGH / MEDIUM / LOW
- 触发条件 + 后果
- 缓解方案
- 转向后是否消解/降级/保留

## 4. 路线决策树

调研完 1.3 后即可定路线：
- **后端硬编码 + 上层有干净 seam** → 双线（新后端走旁路 + 旧后端保留 fallback）。本次 browser 转向即此。
- **后端硬编码 + 上层无 seam** → 整体替换 extension（代价大，~50 handler）。
- **有可插拔 backend 接口** → 单线（实现新 backend 注入），最干净。
- **只需微调行为** → patch，不替换。

## 5. 产出文档结构

```
docs/<ext>-replacement-research.md
├─ §0 调研范围 + 事实校正
├─ §1-7 七步调研结论（每步含 file:line 证据）
├─ §8 风险 R1-Rn
├─ §9 给 spec 的修订清单
├─ §10 下一步建议
└─ §12 架构转向（用户拍板后追加，优先级高于 §0-§11）
```

## 6. 约束

- **调研结论出来前不动 extension 代码**（spec §2.1 约束）
- 遵循记忆铁律 `50-code-repo-only-no-touch-local-instance`：只改代码仓，不碰本地部署实例（`~/.openclaw/` 只读）
- 调研产出是文档（docs/），不是代码改动
