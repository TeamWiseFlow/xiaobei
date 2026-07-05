# 抖音 (Douyin / TikTok China)

> last_verified: 2026-06-15 | 来源：OpenCLI clis/douyin/search.js

## 概览

- 域名：`www.douyin.com`
- 登录要求：**搜索需登录**，匿名访问搜索页返回空骨架
- Auth 策略：Cookie Warmup（必须先访问首页）

## 搜索

### URL

```
https://www.douyin.com/search/{keyword}?type={type}
```

类型（`type=`）：
- `general`（综合，默认）
- `video`（视频）
- `user`（用户）
- `live`（直播）

### Cookie Warmup

1. Navigate `https://www.douyin.com`
2. 等待 3 秒
3. Navigate 到搜索 URL

### 分页

抖音搜索使用**无限滚动**，无 URL 分页参数：
- 每次向下滚动加载更多
- 建议最多滚动 3 次（约 30 条）
- 滚动后等待 3-5 秒（抖音渲染较慢）

### DOM 提取提示

抖音搜索结果的关键特征（**class 名会漂移，只用稳定 hook**）：

```
容器：  [data-e2e="scroll-list"]
行：    容器内的 li
视频链接：a[href*="/video/"]
```

字段提取（SHAPE 解析法，因为 class 名被混淆）：
- **点赞数**：文本中匹配 `数字+万` 或 `数字+亿` 的模式
- **时长**：文本中匹配 `HH:MM` 或 `MM:SS` 的模式
- **作者**：文本中 `@` 后的昵称
- **描述**：剩余最长文本

### 多关键词

用 `%20` 连接：`xiaobei%20AI`

## Pitfalls

### pitfall: search_requires_login

- **触发**：未登录访问搜索页
- **症状**：页面渲染空骨架，无搜索结果卡片
- **workaround**：Cookie Warmup，若仍空 → browser-guide 扫码登录

### pitfall: obfuscated_classnames

- **触发**：尝试用 class 名选择器提取搜索结果
- **症状**：选择器失效（class 名如 `.ckopQfVu` 在每次构建后变化）
- **workaround**：只用 `data-e2e` 属性和 `a[href*="/video/"]` 等稳定 hook

### pitfall: no_xhr_available

- **触发**：尝试拦截 `/aweme/v1/web/general/search/single/` XHR
- **症状**：XHR 不触发（SSR 直出），或手动调用返空（缺 `a_bogus` / `msToken` 签名）
- **workaround**：直接从 DOM 提取，不走 XHR/API

### pitfall: render_timeout

- **触发**：导航到搜索页后立即提取
- **症状**：DOM 中还没有结果卡片
- **workaround**：等待 5-10 秒后再 snapshot，抖音 SPA 初始化较慢

## Fallback

1. 搜索结果为空 → 检查登录态 → 登录后重试
2. DOM 提取失败 → 等更长时间后重试 snapshot
3. 仍失败 → Bing 搜 `site:douyin.com {keyword}`

## Re-entry

- 在 `/search/...` 页且 `data-e2e="scroll-list"` 有内容 → 继续滚动/提取
- 在登录页 → browser-guide 登录后重新搜索
- 在首页 → 重新执行搜索流程
