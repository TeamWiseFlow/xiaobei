---
name: published-track
description: 发布记录追踪。使用 SQLite 数据库记录所有平台发布内容及其互动数据，按平台分表管理。三大块：与发布技能结合（发布记录 + DNA 关联）、数据更新、查询与设置。发布数据的 DNA 表现评估由 content-calibrator 消费。
metadata:
  openclaw:
    emoji: "📊"
    requires:
      bins:
      - bash
      - sqlite3
---

# published-track — 发布记录追踪

统一管理所有平台（微信公众号、微信视频号、知乎、B站、抖音、快手、小红书、今日头条、掘金、Twitter/X、Facebook、Instagram、TikTok、YouTube、Pinterest、Threads）的发布记录与互动数据。

> 企业微信朋友圈不纳入追踪记录（无公开 URL、互动数据无法自动获取、运营复盘价值低），发布后不调 `record.sh`。

---

## 数据库位置与调用约定

`./db/published_track.db`（相对于工作区根目录）。初始化（幂等）：

```bash
published-track init-db
```

**脚本统一走顶层 wrapper `published-track <子命令>`**（在 PATH 中，零路径拼接）：`record` / `update-metrics` / `query` / `query-pending` / `check-published` / `set-distribute-status` / `init-db` / `migrate-v3`。ROOT 按 wrapper 真实路径解析（符号链接自动解析），不限调用目录。

---

## 平台与表对应关系

| 平台 | 表名 | 内容类型 | 特有指标 |
|------|------|---------|---------|
| 微信公众号 | `pub_wx_mp` | article/post | reads, shares, favorites, likes, comments |
| 微信视频号 | `pub_wx_channel` | video | plays, likes, comments, shares, favorites |
| 知乎 | `pub_zhihu` | article/post | views, upvotes, comments, favorites |
| B站 | `pub_bilibili` | video | plays, danmaku, likes, coins, favorites, shares, comments |
| 抖音 | `pub_douyin` | video/post | 自动取 likes, comments, shares, favorites；plays 与 deep_metrics 保留历史值或用户补录 |
| 快手 | `pub_kuaishou` | video | plays, likes, comments, shares |
| 小红书 | `pub_xhs` | video/post | views, likes, favorites, comments, shares；deep_metrics / deep_captured_at / deep_source；fan_portrait（单篇画像 JSON） |
| Twitter/X | `pub_twitter` | post/video | views, likes, retweets, replies, bookmarks |

`--platform` 取「表名」去掉 `pub_` 前缀，如 `wx_mp`、`wx_channel`、`xhs`、`bilibili`。

---

## 表结构

每张表共享通用字段：`id`（自增主键）、`title`、`content_type`（article/video/post）、`source_folder`（原始文件夹，如 `wx_mp/outputs/xxx`，**不做唯一约束，同内容可同平台多次发布**）、`publish_url`、`publish_date`（YYYY-MM-DD）、`distribute_status`（0=待分发，1=无需分发，2=已分发）、`notes`、`created_at`、`updated_at`。各平台特有互动指标默认 0，另有 `top_comment`（主要留言摘要）。

> **视频号（`pub_wx_channel`）特例**：`title` 列存的是**完整视频描述**（含 hashtag，最长约 300 字），即 `wechat-channels-publish` Step 6 填的视频描述；`wx-channel-engagement` 抓取按它匹配后台作品管理页。发布页改版后虽可另填**短标题**，但作品管理页不展示短标题，因此**短标题不入库**——调用方调 `record.sh --platform wx_channel --title` 必须传完整视频描述，不要传短标题、也不要把两者拼接。

### DNA 关联字段（v3 schema）

| 字段 | 说明 |
|------|------|
| `dna_id` | 作品归属的 DNA（如 `dna-0`）；NULL = 未归属/历史作品。`record.sh` 自动从 `<work>/dna-meta.json` 读取写入，`--dna-id` 入参可覆盖 |
| `account` | 发布账号 alias（如 wx_mp `accounts.json` 的 alias）；DNA 表现评估按账号基线归一化用，`record.sh --account` 写入 |
| `perf_evaluated` | 是否已被 content-calibrator 的 DNA 表现评估覆盖（0/1）；评估完成后由 `dna-eval.sh --mark-evaluated` 置 1 |

> **历史兼容**：`cal_enabled` / `cal_score_*` / `cal_composite` / `cal_rubric_version` / `cal_bias_signals` / `cal_bump_evaluated` 等旧打分字段保留但**停止写入**——rubric 打分体系已废除，发布数据直接关联 DNA 做表现评估，见 `content-calibrator` 技能。旧库升级跑 `published-track migrate-v3`（幂等）。

---

# 三大使用方式

## 块一·与发布技能结合

本块描述发布记录脚本的用法与编排意图。**实际编排由各个专家包中的 workflow 承担**；各发布技能本身只管发布。流程顺序为 **发布 → 记录**。

### 流程 1·发布记录（发布后）

发布成功后调用 `record.sh`。**DNA 关联自动建立**：内容生产环节已在 `<work>/dna-meta.json` 落盘所用 DNA（形如 `{"platform":"wx_mp","dna_id":"dna-0"}`），`record.sh` 自动读取写入 `dna_id` 列；文件缺失则 `dna_id` 留 NULL（历史补录/未归属），不报错。

- `--account ALIAS`：传发布时所用账号（如 wx_mp `accounts.json` 的 alias）。DNA 表现评估按账号归一化基线，**多账号平台务必传**。
- `--dna-id`：显式覆盖 DNA 归属（优先级高于 dna-meta.json）。
- `--source-folder` 必须是作品目录（per-work 的 `<work>`）：统一为平台运营文件夹下的 `<platform>/outputs/<work>/`（如 `wx_mp/outputs/<title>/`、`douyin/outputs/<name>/`）。
- **落库语义 = upsert**：去重键 `(source_folder, publish_date)`。同一篇 + 同一平台 + 同一发布日重跑 `record.sh`（重发 / record 被重调）→ **更新旧行**（覆盖 title/url/dna_id/account/distribute_status），不重复插行；不同 `publish_date`（真正再发布 / 补发历史）仍新建行。返回 JSON 的 `action` 字段为 `inserted` 或 `updated`。⚠️ 这只管 DB 层去重——自媒体平台内容是更新还是去重, 由发布技能自己管。

```bash
# 正常发布后（dna-meta.json 自动读入 dna_id；--account 传发布账号）
published-track record \
  --platform wx_mp \
  --title "标题" \
  --content-type article \
  --source-folder "wx_mp/outputs/xxx" \
  --publish-url "https://mp.weixin.qq.com/s/xxx" \
  --account xiaobei-main

# 补登记历史作品（无 dna-meta.json → dna_id 留 NULL，不参与 DNA 评估）
published-track record \
  --platform xhs \
  --title "标题" \
  --content-type post \
  --source-folder "xhs/outputs/xxx/post" \
  --publish-url "https://www.xiaohongshu.com/xxx" \
  --notes "历史补录"
```

参数说明：
- `--distribute-status`：0=待分发（默认），1=无需分发，2=已分发。
- `--publish-date`：**省略即默认当日**。❌ 勿传 `"$(date +%Y-%m-%d)"`（exec 沙箱不展开 `$()`）；仅补登记非当日作品时传字面量如 `2026-06-14`。
- `--publish-url`：发布失败时留空并在 `--notes` 注明原因。
- `--dna-id` / `--account`：见上。

---

## 块二·数据更新

### 流程 2A·平台专家工具取数

本技能只负责发布记录、查询和 `update-metrics` 写库。按平台使用专家包内的取数工具：抖音 `douyin-engagement`、小红书 `xhs-engagement`、微信公众号 `wx-mp-engagement`、微信视频号 `wx-channel-engagement`。各工具按作品 ID 或发布记录行 ID 匹配并写库；不要从公开作品的缺失字段推断零值。B站、快手及其余平台由用户提供数据时再调用 `update-metrics` 补录。

抖音自动取数仅更新公开详情实际返回的点赞、评论、分享和收藏，播放量与后台深指标当前不自动获取；不可得的字段保留原值，库内默认零不代表平台实测零。视频与图文链接都可作为发布记录链接。`pub_douyin.plays`、`deep_metrics`、`deep_captured_at`、`deep_source` 保留用于历史兼容和用户主动提供数据时的补录；不能把历史值描述成本次自动取数结果。深指标仍只保留最新 JSON 及其时间、来源。

### 流程 2B·用户提供数据（Agent 补录）

用户主动告知已发布内容的信息，Agent 用 `record.sh` 录入基础信息，再用 `update-metrics.sh` 补录互动数据：

```bash
# 1) 录入基础信息（历史补录无 dna-meta.json → dna_id 自动留 NULL）
published-track record \
  --platform wx_mp --title "用户提供的标题" --content-type article \
  --source-folder "wx_mp/outputs/xxx" \
  --publish-url "https://mp.weixin.qq.com/s/xxx" \
  --publish-date "2026-06-14" --distribute-status 1 --notes "用户手动录入"

# 2) 补录互动数据（只传用户提供的字段，其余保持不变）
published-track update-metrics \
  --platform wx_mp --source-folder "wx_mp/outputs/xxx" \
  --reads 1234 --likes 56 --shares 12
```

各平台可传指标字段见上方「平台与表对应关系」"特有指标"列。

---

## 块三·查询与平台设置

### 流程 3A·查询待分发内容（白天 heartbeat 用）

```bash
published-track query-pending                # 所有平台待分发
published-track query-pending --platform wx_mp # 单平台
```

返回 JSON 数组，每项含 `platform`、`source_folder`、`title`、`publish_url`。

### 流程 3B·设置

**分发状态**：

```bash
published-track set-distribute-status \
  --platform wx_mp --source-folder "wx_mp/outputs/xxx" --status 2
published-track set-distribute-status \
  --platform wx_mp --id 3 --status 2
published-track set-distribute-status \
  --platform wx_mp --mark-all-distributed
```

### 流程 3C·通用查询（Agent 按需调用）

```bash
published-track query --platform zhihu            # 某平台全部记录
published-track query --platform zhihu --limit 10 # 最近 N 条
published-track check-published \
  --platform zhihu --source-folder "zhihu/outputs/xxx"              # 是否已发布
```

### 流程 3D·DNA 表现评估（凌晨 heartbeat 用）

待评估扫描与聚合由 `content-calibrator eval` 承担（按平台查 `dna_id` + `perf_evaluated` 列），本技能不再提供复盘查询脚本。

---

## 与发布技能的配合

所有发布技能（wx-mp-publisher、xhs-publish、gaoqian-article、wechat-channels-publish、bilibili-publish 等）的流程统一为 **发布 → 记录**（`published-track record` 带 `--account`；DNA 关联经 `dna-meta.json` 自动建立）。各技能 SKILL.md 的"发布记录"段标注此要求，主 agent 无需额外提醒。

**平台代号对照**：`wx-mp-publisher`/`sync-from-mp` → `wx_mp`；`wechat-channels-publish` → `wx_channel`；`xhs-publish` → `xhs`; `douyin-publish` → `douyin`；`bilibili-publish` → `bilibili`；`kuaishou-publish` → `kuaishou`；`zhihu-publish` → `zhihu`; `twitter-post` → `twitter`；`weibo-publish` → `weibo`.

## 平台启用状态与定时取数

`published-track platform-status --platform <douyin|xhs|wx_channel|wx_mp>` 只读工作区 `<platform>/calibration/platform-state.json` 的 `enabled` 字段，兼容旧 `.platform-state.json`。文件不存在返回 `enabled=false, reason=NOT_INITIALIZED`；字段缺失、类型错误或文件损坏返回 `ok=false, enabled=false` 与错误。不因查询而初始化或启用平台。

heartbeat 每个平台取数前查状态，仅 `ok=true, enabled=true` 时取数。抖音交给 `douyin-engagement daily`，其他平台交给各自专家包的 engagement 工具。完整定时流程见 HEARTBEAT.md。
