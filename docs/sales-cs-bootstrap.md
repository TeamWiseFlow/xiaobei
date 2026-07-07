# sales-cs 启用指南（Phase 7 续·sales-cs sample + 软链）

> 2026-07-04 状态确认。dev plan §Phase 7 续 写"默认 seed 不在 openclaw.json；绑 awada；启用由 IT engineer 操作改 enabled: true + 软链 business_knowledge/；自有技能同现仓（已搬入）"——本任务在产品拆分后**全部到位**。

## 当前状态（已就位）

| 检查项 | 现状 |
|--------|------|
| `crews/sales-cs/` 目录 | ✅ 存在 |
| 5 个自有 skill（customer-db / demo-send / exp-invite / payment-send / proactive-send）| ✅ 都已搬入 |
| 标准 workspace 文件（AGENTS / SOUL / IDENTITY / HEARTBEAT / ALLOWED_COMMANDS / DECLARED_SKILLS）| ✅ 都已就位 |
| `openclaw_setting_sample.json`（sales-cs 模板）| ✅ 存在 |
| 默认 seed 在 `config-templates/openclaw.json` | ❌ **不在**（符合 dev plan：默认 seed 关闭） |
| 启用流程 | ✅ SOP 在 `crews/it-engineer/MEMORY.md` §"sales-cs 启用 SOP"（5 步：装依赖 → 注入 → 软链 → 重启 → 验证）|

## 启用流程（用户请求启用 sales-cs 时）

> **不要** main agent 直接编辑 `openclaw.json` —— 通过 it-engineer sub-agent 执行（运维职责分离）。

### 1. 用户 / main 确认

- 询问用户："你确定要启用 sales-cs 吗？启用后 sales-cs 通道（awada）会一直在线"
- 确认 awada 已就绪（无 awada → 先做 awada 启用）
- 确认 HRBP 业务知识库已就位（无 → 让 HRBP 创建后再来）

### 2. spawn IT engineer 执行启用 SOP

参考 `crews/it-engineer/MEMORY.md` §"sales-cs 启用 SOP（Phase 7 续新增）" 5 步流程：

```
Step 1 · 装依赖（确认 workspace-sales-cs/ 完整）
Step 2 · openclaw.json 注入（合并 sample 到 agents.list）
Step 3 · business_knowledge/ 软链（HRBP 源目录 → workspace-sales-cs/）
Step 4 · 重启 Gateway（systemctl --user restart openclaw-gateway.service）
Step 5 · 验证（agent 加载 / awada ping / 微信扫码 / 测试消息）
```

详见 `crews/it-engineer/MEMORY.md`。

### 3. 用户端配合

- 微信扫码绑定 awada 通道（main 引导）
- 发测试消息确认 sales-cs 应答
- 给 sales-cs 设置首次业务知识 / 行业话术

## 停用流程

反向操作：
- 从 `agents.list` 移除 `sales-cs` entry
- workspace 保留（数据不丢）
- awada 通道保留（如果其他 crew 不需要 → 单独关停 awada）

## 自有技能清单（5 个）

| Skill | 用途 |
|-------|------|
| `customer-db` | 客户档案 / 历史 |
| `demo-send` | Demo / 样例材料 |
| `exp-invite` | 体验邀请 / 免费试用 |
| `payment-send` | 收款 / 报价 |
| `proactive-send` | 主动外联 |

每个 skill 都有 ALLOWED_COMMANDS 精确放行（T0 prompt injection 防线）。

## 凭据边界

- **awada 通道**（agent ↔ 外部用户）：走 awada Extension（D8 拍平后单层结构 `awada/`），Redis 直连 awada Server
- **AppID/AppSecret**（如果有）：由 sales-cs 自己的凭据管理（**不**在 main 仓）
- **本 skill 内不持任何 platform 凭据**（与 main 其他 skill 一致；D1 全 proxy 决策）

## Notes

- sales-cs 是**对外** crew（T0），有严格的 ALLOWED_COMMANDS 白名单（**不**走 D19 内 crew T3 full）
- 启用需要用户明确确认（一开就有人来聊天，**不是**轻量决策）
- sales-cs 的 business_knowledge 软链**必须**连到 HRBP workspace（不能让 sales-cs 自己维护业务知识库——会绕过 HRBP 治理）
