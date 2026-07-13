---
name: smart-search
description: 智能搜索路由器。根据用户意图选择最佳搜索源，构造 URL 并导航，获取内容。
  Replaces the built-in web_search tool for targeted, platform-specific searches.
metadata:
  openclaw:
    emoji: 🔍
---

# Smart Search 智能搜索路由器

本技能**只负责搜索和阅读**，不负责发布、点赞、关注、回复等互动操作（那些由各平台专属技能处理）。

## 使用流程

1. **确定数据源**：根据用户意图和下方路由规则，选择搜索平台
2. **读取站点知识**：查看 `./sites/<platform>.md` 获取搜索 URL、分页、pitfalls、fallback
3. **执行搜索**：Cookie Warmup → 导航到搜索 URL → 等待加载 → 提取内容
4. **搜索摘要**：每次查询结束必须汇报（格式见下方）

## 路由规则

### 用户明确指定平台时

直接使用对应平台。平台名与站点知识文件对应：

| 用户可能说 | 站点文件 | 搜索类型 |
|-----------|---------|---------|
| 百度 / Baidu | `sites/general.md` → Baidu | 通用搜索 |
| Bing / 必应 | `sites/general.md` → Bing | 通用搜索（推荐） |
| 夸克 / Quark | `sites/general.md` → Quark | 通用搜索（fallback） |
| 知乎 | `sites/zhihu.md` | 中文问答 |
| 小红书 / XHS / 红薯 | `sites/xiaohongshu.md` | 生活方式/真实体验 |
| 抖音 / Douyin | `sites/douyin.md` | 短视频 |
| B站 / Bilibili | `sites/bilibili.md` | 视频/番剧 |
| 微博 / Weibo | `sites/weibo.md` | 热点/舆论 |
| YouTube / 油管 | `sites/youtube.md` | 视频 |
| Twitter / X / 推特 | `sites/twitter.md` | 实时讨论 |
| Reddit | `sites/reddit.md` | 社区讨论 |
| GitHub | `sites/github.md` | 代码/项目 |
| LinkedIn / 领英 | `sites/linkedin.md` | 职业/招聘 |
| 微信视频号 | `sites/wechat-channels.md` | 视频号内容 |
| 雪球 | `sites/financial.md` → 雪球 | 股票/金融 |
| arXiv | `sites/academic.md` → arXiv | 学术预印本 |
| 百度学术 | `sites/academic.md` → 百度学术 | 中文学术 |
| 万方 | `sites/academic.md` → 万方 | 中文学术 |
| Wikipedia | `sites/academic.md` → Wikipedia | 百科 |
| 贴吧 | `sites/tech.md` → 贴吧 | 兴趣社区 |
| Hacker News | `sites/tech.md` → HN | 科技社区 |
| V2EX | `sites/tech.md` → V2EX | 技术社区 |
| 路透社 / Reuters | `sites/news.md` | 国际新闻 |
| 国务院 | `sites/gov.md` | 政策文件 |
| Amazon | `sites/shopping.md` | 购物 |

### Per-Category Source Guides

每个分类列出**推荐源** + **典型用途** + **数据特征**：

| 分类 | 推荐源 | 典型用途 | 数据特征 |
|------|--------|---------|---------|
| **AI** | openai.com / anthropic.com / huggingface.co / paperswithcode.com / arxiv.org/cs.AI | LLM / 模型 / benchmark / 学术 | 强时效性；英文为主；benchmark 数字多 |
| **info** | reuters.com / bbc.com / ft.com / 36kr.com / 财新 / 新浪财经 / 澎湃 | 行业新闻 / 公司动态 / 政策 | 时效性强；中文 + 英文混合；财经类需付费墙 |
| **media** | youtube.com / bilibili.com / pexels-footage / pixabay-footage（本仓 skill）| 视频 / 音乐 / 媒体库 | 视频 metadata 重要；版权注意 |
| **shopping** | amazon.com / taobao.com / jd.com / pdd.cn | 电商 / 价格 / 评测 | 国内电商需登录；价格波动大 |
| **social** | x.com / weibo.com / xiaohongshu.com / douyin.com | 实时讨论 / 社区 | 短文本；高噪；需 cookie |
| **tech** | github.com / stackoverflow.com / jianshu.com / juejin.cn / segmentfault.com / v2ex.com | 代码 / 开源 / 编程 | 强时效；英文为主；stackoverflow 答案质量高 |
| **travel** | ctrip.com / booking.com / tripadvisor.com / mafengwo.cn | 旅游 / 交通 | 季节性强；多语种；图片重要 |
| **other** | duckduckgo.com / startpage.com / kagi.com / sogou.com / yandex.com | 兜底 / 隐私搜索 / 国内外通用 | 隐私优 DDG；国内兜底 sogou；俄罗斯 Yandex |

**快速选择规则**：
1. 用户**明确指定平台** → 用指定平台（不分类）
2. 用户**未指定** → 按"用户未指定平台时"表的意图特征路由
3. **国内**网络环境下 → DuckDuckGo 可能不稳，**优先** Bing / 夸克

**与路由表配合**：
- 路由表是"按意图 → 选平台"（平台名 → sites/<name>.md）
- 源 guides 是"按分类 → 列备选"（**多了** 1 步选平台的灵活性）
- 推荐组合：先看路由表选定首选 → 源 guides 给备选 → 1 个站不够时切换

本节是"per-category source guides"——最小可行实现。完整 Site Maps Hub（`sitemaps/<site>/` per-site navigation knowledge）超出范围，**不**做。

### 用户未指定平台时

按意图优先级自动路由：

| 意图特征 | 首选 | 补充 |
|---------|------|------|
| 中文通用/热点 | Bing | — |
| 中文深度问答 | 知乎 | — |
| 生活方式/真实体验 | 小红书 | — |
| 短视频内容 | 抖音 | — |
| 视频/番剧 | B站 | — |
| 中文舆论/热搜 | 微博 | — |
| 英文通用 | Bing | — |
| 技术/代码 | GitHub | — |
| 学术/论文 | arXiv | 百度学术 |
| 股票/金融 | 雪球 | — |
| 国际新闻 | Reuters | — |

## 频率限制

同一用户问题（同一意图链路，含追问澄清）内：

- **每个站点最多调用 2 次**（第 2 次必须有明确理由：结果过宽需限定、信息不足需补充角度）
- **不要第 3 次调用**同一站点；若信息仍不足，停止扩搜并说明缺口
- `camoufox-cli --session <s> --json open <search-url>` 导航到搜索 URL、`snapshot` 读取结果，每次导航计为 1 次调用
- Cookie Warmup（仅访问首页）不计入调用次数
- 因报错/超时/验证码/登录墙失败也算 1 次，**不要无限重试**

## Keyword 编码

- **空格**：`+` 用于 Bing、GitHub、Bilibili；`%20` 用于 Douyin、Twitter、Facebook、Zhihu；两者皆可用于 Baidu、Quark、YouTube
- **特殊字符**：URL-encode（`#` → `%23`，`&` → `%26`，`?` → `%3F`）
- **中文**：URL-encode（浏览器导航时自动处理）

## Cookie Warmup 速查

以下平台**必须**先访问首页再搜索，否则返回空结果或跳转登录：

| 平台 | Warmup URL |
|------|-----------|
| 知乎 | `https://www.zhihu.com` |
| 微博 | `https://weibo.com` |
| 小红书 | `https://www.xiaohongshu.com` |
| 抖音 | `https://www.douyin.com` |
| YouTube | `https://www.youtube.com` |
| Twitter/X | `https://x.com` |
| Reddit | `https://www.reddit.com` |
| 雪球 | `https://xueqiu.com` |
| LinkedIn | `https://www.linkedin.com` |
| TikTok | `https://www.tiktok.com` |
| 路透社 | `https://www.reuters.com` |

**不需要 Warmup**：Bing、Baidu、Quark、GitHub、arXiv、Wikipedia、HackerNews、V2EX、贴吧、Amazon、百度学术、万方、国务院

## 浏览器操作最佳实践

> **主力后端 = `target=camoufox`**（`camoufox-cli`）。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本节「流程 + 提示事项」走，不要照搬 `camoufox-cli ...` 命令——用你当前后端自带的浏览器工具语义调用即可。页面加载等待、超时处理、登录墙 / CAPTCHA 处理约定是**后端无关**的，照本节执行。

### 临时性 session（推荐）

搜索 / 浏览 / 取数走 **临时性 session**——不 cp 持久化模板、不带 `--persistent`，每次随机指纹，关闭自清（spec 补充 A，新闻等不登录站点）。

```bash
SESSION="search-$(date +%s)"
camoufox-cli --session "$SESSION" --headless --json open "<url>"
# …snapshot / eval / scroll 取数…
camoufox-cli --session "$SESSION" --json close
```

涉及登录的平台搜索（知乎 / 微博 / 小红书 / 抖音 / Twitter / Reddit / 雪球 / LinkedIn 等）走持久化 session。

### 页面加载等待

- 通用站点：`camoufox-cli --session <s> --json wait` 或 `sleep 3-5`
- 重度客户端渲染（Twitter/X、小红书、抖音）：**5 秒以上**
- `snapshot` 显示内容不完整时再等几秒重新 `snapshot`

### 超时错误处理

- **不重启浏览器**，不 teardown session
- 等待 **30 秒**后在原页面继续（`sleep 30` + `snapshot` 复核）
- 只有重开 session（`camoufox-cli --session <s> close` → 重 `open`）仍报错才是真正出错

> 同一 session 已有命令在跑时，新命令会 fail-first（返回 `session <name> 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。

### 表单输入

- 用 `camoufox-cli --session <s> --json type <ref> "<文本>"`（逐字符输入，触发完整事件链）
- **不用 `fill`**——一次性塞值不触发逐字事件链，受控组件 / mask 字段容易出问题

### snapshot ref 优先

`camoufox-cli --session <s> --json snapshot` 返回带 ref 的语义快照（`@e1` `@e2` …），后续 `click` / `type` / `scroll` 全部优先传 ref，不要自己 hack CSS selector。找不到元素时**先 snapshot 看真实 DOM 结构**再决定 selector 改写。

### 登录墙 / CAPTCHA

- 遇到登录墙、验证码、人机验证，遵循 **browser-guide** 技能
- 不要反复重试，最多 2 次后转其他数据源或告知用户

### 结果区定位

当 DOM snapshot 噪音过多（大量广告/推荐/脚手架 DOM）时，先 `snapshot` 拿语义结构，按 ref 锚到搜索结果区（`main` / `search-results` / `[role="list"]` 等语义角色），再 `eval` 在该子树内提取。不要在整页 selector 上盲试。

## 搜索后操作

1. 确认结果已加载（snapshot）
2. 遇到登录墙/CAPTCHA → browser-guide
3. 提取所需信息
4. 需要更多结果 → 查看 `sites/<platform>.md` 的分页方式
5. 提取完毕后**立即关闭标签页**

## 搜索摘要

**每次查询结束**，回答末尾必须追加搜索摘要，至少包含：

- 使用了什么站点
- 每个站点搜了什么关键词
- 每个站点调用了几次

格式：

```md
搜索摘要
- 站点：<site1> | 关键词：<term1> | 次数：<n>
- 站点：<site2> | 关键词：<term2>；<term3> | 次数：<n>
- 已跳过：<site3>，原因：达到频率上限
```

## 站点详细知识

各平台搜索的详细参数、分页、pitfalls、fallback、DOM 提取提示，见 `./sites/` 目录下对应文件。**执行搜索前务必先读对应站点文件**，避免踩坑。
