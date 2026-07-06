---
name: info-record
description: 当执行 BD（商务拓展）任务时维护 SQLite 情报采集数据库，记录已采集的信息内容，避免重复采集，支持按日查询已采集情报。
---

# Info Record 技能

在 `./db/info_record.db` 中维护持久化 SQLite 数据库，供 intel-gathering（模式三）使用。

## 数据库位置

```
./db/info_record.db
```

初始化（幂等，可重复执行）：`./skills/info-record/scripts/init-db.sh`

---

## 表结构

### intel_items（模式三：情报采集）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | 自增主键 |
| source | TEXT NOT NULL | 信源（URL 或 平台-账号） |
| source_type | TEXT NOT NULL | 信源类型（xhs/dy/ks/bilibili/fb/x/wb/wx-mp/web） |
| title | TEXT | 内容标题（如有） |
| author | TEXT | 作者/发布者（如有） |
| publish_date | TEXT | 发布日期（如有） |
| content | TEXT NOT NULL | 采集内容（按用户要求的采集信息） |
| created_at | TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now','localtime')) | 采集时间 |

---

## 脚本命令

所有脚本均需在 workspace 根目录下执行。

### 初始化数据库

```bash
./skills/info-record/scripts/init-db.sh
```

### 检查内容是否已采集

```bash
./skills/info-record/scripts/check-content.sh --source <信源URL或标识>
```
返回 JSON：`{"exists": true/false}`

### 记录采集内容

```bash
./skills/info-record/scripts/record-content.sh \
  --source <信源URL或标识> \
  --source-type <信源类型> \
  --title <标题> \
  --author <作者> \
  --publish-date <发布日期> \
  --content <采集内容>
```
返回 JSON：`{"ok": true, "id": <记录ID>}` 或 `{"ok": false, "error": "..."}`

### 查询今日采集

```bash
./skills/info-record/scripts/query-today.sh
```
返回今日采集的所有记录（JSON 数组格式）。

---

## 使用规则

1. 打开帖子/视频详情前，先用 `check-content.sh` 判断该内容是否已记录；已记录则跳过。
2. 每个内容采集完成后，立即用 `record-content.sh` 将采集结果记录入库。
3. 执行完毕后，用 `query-today.sh` 读取当日所有采集信息，按与用户约定的交付形式生成交付物。
