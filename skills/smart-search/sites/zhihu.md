# 知乎 (Zhihu)

> last_verified: 2026-06-15 | 来源：OpenCLI clis/zhihu/search.js + answer-detail.js

## 概览

- 域名：`www.zhihu.com`
- 登录要求：搜索可免登录，但部分内容需登录查看
- Auth 策略：Cookie Warmup（推荐先访问首页）

## 搜索

### URL

```
https://www.zhihu.com/search?type=content&q={keyword}
```

内容类型（`type=`）：
- `content`（综合，默认）
- `people`（用户）
- `scholar`（论文）
- `column`（专栏）
- `publication`（电子书）
- `topic`（话题）
- `zvideo`（视频）

### 过滤（综合搜索 type=content）

- 仅回答：`&vertical=answer`
- 仅文章：`&vertical=article`
- 仅视频：`&vertical=zvideo`

### 排序

- 最赞：`&sort=upvoted_count`
- 最新：`&sort=created_time`

### 时间范围

- 一天内：`&time_interval=a_day`
- 一周内：`&time_interval=a_week`
- 一月内：`&time_interval=a_month`
- 三个月内：`&time_interval=three_months`
- 半年内：`&time_interval=half_a_year`
- 一年内：`&time_interval=a_year`

### 分页

知乎搜索使用**offset 分页**：
- 每页 20 条
- 翻页：`&offset={n}` 其中 n = 20, 40, 60...
- 最大建议 1000 条（50 页）

### Cookie Warmup

1. Navigate `https://www.zhihu.com`
2. 等待 3 秒
3. Navigate 到搜索 URL

### 多关键词

用 `%20` 连接：`xiaobei%20AI%20搜索`

## 回答详情

单条回答全文 URL：
```
https://www.zhihu.com/question/{question_id}/answer/{answer_id}
```

文章详情 URL：
```
https://zhuanlan.zhihu.com/p/{article_id}
```

## Pitfalls

### pitfall: numeric_html_entities

- **触发**：读取搜索结果或回答详情时遇到 HTML 数字实体
- **症状**：文本中出现 `&#x4F60;` 或 `&#20320;` 等编码，而非中文字符
- **workaround**：解码 HTML 实体：`&#xHH;` → 对应 Unicode 字符，`&#DDD;` → 对应 Unicode 字符。Python: `html.unescape()`，JS: `new DOMParser().parseFromString(text, 'text/html').body.textContent`

### pitfall: search_pagination_harden

- **触发**：翻页到较深页码（offset > 200）
- **症状**：返回空结果或知乎风控拦截
- **workaround**：单次搜索建议不超过 5 页（100 条），更深层结果用新关键词限定

### pitfall: login_wall_for_detail

- **触发**：访问某些回答详情页
- **症状**：内容被截断，显示"查看完整回答需登录"
- **workaround**：Cookie Warmup 后访问，或用 browser-guide 处理登录

## Fallback

1. 知乎搜索 API 返空 → 检查是否登录墙 → 登录后重试
2. 搜索结果不够 → 换关键词或加时间/类型过滤
3. 仍不足 → Bing 搜 `site:zhihu.com {keyword}`

## Re-entry

- 在 `/search?...` 页 → 从当前 offset 继续翻页
- 在 `/question/...` 页 → 正在读取回答详情，继续提取
- 在 `/signin` 页 → browser-guide 登录后重新搜索
