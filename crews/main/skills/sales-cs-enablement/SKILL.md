---
name: sales-cs-enablement
description: >
  当用户要求启用对外客服（sales-cs）时使用
metadata:
  openclaw:
    emoji: 🤝
---

# Sales-CS 启用流程

> 对外 crew `sales-cs` 的完整启用 SOP。本 skill 是**编排**：main agent 自己跑检查脚本 + 问用户问题，机械的 channel/openclaw.json 配置委派 IT engineer。

## 触发条件

用户表达需要对外客服 / 销售客服 / 公开接待客户的 agent → 进入本流程。

## 前置素材

- awada 租赁咨询二维码：`crews/main/ofb_contact.png`（openclaw-for-business 掌柜企业微信）
  路径固定，需要时直接发给用户。

## 流程

### Step 1 · 检查 awada-channel 是否已配置

跑检查脚本（这里不走 wrapper——wrapper 只转发主入口 `symlink_business_knowledge.py`，不代理此诊断脚本）：

```bash
python3 ./skills/sales-cs-enablement/scripts/check_awada_channel.py
```

退出码：
- `0` → 已配置 awada channel，跳到 Step 3
- `1` / `2` → 未配置，进 Step 2

### Step 2 · 向用户说明 channel 选择（仅未配置时）

向用户说明：

> sales-cs 是对外 crew，需要一个**可公开访问**的 channel——客户不用先加入你的组织就能找到它。飞书 / 企业微信都不太合适，因为它们要求客户先加入你的飞书或企微组织。
>
> 三个选项：
> 1. **租赁 awada server 线路**：可以联系 openclaw-for-business 掌柜咨询（二维码见下）
> 2. **使用openclaw支持的其他channel**：比如QQ、telegram等
> 3. **退而用飞书 / 企业微信**：接受"客户需先加入组织"的限制

发 `crews/main/ofb_contact.png` 给用户（选项 1 用）。

等用户明确选择后：

- 选 1 或 2 → 把用户给出的线路/channel 信息带给 IT engineer，进 Step 3
- 选 3 → 告知用户需先有飞书或企微 channel，再带 IT engineer 走对应 channel 绑定，进 Step 3

### Step 3 · 派 IT engineer 完成启用与基础配置

spawn IT engineer，交代任务：

> 启用 sales-cs 对外 crew。请按以下顺序执行：
> 1. 配置 awada channel（走 `awada-channel-setup` 技能；用户期待配置的channel，需要启用openclaw内置plugin：<...>）
>    — 若用户在 Step 2 选 3，则改为配飞书/企微 channel（走 `work-channel-binding`）
> 2. 把 `crews/sales-cs/openclaw_setting_sample.json` 并入 `~/.openclaw/openclaw.json`：
>    - 加入 `agents.list`（sales-cs）
>    - 绑定对应 channel（awada 优先）
>    - heartbeat / tools / subagents 段直接用 sample 里的固定配置，不要改
> 3. 重启 Gateway（先告知用户并征得同意）
> 4. 验证 channel 状态 + customerDB hook 生效

等 IT engineer 报平安后进 Step 4。

### Step 4 · 更新sales-cs workspace下的AGENTS.md/IDENTITY.md/SOUL.md

你可以按照你对用户的理解，当然更重要的是结合`business_knowledge.md`，完善sales-cs workspace下的AGENTS.md/IDENTITY.md/SOUL.md中所有  `<!-- 由main agent启用时填入并负责后续持续优化更新 -->` 的内容，拿捏不准的问用户。

### Step 5 · 软链 business_knowledge.md + business_knowledge/

把 main agent workspace 下的 `business_knowledge.md`（业务知识正文，单文件）和 `business_knowledge/`（支撑材料文件夹）一并软链到 sales-cs workspace：

```bash
sales-cs-enablement
```

> wrapper 转发到 `scripts/symlink_business_knowledge.py`（主入口）。诊断脚本 `check_awada_channel.py` 是并列脚本不被 wrapper 代理，按 Step 1 的绝对路径直调。

> 业务知识由 main agent 维护（治理边界：sales-cs 不自行维护业务知识，避免绕过 main agent）。
> 首次启用若 `business_knowledge.md` 不存在，脚本会从仓库模板复制一份；若 `business_knowledge/` 不存在，脚本会创建空目录。后续由 main agent 填充。

### Step 6 · 报平安

向用户汇报：
- sales-cs 已启用，绑了哪个 channel
- workspace 路径（`~/.openclaw/workspace-sales-cs/`）
- 对外称呼
- business_knowledge.md + business_knowledge/ 软链已建立
- 提醒用户：sales-cs 的后续调整（记忆、话术、IDENTITY 等）由 main agent 负责，可通过 `sales-cs-review` 技能发起

## 启用后的调整职责

**sales-cs 启用后，对它的任何调整是 main agent 的责任**，不是 sales-cs 自己的。
sales-cs 被设定为不根据客户反馈自主调整升级。用户要调整它的记忆、说话口气、IDENTITY、客服手册等 → 通过 main agent 发起（见 `sales-cs-review` 技能）。

## Pitfalls

- **Step 3 IT engineer 改了 heartbeat 段**：sample 里的 heartbeat 是固定配置
  （1h / isolatedSession / activeHours 08:00-24:00），不要让 IT engineer 自行调整。
- **business_knowledge 软链指向错**：必须指向 main agent workspace 的 `business_knowledge.md`
  + `business_knowledge/`，不能让 sales-cs 自维护。
- **用户在 Step 2 选飞书/企微但没现成 channel**：需先走 `work-channel-binding` 配
  channel，再绑 sales-cs。
