---
name: intel-gathering
description: 定时监控特定信源（自媒体账号/网页），按预设标准提取商业情报，生成简报或报告。
---

# Intel Gathering 技能

定时监控特定信源（自媒体账号或网页），按预设提取标准采集商业情报，生成简报/报告交付用户。

**依赖技能**：`smart-search`（构造搜索 URL）、`browser-guide`（浏览器操作）、`rss-reader`（网页 RSS 监控）、`info-record`（采集记录与去重）

---

## 前置条件

执行前需确认以下信息：
- 监控信源列表（平台+账号 或 网页 URL）
- 提取标准（要采集什么信息）
- 交付形式（简报 / 报告 / 表格）

---

## 执行流程

### Step 1: 准备工作

```
1. 读取 HEARTBEAT.md 获取当前配置（信源列表、提取标准、交付形式）
2. 确保浏览器可用（遵循 browser-guide）
3. 初始化 info-record 数据库（幂等）：./skills/info-record/scripts/init-db.sh
```

### Step 2: 逐信源采集

对 HEARTBEAT.md 中配置的每个信源，按顺序执行：

#### 自媒体平台账号

```
1. 导航到该账号的内容列表页（主页/作品页）

2. 收集最新内容列表（按由新到旧排序）：
   - 仅分析发布日期为当日的内容（或上次执行后新发布的内容）
   - 如无法精确筛选日期，则取前 10 条内容

3. 对每条内容：
   a. 提取内容标识（source=平台-账号, title, author, publish_date）

   b. 去重检查：
      ./skills/info-record/scripts/check-content.sh --source <内容URL>
      如果 {"exists": true}，跳过该内容

   c. 打开内容详情页

   d. 按 HEARTBEAT.md 中预设的提取标准采集信息：
      - 阅读内容标题、正文/简介
      - 视频内容只需分析视频简介/描述文字，不下载视频
      - 提取与标准相关的关键信息

   e. 记录采集结果：
      ./skills/info-record/scripts/record-content.sh \
        --source <内容URL> \
        --source-type <平台标识> \
        --title <标题> \
        --author <作者> \
        --publish-date <发布日期> \
        --content <提取的关键信息>

   f. 每条内容之间保持适当间隔（10-30 秒）
```

#### 网页信源

```
1. 对于 RSS 支持的网站：使用 rss-reader 技能获取最新文章
   node ./skills/intel-gathering/scripts/fetch-rss.mjs <feed_url> --limit 10

2. 对于不支持 RSS 的网站：
   a. 使用 browser 导航到网页
   b. 等待加载完成
   c. 收集最新内容列表（按页面显示的新到旧排序）

3. 对每条内容：
   a. 去重检查（同上）
   b. 打开内容详情页（browser 或 web_fetch）
   c. 按提取标准采集信息
   d. 记录到 info-record
```

### Step 3: 生成交付物

```
1. 查询当日所有采集信息：
   ./skills/info-record/scripts/query-today.sh

2. 按 HEARTBEAT.md 中预设的交付形式生成交付物：

   简报模式：
   - 每条信息：一句话摘要 + 原文链接
   - 按信源分组

   报告模式：
   - 概述 + 按信源分章节 + 每节包含关键发现和分析
   - 标注信息来源链接

   监控表格模式：
   - Markdown 表格：日期 | 信源 | 标题 | 关键信息 | 原文链接

3. 使用 message 工具将交付物发送给用户
```

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 账号/页面无法访问 | 记录并跳过该信源，下次执行时重试 |
| 内容详情页打不开 | 记录 URL，标注"无法访问"后跳过 |
| RSS feed 不可用 | 降级为 browser 直接访问网页 |
| 网页结构变化（提取失败） | 记录信源和错误，不阻塞其他信源 |
| 浏览器异常 | **不需要重启、不需要报错**!等待 30 秒后在原页面继续操作即可。若仍无法操作,再等 30 秒;若还不行,尝试关闭浏览器后重开;只有关闭重开后仍报错才是真的出错,需停止并反馈用户。 |
| 持续错误 | spawn IT Engineer 协助排查 |

---

## 注意事项

- 视频内容通过视频简介/描述文字分析，不下载视频
- 微信公众号内容可能需要通过搜狗微信搜索或其他渠道访问
- 部分平台可能需要登录才能查看完整内容（遵循 browser-guide）
