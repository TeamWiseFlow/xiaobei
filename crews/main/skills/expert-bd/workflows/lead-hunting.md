# Lead Hunting（潜在客户探索）

通过自媒体平台搜索特定关键词内容，按搜集策略筛选潜在客户。策略 A 逐一分析创作者主页判定是否为潜在客户；策略 B 扫描帖子评论区，根据评论内容挖掘潜在客户。

**依赖**：`smart-search`（其他平台搜索 URL）、`browser-guide`（其他平台浏览器操作）、`douyin-hunter`（抖音搜索与账号作品）、`douyin-im`（抖音私信）、`wx-mp-hunter`(微信公众号内容获取)、`email-ops`（邮件）、`bd-record`（去重记录）。

---

## 前置条件

执行前需确认以下信息（一次性任务与用户对话确认；定时任务从 HEARTBEAT.md 配置读取）：
- 搜集策略（A 发布者画像匹配 / B 评论区潜客挖掘，互斥，不可混用）
- 目标平台列表及对应的搜索关键词
- 潜在客户判定标准 / 评论筛选标准
- 每次最大探索量
- 反馈形式（列表报告 / Cold Touch 私信 / Email 联系）

---

## 执行流程

### Step 1: 准备工作

1. 确认当前配置（搜集策略、平台、关键词、判定标准、最大探索量）：定时任务从 HEARTBEAT.md 读取；一次性任务用与用户对话确认的配置
2. 确保浏览器可用（遵循 `browser-guide`）
3. 初始化 bd-record 数据库（幂等）：`bd-record init-db`

### Step 2: 逐平台搜索

对配置的每个平台，按顺序执行：

1. 抖音用 `douyin-hunter search`；其他平台使用对应搜索工具或 `smart-search` 构造 URL
2. 导航到搜索结果页，等待页面加载完成
3. 收集搜索结果列表中的内容链接（最多取配置的最大探索量）
   - 内容按由新到旧排序（使用平台默认排序）
   - 提取每个内容的创作者主页链接
4. 微信公众号内容使用 `wx-mp-hunter` 技能，不要使用浏览器

### Step 3 (策略 A): 逐创作者判定

对每个搜索到的创作者，按顺序执行：

1. 提取创作者标识信息（平台、creator_id、nickname、homepage_url）

2. 去重检查：
   ```bash
   bd-record check-creator --platform <平台> --creator-id <创作者ID>
   ```
   如果 `{"exists": true}`，则跳过该创作者，继续下一个

3. 抖音用 `douyin-hunter call user_profile` 与 `douyin-hunter user-posts` 读取资料和作品；其他平台导航到创作者主页

4. 读取创作者主页介绍

5. 浏览创作者前 10 个作品（不足则全部浏览）：
   - 对每个作品读取标题、简介/描述文字
   - 视频内容只需分析视频简介，不下载视频

6. 按预设的判定标准，判断是否符合潜在客户：
   - 分析创作者定位、内容方向、商业属性
   - 排除同行/竞对（内容与我们相似但非潜在客户）
   - 判定为潜在客户需给出明确理由

7. 记录到数据库（不管是否符合标准）：
   ```bash
   bd-record record-creator \
     --platform <平台> \
     --creator-id <创作者ID> \
     --nickname <昵称> \
     --homepage-url <主页URL> \
     --qualified <1或0> \
     --notes <判定理由>
   ```

8. 操作间隔：每个创作者之间保持 30-60 秒间隔，避免平台风控

### Step 3 (策略 B): 逐帖子评论区挖掘

对每个搜索到的帖子，按顺序执行：

1. 提取帖子标识（platform, post_url, post_title）

2. 抖音用 `douyin-hunter comments` 采样；其他平台导航到帖子详情页并等待评论区加载

3. 如果支持按时间排序，切换到按时间排序，确保评论从新到旧排列

4. 滚动浏览评论区，查找符合评论筛选标准的评论：
   - 提取评论者信息：昵称、user_id、IP属地、评论内容、评论日期
   - 微信公众号平台不支持评论获取

5. 对每条符合标准的评论：
   a. 以评论者 user_id 作为 --creator-id 做去重检查：
      ```bash
      bd-record check-creator --platform <平台> --creator-id <评论者user_id>
      ```
      如果 `{"exists": true}`，则跳过该评论者

   b. 记录到数据库：
      ```bash
      bd-record record-creator \
        --platform <平台> \
        --creator-id <评论者user_id> \
        --nickname <昵称> \
        --homepage-url <原贴URL> \
        --qualified <1或0> \
        --notes <评论内容及判定理由>
      ```

6. 操作间隔：每个帖子之间保持 30-60 秒间隔，避免平台风控

### Step 4: 汇总报告

1. 统计本批次结果：
   - 策略 A：探索总数、符合数、跳过数（已记录）
   - 策略 B：扫描帖子数、发现潜客数、跳过数（已记录）

2. 列出所有符合标准的潜在客户：
   - 策略 A：平台、昵称、ID、主页 URL、判定理由
   - 策略 B：平台、昵称、user_id、IP属地、评论内容、评论日期、原贴url

3. 按配置的反馈形式执行（仅策略 A 支持 Cold Touch 私信 / Email 联系）：
   - **Cold Touch 私信**：逐一给符合标准的创作者发送预设话术私信；抖音先核实数字 UID 并用 `douyin-im create --my-user-id <本账号UID> --to-user-id <收件人UID> --confirm` 建会话，再用返回的 `conversation_file` 执行 `douyin-im send --conversation-file <文件> --text <消息> --confirm`。其他平台使用其消息功能，每个私信之间保持 30-60 秒间隔
   - **Email 联系**：先校验 `email-ops` 所需环境变量是否齐全，若不全则跳过 Email 步骤并记录；齐全则使用 `email-ops` 发送邮件，每封邮件之间保持 30-60 秒间隔

4. 使用 message 工具将汇总报告发送给用户

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 平台搜索结果为空 | 记录平台名称，跳过该平台，继续下一个 |
| 创作者主页无法访问 | 记录"无法访问"后跳过，不阻塞流程 |
| 浏览器异常 | **不需要重启、不需要报错**！等待 30 秒后在原页面继续操作即可。若仍无法操作，再等 30 秒；若还不行，尝试关闭浏览器后重开；只有关闭重开后仍报错才是真的出错，需停止并反馈用户。 |
| 平台风控/验证码 | 停止当前平台操作，记录并继续下一个平台 |
| 持续错误 | spawn IT Engineer 协助排查，当前任务标记为部分完成 |
