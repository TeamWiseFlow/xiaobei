---
name: zhihu-publish
description: 通过 forked camoufox-cli 持久化 session zhihu 在知乎发布文章或回答。知乎无可用公开 API，需通过浏览器操作完成发布。
metadata:
  openclaw:
    emoji: 📝
---

# 知乎发布

通过 **camoufox-cli** 持久化 session `zhihu`（一个且只有一个持久化 session，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在知乎上发布文章或回答。知乎没有对个人开发者开放的发布 API，只能通过浏览器自动化。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本 skill 的「流程 + 提示事项」走——何时有头 / 何时无头 / 频率限制 / 错误处理约定是**后端无关**的，照本 skill 执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义调用即可。

---

## 前置条件

1. login-manager 已有 `zhihu` cookie + UA（中央存储 `~/.openclaw/logins/zhihu.json` + `~/.openclaw/logins/zhihu.ua.json`）
2. 首次使用 / cookie 失效需走 login-manager **有头手动**登录流（原则 3：zhihu 有头登录）：
   - `camoufox-cli --session zhihu --persistent --headed --json open "https://www.zhihu.com"`
   - 告知用户「**知乎** 浏览器已打开，请在窗口里手动登录，完成后告诉我」
   - 登录就位后**同时导出 cookie + UA**：
     - `camoufox-cli --session zhihu --persistent --json cookies export ~/.openclaw/logins/zhihu.json`
     - `camoufox-cli --session zhihu --persistent --json identity export ~/.openclaw/logins/zhihu.ua.json`
   - 关 session：`camoufox-cli --session zhihu --json close`

> **同时导入 cookie 和 UA**（原则 4，spec §4.2）：知乎设备指纹 cookie 必须配同一指纹的 UA，否则被风控错配。本 skill 走持久化 session `zhihu`（登录态 + 指纹冻结在 session profile 里），中央存储的 cookie/UA 仅用于探活与备份。

> zhihu 不在 login-manager 支持的 6 平台之列（spec §4），登录态管理**不走 login-manager SKILL.md**——本 skill 自管持久化 session `zhihu`，cookie/UA 导出/导入由 forked cli 的 `cookies export` / `identity export` / `cookies import` 命令完成。

---

## 发布文章

```
1. 启持久化 session + 打开创作页：
   camoufox-cli --session zhihu --persistent --headless --json open "https://zhuanlan.zhihu.com/write"
2. sleep 3-5 加载编辑器，snapshot 确认 .WriteIndex-page 或 .PostEditor 出现
3. snapshot 拿到标题输入框 ref：input[placeholder*="标题"] 或 .WriteIndex-titleInput input
4. camoufox-cli --session zhihu --persistent --json type <标题-ref> "文章标题"
   - 最长 100 字符
5. snapshot 拿到正文编辑器 ref：.ProseMirror 或 .public-DraftEditor-root 或 [contenteditable="true"]
6. camoufox-cli --session zhihu --persistent --json click <正文-ref> 聚焦编辑器
7. camoufox-cli --session zhihu --persistent --json type <正文-ref> "正文内容"
   - 知乎使用富文本编辑器（ProseMirror / Draft.js），不支持直接输入 Markdown
   - Markdown 内容需先转换为纯文本或手动分段输入
8. （可选）添加话题：snapshot 找"添加话题"按钮 ref → click → type 话题名称 → 从下拉选
9. snapshot 找"发布"按钮 ref → camoufox-cli --session zhihu --persistent --json click <发布-ref>
10. sleep 3，snapshot 确认发布成功（URL 变为文章详情页）
```

### 正文格式

知乎编辑器支持：标题（H1/H2）/ 粗体 / 斜体 / 链接 / 图片（需先上传）/ 代码块 / 引用 / 有序无序列表。**不支持直接输入 Markdown**——需通过编辑器工具栏或快捷键操作。

---

## 发布回答

```
1. 启持久化 session + 打开问题页：
   camoufox-cli --session zhihu --persistent --headless --json open "https://www.zhihu.com/question/{question_id}"
2. sleep 3-5 加载
3. snapshot 找"写回答"按钮 ref：button.Button--blue 或文本为"写回答"的按钮
4. camoufox-cli --session zhihu --persistent --json click <写回答-ref>
5. sleep 等编辑器出现，snapshot 拿到编辑器 ref
6. 填写回答内容（同文章正文步骤 6-7）
7. snapshot 找"发布"按钮 ref → click
8. sleep 3，snapshot 确认
```

---

## 图片上传

知乎编辑器插入图片需先上传：

```
1. snapshot 找编辑器工具栏的"图片"按钮 ref → click 触发文件选择
2. snapshot 拿到弹出的 <input type="file"> ref
3. camoufox-cli --session zhihu --persistent --json upload <图片-input-ref> <image.jpg>
   - forked cli upload 命令底层走 Playwright setInputFiles，无需 CDP setFileInput hack
4. sleep 等待上传完成（snapshot 看图片出现在编辑器）
```

---

## 必做约束

- **不主动 close 持久化 session `zhihu`**——登录态 + 指纹冻结留着下次用。只在 session 卡死时 `camoufox-cli --session zhihu --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session zhihu 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。
- 每次发布间隔 60 秒以上，避免触发反垃圾。

---

## Pitfalls

### pitfall: editor_not_prosemirror

- **触发**：知乎编辑器 DOM 结构变更
- **症状**：`.ProseMirror` 选择器找不到编辑器
- **workaround**：fallback 到 `.public-DraftEditor-root` 或 `[contenteditable="true"]`

### pitfall: markdown_not_supported

- **触发**：直接粘贴 Markdown 文本到编辑器
- **症状**：Markdown 标记原样显示，不被渲染
- **workaround**：用编辑器工具栏格式化，或分段输入（先输入纯文本，再用快捷键加粗/设标题等）

### pitfall: image_upload_timeout

- **触发**：上传大图片
- **症状**：上传进度卡住
- **workaround**：图片压缩到 2MB 以内再上传；超时后重试一次

### pitfall: anti_spam_check

- **触发**：短时间内发布多篇内容
- **症状**：出现验证码或"操作过于频繁"提示
- **workaround**：每次发布间隔 60 秒以上

### pitfall: numeric_html_entities

- **触发**：从知乎复制内容时
- **症状**：文本含 `&#x4F60;` 等编码
- **workaround**：解码 HTML 实体后再使用

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 未登录 / 登录墙 | 走前置条件的有头手动登录流，重试一次 |
| 编辑器未加载 | 等待 5 秒后重试，检查选择器 |
| 发布按钮灰色 | 检查标题/正文是否已填写 |
| 验证码 / 频率限制 | 等待 60 秒后重试 |
| session 正忙（fail-first） | 等当前操作完成再重试，不要盲试 |

## 发布后

**必须**调用 `published-track` 技能记录本次发布。
