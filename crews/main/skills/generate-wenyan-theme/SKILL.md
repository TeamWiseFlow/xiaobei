---
name: generate-wenyan-theme
description: Generate custom WeChat CSS themes from natural language descriptions,
  WeChat article URLs, or recent articles from a WeChat Official Account.
  Produces a valid CSS file conforming to wenyan and ready for wx-mp-publisher.
metadata:
  openclaw:
    emoji: 🎨
    requires:
      bins:
      - node
---

# 微信公众号自定义主题 CSS 生成器

根据用户的自然语言需求，生成符合微信公众号排版规范的自定义 CSS 样式表，保存为本地文件。

---

## 核心能力

- **自然语言转 CSS**：理解视觉需求（如"赛博朋克风"、"深色代码块"、"带装饰的引用块"），转换为精确的 CSS 代码
- **微信文章仿样式生成**：当用户提供 `https://mp.weixin.qq.com` 文章链接时，调用 `wx-mp-hunter fetch <url> --html` 获取正文 HTML，分析原文排版特征后生成 wenyan CSS
- **公众号近期文章归纳生成**：当用户提供公众号账号时，调用 `wx-mp-hunter search` + `account-posts` + `fetch --html` 采集近期文章 HTML，抽取共性后生成模板
- **主题注册联动**：生成自定义 CSS 后，自动更新同 crew 内 `./skills/wx-mp-publisher/SKILL.md` 的主题列表，方便后续发布优先选用
- **微信排版规范适配**：严格遵循 `#wenyan` 命名空间约束，确保样式能完美注入微信公众号 DOM 结构
- **高级排版特效**：支持伪元素 (`::before`/`::after`)、渐变背景 (`linear-gradient`)、内联 SVG/Base64 图片等高级 CSS 特性

---

## 输入模式识别

本技能支持三种模式，按以下优先级判断：

1. **单篇文章 URL 模式**：用户输入包含 `https://mp.weixin.qq.com` 开头的链接。
2. **公众号账号模式**：用户明确提供微信公众号账号名、别名或要求“参考某公众号/抓取某公众号最近文章”。
3. **自然语言模式**：没有微信文章链接或公众号账号时，按普通视觉需求生成。

---

## 文章采集脚本

通过 PATH 调用 wrapper：`generate-wenyan-theme <cmd>`，无需拼接脚本路径。

调用方式：`generate-wenyan-theme ...`

该脚本会调用全局 `wx-mp-hunter` wrapper：

- URL 模式：`wx-mp-hunter fetch <url> --html`
- 账号模式：`wx-mp-hunter search <account>` → `account-posts <fakeid>` → 对候选文章逐篇 `fetch --html`

### URL 模式

```bash
generate-wenyan-theme --url <mp.weixin.qq.com-url> --output wenyan-theme-sources.json
```

输出 JSON 中 `articles[0].content_html` 为文章正文 HTML。

### 公众号账号模式

```bash
generate-wenyan-theme --account <公众号名> --count 10 --output wenyan-theme-sources.json
```

如果用户同时给出关键词或筛选信息，传入 `--keywords`：

```bash
generate-wenyan-theme --account <公众号名> --keywords "关键词1,关键词2" --count 10 --scan-batch 20 --max-scan 100 --output wenyan-theme-sources.json
```

筛选规则：

- 无关键词：默认取最近 10 篇。
- 有关键词：先抓最近 20 篇，按标题、摘要、作者匹配关键词；不足目标数量时继续抓下一批 20 篇，直到满足数量、无更多文章或达到 `--max-scan`。
- 每篇文章会通过 `fetch --html` 获取 `content_html`。

> 若 `wx-mp-hunter` 返回 `SESSION_EXPIRED`，按 `wx-mp-hunter` 技能的扫码登录流程处理后重试原命令。

---

## HTML 样式分析要点

从 `content_html` 中抽取共性时，只分析可迁移到 wenyan CSS 的视觉规律，不复制微信原文中不可控或依赖原始 DOM 的实现细节：

- 颜色：正文色、标题色、强调色、引用/代码/分割线背景色
- 字号与层级：h1/h2/h3、正文、注释、小字之间的相对比例
- 间距节奏：段落间距、标题上下留白、列表缩进、引用块 padding
- 装饰语言：标题前后缀、底纹、边框、圆角、分割线、卡片感
- 内容类型：是否频繁使用图片、引用、列表、代码、表格
- 共同约束：多篇账号样本中重复出现的风格才作为模板核心；单篇偶发元素只作为可选细节

---


### 1. 强制命名空间约束（最重要）

所有 CSS 选择器 **必须** 以 `#wenyan` 开头，中间用空格隔开。缺少 `#wenyan` 前缀的样式将失效。

- ✅ `#wenyan h1 { color: red; }`
- ❌ `h1 { color: red; }`

### 2. 字体与字号

- **font-family**：严禁主动设置，保持默认以适配微信公众号编辑器的系统字体
- **font-size**：建议 12px - 18px 范围，避免排版溢出或阅读困难

### 3. 支持的 CSS 选择器字典

| 目标元素 | CSS 选择器 | 常用定制属性 |
|---------|-----------|------------|
| 全局默认 | `#wenyan` | `background-image`, `line-height`, `color` |
| 各级标题 | `#wenyan h1` ~ `#wenyan h6` | `font-size`, `text-align`, `border-bottom`, `margin` |
| 标题文字 | `#wenyan h1 span` | `color`, `font-weight`, `background` |
| 标题装饰 | `#wenyan h1::before` | `content`, `display`, `width`, `height`, `background-image` |
| 段落文本 | `#wenyan p` | `text-indent`, `letter-spacing`, `color` |
| 引用块 | `#wenyan blockquote` | `border-left`, `background-color`, `padding` |
| 代码块外层 | `#wenyan pre` | `background-color`, `border-radius`, `padding`, `overflow-x: auto` |
| 代码块内容 | `#wenyan pre code` | `color` |
| 分割线 | `#wenyan hr` | `border`, `border-top-style`, `border-color` |
| 超链接 | `#wenyan a` | `color`, `text-decoration`, `border-bottom` |

### 4. 外部资源引用限制

- **禁止本地路径**：严禁 `url("./bg.png")` 等本地路径
- **合法引入方式**：
  - Data URI（推荐）：`url("data:image/svg+xml;utf8,<svg>...</svg>")`
  - HTTPS 地址：`url(https://example.com/bg.jpg)`
- **禁止 Web 字体**：不支持 `@font-face`，只能使用系统字体

### 5. 输出文件路径约束

- 采集输出 JSON：必须是当前工作目录下的单个 `.json` 文件名，禁止目录、绝对路径和 `..` 上跳。
- 生成的 CSS：只写入当前工作目录内的相对 `.css` 路径，禁止绝对路径、`..` 上跳、隐藏目录和非 `.css` 后缀。

---

## 参考模板（default.css 结构）

```css
/* 全局属性 */
#wenyan {
    line-height: 1.75;
    font-size: 16px;
}

/* 标题与段落间距 */
#wenyan h1,
#wenyan h2,
#wenyan h3,
#wenyan h4,
#wenyan h5,
#wenyan h6,
#wenyan p {
    margin: 1em 0;
}

/* 一级标题 */
#wenyan h1 {
    text-align: center;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
    font-size: 1.5em;
}

/* 二级标题 */
#wenyan h2 {
    text-align: center;
    font-size: 1.2em;
    border-bottom: 1px solid #f7f7f7;
    font-weight: bold;
}

/* 列表 */
#wenyan > ul,
#wenyan > ol {
    padding-left: 1rem;
}

#wenyan ul,
#wenyan ol {
    margin-left: 1rem;
    font-size: 0.9rem;
}

/* 图片 */
#wenyan img {
    max-width: 100%;
    height: auto;
    margin: 0 auto;
    display: block;
}

/* 表格 */
#wenyan table {
    border-collapse: collapse;
    margin: 1.4em auto;
    max-width: 100%;
    table-layout: fixed;
    text-align: left;
    overflow: auto;
    display: table;
}

/* 引用块 */
#wenyan blockquote {
    background: #afb8c133;
    border-left: 0.5em solid #ccc;
    margin: 1.5em 0;
    padding: 0.5em 10px;
    font-style: italic;
    font-size: 0.9em;
}

/* 行内代码 */
#wenyan p code {
    color: #ff502c;
    padding: 4px 6px;
    font-size: 0.78em;
}

/* 代码块外围 */
#wenyan pre {
    border-radius: 5px;
    line-height: 2;
    margin: 1em 0.5em;
    padding: .5em;
    box-shadow: rgba(0, 0, 0, 0.55) 0px 1px 5px;
    font-size: 12px;
}

/* 代码块 */
#wenyan pre code {
    display: block;
    overflow-x: auto;
    margin: .5em;
    padding: 0;
}

/* 分割线 */
#wenyan hr {
    border: none;
    border-top: 1px solid #ddd;
    margin-top: 2em;
    margin-bottom: 2em;
}

/* 链接 */
#wenyan a {
    word-wrap: break-word;
    color: #0069c2;
}
```

---

## Agent 执行步骤

### A. 自然语言模式

1. **分析需求**：提取关键词（如：深色、科技风、可爱），确定主色调和风格方向
2. **生成 CSS**：严格按照命名空间约束和上述规范，生成完整的 CSS 代码
3. **保存文件**：将 CSS 写入本地文件（如 `custom-theme.css`）
4. **注册主题**：更新 `./skills/wx-mp-publisher/SKILL.md` 的“主题选择”表格，追加或更新该自定义主题记录
5. **后续引导**：提示使用 `wx-mp-publisher` 技能的第二个位置参数传入自定义 CSS 路径进行发布

### B. 单篇文章 URL 模式

1. **识别链接**：确认用户输入包含 `https://mp.weixin.qq.com` 开头的文章 URL。
2. **采集 HTML**：运行采集脚本：
   ```bash
   generate-wenyan-theme --url <url> --output wenyan-theme-sources.json
   ```
3. **分析样式**：读取输出 JSON，基于 `articles[0].content_html` 分析标题、段落、引用、分割线、强调、图片周边等样式特征。
4. **生成 CSS**：将可迁移特征映射到 `#wenyan` 选择器体系，不复制无效的微信原始 class 或 inline style。
5. **保存文件、注册主题并引导发布**。

### C. 公众号账号模式

1. **识别账号与筛选意图**：提取公众号账号名；如果用户提供关键词、主题、人群或文章类型，将其整理为 `--keywords`。
2. **采集样本**：
   - 无筛选信息：抓最近 10 篇。
   - 有筛选信息：从最近 20 篇开始筛选，不足则继续下一批 20 篇。
   ```bash
   generate-wenyan-theme --account <公众号名> --count 10 --output wenyan-theme-sources.json
   ```
   或：
   ```bash
   generate-wenyan-theme --account <公众号名> --keywords "关键词1,关键词2" --count 10 --scan-batch 20 --max-scan 100 --output wenyan-theme-sources.json
   ```
3. **向用户确认**：生成 CSS 前，必须向用户展示拟参考的文章列表（标题、发布时间/链接、匹配关键词），并询问是否继续。用户确认后再生成。
4. **抽取共性**：优先使用多篇文章共同出现的视觉规律；冲突样式按出现频次和标题层级一致性取舍。
5. **生成 CSS**：输出一个适合该账号整体调性的 wenyan 主题，而不是拼贴单篇文章的局部样式。
6. **保存文件、注册主题并引导发布**。


---

## 生成前确认要求

仅公众号账号模式需要生成前确认。确认消息应包含：

- 公众号名称/别名
- 实际采集文章数量
- 文章标题列表
- 如有关键词：说明命中的关键词或筛选依据
- 输出主题文件名建议

用户确认“继续/可以/确认”后，才能写 CSS 文件。

---

## 生成主题注册规则

`generate-wenyan-theme` 与 `wx-mp-publisher` 都是你的私有技能，目录相对位置固定。因此每次成功生成自定义 CSS 后，必须同步更新：

```text
./skills/wx-mp-publisher/SKILL.md
```

在 `wx-mp-publisher/SKILL.md` 的“主题选择”表格中追加或更新一行自定义主题记录：

```markdown
| `<theme-id>` | 用户自定义：<风格摘要>（文件：`<css-file>`） | 用户明确指定参考该主题时优先采用；相似内容可优先建议 |
```

**登记表是 client 侧 id → 本地 CSS 路径映射，relay 不存主题。** CSS 内容随发布请求上传（`custom_theme` 字段）。

注册要求：

- `theme-id` 使用 CSS 文件名去掉 `.css` 后缀，例如 `custom-theme.css` → `custom-theme`。
- CSS 文件路径写相对路径，优先使用当前 crew workspace 内路径。
- 如果同名 `theme-id` 已存在，更新原行，不重复追加。
- 自定义主题必须在风格描述中标注“用户自定义”。
- 自定义主题的适用场景必须强调：**用户指定参考时优先采用**。
- 不要修改内置主题 ID 的含义。

注册后，`wx-mp-publisher` 发布时通过第二个位置参数引用自定义主题，两种写法等价：

```bash
# 1) 直接传 CSS 文件路径
wx-mp-publisher article.md custom-theme.css
# 2) 传登记在主题表里的 theme-id（脚本自动解析出 CSS 路径）
wx-mp-publisher article.md custom-theme
```

---

## 与 wx-mp-publisher 配合使用

生成 CSS 文件后，用 `wx-mp-publisher` 发布，第二个位置参数即主题（CSS 路径或登记的 theme-id 均可）：

```bash
wx-mp-publisher article.md custom-theme.css
# 或
wx-mp-publisher article.md custom-theme
```

> 注：发布统一走 `publish_wx_mp.py`，当 theme 参数指向本地 `.css` 文件路径、或为主题表中登记的自定义 id 时，脚本读出 CSS 内容作 `custom_theme` 字段随 multipart 上传 relay；relay 侧请求结束即清理，不持久化、不落盘、不按用户存主题。
