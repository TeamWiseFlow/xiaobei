---
name: published-track
description: 发布记录追踪。使用 SQLite 数据库记录所有平台发布内容及其互动数据，按平台分表管理。三大块：与发布技能结合（发布记录 1B；打分+预测 1A 由 content-calibrator 负责）、数据更新、查询与平台设置。
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

## 数据库位置

`./db/published_track.db`（相对于工作区根目录）。初始化（幂等）：

```bash
./skills/published-track/scripts/init-db.sh
```

---

## 平台与表对应关系

| 平台 | 表名 | 内容类型 | 特有指标 |
|------|------|---------|---------|
| 微信公众号 | `pub_wx_mp` | article | reads, shares, favorites, likes, comments |
| 微信视频号 | `pub_wx_channel` | video | plays, likes, comments, shares, favorites |
| 知乎 | `pub_zhihu` | article/post | views, upvotes, comments, favorites |
| B站 | `pub_bilibili` | video | plays, danmaku, likes, coins, favorites, shares, comments |
| 抖音 | `pub_douyin` | video | plays, likes, comments, shares, favorites |
| 快手 | `pub_kuaishou` | video | plays, likes, comments, shares |
| 小红书 | `pub_xhs` | article/video/post | views, likes, favorites, comments, shares |
| Twitter/X | `pub_twitter` | post/video | views, likes, retweets, replies, bookmarks |

`--platform` 取「表名」去掉 `pub_` 前缀，如 `wx_mp`、`wx_channel`、`xhs`、`bilibili`。

---

## 表结构

每张表共享通用字段：`id`（自增主键）、`title`、`content_type`（article/video/post）、`source_folder`（原始文件夹，如 `output_articles/xxx`，**不做唯一约束，同内容可同平台多次发布**）、`publish_url`、`publish_date`（YYYY-MM-DD）、`distribute_status`（0=待分发，1=无需分发，2=已分发）、`notes`、`created_at`、`updated_at`。各平台特有互动指标默认 0，另有 `top_comment`（主要留言摘要）。

### content-calibrator 打分字段

| 字段 | 说明 |
|------|------|
| `cal_enabled` | 该记录是否参与 content-calibrator 复盘（0/1） |
| `cal_score_er/hp/sr/ql/na/ab/pv` | 7 维分（0-5）：情感共鸣/钩子强度/社会议题/金句密度/叙事性/受众广度/实用价值 |
| `cal_composite` | 综合分（0-10） |
| `cal_rubric_version` | 打分时 rubric 版本 |
| `cal_scored_at` | 打分时间 |

> 打分/预测按作品归集（per-work）：同一作品发到多个平台，各平台记录的 `cal_*` 分数值相同（取自 `<work>/calibration/score.json`）。rubric 全平台统一。

---

# 三大使用方式

## 块一·与发布技能结合

本块描述发布记录脚本的用法与编排意图。**实际编排由 `AGENTS.md`（"按需写作 / 发布记录管理与复盘"）与执行流类技能（`gaoqian-article`、`video-product`）承担**；各发布技能本身只管发布，不提及打分与记录。流程顺序为 **打分+预测(1A) → 发布 → 记录(1B)**。

### 流程 1A·打分+盲预测（发布前自检）

**打分+预测由 `content-calibrator` 技能负责**（blind sub-agent 一次出分+预测 + `score-only.sh` 阈值门 + `commit-prediction.sh` 落盘到 `<work>/calibration/` + 最多 2 轮改稿重打 + 平台未启用跳过；视频内容锚在脚本定稿前）。完整流程见 `content-calibrator/SKILL.md` 的"流程 1A·打分+盲预测"，本技能不重复描述。

### 流程 1B·发布记录（发布后）

发布成功后调用合并入口 `record.sh`。**分数不再通过入参传递**——`record.sh` 直接从 `--source-folder` 指向的 `<work>/calibration/score.json` 读取（per-work 权威落盘，composite + rubric_version 已在其中）。

- **默认（不传 `--no-cal`）**：要求 `<work>/calibration/score.json` + `prediction.md` 齐全 → 读分、置 `cal_enabled=1`；**缺失则报错退出**，提示主 agent 上一步（1A 打分+预测）未执行或落盘失败，须先补跑 `commit-prediction.sh` 再 record。
- **`--no-cal`**：显式跳过读分（补发 / 补登记历史作品 / 不打分场景）→ `cal_enabled=0`，不校验文件。

`--source-folder` 必须是**直接包含 `calibration/` 的目录**（即 per-work 的 `<work>`）：普通文章 `output_articles/<title>/`，gaoqian 双内容 `output_articles/<title>/article` 或 `.../post`，视频 `output_videos/<name>/`。
- **落库语义 = upsert**：去重键 `(source_folder, publish_date)`。同一篇 + 同一平台 + 同一发布日重跑 `record.sh`（重打分 / 重发 / record 被重调）→ **更新旧行**（覆盖 title/url/cal_*/distribute_status），不重复插行；不同 `publish_date`（真正再发布 / 补发历史）仍新建行。返回 JSON 的 `action` 字段为 `inserted` 或 `updated`。⚠️ 这只管 DB 层去重——公众号后台是否堆积草稿由 `wx-mp-publisher` 自身幂等性决定，本脚本管不到，发布前应查 `check-published.sh`。

```bash
# 正常发布后（1A 已落盘 score.json+prediction.md，record.sh 自动读分）
./skills/published-track/scripts/record.sh \
  --platform wx_mp \
  --title "标题" \
  --content-type article \
  --source-folder "output_articles/xxx" \
  --publish-url "https://mp.weixin.qq.com/s/xxx"

# 补发 / 补登记历史作品 / 不打分 → 显式 --no-cal
./skills/published-track/scripts/record.sh \
  --platform xhs \
  --title "标题" \
  --content-type post \
  --source-folder "output_articles/xxx/post" \
  --publish-url "https://www.xiaohongshu.com/xxx" \
  --no-cal
```

参数说明：
- `--distribute-status`：0=待分发（默认），1=无需分发，2=已分发。
- `--publish-date`：**省略即默认当日**。❌ 勿传 `"$(date +%Y-%m-%d)"`（exec 沙箱不展开 `$()`）；仅补登记非当日作品时传字面量如 `2026-06-14`。
- `--publish-url`：发布失败时留空并在 `--notes` 注明原因。
- `score-and-record.sh` 已合并为 `record.sh` 的薄 wrapper，兼容保留，新调用直接用 `record.sh`。

> **设计依据**：score.json 是 per-work 权威落盘，record.sh 从中读分可避免入参与落盘打架；默认强校验文件齐全以拦截漏跑 1A；`--no-cal` 为补发等明确不打分场景的显式出口。

---

## 块二·数据更新

### 流程 2A·自动更新（定时任务用）

`fetch-and-update-metrics.sh` 封装探活 → API 抓取 → DB 写入，凌晨复盘心跳调用：

```bash
# 通过 source-folder 从 DB 查 publish_url → 抓取 → 写入
./skills/published-track/scripts/fetch-and-update-metrics.sh \
  --platform <platform> --source-folder "output_articles/xxx"

# 按 id 逐条抓（同 folder 多条记录各自独立统计，推荐）
./skills/published-track/scripts/fetch-and-update-metrics.sh \
  --platform xhs --id <rowid> --xsec-token <tok> --xsec-source pc_feed
```

返回 JSON 统一格式：

| 场景 | 返回示例 |
|------|---------|
| 脚本获取成功 | `{"ok":true,"method":"script","platform":"bilibili","content_id":"BVxxx","metrics_params":"..."}` |
| Cookie 失效 | `{"ok":false,"error":"SESSION_EXPIRED","platform":"xhs","method":"script","hint":"..."}` |
| 需浏览器获取 | `{"ok":false,"method":"browser","platform":"twitter","hint":"使用 twitter-interact 技能..."}` |
| 需手动提供 | `{"ok":false,"method":"manual","platform":"wx_channel","hint":"该平台互动数据无法自动获取..."}` |

Exit codes：0=成功/浏览器/手动（非错误），1=一般错误，2=SESSION_EXPIRED。

- **脚本支持**：xhs、bilibili、douyin、kuaishou（走 `fetch-retro-data.ts` 纯 HTTP + cookie + UA）；wx_mp（走同目录下的 `wx-mp-engagement` skill
- **xhs 取数路线**：走 `get_note_by_id_from_html`——GET 笔记详情页 HTML 解析 `window.__INITIAL_STATE__` 拿互动计数，**不走** `/api/sns/web/v1/feed`（feed 需 xsec_token 且极易触发滑块/500）。仅需 cookie + 浏览器头，无需 relay 签名、无需 camoufox。
- **xsec_token 获取**：feed/HTML 路线均强制要 xsec_token，而 `publish_url` 不带、发布响应也不返，唯一来源是 profile 页 note 列表。`fetch-retro-data.ts` 在未传 `--xsec-token` 时，**纯 HTTP** GET 自己 profile 页（`/user/profile/{user_id}`，user_id 取 `xhs-user-id.cache`）解析 `user.notes` 建 note_id→xsec_token 映射（仅近期 ~20 条可见），查到目标 note 的 token 后再 GET 笔记详情页。`fetch-and-update-metrics.sh` 也会从 `publish_url` query 抽 xsec_token 透传（未来发布侧落 token 时直接生效）。笔记不在 profile 首页范围 → `NOTE_NOT_IN_PROFILE`。
- **xhs headers**：按 UA 家族区分 sec-ch-ua（camoufox=Firefox 不发 brand 列表，Chrome 发完整 sec-ch-ua），避免指纹破绽；sec-fetch 用 document/navigate（真实页面导航）。评论内容（`top_comment`）暂不抓（comment API 同样依赖 xsec_token，待发布侧落 token 后再补）。

### 流程 2B·用户提供数据（Agent 补录）

用户主动告知已发布内容的信息，Agent 用 `record.sh` 录入基础信息，再用 `update-metrics.sh` 补录互动数据：

```bash
# 1) 录入基础信息（补登记历史作品通常不打分 → --no-cal）
./skills/published-track/scripts/record.sh \
  --platform wx_mp --title "用户提供的标题" --content-type article \
  --source-folder "output_articles/xxx" \
  --publish-url "https://mp.weixin.qq.com/s/xxx" \
  --publish-date "2026-06-14" --distribute-status 1 --notes "用户手动录入" --no-cal

# 2) 补录互动数据（只传用户提供的字段，其余保持不变）
./skills/published-track/scripts/update-metrics.sh \
  --platform wx_mp --source-folder "output_articles/xxx" \
  --reads 1234 --likes 56 --shares 12
```

各平台可传指标字段见上方「平台与表对应关系」"特有指标"列。

---

## 块三·查询与平台设置

### 流程 3A·查询待分发内容（白天 heartbeat 用）

```bash
./skills/published-track/scripts/query-pending.sh                # 所有平台待分发
./skills/published-track/scripts/query-pending.sh --platform wx_mp # 单平台
```

返回 JSON 数组，每项含 `platform`、`source_folder`、`title`、`publish_url`。

### 流程 3B·设置

**分发状态**：

```bash
./skills/published-track/scripts/set-distribute-status.sh \
  --platform wx_mp --source-folder "output_articles/xxx" --status 2
./skills/published-track/scripts/set-distribute-status.sh \
  --platform wx_mp --id 3 --status 2
./skills/published-track/scripts/set-distribute-status.sh \
  --platform wx_mp --mark-all-distributed
```

**平台打分开关 + 全局阈值**：

```bash
./skills/content-calibrator/scripts/cal-toggle.sh --list                       # 全平台开关 + 全局阈值
./skills/content-calibrator/scripts/cal-toggle.sh --platform wx_mp --status    # 单平台开关
./skills/content-calibrator/scripts/cal-toggle.sh --platform wx_mp --enable    # 启用
./skills/content-calibrator/scripts/cal-toggle.sh --platform wx_mp --disable   # 停用（需确认）
./skills/content-calibrator/scripts/cal-toggle.sh --threshold          # 查看全局阈值
./skills/content-calibrator/scripts/cal-toggle.sh --set-threshold 2    # 设全局阈值
```

阈值语义：每维 0-5，需 **> 阈值**才放行发布；阈值 0 = 不拦截（起步默认）。**阈值为全局统一**（per-work 质量门，不分平台）。Agent 不得自动启用某平台打分或自动改阈值，必须告知用户由用户决定。阈值可由 Agent 在 content-calibrator 复盘后根据累积数据推荐并经用户确认后设置（见 `content-calibrator/SKILL.md` 复盘段）。

### 流程 3C·通用查询（Agent 按需调用）

```bash
./skills/published-track/scripts/query.sh --platform zhihu            # 某平台全部记录
./skills/published-track/scripts/query.sh --platform zhihu --limit 10 # 最近 N 条
./skills/published-track/scripts/check-published.sh \
  --platform zhihu --source-folder "output_articles/xxx"              # 是否已发布
```

---

## 与发布技能的配合

所有发布技能（wx-mp-publisher、xhs-publish、gaoqian-article、wechat-channels-publish、bilibili-publish 等）的流程统一为 **打分+预测(1A) → 发布 → 记录(1B)**。各技能 SKILL.md 的"打分评估 / 发布记录"段标注此要求，主 agent 无需额外提醒。

**平台代号对照**：`wx-mp-publisher`/`sync-from-mp` → `wx_mp`；`wechat-channels-publish` → `wx_channel`；`xhs-publish` → `xhs`。
