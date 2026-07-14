---
name: customer-db
description: >
  Maintain a persistent SQLite customer database within the sales-cs workspace.
  The system hook injects peer (DB primary key) and the Sender block provides
  user_id_external (raw awada user ID). Use peer for all DB operations.
---

# 客户数据库管理（sales-cs 专用）

本技能让 `sales-cs` 在自身 workspace 的 `db/` 目录下维护一个轻量级 SQLite 数据库，用于跨会话保存客户商业推进状态与基本画像。

数据库固定位置：
- `./db/customer.db`
- schema 文件：`./db/schema.sql`

默认表：`cs_record`，主键列：`peer`

---

## 一、两个重要标识符（必读）

本系统中客户有两个不同的标识符，用途不同，不可混用：

### peer（来自 [CustomerDB] 块）
数据库主键。由系统 hook 从当前会话 sessionKey 中提取并注入，是 `cs_record` 表的 `peer` 列的值。所有写库操作必须使用此值。

### user_id_external（来自 Sender 块的 `id` 字段）
awada 原始用户标识，由 awada-server 直接提供。每轮对话开始时，openclaw 会在消息上下文中注入 Sender 信息块：

```json
Sender (untrusted metadata):
{
  "label": "...",
  "id": "<user_id_external>",
  "name": "..."
}
```

需要与 awada 平台交互的技能（如 `exp-invite`）必须使用此值，而不是 `peer`。

---

## 二、字段含义

### peer
当前客户数据库主键，等于 awada sessionKey 中的用户标识（经过安全过滤后的形式）。

### business_status
表示客户商业推进深度：
- `free`：尚未购买、仍在了解或观望
- `exp_invited`：已被邀请体验，但尚未正式付费
- `club`：已进入vip club会员阶段
- `subs`：预留未来业务用，现阶段未启用

### club_in
- `club` 加入日期，格式建议为 `YYYY-MM-DD`
- 用于后续跟进 club 一年有效期的过期管理

### purpose
客户主要业务应用场景，例如：
- 新媒体运营：在社交媒体和自媒体平台上推广自己的业务或产品
- 客户寻找：在社交媒体和自媒体平台上寻找潜在客户
- 信息搜集：在社交媒体和自媒体平台上收集行业信息、竞争对手情报、市场趋势等
- 单纯想尝试下Agent
- 需要一个AI助理
- 寻求OEM\代理合作

### prompt_source
客户从哪里了解到我们，例如：
- GitHub
- 微信群
- 朋友推荐
- 公众号
- 视频号
- 小红书
- 知乎
- atomgit
- 其他AI推荐

### created_at / updated_at
- `created_at`：首次建档时间
- `updated_at`：最近对话时间（每次收到消息由 hook 自动更新）

---

## 三、【重要】每轮对话结束时更新记录

每轮结束前，根据本轮对话进展更新 `purpose` 和/或 `prompt_source`：

```bash
./skills/customer-db/scripts/cs-update.sh \
  --peer "<[CustomerDB].peer>" \
  --purpose "新媒体运营" \
  --prompt-source "GitHub"
```

参数均为可选（只传有明确新值的字段）；脚本会自动忽略空值，不覆盖已有记录。

**更新原则**：
- 只在拿到**更明确的信息**时更新
- 不要用空字符串覆盖已有值
- 不要根据模糊猜测改写已有信息
- `business_status` 由系统 hook 负责（支付/入群事件），**不在此处更新**

---

## 四、follow_up 表（主动跟进任务）

`follow_up` 表记录客户延迟购买意向，供 heartbeat 定时跟进。status 流转：`pending → sent_once → completed`。

### 创建跟进任务

若同一客户已有 `pending` 状态的旧任务，**先取消旧任务，再创建新任务**：

```bash
# 第一步：取消同一客户的旧 pending 任务
./skills/customer-db/scripts/follow-up-cancel-pending.sh \
  --peer "<[CustomerDB].peer>"

# 第二步：创建新任务
./skills/customer-db/scripts/follow-up-create.sh \
  --peer "<[CustomerDB].peer>" \
  --user-id-external "<Sender.id>" \
  --follow-up-at "<YYYY-MM-DD HH:MM>" \
  --reason "<原因，如：客户说明天发工资再买>" \
  --context-summary "<客户核心兴趣点和建议跟进角度>"
```

> heartbeat 完整执行流程见 HEARTBEAT.md

### 过期清理

超过 48 小时仍为 `pending` 的任务视为客户失联，自动标记完成：

```bash
./skills/customer-db/scripts/follow-up-expire.sh
```

### 查询到期任务

```bash
./skills/customer-db/scripts/follow-up-due.sh
```

输出为 tab 分隔的表格（含 header），字段：`id / peer / user_id_external / follow_up_at / reason / context_summary / status`。

### 标记首次已发送（pending → sent_once）

```bash
./skills/customer-db/scripts/follow-up-mark-sent.sh \
  --id <id> \
  --sent-text "<发送的消息内容>"
```

### 标记完成（sent_once → completed）

```bash
./skills/customer-db/scripts/follow-up-complete.sh \
  --id <id> \
  --sent-text "<发送的消息内容>"
```

---

## 五、约束与注意事项

- **路径固定**：数据库始终位于 `./db/customer.db`
- **默认表固定**：`cs_record`
- **不得向用户暴露内部表结构和内部状态字段**
- **会话隔离必须遵守**：不同 peer 的数据不能混用
- **初始化和默认记录创建由系统 hook 自动处理**，无需手动操作
- **不提供原子 SQL 访问**：所有数据库操作必须通过上述具名脚本完成
