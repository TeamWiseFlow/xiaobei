# YouTube

当前 crew 可调用 `youtube-hunter` 且任务命中其搜索、频道、播放列表、视频/评论读取能力时，优先读取其 SKILL.md。以下浏览器规则只供未配置该技能的 crew 使用，不因采集技能失败自动切换；这里的 default profile 不替代 youtube-hunter 的专属登录 profile。

> 时间/类型/排序规则参考 [OpenCLI](https://github.com/jackwener/OpenCLI/blob/b06ab7780e73d3021e12e0f170086c2d55675776/clis/youtube/search.js)。固定 session/profile `default`，带 --persistent。

## 搜索

### URL

```
https://www.youtube.com/results?search_query={keyword}
```

### 时间过滤（追加 `&sp=`）

- 一小时内：`EgIIAQ%3D%3D`
- 今天：`EgIIAg%3D%3D`
- 本周：`EgIIAw%3D%3D`
- 本月：`EgIIBA%3D%3D`
- 本年：`EgIIBQ%3D%3D`

### 类型过滤（追加 `&sp=`，与时间/排序互斥）

- 仅视频：`EgIQAQ%3D%3D`
- 仅 Shorts：`EgIQCQ%3D%3D`
- 仅频道：`EgIQAg%3D%3D`
- 仅播放列表：`EgIQAw%3D%3D`

### 排序（追加 `&sp=`，与类型互斥）

- 按上传日期：`CAI%3D`
- 按观看次数：`CAM%3D`
- 按评分：`CAE%3D`

同一 URL 只使用一个 sp；当前上游优先级为类型 > 时间 > 排序。需要组合条件时通过页面控件确认实际生成的 sp，不能把多个 Base64 值拼接。筛选结果、频道和 Shorts 以实际渲染内容为准。

### Cookie 初始化

1. Navigate `https://www.youtube.com`
2. 等待 3 秒
3. Navigate 到搜索 URL

### 多关键词

用 `+` 连接

## Pitfalls

### pitfall: heavy_client_rendering

- **触发**：导航到搜索结果页后立即提取
- **症状**：内容未加载
- **workaround**：等待 5 秒以上再 snapshot

### pitfall: video_tab_fallback

- **触发**：搜索结果中某些视频格式
- **症状**：`lockupViewModel` 格式的视频卡片被遗漏
- **workaround**：先 snapshot 读取真实卡片，不只盯 ytd-video-renderer；页面状态还可能含 lockupViewModel、shortsLockupViewModel、旧 reelItemRenderer 或播放列表/频道节点。字段名称不是固定 CSS selector，按实际 DOM/页面状态读，不构造 InnerTube 接口续查。

## Fallback

1. 搜索无结果 → 换关键词
2. 仍不足 → Bing 搜 `site:youtube.com {keyword}`
