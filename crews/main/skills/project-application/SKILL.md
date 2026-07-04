---
name: project-application
description: IR 模式 2 · 项目申报。帮 OPC / 中小微企业老板准备和跟踪各类外部申报
  项目：高新技术企业认定、加速器申请、政府补贴、资质认证（软著 / 商标 / 专利
  配套）、行业奖项。涵盖材料生成 + 时间线管理 + 状态跟踪。
metadata:
  openclaw:
    emoji: 📋
---

# 项目申报（IR 模式 2）

> **Phase 7 续·IR 三模式抽三 skill（2026-07-04）**：从原 IR crew AGENTS 抽三模式。
> **模式 2 = 项目申报**（本 skill）；模式 1 = `business-model-polish`；模式 3 = `investor-pipeline`。

帮用户准备、跟踪各类外部申报项目。

---

## 适用场景

用户说：
- "我想申请高新技术企业认定 / 专精特新 / 科技型中小企业"
- "我看到 X 加速器在招创业团队，能帮我准备申请吗"
- "政府有 Y 补贴项目，截止日期 Z，能帮我看下材料吗"
- "我想申请软著 / 商标 / 专利"
- "我要申报 X 行业奖项"

---

## 常见申报类型

| 类型 | 典型材料 | 委派子 skill |
|------|---------|-------------|
| 高新技术企业认定 | 知识产权 + 研发费用 + 人员名单 + 财务审计 | `swcr-register` + `market-research` |
| 加速器申请 | BP + One-Pager + 团队介绍 + 牵引数据 | `investor-materials` |
| 政府补贴 | 申报书 + 财务报表 + 项目实施方案 | `market-research`（行业数据）|
| 软著登记 | 源程序文档 + 操作手册 | `swcr-register` |
| 商标 / 专利 | 技术交底书 + 权利要求书 | （直接走，不委派）|
| 行业奖项 | 案例描述 + 客户证言 + 量化数据 | `market-research`（行业 baseline）|

---

## 工作流

### Step 1: 问清申报项目

问用户：
- **申报项目名称**（具体哪个 / 哪个机构的）
- **截止日期**
- **所需材料清单**（用户已知；如未知 → 让用户去官网看要求，AI 不替用户读官网）
- **已有什么材料** / **缺什么材料**

### Step 2: 拆任务 + 委派子 skill

按材料清单拆任务，按 skill 边界委派：

| 材料 | 委派给 |
|------|--------|
| 软著材料（源程序 + 操作手册）| `swcr-register` |
| 行业市场数据 / 竞品分析 | `market-research` |
| BP / One-Pager | `investor-materials` |

子 skill 输出后，main 整合成"申报书完整版"。

### Step 3: 时间线 + 提醒

写入 `ir-record` 的 `applications` 表：

```bash
./skills/ir-record/scripts/record-application.sh \
  --name "2026 国高认定" \
  --type "high-tech-enterprise" \
  --organizer "科技部" \
  --deadline "2026-09-30" \
  --status "planning"
```

心跳会查 `query-stale.sh`（7 天过期提醒）—— 用户记得 deadline。

### Step 4: 状态跟踪

```
planning → preparing → submitted → reviewing → approved/rejected
```

每状态变更：
```bash
./skills/ir-record/scripts/update-status.sh \
  --type application --id <rowid> --status <new>
```

跟踪结果（如"已提交 / 已通过 / 未通过"）也写入 `applications` 表。

---

## 与其他 IR skill 的关系

- **swcr-register**：软著专用（模式 2 频繁需要的子材料）
- **market-research**：行业数据（多个申报类型需要）
- **investor-materials**：BP / 加速器申请需要
- **business-model-polish**（模式 1）：申报前先打磨商业模式（很多申报材料要先有清晰的商业故事）

---

## Pitfalls

### pitfall: 替用户读官网

- **症状**：用户问"X 加速器需要什么材料"，Agent 直接编
- **workaround**：让用户去官网看，AI 协助整理已读到的内容

### pitfall: 跨截止日期未提醒

- **症状**：用户提了 deadline 但没在 ir-record 记
- **workaround**：**所有** deadline 必记 `applications` 表（心跳 7 天提醒）

### pitfall: 申报材料不更新状态

- **症状**：用户说"我已经提交了"，但 `applications.status` 还是 preparing
- **workaround**：每次用户反馈进度，立即调 `update-status.sh`

---

## Notes

- 软著 / 商标 / 专利的"材料生成"严格走 `swcr-register` skill（合规性边界）
- 财务审计报告、税务证明等"硬材料"由用户/会计师提供，AI 不替生成
- 申报通过率不承诺，AI 只保证材料齐整 / 表达清晰 / 时间线追踪
