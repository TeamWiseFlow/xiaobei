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

### 场景 A：用户提供小红书帖子 URL

用户直接给出一个或多个小红书图文笔记 URL（含 `xhslink.com/o/xxx` 短链），下载并分析。

```
1. 直接把 URL 传给脚本，脚本内部解析短链、提取 note_id 和 xsec_token：
   ./skills/xhs-content-ops/scripts/fetch_note_content.sh --url <url> --output-dir campaign_assets/<slug>/
2. 读取下载的图片和正文，执行对标分析
```

`--output-dir` 必须是工作区相对路径（如 `campaign_assets/<slug>/`），不要用 `/tmp`——否则后续 image 工具读不到图片。

若已单独拿到 note_id（例如从搜索结果 snapshot 里读的），也可用 `--note-id`，此时如同时有 `xsec_token` 请一并传 `--xsec-token` / `--xsec-source`，否则部分笔记 feed API 会返回 `note_card not found`。

### 场景 B：用户要求调研某话题

用户给出关键词，搜索小红书找到代表性图文笔记，下载并分析。

```
1. 导航到搜索页，按"最多点赞"排序
   URL: https://www.xiaohongshu.com/search_result?keyword=目标关键词
2. Snapshot 获取搜索结果列表，选取前 3-5 篇高互动图文笔记
3. 对每篇笔记，提取 note_id，运行图文下载脚本
4. 汇总所有下载内容，执行竞品对标分析
```

### 场景 C：用户要求对标分析

用户要求将自己的内容与小红书上的内容做对标。

```
1. 搜索目标关键词，找到 3-5 篇代表性图文笔记
2. 下载图片和正文
3. 与用户提供的内容逐项对标：
   - 标题风格对比
   - 正文结构对比
   - 话题标签使用对比
   - 图片构图/风格对比
   - 互动数据对比
4. 输出对标报告和改进建议
```

---

## 图文下载脚本

### 前置条件

1. 探活按 login-manager SKILL.md 步骤 0：`camoufox-cli --session xhs-browse --persistent --headless --json open "https://www.xiaohongshu.com/"` + `snapshot` 看是否跳登录页（登录态有效 = 没跳登录页；跳登录页 = 失效）。
2. 若 exit 2，按 login-manager skill 的流程完成**有头手动**登录（原则 3：xhs-browse 有头登录）：
   - 启有头 session：`camoufox-cli --session xhs-browse --persistent --headed --json open "https://www.xiaohongshu.com/"`
   - 告知用户「**小红书** 浏览器已打开，请在窗口里手动扫码登录，完成后告诉我」
   - 登录就位后**同时导出 cookie + UA**：
     - `camoufox-cli --session xhs-browse --persistent --json cookies export ~/.openclaw/logins/xhs-browse.json`
     - `camoufox-cli --session xhs-browse --persistent --json identity export ~/.openclaw/logins/xhs-browse.ua.json`
   - 关 session：`camoufox-cli --session xhs-browse --json close`

> **同时导入 cookie 和 UA**（原则 4，spec §4.2）：xhs 的 `a1`/`websectiga` 等设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配（2026-06-29 CDP 注入教训）。本 skill 的 `fetch_note_content.ts` 已同时读 `xhs-browse.json` + `xhs-browse.ua.json`。

### 运行

```bash
# 推荐：直接传 URL（支持 xhslink.com 短链和完整 explore 链接，脚本自动解析 note_id + xsec_token）
./skills/xhs-content-ops/scripts/fetch_note_content.sh \
  --url <url> \
  --output-dir <output_dir>

# 或：已拿到 note-id 时（若有 xsec_token 一并传，否则部分笔记会 note_card not found）
./skills/xhs-content-ops/scripts/fetch_note_content.sh \
  --note-id <note_id> \
  --xsec-token <token> \
  --xsec-source <source> \
  --output-dir <output_dir>
```

> **⚠️ `--output-dir` 必须用工作区相对路径**（如 `campaign_assets/<slug>/`），**不要用 `/tmp`**。后续要用 image 工具读取下载的图片做视觉分析，而 image 工具只能读允许目录（工作区）下的文件，`/tmp` 下的图片会被拒绝（`Local media path is not under an allowed directory`），导致整轮分析白跑、还要重跑一次。

**参数：**

| 参数 | 必填 | 说明 |
|------|------|------|
| `--url` | 二选一 | 笔记 URL（`xhslink.com` 短链或 `xiaohongshu.com/explore/...` 完整链接），脚本自动解析 note_id + xsec_token |
| `--note-id` | 二选一 | 小红书笔记 ID（与 `--url` 二选一） |
| `--xsec-token` | 否 | xsec_token（用 `--note-id` 时若同时有 token 建议传；用 `--url` 时脚本自动提取） |
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

**Exit codes：**
- `0` — 成功
- `1` — 一般错误
- `2` — Cookie 无效 → 触发 login-manager 重新登录

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
