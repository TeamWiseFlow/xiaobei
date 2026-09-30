---
name: content-calibrator
description: DNA 表现评估引擎——消费 published-track 的发布与互动数据，按量触发（每平台每 DNA 累积 ≥5 条成熟记录）评估 DNA 好坏，趋势优先（账号基线归一化 + 走向判定），产出评估报告与优化建议，经用户确认后回写 DNA。平台特有的归因方法由各平台专家包 review workflow 提供。发布记录与数据采集由 published-track 统一管理。
metadata:
  openclaw:
    emoji: 🎯
    requires:
      bins:
      - bash
      - sqlite3
      - python3
---

# Content Calibrator — DNA 表现评估引擎

> **四条评估铁律**：
> 1. **趋势优先**：绝对值只作上下文。数据好坏看「同账号相对值 + 其走向」——新号数据天然低、老号天然高，同 DNA 跨账号不可直接比绝对值，要的是趋势
> 2. **脚本只给证据**：聚合、基线、比值、走向由 `content-calibrator eval` 计算；好坏归因由 Agent 回读 DNA 文档与作品原文完成，脚本不下结论
> 3. **先排混杂再归因**：账号成熟度、粉丝自然增长、选题热度、季节性流量都会污染信号；排除不了的混杂，结论降级写「观察」不写「结论」
> 4. **DNA 更新必须用户逐条确认**：评估只产出建议，Agent 不得自动改 DNA

---

## 职责边界（与 review / published-track 的分工）

| 角色 | 回答什么 | 产出 |
|------|---------|------|
| `published-track` | 数据在哪 | 发布记录 + 互动指标（每日采集入库） |
| **本技能** | **这个 DNA 好不好、该怎么改**（共性引擎） | 触发规则、基线归一化与趋势证据、评估报告结构；`<platform>/dna/<dna-id>/evals/*.eval.md` |
| 各平台专家包 `review` workflow | 该平台的数据复盘怎么做（平台特性） | 平台归因方法（指标语义、映射、混杂因素）+ 复盘编排；heartbeat 与用户临时发起的该平台复盘都走它 |

本技能只给**共性归因步骤与原则**，不含任何平台特有归因方法，平台归因方法一律由该平台专家包 review workflow 提供。本技能的结论**必须落到 DNA 动作**（保持 / 调整某维度规则 / 调整 template 某部分），经用户逐条确认后走对应平台的 style-dna workflow 更新。

---

## 核心闭环

```
📥 每日数据采集(published-track) → 📊 阈值检查(--check) → 🧬 DNA 评估(聚合+归因) → 📝 评估报告 → 👤 用户逐条确认 → 🔁 style-dna 更新 DNA
```

### 触发机制：数据采集每天跑，评估按量触发

- **每日**：heartbeat 采集互动数据入库（published-track 职责，不变）。
- **按量**：每个（平台, DNA）的**成熟待评估记录**累积 **≥5 条**时评估一轮。成熟 = 发布 ≥3 天（数据稳定）；待评估 = `perf_evaluated=0` 且 `dna_id` 非空。一轮评估覆盖该 DNA 全部待评估记录（可多于 5 条）。
- **手动兜底**：低频 DNA 凑不满 5 条时，用户说「复盘一下这个 DNA」→ `--force` 强制评估。
- `dna_id=NULL`（历史补录/未归属）不参与 DNA 评估。

### 归因：共性步骤与原则

**原则**：

1. **归因方法平台特有，本技能不定义**：指标语义、互动路径（漏斗/完播/其他）、到 DNA 维度的映射、平台混杂因素清单，全部由该平台专家包 review workflow 提供。本技能只做平台无关的事：触发、聚合、归一化、趋势、报告结构。
2. **判定看相对值与走向**：绝对值只作上下文；`baseline_insufficient` 的记录只作绝对观察，不参与趋势结论。
3. **先排混杂再归因**：账号成熟度、粉丝自然增长、平台流量波动、选题热度、季节性等 DNA 之外能影响数据的因素，排除不了的，结论降级写「观察」不写「结论」。

**共性步骤**：

1. 读 `content-calibrator eval` 聚合 JSON：每篇绝对值 + 同账号比值 + 每指标趋势走向。
2. 对照 `<platform>/calibration/platform-state.json`、`audience.md` 了解账号阶段与受众背景。
3. 按该平台 review workflow 的归因方法，把趋势变化落到 DNA 的具体部分与维度（需回读 `{dna-id}.dna.md` / `{dna-id}.template.md` 与待评估作品原文，`source_folder` 可定位）。
4. 混杂排不掉 → 写「观察」；能归因 → 写「结论 + 建议」，每条建议注明改哪个维度 / template 部分。

---

## 评估产物

评估报告写入 Workspace：

```text
<platform>/dna/<dna-id>/evals/{YYYY-MM-DD}.eval.md
```

报告结构：

1. **整体判定**：这个 DNA 近期表现（趋势语言：改善 / 平稳 / 下滑），置信度与样本量。
2. **趋势表**：每指标的比值走势（引 `content-calibrator eval` 输出，不重算）。
3. **template 归因**：哪个 template 部分在起作用 / 拖后腿，证据是哪几篇（归因口径按平台 review workflow 的方法）。
4. **逐条优化建议**：每条 = 建议内容 + 目标维度/template 部分 + 证据篇目。供用户逐条确认。
5. **观察区**：归因不了但值得记录的信号（含混杂说明）。

写完报告后必须调 `--mark-evaluated` 标记覆盖的记录，防止下轮重复评估。

---

## 脚本

统一走顶层 wrapper `content-calibrator`（在 PATH 中，零路径拼接）。

### eval — DNA 表现评估聚合引擎（唯一数据入口）

```bash
# 廉价阈值检查（heartbeat 每日跑，无触发不消耗后续 token）
content-calibrator eval --platform <platform> --check

# 聚合触发 DNA 的证据（绝对值 + 账号基线比值 + 趋势走向）
content-calibrator eval --platform <platform>

# 手动触发低频 DNA（不达阈值也评估）
content-calibrator eval --platform <platform> --dna-id <dna-id> --force

# 评估报告写完后标记（防重复评估）
content-calibrator eval --platform <platform> --mark-evaluated --ids 3,4,5
```

参数：`--min-samples 5`（触发阈值）、`--mature-days 3`（成熟窗口）、`--baseline-window 10`（账号基线取此前最多 N 篇均值）。须从 Workspace 根调用。

基线语义：同账号**此前**（发布日更早）最多 N 篇的指标均值，避免后视；此前 <3 篇 → `baseline_insufficient`。`account` 为空的记录归入未知账号组，不与其他账号混算。

### query-metrics — 单篇指标查询

```bash
content-calibrator query-metrics --platform <platform> --source-folder <work 目录>
```

### init — 平台初始化

```bash
content-calibrator init --platform <platform_id>
```

幂等。创建 `<platform>/calibration/`，默认只含 `platform-state.json`（baseline 兜底参考）+ `audience.md`；存量旧点号文件 `.platform-state.json` 自动改名。对标记录（如 `benchmark.md`）不在默认初始化内，由 `account-benchmark` workflow 按需生成。

---

## Heartbeat 集成（凌晨任务）

1. 数据采集：按各平台专家包的 engagement 工具更新（每日必跑）。**评估前必须保证数据新鲜**；本技能只消费 DB，不直接取数。
2. 阈值检查：各启用平台跑 `content-calibrator eval --platform <platform> --check`；全部 `triggered=false` → 本轮评估结束。
3. 有触发 → **该平台的复盘走其专家包 review workflow**（如 wx_mp → expert-wx-mp 的 Review Workflow）：取数刷新、聚合、平台归因、写 `evals/{date}.eval.md`、标记，都在 review workflow 内完成。无专家包 review workflow 的平台按上方共性步骤执行，归因只到「观察」级。
4. 汇总：上报本轮评估的 DNA、整体判定与待用户确认的优化建议。**Agent 不得自动更新 DNA。**

派发纪律：heartbeat isolated 会话中全部流程须**主 agent inline 执行**，不 spawn subagent、不 sessions_yield（评估需连续回读多文件，隔离会话无上下文污染问题）。

---

## Status — 状态看板

向用户报告校准状态时展示：

```
🧬 Content Calibrator 状态（DNA 表现评估）

【平台】<platform>：baseline 未定 / 已定
【待评估】<dna-id>：3/5 条成熟记录（未触发）
【最近评估】<platform>/dna/<dna-id>/evals/<date>.eval.md — 判定：改善
【待确认建议】2 条
```

数据来源：`content-calibrator eval --check` + `<platform>/dna/*/evals/` 目录。

---

## 历史说明

本技能前身为「内容校准预测循环」（统一 rubric 打分 + 盲预测 + 阈值门 + bump 升级）。2026-08-20 起 rubric 体系废除：发布前不再打分，判断准则不再是独立进化对象，发布数据直接关联 DNA（`pub_*` 表 `dna_id` 列）做表现评估。DB 中 `cal_*` 列为历史兼容保留。
