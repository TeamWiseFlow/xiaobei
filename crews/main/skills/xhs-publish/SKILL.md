---
name: xhs-publish
description: Publish image-text notes and video notes to Xiaohongshu (小红书) via
  creator COS upload + web_api v2. Supports image posts (up to 18 images),
  video posts, topics/hashtags. Uses login-manager for cookie-based authentication.
metadata:
  openclaw:
    emoji: 📕
    requires:
      bins:
      - python3
---

# 小红书发布（xhs-publish）

通过 creator 平台 COS 上传 + `/web_api/sns/v2/note` 创建笔记，支持图文和视频两种模式。使用 login-manager 管理 cookie 认证。签名使用 relay sign 服务。

上传流程：
1. 获取 COS 上传许可证：`creator.xiaohongshu.com/api/media/v1/upload/web/permit`
2. PUT 文件到 COS 对象存储（大文件自动分片）
3. 创建笔记：`edith.xiaohongshu.com/web_api/sns/v2/note`

---

## 前置条件

1. 探活按 login-manager SKILL.md 步骤 0：`camoufox-cli --session xhs-publish --persistent --json open "https://creator.xiaohongshu.com/"`（默认 headless）+ `snapshot` 看是否跳登录页（登录态有效 = 没跳登录页；跳登录页 = 失效）。
2. 若 exit 2，按 login-manager skill 的流程完成**有头手动**登录（xhs-publish 走有头登录）：
   - 启有头 session：`camoufox-cli --session xhs-publish --persistent --headed --json open "https://creator.xiaohongshu.com/publish/publish?source=official"`
   - 告知用户「**小红书创作者** 浏览器已打开，请在窗口里手动扫码登录，完成后告诉我」
   - 登录就位后**同时导出 cookie + UA**：
     - `camoufox-cli --session xhs-publish --persistent --json cookies export ~/.openclaw/logins/xhs-publish.json`
     - `camoufox-cli --session xhs-publish --persistent --json identity export ~/.openclaw/logins/xhs-publish.ua.json`
   - 登录后**不关 session**——持久化 session `xhs-publish` 登录态留着给本 skill 下次用，主动 close 会破坏复用。
3. 确保 `Pillow` 已安装（用于读取图片尺寸）：`pip install Pillow`

> **同时导入 cookie 和 UA**：xhs 的 `a1`/`websectiga` 等设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配。本 skill 的 `publish_xhs.py` 已同时读 `xhs-publish.json` + `xhs-publish.ua.json`。

---

## 使用方式

通过 PATH 调用 wrapper：`xhs-publish "<正文>" [附件...]`，无需拼接脚本路径。

### 图文笔记

```bash
xhs-publish \
  --mode image \
  --title "笔记标题" \
  --body "正文内容 #话题1 #话题2" \
  --images img1.jpg img2.jpg img3.jpg
```

### 视频笔记

```bash
xhs-publish \
  --mode video \
  --title "笔记标题" \
  --body "正文内容" \
  --video video.mp4 \
  --cover cover.jpg
```

#### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--mode` | 是 | `image` 或 `video` |
| `--title` | 是 | 笔记标题，最多 20 字 |
| `--body` | 是 | 正文内容，最多 1000 字；`#话题` 会自动提取为话题标签，**最多 10 个**（小红书硬约束） |
| `--images` | 图文必填 | 图片路径列表，最多 18 张，支持 jpg/png/webp |
| `--video` | 视频必填 | 视频文件路径，支持 mp4，建议 9:16 |
| `--cover` | 否 | 封面图路径；视频模式默认取第一帧 |
| `--topics` | 否 | 额外话题名称（与 body 中 #话题 互补） |
| `--private` | 否 | 设为仅自己可见（默认公开） |

#### ⚠️ 踩过的坑（必读）

### 坑 1：`--body` 必须传实际文字，不能传文件路径或用命令替换

**事故记录**：2026-06-16 凌晨首次发布时，用了
```bash
--body "$(cat output_articles/xxx/post.md)"
```
结果发布的正文是字面量字符串 `$(cat output_articles/xxx/post.md)`——一串乱码。原因：**exec sandbox 禁用 `$(...)` 命令替换**（参见 TOOLS.md "exec 命令规范"），Python 收到的是 shell 没展开的原始字符串。

**正确做法**：

把整段正文直接硬编码到命令里**
```bash
xhs-publish --body "这里就是实际正文，不是文件路径"
```

**禁止**：
- ❌ `--body "$(cat file.md)"`（`$()` 被沙箱禁掉）
- ❌ `--body post.md`（会被当字面量字符串传）

---

## 内容规范

- 标题不超过 20 字，正文不超过 1000 字
- 图片建议 3:4 竖版，最多 18 张
- 视频建议 9:16，时长 5s-15min
- AI 生成内容需声明（脚本默认声明）
- 禁止引流、导流内容
- **hashtag 最多 10 个**（小红书硬约束：超出会被静默丢弃或限流，建议选核心场景/人群词）

---

## Agent 工作流

1. 探活按 login-manager SKILL.md 步骤 0：`camoufox-cli --session xhs-publish --persistent --json open "https://creator.xiaohongshu.com/"`（默认 headless）+ `snapshot` 看是否跳登录页（exit 0 = 有效）
2. 准备素材（图片/视频 + 标题 + 正文）
3. 运行 `publish_xhs.py` 脚本
4. 检查 stdout JSON 输出：
   - `{"ok": true, "note_id": "xxx", "url": "https://www.xiaohongshu.com/explore/xxx"}` → 发布成功
   - `{"ok": false, "error": "AUTH_EXPIRED"}` → 触发 login-manager 重新登录，重试一次
   - `{"ok": false, "error": "..."}` → 其他错误，反馈用户

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| AUTH_EXPIRED | cookie 失效 | login-manager 重新登录后重试 |
| UPLOAD_FAILED | COS 上传失败 | 检查文件格式和大小，重试一次 |
| TITLE_TOO_LONG | 标题超 20 字 | 截断标题后重试 |
| BODY_TOO_LONG | 正文超 1000 字 | 精简正文后重试 |
| RATE_LIMIT | 发布频率限制 | 等待 30 分钟后重试 |
