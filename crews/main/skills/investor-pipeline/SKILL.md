---
name: investor-pipeline
description: IR 模式 3 · 投资人发掘与跟进。完整的融资沟通流水线：发掘潜在投资人
  → 准备触达材料 → 发起接触 → 跟踪反馈 → 状态机推进。状态：new→contacted→
  bp_sent→meeting→dd→ts→invested/passed。
metadata:
  openclaw:
    emoji: 🎯
---

# 投资人流水线（IR 模式 3）

> **模式 3 = 投资人发掘与跟进**（本 skill）；模式 1 = `business-model-polish`；模式 2 = `project-application`。

完整的融资沟通流水线：从"找谁"到"投没投"全流程跟踪。

---

## 适用场景

用户说：
- "我想找天使投资人 / VC 聊一聊"
- "帮我找下 X 领域的投资人"
- "我已经联系了一些投资人，要跟进"
- "我刚收到 X 基金约我 meeting"
- "我要做 X 轮融资"

---

## 状态机

```
new → contacted → bp_sent → meeting → dd → ts → invested/passed
                                                ↗
                                          (任意状态可 → passed)
```

| 状态 | 含义 | 触发动作 |
|------|------|----------|
| `new` | 已建档，未联系 | 准备触达材料 |
| `contacted` | 已发出首次接触（邮件 / 暖介绍） | 等回复 / 跟进 |
| `bp_sent` | BP 已发出 | 等投资人消化 / 回复 |
| `meeting` | 已约初次或后续 meeting | 准备 meeting |
| `dd` | Due Diligence 进行中 | 准备数据室 + 配合尽调 |
| `ts` | Term Sheet 谈判中 | 谈条款 |
| `invested` | 已打款 | 完结 |
| `passed` | 拒绝 / 不再跟进 | 完结（保留档案） |

---

## 工作流

### Step 1: 模式 1 / 模式 2 跑通了吗？

> 投资人接触前**先确认**：
> - 模式 1 商业模式已打磨（30 秒电梯版 + 5 问结构化）
> - 模式 1 输出已落 `MEMORY.md`
> - 模式 3 才有"可讲的内容"

如果用户跳过模式 1 直接进模式 3 → **先**跑 `business-model-polish`。

### Step 2: 发掘投资人 → 委派 investor-hunting

```bash
# 调用子 skill
# agent 形式：sessions_spawn 或直接 exec 子 skill 脚本
```

`investor-hunting` 输出去重 + match_score 排序后的投资人列表。Main 把"重点跟进"的人写入 `ir-record`：

```bash
./skills/ir-record/scripts/record-investor.sh \
  --name "张三" --firm "红杉" --type "VC" --focus_areas "AI, SaaS" \
  --match_score "high" --status "new"
```

### Step 3: 准备触达材料 → 委派 investor-materials

对每个 `new` 状态的 investor：
- 用 `investor-materials` 生成 One-Pager / BP
- （同一份 BP 模板可发多个投资人，one-pager 个性化）

### Step 4: 发起接触 → 委派 investor-outreach

```bash
# 用 investor-outreach 写个性化触达邮件
# 邮件发出后 → 状态 new → contacted
./skills/ir-record/scripts/update-status.sh \
  --type investor --id <rowid> --status contacted
```

每次接触记入 `contacts` 表：

```bash
./skills/ir-record/scripts/record-contact.sh \
  --investor-id <id> \
  --contact-type "email" --direction "outbound" \
  --summary "发送初次接触邮件 + BP 附件" \
  --next-step "等 7 天无回复则 follow up"
```

### Step 5: 持续跟进 + 状态推进

每次投资人回复 / 用户 update → 调 `record-contact.sh` + 必要时 `update-status.sh`：

| 用户反馈 | 状态推进 |
|----------|----------|
| 投资人"不感兴趣" | → `passed` |
| 投资人"约 meeting" | → `meeting` |
| 投资人"看 BP" | → `bp_sent`（如果还没） |
| 投资人"进入 DD" | → `dd` |
| 投资人"发 TS" | → `ts` |
| 投资人"打款" | → `invested` |

### Step 6: HEARTBEAT 巡检

心跳任务会查 `query-stale.sh`：7 天无 contact 进展的 investor → 提醒用户。

---

## 与其他 IR skill 的关系

- **`investor-hunting`**（子 skill）：发掘 + 筛选 + 去重
- **`investor-materials`**（子 skill）：BP / One-Pager / 路演材料
- **`investor-outreach`**（子 skill）：触达邮件 / 暖介绍文案
- **`ir-record`**（数据层）：所有投资人档案 / 接触历史 / 状态机
- **`business-model-polish`**（模式 1）：投资人接触前必跑
- **`project-application`**（模式 2）：与模式 3 平行（项目申报 vs 融资）

---

## Pitfalls

### pitfall: 跳过模式 1 直接接触投资人

- **症状**：用户说"我要找投资人"，Agent 直接进模式 3
- **workaround**：**先**跑 `business-model-polish`（30 秒电梯版 + 5 问结构化）

### pitfall: 同一投资人发多份 BP 模板

- **症状**：所有投资人发同一份 BP，不个性化
- **workaround**：One-Pager 个性化（强调与对方基金 focus_areas 的契合）

### pitfall: 状态推进滞后

- **症状**：投资人已回 "约 meeting"，但 `investors.status` 还是 `contacted`
- **workaround**：每次用户反馈 → 立即 `update-status.sh`

### pitfall: 7 天没进展未提醒

- **症状**：投资人不回复，用户忘记跟进
- **workaround**：HEARTBEAT 巡检 `query-stale.sh` → 提醒用户

### pitfall: 把"暖介绍"搞砸

- **症状**：暖介绍邮件里直接放 BP 全文，介绍人尴尬
- **workaround**：暖介绍邮件只放 1 句话 context + 询问是否愿意被介绍

---

## Notes

- **不**直接调 email send tool：先调 `investor-outreach` 出文案，让用户确认后再发
- **不**承诺融资成功率：只保证流程齐整 / 状态准确 / 跟进及时
- **不**接触"明显不匹配"的投资人（如 5 亿 VC 投 50 万种子轮）—— match_score 阶段过滤
- 跨轮次（A 轮 / B 轮）的投资人池完全不同；同一投资人池按轮次隔离
