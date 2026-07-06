---
name: ir-record
description: 当执行 IR（投资人关系）任务时维护 SQLite 追踪数据库，记录投资人档案、接触历史和项目申报，避免重复，跟踪进展。
---

# IR Record 技能

在 `./db/ir_record.db` 中维护持久化 SQLite 数据库，供投资人关系三大工作块使用。

## 数据库位置

```
./db/ir_record.db
```

初始化（幂等，可重复执行）：`./skills/ir-record/scripts/init-db.sh`

---

## 表结构

### investors（投资人档案）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| name | TEXT NOT NULL | 投资人姓名 |
| type | TEXT NOT NULL | 投资人类别（angel/vc/pe/cvc/fo/other） |
| firm | TEXT | 所属机构 |
| title | TEXT | 职位 |
| email | TEXT | 邮箱 |
| phone | TEXT | 电话 |
| wechat | TEXT | 微信号 |
| linkedin | TEXT | LinkedIn URL |
| source | TEXT | 来源 |
| focus_areas | TEXT | 关注领域（逗号分隔） |
| match_score | TEXT | 匹配度（high/medium/low） |
| status | TEXT NOT NULL DEFAULT 'new' | 进展状态 |
| notes | TEXT | 备注 |
| created_at | TEXT | 记录创建时间 |
| updated_at | TEXT | 最后更新时间 |

**状态机**：
```
new → contacted → bp_sent → meeting → dd → ts → invested
  ↓        ↓         ↓         ↓       ↓     ↓
passed   passed    passed    passed  passed passed
```

### contacts（接触记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| investor_id | INTEGER NOT NULL | 关联 investors.id |
| contact_type | TEXT NOT NULL | 接触方式（email/phone/meeting/intro/pitch/other） |
| direction | TEXT NOT NULL | 方向（outbound/inbound） |
| summary | TEXT NOT NULL | 接触内容摘要 |
| result | TEXT | 结果/对方反馈 |
| next_step | TEXT | 下一步行动 |
| contact_date | TEXT NOT NULL | 接触日期（YYYY-MM-DD） |
| created_at | TEXT | 记录时间 |

### applications（项目申报）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| name | TEXT NOT NULL | 申报项目名称 |
| type | TEXT NOT NULL | 申报类别（competition/grant/subsidy/incubator/other） |
| organizer | TEXT | 主办方/组织方 |
| platform_url | TEXT | 申报平台 URL |
| deadline | TEXT | 截止日期（YYYY-MM-DD） |
| status | TEXT NOT NULL DEFAULT 'planning' | 申报状态 |
| submitted_date | TEXT | 实际提交日期 |
| result | TEXT | 结果/获奖情况 |
| notes | TEXT | 备注 |
| created_at | TEXT | 记录创建时间 |
| updated_at | TEXT | 最后更新时间 |

**申报状态**：
```
planning → drafting → submitted → shortlisted → awarded
                ↓          ↓           ↓
             passed     rejected    rejected
```
- `planning`：计划申报
- `drafting`：材料准备中
- `submitted`：已提交
- `shortlisted`：入围/初筛通过
- `awarded`：获奖/获批
- `rejected`：未通过
- `passed`：放弃申报

---

## 脚本命令

所有脚本均需在 workspace 根目录下执行。

### 初始化数据库

```bash
./skills/ir-record/scripts/init-db.sh
```

### 投资人档案管理

**检查投资人是否已记录**（按姓名+机构去重）：
```bash
./skills/ir-record/scripts/check-investor.sh --name <姓名> --firm <机构名>
```
返回 JSON：`{"exists": true/false, "id": <记录ID或null>}`

**记录新投资人**：
```bash
./skills/ir-record/scripts/record-investor.sh \
  --name <姓名> --type <angel|vc|pe|cvc|fo|other> --firm <机构名> \
  [--title <职位>] [--email <邮箱>] [--phone <电话>] [--wechat <微信号>] \
  [--linkedin <LinkedIn>] [--source <来源>] [--focus-areas <关注领域>] \
  [--match-score <high|medium|low>] [--status <new|contacted|...>] [--notes <备注>]
```
必填：`--name`、`--type`、`--firm`。

**更新投资人状态**：
```bash
./skills/ir-record/scripts/update-status.sh --id <投资人ID> --status <新状态> [--notes <备注>]
```

### 接触记录管理

**检查近期接触**：
```bash
./skills/ir-record/scripts/check-contact.sh --investor-id <ID> --days <天数>
```

**记录接触**：
```bash
./skills/ir-record/scripts/record-contact.sh \
  --investor-id <投资人ID> --contact-type <email|phone|meeting|intro|pitch|other> \
  --direction <outbound|inbound> --summary <接触内容摘要> \
  --contact-date <YYYY-MM-DD> [--result <结果>] [--next-step <下一步行动>]
```
必填：`--investor-id`、`--contact-type`、`--direction`、`--summary`、`--contact-date`。

### 进展查询

**查询投资人 Pipeline 摘要**：
```bash
./skills/ir-record/scripts/query-progress.sh
```

**查询待跟进投资人**：
```bash
./skills/ir-record/scripts/query-stale.sh --days <天数>
```

### 项目申报管理

**检查申报是否已记录**（按项目名+主办方去重）：
```bash
./skills/ir-record/scripts/check-application.sh --name <项目名> [--organizer <主办方>]
```
返回 JSON：`{"exists": true/false, "id": <记录ID或null>}`

**记录新申报**：
```bash
./skills/ir-record/scripts/record-application.sh \
  --name <项目名> --type <competition|grant|subsidy|incubator|other> \
  [--organizer <主办方>] [--platform-url <申报平台URL>] [--deadline <YYYY-MM-DD>] \
  [--status <planning|drafting|submitted|shortlisted|awarded|rejected|passed>] \
  [--submitted-date <YYYY-MM-DD>] [--result <结果>] [--notes <备注>]
```
必填：`--name`、`--type`。

**查询申报记录**：
```bash
./skills/ir-record/scripts/query-applications.sh [--status <状态>] [--upcoming <天数>]
```
- 无参数：返回所有申报，按状态排序
- `--status`：按状态过滤
- `--upcoming`：查询未来 N 天内截止的申报

---

## 使用规则

1. **工作块一（商业模式打磨）**：不直接使用数据库。
2. **工作块二（项目申报）**：
   - 发现申报机会后，先用 `check-application.sh` 判断是否已记录
   - 已在数据库中则跳过，避免重复申报
   - 确认申报后用 `record-application.sh` 记录（status=planning）
   - 提交后更新 status 为 submitted
   - HEARTBEAT 触发时运行 `query-applications.sh --upcoming 7` 提醒即将截止的申报
3. **工作块三（投资人发掘与跟进）**：
   - 搜索到投资人后，先用 `check-investor.sh` 判断是否已记录
   - 已在数据库中则跳过，除非有新信息需要更新
   - 新投资人立即用 `record-investor.sh` 记录（status=new）
   - 首次接触后，用 `update-status.sh` 更新状态，用 `record-contact.sh` 记录接触
   - HEARTBEAT 触发时运行 `query-stale.sh --days 7` 检查超期未跟进
   - 每周运行 `query-progress.sh` 获取全局 Pipeline 视图
