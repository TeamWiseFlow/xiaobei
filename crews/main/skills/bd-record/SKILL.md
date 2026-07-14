---
name: bd-record
description: 当执行 BD（商务拓展）任务时维护 SQLite 追踪数据库，记录已探索的创作者（模式一）和已互动的帖子（模式二），避免重复追踪和重复互动。
---

# BD Record 技能

在 `./db/bd_record.db` 中维护持久化 SQLite 数据库，供 lead-hunting（模式一）和 comment-engagement（模式二）使用。

## 数据库位置

```
./db/bd_record.db
```

初始化（幂等，可重复执行）：`./skills/bd-record/scripts/init-db.sh`

---

## 表结构

### lead_creators（模式一：创作者探索）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| platform | TEXT NOT NULL | 平台标识（xhs/dy/ks/bilibili/fb/x/wb） |
| creator_id | TEXT NOT NULL | 平台上的创作者 ID |
| nickname | TEXT | 创作者昵称 |
| homepage_url | TEXT NOT NULL | 创作者主页 URL |
| qualified | INTEGER DEFAULT 0 | 是否符合潜在客户标准（1=是，0=否） |
| notes | TEXT | 备注（符合/不符合的原因摘要） |
| created_at | TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')) | 记录时间 |

### comment_posts（模式二：帖子互动）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| platform | TEXT NOT NULL | 平台标识 |
| post_title | TEXT | 帖子标题（如有） |
| post_url | TEXT NOT NULL | 帖子 URL |
| strategy | TEXT NOT NULL | 互动策略（direct_comment/reply_dm/direct_dm） |
| replied | INTEGER DEFAULT 0 | 是否已互动（1=是，0=否） |
| reply_content | TEXT | 我们发送的互动内容 |
| reply_target_id | TEXT | 互动目标 ID（回复的评论 ID 或私信的用户 ID） |
| created_at | TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')) | 记录时间 |

---

## 脚本命令

所有脚本均需在 workspace 根目录下执行。

### 初始化数据库

```bash
./skills/bd-record/scripts/init-db.sh
```

### 模式一：创作者记录

**检查创作者是否已记录**：
```bash
./skills/bd-record/scripts/check-creator.sh --platform <平台> --creator-id <创作者ID>
```
返回 JSON：`{"exists": true/false}`

**记录创作者**：
```bash
./skills/bd-record/scripts/record-creator.sh \
  --platform <平台> \
  --creator-id <创作者ID> \
  --nickname <昵称> \
  --homepage-url <主页URL> \
  --qualified <0或1> \
  --notes <备注>
```
返回 JSON：`{"ok": true, "id": <记录ID>}` 或 `{"ok": false, "error": "..."}`

### 模式二：帖子互动记录

**检查帖子是否已互动**：
```bash
./skills/bd-record/scripts/check-post.sh --platform <平台> --post-url <帖子URL>
```
返回 JSON：`{"exists": true/false, "replied": true/false}`

**记录互动**：
```bash
./skills/bd-record/scripts/record-post.sh \
  --platform <平台> \
  --post-title <标题> \
  --post-url <帖子URL> \
  --strategy <direct_comment|reply_dm|direct_dm> \
  --reply-content <互动内容> \
  --reply-target-id <目标ID>
```
返回 JSON：`{"ok": true, "id": <记录ID>}` 或 `{"ok": false, "error": "..."}`

---

## 使用规则

1. **模式一**：打开创作者主页前先用 `check-creator.sh` 判断是否已记录；如果已在记录中则跳过。读取创作者信息后，不管是否符合标准，都要用 `record-creator.sh` 记录。
2. **模式二**：
   - 直接回帖策略：打开帖子前先用 `check-post.sh` 判断是否已操作过，已操作则跳过；回复后用 `record-post.sh` 记录。
   - reply/dm 策略：互动前先判断是否对同一内容/发布者已 touch 过，已 touch 则跳过；touch 后用 `record-post.sh` 记录。
