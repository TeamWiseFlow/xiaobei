---
name: xhs-content-ops
description: 小红书图文内容调研与对标分析。搜索小红书图文笔记，下载图片和正文进行深度分析。当用户要求小红书竞品分析、对标分析、图文内容调研时触发。视频内容请使用 viral-chaser 技能。
metadata:
  openclaw:
    emoji: 📊
    requires:
      bins:
      - python3
      - node
---

# 小红书图文内容调研与对标分析

用于搜索小红书图文笔记、下载图片和正文、进行竞品对标分析。

**⚠️ 本技能仅处理图文笔记**。视频笔记请使用 **viral-chaser** 技能。

---

## 技能边界

| 能力 | 本技能 | 其他技能 |
|------|--------|---------|
| 搜索/浏览小红书 | ✅ camoufox-cli session | — |
| 图文笔记下载与分析 | ✅ 脚本 | — |
| 视频笔记下载与分析 | ❌ | → viral-chaser |
| 发布笔记 | ❌ | → xhs-publish |
| 评论/点赞/收藏 | ❌ | → xhs-interact |

---

## ⚙️ 执行方式（强制）

本技能涉及多步骤生产流程，你应该 self-spawn 一个 subagent 来执行，原因：subagent 独立上下文，不会因对话历史积累而降低输出质量。

你只负责跟进subagent的执行，避免它们长时间卡在某个步骤，必要时可以提供提示或调整执行策略。

---

## 小红书 URL 格式参考

| 页面 | URL |
|------|-----|
| 搜索结果 | `https://www.xiaohongshu.com/search_result?keyword=关键词` |
| 笔记详情 | `https://www.xiaohongshu.com/explore/{feed_id}?xsec_token={token}&xsec_source=pc_feed` |
| 用户主页 | `https://www.xiaohongshu.com/user/profile/{user_id}` |

**提取 feed_id 和 xsec_token**：打开笔记页面后，从浏览器地址栏 URL 中读取。

---

## 使用场景

> **场景 B/C 的浏览器搜索部分**走 **camoufox-cli**（复用 `xhs-browse` 持久化 session，`--session xhs-browse --persistent`，不开独立 session、不 import cookie）——`open` 搜索页 + `snapshot` 读搜索结果列表 + `eval` 拿笔记 URL 提 note_id/xsec_token。拿到 note_id 后切脚本下载。
> 期间如果发现登录失效, 则走 login-manager skill 流程，复用 `xhs-browse` 持久化 session（消费者域 `www.xiaohongshu.com`）

### 场景 A：用户提供小红书帖子 URL

用户直接给出一个或多个小红书图文笔记 URL（含 `xhslink.com/o/xxx` 短链），下载并分析。

```
1. 直接把 URL 传给脚本，脚本内部解析短链、提取 note_id 和 xsec_token：
   xhs-content-ops --url <url> --output-dir campaign_assets/<slug>/

   ⚠️ 脚本走无 cookie SSR HTML 路线（GET 笔记详情页 HTML 解析 og:meta + `__INITIAL_STATE__`，不走 feed API/relay 签名）。无 cookie 抓不到时才用本机 xhs-browse cookie + 同指纹 UA 回退（同时读 ~/.openclaw/logins/xhs-browse.json + ~/.openclaw/logins/xhs-browse.ua.json，同一指纹下的 cookie 才不会被风控错配）。

2. 读取下载的图片和正文，执行对标分析
```

`--output-dir` 必须是工作区相对路径（如 `campaign_assets/<slug>/`），不要用 `/tmp`——否则后续 image 工具读不到图片。

若已单独拿到 note_id（例如从搜索结果 snapshot 里读的），也可用 `--note-id`，但**必须同时传 `--xsec-token` / `--xsec-source`**（从搜索 snapshot 的笔记 URL 里抽）——HTML 路线无 xsec_token 会拿到空页。

### 场景 B：用户要求调研某话题

用户给出关键词，搜索小红书找到代表性图文笔记，下载并分析。

```
1.走 camoufox-cli 浏览器操作（复用 xhs-browse 持久化 session）导航到搜索页，按"最多点赞"排序：
   camoufox-cli --session xhs-browse --persistent --json open "https://www.xiaohongshu.com/search_result?keyword=目标关键词"
3. camoufox-cli snapshot 获取搜索结果列表，选取前 3-5 篇高互动图文笔记；用 eval 从笔记链接里提取 note_id + xsec_token（URL 格式见「小红书 URL 格式参考」段，从 explore/{feed_id}?xsec_token={token} 解）。

  上面过程中，如果发现登录失效, 则走 login-manager skill 流程，复用 `xhs-browse` 持久化 session（消费者域 `www.xiaohongshu.com`）

4. 对每篇笔记，运行图文下载脚本（无 cookie HTML 路线，cookie 仅回退，无需手动传）：
   xhs-content-ops --note-id <note_id> --xsec-token <token> --xsec-source pc_feed --output-dir campaign_assets/<slug>/

   脚本走无 cookie SSR HTML 路线（带 xsec_token 的公开笔记无需 cookie）；无 cookie 抓不到（滑块/空页）时用本机 xhs-browse cookie 回退一次，仍失败 exit 2 交 login-manager 重登。

5. 汇总所有下载内容，执行竞品对标分析
```

### 场景 C：用户要求对标分析

用户要求将自己的内容与小红书上的内容做对标。

```
1.走 camoufox-cli 浏览器操作（复用 xhs-browse 持久化 session）搜索目标关键词，找到 3-5 篇代表性图文笔记（同场景 B 的 camoufox-cli 搜索流程），用 eval 提 note_id + xsec_token。

  上面过程中，如果发现登录失效, 则走 login-manager skill 流程，复用 `xhs-browse` 持久化 session（消费者域 `www.xiaohongshu.com`）

3. 对每篇笔记，运行图文下载脚本下载图片和正文（无 cookie HTML 路线，cookie 仅回退，无需手动传）：
   xhs-content-ops --note-id <note_id> --xsec-token <token> --xsec-source pc_feed --output-dir campaign_assets/<slug>/

      脚本走无 cookie SSR HTML 路线（带 xsec_token 的公开笔记无需 cookie）；无 cookie 抓不到（滑块/空页）时用本机 xhs-browse cookie 回退一次，仍失败 exit 2 交 login-manager 重登。

4. 与用户提供的内容逐项对标：
   - 标题风格对比
   - 正文结构对比
   - 话题标签使用对比
   - 图片构图/风格对比
   - 互动数据对比
5. 输出对标报告和改进建议
```

---

## 图文下载脚本

### 运行

通过 PATH 调用 wrapper：`xhs-content-ops <cmd>`，无需手动拼接 node 命令或脚本路径。

> 脚本走无 cookie SSR HTML 路线，cookie 仅作回退；若 cookie 回退仍失败（exit 2），则重走 login-manager 技能的登录流程。

```bash
# 推荐：直接传 URL（支持 xhslink.com 短链和完整 explore 链接，脚本自动解析 note_id + xsec_token）
xhs-content-ops \
  --url <url> \
  --output-dir <output_dir>

# 或：已拿到 note-id 时（必须同时传 xsec_token，否则 HTML 路线拿到空页）
xhs-content-ops \
  --note-id <note_id> \
  --xsec-token <token> \
  --xsec-source <source> \
  --output-dir <output_dir>
```

> **⚠️ `--output-dir` 必须用工作区相对路径**（如 `campaign_assets/<slug>/`），**不要用 `/tmp`**。后续要用 image 工具读取下载的图片做视觉分析，而 image 工具只能读允许目录（工作区）下的文件，`/tmp` 下的图片会被拒绝（`Local media path is not under an allowed directory`），导致整轮分析白跑、还要重跑一次。

> 脚本不再依赖 relay 签名 / OFB_KEY（HTML 路线无需签名）。`exit 1` 的 `NO_XSEC_TOKEN` 表示缺 xsec_token；`NEED_VERIFY` 表示触发滑块。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--url` | 二选一 | 笔记 URL（`xhslink.com` 短链或 `xiaohongshu.com/explore/...` 完整链接），脚本自动解析 note_id + xsec_token |
| `--note-id` | 二选一 | 小红书笔记 ID（与 `--url` 二选一） |
| `--xsec-token` | `--note-id` 时必填 | xsec_token（用 `--note-id` 时必传，否则 HTML 路线拿空页；用 `--url` 时脚本自动提取） |
| `--xsec-source` | 否 | xsec_source，默认 `pc_feed` |
| `--output-dir` | 是 | 输出目录，**必须工作区相对路径**（如 `campaign_assets/<slug>/`），图片和正文保存到此 |

**输出：** JSON 到 stdout

```json
{
  "ok": true,
  "noteId": "xxx",
  "noteType": "normal",
  "title": "笔记标题",
  "desc": "正文内容",
  "author": "作者昵称",
  "stats": { "likeCount": 100, "collectCount": 50, "commentCount": 20, "shareCount": 10 },
  "images": ["output_dir/img_00.jpg", "output_dir/img_01.jpg"],
  "coverUrl": "https://...",
  "tags": ["话题1", "话题2"]
}
```

### ⚠️ 视频笔记处理

如果目标笔记是视频类型（`noteType: "video"`），脚本会返回错误并提示使用 viral-chaser：

```json
{
  "ok": false,
  "error": "VIDEO_NOTE",
  "noteId": "xxx",
  "noteType": "video",
  "hint": "请使用 viral-chaser 技能下载和分析视频笔记"
}
```

---

## 分析框架

### 竞品对标分析

对下载的图文笔记逐项分析：

| 维度 | 分析内容 |
|------|---------|
| 标题 | 字数、风格（提问/陈述/数字/痛点）、是否含话题标签 |
| 正文 | 结构（开头钩子→价值传递→CTA）、字数、段落数、话题标签数 |
| 图片 | 数量、构图类型（产品展示/场景/文字卡片/对比图）、色调风格 |
| 互动 | 点赞/收藏/评论/分享比例，收藏率（收藏/点赞）反映内容价值 |
| 话题 | 标签数量、是否覆盖核心场景词和人群词 |

### 改进建议

基于对标结果，给出 3-5 条可直接落地的改进建议。

---

## 必做约束

- 复合流程中每一步都应向用户报告进度
- **控制频率**：搜索翻页间隔 3-5 秒，下载间隔 5-10 秒
- 所有分析结果使用 markdown 表格结构化呈现
- **仅处理图文笔记**：遇到视频笔记，提示用户使用 viral-chaser

---

## 运营建议

- **调研频率**：每周 1-2 次，跟踪竞品动态
- **发布时间**：工作日 12:00-13:00、18:00-21:00 为高峰时段
- **内容合规**：不得出现引流导流信息，不得搬运他人内容

## 失败处理

| 情况 | 处理 |
|------|------|
| 搜索页面出现登录墙 | 走 login-manager 有头手动登录流程，重试一次 |
| 笔记无法访问 | 该笔记可能已删除或设为私密，跳过 |
| Cookie 过期 (exit 2) | login-manager 重新登录后重试一次 |
| 视频笔记 | 提示用户使用 viral-chaser 技能 |
