# 部署后真机验证流程

> 部署到本地实例后，Agent 按本文档逐项真机验证。各 skill 的 SKILL.md 不写"spike 验证"开发期注释——统一收纳到本文档，避免开发仓路径污染 skill 指导。

---

## 抖音创作者中心（douyin-publish）

8 个 selector 需真机验证：
- 上传 input 元素：`input[type="file"][accept*="video"]`
- 标题输入：`input[placeholder*="标题"]`
- 描述 contenteditable：`div[contenteditable][data-placeholder*="描述"]`
- 发布按钮：`button:has-text("发布")`
- 上传成功文本："上传成功"
- 发布成功提示："发布成功"
- 视频管理页第一条 selector：`[class*="content-item"]:first-child`
- 视频链接 selector：`a[href*="/video/"]` 或 data-aweme-id

**验收**：跑通一条真实视频从 upload 到 get-link 全流程。

---

## 微信视频号创作者中心（wechat-channels-publish）

wujie shadow DOM 内的表单元素 selector 需真机验证：
- 上传触发按钮：`span.add-icon` 或 `div.upload-content`
- 视频文件 input（shadow DOM 内）
- 标题输入：`input[placeholder*="短标题"]`
- 描述输入：`div[contenteditable][data-placeholder="添加描述"]`
- 发表按钮：文本为"发表"或"发布"的按钮

**验收**：跑通一条真实视频从上传到取链接全流程。

---

## Twitter/X（twitter-post / twitter-interact）

- `[data-testid="like"]` / `[data-testid="retweet"]` / `[data-testid="reply"]` / `[data-testid="bookmark"]` 等 stats selector
- `[href*="/analytics"]` view 数 selector
- compose box `[data-testid="tweetTextarea_0"]`

**验收**：发一条纯文本推文 + 抓 stats；回复 / quote 各试一条。

---

## 通用约定

- **selector 改版**：各平台前端改版频繁，selector 失效时更新对应 skill 的脚本 / SKILL.md，并在本文档同步记录验证状态
- **指纹冻结**：持久化 session 首次 `--persistent` 启动后冻结 `camoufox-cli.json`，后续验证复用同一 session
- **fail-first 队列**：同 session 已有命令在跑时新命令直接 fail，验证时按顺序逐个跑，不要并发
