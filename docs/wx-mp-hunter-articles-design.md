# wx-mp-hunter 借鉴 wechat-article-exporter 设计（2026-07-05）

> **背景**：用户原话——"目前我们的 crews/main/skills/wx-mp-hunter 技能主要是获取微信公众号的什么？html嘛？图片可以拿下来吗？似乎这一块我们没有完全继承 https://github.com/wechat-article/wechat-article-exporter 的能力"。
>
> **答**：当前只返回 markdown 字符串（图片保留 URL，**不**下载到本地）。**没有**继承 wechat-article-exporter 的图片本地化 + 完整 HTML 导出能力。

## 一、wechat-article-exporter 关键能力

| 能力 | 描述 | 适合借鉴？ |
|------|------|----------|
| **HTML 全文保存** | 单文件 `.html` 含所有内联样式 + 图片（`data:` URI 或外链） | 🟡 可借鉴（agent 阅读 HTML 比 markdown 完整） |
| **图片本地化** | 所有 `<img>` 下载到 `./images/`，HTML 改用相对路径 | 🟢 **强相关**（当前最缺） |
| **Markdown 导出** | 完整 markdown + 本地图片相对路径 | 🟢 强相关 |
| **CLI / 包格式** | 支持 CLI / GUI / 浏览器扩展 | 🟡 仅 CLI 可借鉴 |
| **元数据导出** | 标题 / 作者 / 发布时间 / 公众号 / 摘要 / 阅读数 | 🟡 部分可借鉴 |
| **浏览器扩展** | Chrome / Edge 扩展，一键下载 | ❌ 不适合本仓（容器内 + D18 camoufox 主推） |

## 二、本仓借鉴范围（**最小可用版**）

### 2.1 借鉴哪些
- ✅ **图片本地化**（强）：fetch 公众号文章时，把 `<img src="https://mmbiz...">` 下载到 `output-dir/images/<hash>.<ext>`，markdown 改 `![](images/<hash>.<ext>)`
- ✅ **HTML 全文保存**（中）：可选输出 `<output-dir>/article.html`（含内联样式 + 完整 DOM）
- ✅ **元数据**（强）：输出 `<output-dir>/meta.json`（标题 / 作者 / 发布时间 / 公众号）
- ✅ **CLI 标志** `--download-images <dir>` 控制是否下载

### 2.2 不做
- ❌ zip 打包（本仓无需求）
- ❌ GUI / 浏览器扩展（容器内 + D18）
- ❌ 阅读数 / 点赞数（需要 cookie + 风控）
- ❌ 评论抓取（用户原 SKILL.md 明示 not support）
- ❌ video 视频号（同上 not support）

## 三、实现设计

### 3.1 新接口（保持兼容）

```
fetch-article <url>
  [--output-dir <dir>]               # 落盘目录（不传则只返 stdout JSON，不落盘）
  [--download-images]                  # 启用图片本地化（仅 --output-dir 时生效）
  [--html]                              # 额外落 .html 全文
```

**默认行为不变**：只 stdout JSON（含 markdown 字符串 + image URLs）。**新增** `--output-dir` / `--download-images` / `--html` 是**可选**。

### 3.2 输出结构（`--output-dir` 时）

```
<output-dir>/
  article.md             # 完整 markdown（图片相对路径如 ![](images/abc.jpg)）
  article.html           # 完整 HTML 全文（仅 --html 时）
  meta.json              # {title, author, publish_time, account, url, ...}
  images/                # 仅 --download-images 时
    0.jpg
    1.png
    ...
```

### 3.3 实施位置

- `wx-mp-hunter/scripts/wx_mp_hunter.ts`：
  - 解析 markdown 提取图片 URL（regex `!\[[^\]]*\]\(([^)]+)\)`）
  - `downloadImages(urls, destDir)` helper
  - 改 markdown 内容（URL → 相对路径）
- `wx-mp-hunter/scripts/download_images.ts`：核心下载逻辑（并发 4 / 重试 1 / 跳过 GIF）
- `wx-mp-hunter/SKILL.md`：更新用法 + 新选项

### 3.4 频率 / 安全

- 单次 download ≤ 50 张图
- 单图 ≤ 5MB（wechat 公众号图片实际 ≤ 2MB）
- 总下载 ≤ 100MB
- 并发 4（避免触发微信风控）
- 失败 1 次重试（避免偶发 5xx）

### 3.5 单测

- `download_images.ts` 单元测试（mock fetch + tempdir 验证）
- `wx_mp_hunter.ts` 集成测试（mock markdown 内容 + 验证 URL 替换）

## 四、本轮交付清单

1. **`docs/wx-mp-hunter-articles-design.md`** ← 本 doc
2. **`crews/main/skills/wx-mp-hunter/scripts/download_images.ts`**（~80 行）
3. **`crews/main/skills/wx-mp-hunter/scripts/wx_mp_hunter.ts`** 改 `fetch-article` 加 `--output-dir` / `--download-images` / `--html`（~50 行增量）
4. **`crews/main/skills/wx-mp-hunter/scripts/wx-mp-hunter.sh`** 透传新参数（~5 行）
5. **`crews/main/skills/wx-mp-hunter/SKILL.md`** 更新用法
6. **`crews/main/skills/wx-mp-hunter/scripts/tests/test_download_images.ts`**（~10 个测试）

## 五、本轮**不**实施（**Phase 6+ 后续**）

- 视频号内容（依赖浏览器自动化 + cookies）
- 评论抓取（风控 + cookies）
- 阅读数（风控 + 限频）
- 多文章批量导出 zip（用户场景：现在不需要）

## 六、与现有架构的兼容性

- ✅ **不破坏** `fetch-article` 不带新参数时的行为（仍返 stdout JSON）
- ✅ **不引入** 新的 npm 依赖（用 Node 18+ stdlib `fetch` + `URL`）
- ✅ **不** 改变 cookie 路径（沿用 `~/.openclaw/logins/wechat-mp.json`）
- ✅ **不** 增加新 CLI 子命令（仅加 `fetch-article` 选项参数）

## 七、spike 验证 checklist

部署后由用户跑：
- [ ] 抓 1 篇带 5 张图的文章 → output-dir 有 article.md + 5 张本地图
- [ ] 抓 1 篇带 10 张图的文章 → 不触发微信风控
- [ ] 抓 1 篇纯文本（无图）→ 仅 article.md，无 images/ 目录
- [ ] 不传 --output-dir → 仍返 stdout JSON
- [ ] 传 --output-dir 但不传 --download-images → 仅 article.md，图片 URL 保留为远程

---

关联：
- `crews/main/skills/wx-mp-hunter/SKILL.md`（当前 SKILL.md）
- `docs/camoufox-spike-2026-07.md`（camoufox 集成 spike 报告）
- `docs/wechat-mp-engagement-design.md`（公众号 engagement 设计，与本文互补——抓 vs 互动数据）
