# Comment Engagement（评论区拓展）

通过自媒体平台搜索特定关键词内容，进入内容评论区按预设互动策略进行留言、回复或私信，拓展潜在客户或做品牌宣传（俗称“截流”）。

**依赖**：`smart-search`（构造搜索 URL）、`browser-guide`（浏览器操作）、`bd-record`（去重记录）、`xhs-hunter`（小红书搜索和评论采集）、`twitter-interact`（Twitter/X 点赞/转推/关注）、`twitter-post`（Twitter/X 回复，收纳在 `expert-twitter` 包内）。

> ⚠️ 小红书不支持本 workflow 的批量互动。用 `xhs-hunter` 采集笔记与评论；互动逐条执行并严格控制频次。

---

## 前置条件

执行前需确认以下信息（一次性任务与用户对话确认；定时任务从 HEARTBEAT.md 配置读取）：
- 目标平台列表及对应的搜索关键词
- 互动策略（direct_comment / reply_dm / direct_dm）
- 互动话术（用户指定或已确认的自动生成话术）
- 执行频率

---

## 执行流程

### Step 1: 准备工作

1. 确保浏览器可用（遵循 `browser-guide`）
2. 初始化 bd-record 数据库（幂等）：`bd-record init-db`

### Step 2: 逐平台搜索

对配置的每个平台，按顺序执行：

1. 使用 `smart-search` 构造该平台的关键词搜索 URL
2. 导航到搜索结果页，等待页面加载完成
3. 收集搜索结果列表中的内容链接（按由新到旧排序）
   - 每次采集数量参考配置，建议不超过 12 个

### Step 3: 逐内容互动

对每个搜索到的内容，按配置的互动策略执行。通用要求：输入使用 `type` + `slowly: true`，不要用 `fill()`。**X/Twitter 例外**：评论/回复含中文/日文/韩文时**禁用 `type`**（camoufox-cli `type` 逐字符按键流与 X Draft.js 异步处理竞态，中文实测丢字+乱序）——按 `expert-twitter/tools/twitter-post/SKILL.md`「CJK 正文输入与校验闸门」改用 eval + `document.execCommand("insertText")` + 发布前校验 MATCH。X 回复应走平台表中 `twitter-post` Reply workflow，同样适用该闸门。

#### 策略 A：直接留言（direct_comment）

1. 提取帖子标识（platform, post_url, post_title）

2. 去重检查：
   ```bash
   bd-record check-post --platform <平台> --post-url <帖子URL>
   ```
   如果 `{"replied": true}`，则跳过

3. 导航到帖子详情页

4. 按平台方式发表评论：
   - 小红书：用 `xhs-hunter` 核实笔记和评论后，按 `browser-guide` 在页面逐条发表评论
   - 其他平台：找到评论区输入框，输入话术，点击发送
   - 评论内容使用预设的话术

5. 等待 1-2 秒确认评论发出

6. 记录互动：
   ```bash
   bd-record record-post \
     --platform <平台> \
     --post-title <标题> \
     --post-url <帖子URL> \
     --strategy direct_comment \
     --reply-content <话术内容>
   ```

#### 策略 B：寻找特定留言并回复（reply_dm）

1. 提取帖子标识，做去重检查（同上）

2. 导航到帖子详情页，等待加载

3. 滚动浏览评论区，查找符合特征的留言：
   - 如"咨询/询价类留言"、"提问类留言"
   - 按预设的留言特征匹配

4. 对每条符合特征的留言：
   a. 检查是否已回复过该留言（通过 reply_target_id 查 `bd-record`）
   b. 如已回复则跳过
   c. 点击回复按钮
   d. 输入个性化回复内容（基于话术模板，结合留言具体内容微调）
   e. 点击发送
   f. 记录互动（含 `--reply-target-id` = 留言ID）

5. 每条回复之间保持 30-60 秒间隔

#### 策略 C：寻找特定留言并私信（direct_dm）

> 注意：此策略风控风险较高，不建议频繁使用。

1. 提取帖子标识，做去重检查（同上）

2. 导航到帖子详情页，等待加载

3. 滚动浏览评论区，查找符合特征的留言

4. 对每条符合特征的留言：
   a. 点击留言发布者头像/昵称进入其主页
   b. 检查是否已对该用户私信过（通过 `bd-record` 查 reply_target_id）
   c. 如已私信则跳过
   d. 找到私信/消息入口，发送预设话术
   e. 记录互动（含 `--reply-target-id` = 用户ID）

5. 每个私信之间保持 60 秒以上间隔

### Step 4: 汇总报告

1. 统计本批次结果：浏览帖子数、已跳过数（重复）、互动成功数、失败数
2. 使用 message 工具将汇总报告发送给用户

---

## 平台特殊处理

| 平台 | 互动方式 | 注意事项 |
|------|---------|---------|
| 小红书 | `xhs-hunter` 采集，浏览器逐条互动 | 每天评论不超过 20 条；仅发送已确认的话术 |
| 抖音 | browser 直接操作 | 评论内容避免包含网址和外链 |
| B站 | browser 直接操作 | 评论区支持链接 |
| 微博 | browser 直接操作 | 评论支持链接和 @ |
| Twitter/X | 回复走 `twitter-post` Reply workflow；点赞/转推/关注走 `twitter-interact` | 公开回复和 DM 均可 |
| Facebook | browser 直接操作 | 公开评论和 Messenger 均可 |

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 帖子无法访问（已删除/私密） | 跳过，记录到 bd-record 标记为已处理 |
| 评论区无法加载 | 重试一次，仍失败则跳过该帖子 |
| 评论发送失败（风控/限流） | 停止当前平台操作，记录并继续下一个平台 |
| 浏览器异常 | **不需要重启、不需要报错**！等待 30 秒后在原页面继续操作即可。若仍无法操作，再等 30 秒；若还不行，尝试关闭浏览器后重开；只有关闭重开后仍报错才是真的出错，需停止并反馈用户。 |
