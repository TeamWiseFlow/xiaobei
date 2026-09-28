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

**脚本统一走顶层 wrapper `published-track <子命令>`**（在 PATH 中，零路径拼接）：`record` / `update-metrics` / `fetch-metrics` / `query` / `query-pending` / `check-published` / `set-distribute-status` / `init-db` / `migrate-v3`。ROOT 按 wrapper 真实路径解析（符号链接自动解析），不限调用目录。

---

## 平台与表对应关系

| 平台 | 表名 | 内容类型 | 特有指标 |
|------|------|---------|---------|
| 微信公众号 | `pub_wx_mp` | article/post | reads, shares, favorites, likes, comments |
| 微信视频号 | `pub_wx_channel` | video | plays, likes, comments, shares, favorites |
| 知乎 | `pub_zhihu` | article/post | views, upvotes, comments, favorites |
| B站 | `pub_bilibili` | video | plays, danmaku, likes, coins, favorites, shares, comments |
| 抖音 | `pub_douyin` | video | plays, likes, comments, shares, favorites, deep_metrics |
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

### 流程 2A·自动更新（定时任务用）

`fetch-and-update-metrics.sh` 封装探活 → API 抓取 → DB 写入，凌晨复盘心跳调用（仅 douyin 一个纯 HTTP 平台）：

```bash
# 通过 source-folder 从 DB 查 publish_url → 抓取 → 写入
published-track fetch-metrics \
  --platform <platform> --source-folder "<platform>/outputs/xxx"

# 按 id 逐条抓（同 folder 多条记录各自独立统计，推荐）
published-track fetch-metrics \
  --platform douyin --id <rowid>
```

返回 JSON 统一格式：

| 场景 | 返回示例 |
|------|---------|
| 脚本获取成功 | `{"ok":true,"method":"script","platform":"bilibili","content_id":"BVxxx","metrics_params":"..."}` |
| Cookie 失效 | `{"ok":false,"error":"SESSION_EXPIRED","platform":"douyin","method":"script","hint":"..."}` |
| 需浏览器获取 | `{"ok":false,"method":"browser","platform":"twitter","hint":"..."}` |
| 需手动提供 | `{"ok":false,"method":"manual","platform":"twitter","hint":"该平台互动数据无法自动获取..."}` |

Exit codes：0=成功/浏览器/手动（非错误），1=一般错误，2=SESSION_EXPIRED。

**douyin 取数双车道**（`fetch-retro-data.ts`）：
- 公开侧 `aweme/detail`：点赞/评论/分享/收藏。**play_count 公开侧恒为 0**（播放量仅创作者可见）。
- 创作侧 `creator/item/list`（`_shared/douyin-web.ts` `douyinCreatorItem`）：**播放量唯一来源**（`view_count`）+ 26 字段深指标（5s 完播率 / 2s 跳出率 / 封面曝光与点击率 / 粉丝观看占比 / 关注转化等），**视频与图文(note)作品通用**；creator 域 cookie-only 无需 a_bogus，用中央 douyin cookie 即可。失败时 graceful 降级（只缺播放量/深指标，公开侧数据不受影响）。**深指标存储**：`fetch-and-update-metrics.sh` 经 `--deep-file` 写入 `pub_douyin.deep_metrics`（单行 JSON，`deep_captured_at` / `deep_source` 同行），**只存最新值不留历史**（2026-09-18 定调）；`query.sh` 走 `SELECT *`，deep 列自动可见。
- **链接格式**：视频 `douyin.com/video/<id>`、图文 `douyin.com/note/<mid>` 均可提取 content_id（2026-09-17 起支持 note）。

- **脚本支持**：douyin（走 `fetch-retro-data.ts` 纯 HTTP + cookie + UA）。**自动取数仅覆盖完全支持 Expert 架构的 4 个平台**：douyin 走本技能 `fetch-metrics`；xhs / wx_mp / wx_channel 均不走本技能的 fetch-metrics（收到这三个平台直接 exit 1 指路）——xhs 走 `expert-xhs` 的 `xhs-engagement`（Creator 本地 HTTP），wx_mp 走 `expert-wx-mp` 的 `wx-mp-engagement`，wx_channel 走 `expert-wx-channel` 的 `wx-channel-engagement`。**bilibili / kuaishou 及其余平台不做自动取数**（收到直接 exit 1 报 `PLATFORM_OUT_OF_FETCH_SCOPE`）——发布记录与查询照常支持，只是不抓互动数据。

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

**平台代号对照**：`wx-mp-publisher`/`sync-from-mp` → `wx_mp`；`wechat-channels-publish` → `wx_channel`；`xhs-publish` → `xhs`; `douyin-video-publish` / `douyin-note-publish` → `douyin`；`bilibili-publish` → `bilibili`；`kuaishou-publish` → `kuaishou`；`zhihu-publish` → `zhihu`; `twitter-post` → `twitter`；`weibo-publish` → `weibo`.

## 平台启用状态与定时取数

`published-track platform-status --platform <douyin|xhs|wx_channel|wx_mp>` 只读工作区 `<platform>/calibration/platform-state.json` 的 `enabled` 字段，兼容旧 `.platform-state.json`。文件不存在返回 `enabled=false, reason=NOT_INITIALIZED`；字段缺失、类型错误或文件损坏返回 `ok=false, enabled=false` 与错误。不因查询而初始化或启用平台。

heartbeat 每个平台取数前查状态，仅 `ok=true, enabled=true` 时取数。抖音用 `published-track query --platform douyin --limit 30` 查询图文与视频合计最近 30 条，按返回的每条 `id` 依次 `published-track fetch-metrics --platform douyin --id <id>`。无需按天数过滤或手传 `--content-id`。登录失效停止该平台，其他单条错误记录后继续。完整定时流程见 HEARTBEAT.md。
