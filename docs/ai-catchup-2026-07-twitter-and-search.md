# AiToEarn + OpenCLI 借鉴分析（Twitter & Smart-Search，2026-07-05）

> **背景**：本轮已实施 Phase 4.5/4.6/5/7 续全部开发。本地实例已停止，openclaw v6.10 → v6.11 升级中（patches 全部 apply OK，正在 pnpm install + build）。
>
> **本任务**：基于用户问题"看 AiToEarn Twitter 规则" + "看 OpenCLI smart-search 升级"，输出**借鉴分析 + 是否 follow 升级**决策。

---

## 一、AiToEarn v2.5.0 Twitter 规则 + 借鉴分析

### 1.1 v2.4 → v2.5 变更（2026-05-21 → 2026-06-23）

#### v2.4.0（2026-05-21）"Twitter/X 能力增强"

- **新增前端探索控制台**（web 版）：时间线 / 我的推文 / 提及 / 书签 / 粉丝/关注 / 列表 / 搜索 / 推文详情 / 对话 / 引用 / 转推
- **支持互动操作**：回复 / 引用 / 点赞 / 转推 / 收藏

#### v2.5.0（2026-06-23）

- 重点是 Relay 架构变更（Server Relay / AI Relay），**Twitter 部分延续 v2.4 增强**
- "Twitter APIs now support richer posting, interaction, typed publishing options, and stronger response definitions"

### 1.2 平台 Twitter 规则（公开信息综合）

| 维度 | 标准 | Premium / Blue（v2.5 "richer posting" 可能支持更长）|
|------|------|------------------------------------------|
| 标准推文字符 | 280 | 25,000（"long post"）|
| URL 计数 | 23 字符（不论实际长度）| 23 字符 |
| Emoji 计数 | 2 字符 / 个 | 2 字符 / 个 |
| 图片 | 最多 4 / 帖 | 最多 4 / 帖 |
| 视频 | 1 / 帖，最长 2:20，最大 512MB（mastodon standard 14:00，X 更短）| 同 |
| GIF | 最大 15MB | 同 |
| 帖类型 | normal / long post / **quote** / **reply** | + 投票 / 线程 |

参考：[X Help: Types of Posts](https://help.x.com/en/using-x/types-of-posts) + AiToEarn 2025-09-16 v1.0.18 首次集成 Twitter。

### 1.3 本仓 twitter-post 现状

`crews/main/skills/twitter-post/SKILL.md` 涵盖：

| 能力 | 有？| 备注 |
|------|---|------|
| 推纯文本（标准 ≤ 280）| ✅ | 浏览器方案 |
| 推图片 | ✅ | locator.drop fallback |
| 推视频 | ✅ | max 512MB / 2:20 |
| Thread（连续推）| ✅ | "+" 拼接 |
| Quote Tweet（带评论引用）| ❌ | 缺失 |
| Reply to Tweet | ❌ | 缺失 |
| Long post（25,000 字符）| ❌ | 仅标准 280 |
| 互动操作（like / retweet / bookmark）| ❌ | 无 twitter-interact skill |
| Post 后取 permalink + stats | ⚠️ | 仅 URL |

### 1.4 借鉴建议

| 借鉴项 | 来源 | 价值 | 工作量 | 优先级 |
|--------|------|------|--------|--------|
| **Quote Tweet** | AiToEarn v2.4 | 用户转发 + 自己的评论；BD 场景强 | ~1h（SKILL.md + selector 验证）| P1 |
| **Reply to Tweet** | AiToEarn v2.4 | 评论监控 / 互动场景 | ~1h | P1 |
| **long post 25,000 字符** | AiToEarn v2.5 "richer posting" | 适配 Premium 用户 | ~30min（仅规则 + 检测）| P3 |
| **richer response 解析** | AiToEarn v2.5 | post 后立即拿 stats（view / reply / retweet）| ~1h | P2 |
| **互动操作：like / retweet / bookmark** | AiToEarn v2.4 | BD 自动化 engagement | ~2h（新建 twitter-interact skill）| P1 |
| **Anti-automation frequency limit** | AiToEarn 文档 | 强化 15min retry → 30min hard limit | ~30min | P2 |

**本轮建议动作**：
- **新建 `crews/main/skills/twitter-interact/`**：推 + 互动全套（v2.4 借鉴）—— ~2h
- **更新 `crews/main/skills/twitter-post/` SKILL.md**：
  - 加 Quote Tweet / Reply to Tweet 流程（v2.4 借鉴）
  - 加 Long post（25K）路径（v2.5 借鉴）
  - 加 Post 后解析 stats 的建议（v2.5 借鉴）
  - 强化 Anti-automation limit（参考 AiToEarn）

**架构约束提醒**：AiToEarn 走 SaaS Relay（aitoearn.ai 平台统一 token），本仓走**浏览器 + login-manager 中央 cookie**（Phase 4.5.2 D18 决策）—— **不搬代码**，只吸收 design pattern。

---

## 二、OpenCLI v1.8.2 smart-search 升级（v1.0.21 / v1.5 / v1.6 全部 catchup 综述）

### 2.1 OpenCLI 关键版本变化

| 版本 | 日期 | 关键变更 |
|------|------|----------|
| v1.5 → v1.6.5 | 2026-04 | "AI-driven self-healing" / "vigilant mode"（与本仓架构不兼容）|
| **v1.8.2** | **2026-06-03** | **Mid-cycle release：Site Maps Hub 子系统 + smart-search skill 恢复 + per-category source guides** |
| v1.8.4 | 2026-06-15 | 50+ adapter auth coverage / skills npm package |
| v1.0.21 | 2026-07-03 | chore only（v1.0.x 系列最末） |

### 2.2 v1.8.2 smart-search 关键升级

**`skills/smart-search/`**（从早期移除后**恢复**）：

- **per-category source guides**（8 分类）：
  - **AI**：AI 工具 / 模型 / 评测 / benchmark
  - **info**：新闻 / 媒体 / 行业动态
  - **media**：视频 / 音乐 / 图片 / 媒体库
  - **shopping**：电商 / 优惠 / 评测
  - **social**：社交平台 / 社区
  - **tech**：技术 / 开源 / 编程
  - **travel**：旅游 / 交通
  - **other**：兜底

**Site Maps Hub 子系统**（新）：
- `sitemaps/<site>/` 顶层目录（与 `clis/` `skills/` 并列）
- per-site navigation knowledge —— agent 需要的"导航知识"
- Twitter + HackerNews seeded as v1 baselines
- schema：`workflows.md` / `apis.md` / `pitfalls.md` + action `state_signature`（re-entry 用） + `adapter_health` enum + stable-id matching

### 2.3 本仓 smart-search 现状

`skills/smart-search/SKILL.md`：

- **借鉴 OpenCLI 早期 design pattern**（v2026.4 之前）：搜索频率限制 / fallback / re-entry / 摘要规范
- **主推引擎**（memory 05-smart-search-engines.md）：
  - **Bing**（国内网络下 Google 不稳定 → Bing 主推）
  - **百度** backup
  - **Quark** fallback（中文新闻 / 移动内容）
  - **Google** 已从 SKILL.md 删除（不推荐）
- **通用规则**（已借鉴）：
  - 频率限制：AI 站 1 次 / 非 AI 站 2 次
  - 搜索摘要规范
  - Sitemap pitfalls / fallback / re-entry

### 2.4 v1.8.2 per-category source guides 借鉴

**本仓 smart-search 缺**：
- 8 分类的"源 guides"（AI / info / media / shopping / social / tech / travel / other）
- 每个分类推荐的"权威站点 / 站内搜索 / 数据源"

**建议动作**：
- 在 `skills/smart-search/SKILL.md` 加 "Per-Category Source Guides" 章节
- 8 分类 + 分类下推荐源（基于 xiaobei 业务场景，不是 OpenCLI 全套）：
  - **AI**：openai.com / anthropic.com / huggingface.co / paperswithcode.com
  - **info**：reuters.com / bbc.com / 36kr.com（国内）/ 新浪财经
  - **media**：youtube.com / bilibili.com / pexels-footage（已搬入）/ pixabay-footage（已搬入）
  - **shopping**：amazon.com / taobao.com / 京东 / 拼多多
  - **social**：x.com / weibo.com / 小红书 / 抖音
  - **tech**：github.com / stackoverflow.com / 思否 / 掘金
  - **travel**：携程 / booking.com / tripadvisor
  - **other**：兜底（按需扩展）

**本轮借鉴动作**（~1h）：
- 写 `skills/smart-search/SKILL.md` 加 8 分类源 guides 章节
- **不**照搬 OpenCLI 完整 sitemap 体系（架构不兼容）—— 只吸收"分类 + 源 guides"这一最有价值的设计模式

### 2.5 Site Maps Hub 借鉴（**长期，不本轮**）

**Site Maps Hub** 概念价值：
- "per-site navigation knowledge"——agent 需要的"每个网站的导航知识"
- 写 schema：`workflows.md` / `apis.md` / `pitfalls.md` + `state_signature`

**本仓相似物**：
- `skills/browser-guide/SKILL.md §0` —— camoufox-cli 通用流程（不是 site-specific）
- 各种 skill 的 SKILL.md（viral-chaser / xhs-interact / twitter-post 等）—— 散落在各 skill 里

**本轮不实施 Site Maps Hub**（架构重组，超出本轮范围）。但**记录**到 Phase 6+ 后续考虑。

---

## 三、本轮建议动作总结

### 立即（如果用户同意）— 工作量 ~3h

1. **更新 twitter-post SKILL.md**（~1h）
   - 加 Quote Tweet / Reply to Tweet 流程
   - 加 Long post（25K）路径
   - 加 Post 后解析 stats
   - 强化 Anti-automation limit
2. **新建 twitter-interact skill**（~2h）
   - like / retweet / bookmark / 关注 / 取关
   - 借鉴 AiToEarn v2.4 互动操作

### 短期（建议作为单独一轮）

3. **更新 smart-search SKILL.md per-category source guides**（~1h）
   - 8 分类（AI/info/media/shopping/social/tech/travel/other）
   - 每分类 3-5 个推荐源

### 长期（Phase 6+ 后续）

4. **Site Maps Hub** 概念引入（架构重组，不本轮）

---

## 四、与本轮其他工作的交叉

| 关联项 | 状态 |
|--------|------|
| openclaw 升级 v6.10 → v6.11 | 进行中（pnpm install + build 后台跑）|
| camoufox-cli 集成（Phase 4.5）| ✅ 完成 |
| login-manager 中央 cookie（Phase 4.5.2）| ✅ 完成 |
| published-track 平台限制表更新 | 待评估（AiToEarn 18 平台表完整借鉴是更大工程）|

---

关联：
- `docs/upstream-catchup-2026-07.md`（6 上游综合 catchup 报告）
- `skills/smart-search/SKILL.md`（本仓 smart-search）
- `crews/main/skills/twitter-post/SKILL.md`（本仓 twitter-post）
- `~/.claude/projects/-home-wukong-wiseflow/memory/02-upstream-sources.md`（上游来源表）
- `~/.claude/projects/-home-wukong-wiseflow/memory/05-smart-search-engines.md`（smart-search 引擎策略）
