# Investor Pipeline（融资沟通流水线）

完整的融资沟通流水线：发掘潜在投资人 → 准备触达材料 → 发起接触 → 跟踪反馈 → 状态机推进。

状态机：`new → contacted → bp_sent → meeting → dd → ts → invested/passed`

## 适用场景

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

### Step 1: 商业模式打磨了吗？

> 投资人接触前**先确认**：
> - 商业模式已打磨（30 秒电梯版 + 5 问结构化）
> - 打磨输出已落 `MEMORY.md`
> - 流水线才有"可讲的内容"

如果用户跳过打磨直接进流水线 → **先**与用户一起完成商业模式梳理（基于 `business_knowledge/business_knowledge.md`；多路径权衡用 `council`），结论落 `MEMORY.md` 后再继续。

### Step 2: 发掘投资人 → Investor Hunting Workflow

按 Investor Hunting Workflow 执行搜索、筛选、去重、记录，输出去重 + match_score 排序后的投资人列表。"重点跟进"的投资人写入 `ir-record`：

```bash
ir-record record-investor \
  --name "张三" --firm "红杉" --type "vc" \
  --focus-areas "AI, SaaS" --match-score "high" --status "new"
```

### Step 3: 准备触达材料 → Investor Materials Workflow

对每个 `new` 状态的 investor：
- 按 Investor Materials Workflow 生成 One-Pager / BP
- （同一份 BP 模板可发多个投资人，one-pager 个性化）

### Step 4: 发起接触 → Investor Outreach Workflow

按 Investor Outreach Workflow 写个性化触达文案，经用户确认后用 `email-ops` 发出。邮件发出后 → 状态 `new → contacted`：

```bash
ir-record update-status --id <rowid> --status contacted
```

每次接触记入 `contacts` 表：

```bash
ir-record record-contact \
  --investor-id <id> \
  --contact-type "email" --direction "outbound" \
  --summary "发送初次接触邮件 + BP 附件" \
  --contact-date <YYYY-MM-DD> \
  --next-step "等 7 天无回复则 follow up"
```

### Step 5: 持续跟进 + 状态推进

每次投资人回复 / 用户 update → 调 `ir-record record-contact` + 必要时 `ir-record update-status`：

| 用户反馈 | 状态推进 |
|----------|----------|
| 投资人"不感兴趣" | → `passed` |
| 投资人"约 meeting" | → `meeting` |
| 投资人"看 BP" | → `bp_sent`（如果还没） |
| 投资人"进入 DD" | → `dd` |
| 投资人"发 TS" | → `ts` |
| 投资人"打款" | → `invested` |

#### DD / TS 阶段的企业背景核验（按需）

本次尽职调查、Term Sheet 谈判或签约准备需要企业背景资料时，可用天眼查 `tyc` 核验融资企业、投资机构管理公司或实际交易主体。先遵循本包 [SKILL.md 的安装与授权规则](../SKILL.md#安装与授权规则)：已安装直接复用；仅未安装时先展示免费额度与计费规则，再询问用户是否同意安装，得到同意后才安装。不因进入 `dd` / `ts` 状态就自动遍历所有查询维度。

以下为独立查询示例，按本次核验范围选择，将示例企业替换为已确认的实际主体全称或统一社会信用代码：

```bash
# 工商登记与交易主体信息
tyc company registration-info "乐视网信息技术（北京）股份有限公司" --head 80

# 股东结构（需要相应数据权益）
tyc company shareholder-info "乐视网信息技术（北京）股份有限公司" --head 80

# 基础风险总览
tyc risk overview "乐视网信息技术（北京）股份有限公司" --head 80
```

优先复用本轮已有核验资料。结果保存到 Workspace `ir/` 本次尽调资料目录，注明企业全称、信用代码、来源（天眼查及所用命令）、查询时间、返回事实与待核实项，结论与原始数据分开。`--head` 仅限制展示行数，完整结果按 SKILL.md 在同一次查询中保存。额度不足、无权限、查询失败与无数据分别标注，不能据此认定“无风险”或尽调已完成；公开企业数据不能替代用户提供的合同、财务和实际交易材料。

企业查询结果仅补充尽调资料，不自动推进融资状态；状态变更仍依据用户反馈。

### Step 6: 过期跟进提醒

过期跟进默认靠用户反馈与主动查询：`ir-record query-stale --days 7`（7 天无 contact 进展的投资人）。用户希望自动提醒时，启用定时模式（见包内 `scheduling.md`），心跳会定期查过期投资人并提醒。

---

## 与其他环节的关系

- **Investor Hunting Workflow**：发掘 + 筛选 + 去重
- **Investor Materials Workflow**：BP / One-Pager / 路演材料
- **Investor Outreach Workflow**：触达邮件 / 暖介绍文案
- **`ir-record`**（数据层）：所有投资人档案 / 接触历史 / 状态机
- **商业模式打磨**（Step 1）：投资人接触前必做
- **Project Application Workflow**（包内）：与融资平行（项目申报 vs 融资）

---

## Pitfalls

### pitfall: 跳过商业模式打磨直接接触投资人

- **症状**：用户说"我要找投资人"，直接进入发掘
- **workaround**：**先**完成商业模式打磨（30 秒电梯版 + 5 问结构化）

### pitfall: 同一投资人发多份 BP 模板

- **症状**：所有投资人发同一份 BP，不个性化
- **workaround**：One-Pager 个性化（强调与对方基金 focus_areas 的契合）

### pitfall: 状态推进滞后

- **症状**：投资人已回 "约 meeting"，但 `investors.status` 还是 `contacted`
- **workaround**：每次用户反馈 → 立即 `ir-record update-status`

### pitfall: 7 天没进展未提醒

- **症状**：投资人不回复，用户忘记跟进
- **workaround**：`ir-record query-stale` 主动查询 → 提醒用户；需要自动提醒时启用定时模式（见 `scheduling.md`）

### pitfall: 把"暖介绍"搞砸

- **症状**：暖介绍邮件里直接放 BP 全文，介绍人尴尬
- **workaround**：暖介绍邮件只放 1 句话 context + 询问是否愿意被介绍

---

## Notes

- **不**直接调邮件发送：先出文案，让用户确认后再发
- **不**承诺融资成功率：只保证流程齐整 / 状态准确 / 跟进及时
- **不**接触"明显不匹配"的投资人（如 5 亿 VC 投 50 万种子轮）—— match_score 阶段过滤
- 跨轮次（A 轮 / B 轮）的投资人池完全不同；同一投资人池按轮次隔离
