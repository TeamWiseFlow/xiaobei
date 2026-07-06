---
name: sales-cs-review
description: >
  当用户想复盘或升级已启用的 sales-cs 时使用。扫描 sales-cs 的 feedback/ 聚合客户
  反馈，结合用户意见提出升级建议（调整 MEMORY 客服手册 / 话术 / IDENTITY 称呼 /
  DECLARED_SKILLS 等），确认后由 main agent 直接改 sales-cs workspace 文件。
  sales-cs 是对外 crew，不自行升级，所有调整经本技能由 main agent 落地。
metadata:
  openclaw:
    emoji: 🛠️
---

# Sales-CS 复盘与升级

> 参考 `~/wiseflow-pro/crews/hrbp` 的 feedback-review / modify 模式，但**没有 hrbp
> crew**——main agent 直接兼任 sales-cs 的治理者。本技能是编排 + 直接落地，不 spawn
> 其他 crew。

## 触发条件

- 用户说"复盘下 sales-cs"/"看看客服最近怎么样"/"调整下客服话术"等
- 用户要求改 sales-cs 的记忆、说话口气、IDENTITY、客服手册、可用技能
- main agent 自己定期想检查 sales-cs 反馈

## 前置条件

- sales-cs 已启用（`~/.openclaw/workspace-sales-cs/` 存在）。未启用 → 提示用户先走
  `sales-cs-enablement`。

## 流程

### Step 1 · 扫描反馈

```bash
python3 /<workspace 绝对路径>/crews/main/skills/sales-cs-review/scripts/scan_feedback.py
# 或限定时间窗：
python3 /<workspace 绝对路径>/crews/main/skills/sales-cs-review/scripts/scan_feedback.py --since 2026-06-01
```

输出 JSON：反馈条目数、按文件分布、高频关键词（投诉/退款/价格/试用/开票/人工…）。

### Step 2 · 结合用户意见生成升级建议

读反馈摘要 + 用户本轮诉求，提出具体建议（**不直接动手**，先呈现给用户确认）：

- **客服手册（MEMORY.md）**：补/改 FAQ、价格政策、开票流程
- **话术（AGENTS.md 意图分流段）**：调整 3.1-3.6 各场景应对策略
- **IDENTITY 称呼**：改对外自我称呼
- **DECLARED_SKILLS**：增减 sales-cs 可用技能（如加 `order-cli` 查订单）
- **SOUL.md**：调整语气/边界（少见，谨慎）

呈现形式：

```
建议改动：
1. MEMORY.md「常见问题 FAQ」补一条：退款流程 → 引导填反馈问卷
2. AGENTS.md 3.1 话术：把"先讲适合解决什么问题"改为"先问客户场景再匹配"
3. IDENTITY 称呼：小明助手 → 小贝同学
确认后我直接改 sales-cs workspace。
```

### Step 3 · 用户确认后落地

用户确认后，main agent **直接编辑** `~/.openclaw/workspace-sales-cs/` 下的对应文件：

- `MEMORY.md` / `AGENTS.md` / `IDENTITY.md` / `SOUL.md` / `DECLARED_SKILLS`
- 改完报平安：列出改了哪些文件、改了什么
- **不需要 spawn IT engineer**（这些是 workspace 文档，不是 openclaw.json / channel 配置）
- 若涉及 channel / openclaw.json / schema 变更 → 才 spawn IT engineer

### Step 4 ·（可选）重启 sales-cs

文档改动一般无需重启。仅当改了 `DECLARED_SKILLS` / `SOUL.md` 影响运行时行为时，
spawn IT engineer 重启 Gateway（先告知用户并征得同意）。

## 调整边界

- **可改**：sales-cs workspace 下所有 .md / DECLARED_SKILLS / 业务知识
- **慎改**：SOUL.md（角色边界）、openclaw_setting_sample.json 的 heartbeat 段（固定配置）
- **不改**：sales-cs 的 feedback/ 历史记录（只读，用于复盘）
- **schema 变更**：customer-db schema 改动走 IT engineer，不在此技能直接动

## 与 sales-cs-enablement 的衔接

- 首次启用 → `sales-cs-enablement`
- 启用后任何调整 → 本技能（`sales-cs-review`）

## Pitfalls

- **没确认就改**：必须先呈现建议给用户确认，再落地。sales-cs 面对外部客户，误改话术
  影响真实对话。
- **改了 openclaw.json 没重启**：binding / agents.list 改动需重启 Gateway 才生效——
  但本技能一般不动 openclaw.json，动的话交给 IT engineer。
- **业务知识双写**：business_knowledge 是软链到 main workspace 的，改业务知识在 main
  workspace 改，不要在 sales-cs workspace 改软链目标。
