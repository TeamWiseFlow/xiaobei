---
name: pitch-deck
description: 当执行 BD/IR 任务需要对外演示材料时创建精美的 HTML 演示文稿——路演 PPT、合作提案、客户 Demo、产品介绍。零依赖单文件输出，可直接通过邮件/微信发送或浏览器演示。
metadata:
  openclaw:
    emoji: 🎯
    always: false
    requires:
      bins:
      - python3
---

# Pitch Deck 技能

为商务拓展（BD）/投资人关系（IR）场景生成零依赖、动效丰富的 HTML 演示文稿，直接在浏览器中运行。

> 📍 **全局技能路径提示**：文中所有 `./scripts/` 路径均相对于本技能所在目录（即 `<skill>` 标签 `location` 属性所指目录），**不是**工作区目录。执行时按本技能实际安装路径拼接。

## 激活时机

- 制作投资人路演 PPT / 融资演讲稿
- 制作合作提案 / 联盟合作邀约文件
- 制作客户 Demo / 产品介绍演示
- 制作案例汇报 / 季度复盘报告
- 将现有 `.ppt` / `.pptx` 文件转换为 Web 版演示

## 硬性要求

1. **零依赖**：默认输出单个自包含 HTML 文件（内联 CSS + JS），可直接在任意浏览器打开。
2. **视口强制适配**：每张幻灯片必须在一个视口内完整呈现，禁止内部滚动。
3. **视觉先行**：用视觉预览代替抽象风格问卷，用户选择感觉而非参数。
4. **商务可信度**：避免廉价渐变、模板感设计；演示文稿要传递专业性和可信度。
5. **生产质量**：代码有注释，支持响应式，兼容键盘 / 触屏 / 鼠标滚轮操作。

生成前，务必读取 `STYLE_PRESETS.md` 获取视口安全的 CSS 基础、密度限制、预设目录和 CSS 注意事项。

## 工作流

### 第一步：确认模式

选择以下其中一条��径：
- **新建演示**：用户有主题、要点或完整草稿
- **PPT 转换**：用户有 `.ppt` 或 `.pptx` 文件
- **优化现有**：用户已有 HTML 演示文稿，需要改进

### 第二步：了解内容

只问必要的问题：
- **用途**：路演 / 合作提案 / 客户 Demo / 产品介绍 / 案例汇报
- **受众**：投资人 / 潜在合作伙伴 / 客户 / 内部团队
- **页数**：短（5–10）/ 中（10–20）/ 长（20+）
- **内容状态**：已有完整文案 / 粗略要点 / 仅有主题

如果用户有内容，先让他粘贴，再讨论风格。

### 第三步：确认演示类型与结构

根据用途，给出对应的标准结构建议：

**路演 / 投资人演示（Investor Pitch）**
```
1. 封面（公司名 + 一句话定位）
2. 问题（用数据量化痛点）
3. 解决方案（产品/服务是什么）
4. 市场规模（TAM / SAM / SOM）
5. 产品演示（截图 / 核心功能）
6. 商业模式（如何赚钱）
7. 牵引力（数据、客户、里程碑）
8. 竞争对比（差异化定位）
9. 团队（关键成员 + 背景）
10. 融资需求（金额 + 用途 + 联系方式）
```

**合作提案（Partnership Proposal）**
```
1. 封面（提案标题 + 日期）
2. 背景（为什么找你们）
3. 我们是谁（公司简介 + 核心优势）
4. 合作方式（模式 + 流程）
5. 双赢分析（对方能得到什么）
6. 案例参考（过往合作成果）
7. 合作条款（关键条件概述）
8. 下一步行动（CTA + 联系方式）
```

**客户 Demo / 产品介绍**
```
1. 封面（产品名 + 核心价值主张）
2. 你的痛点（场景化描述）
3. 我们的方案（功能亮点）
4. 效果展示（案例 / 数据）
5. 定价方案（清晰直观）
6. 常见问题（FAQ）
7. 开始使用（CTA + 联系方式）
```

### 第四步：选择风格

默认走视觉探索流程。

如果用户已知道想要的预设，跳过预览直接使用。

否则：
1. 询问演示文稿应传达的感觉：**权威可信 / 创新活力 / 专业简洁 / 高端精致**
2. 在 `.pitch-deck-previews/` 下生成 **3 个单页预览文件**
3. 每个预览须独立、清晰呈现排版/配色/动效，控制在约 100 行幻灯片内容以内
4. 询问用户保留哪个，或混合哪些元素

根据场景推荐以下预设（详见 `STYLE_PRESETS.md`）：

| 场景 | 推荐预设 |
|---------|---------|
| 投资人路演 | Bold Signal、Electric Studio |
| 合作提案 | Swiss Modern、Notebook Tabs |
| 高端品牌客户 | Dark Botanical、Vintage Editorial |
| 科技 / AI 产品 | Neon Cyber、Creative Voltage |
| 通用商务 | Pastel Geometry、Split Pastel |

### 第五步：构建演示文稿

输出文件：
- `pitch-deck.html`
- 或 `[主题名称]-pitch.html`

只有演示中含有外部图片资源时，才创建 `assets/` 文件夹。

必须包含的结构：
- 语义化幻灯片 `<section>`
- 来自 `STYLE_PRESETS.md` 的视口安全 CSS 基础
- CSS 自定义属性管理主题变量
- 演示控制器类（键盘 / 滚轮 / 触屏导航）
- Intersection Observer 触发入场动画
- `prefers-reduced-motion` 支持

### 第六步：强制视口适配

视为硬性验收标准。

规则：
- 每个 `.slide` 必须使用 `height: 100vh; height: 100dvh; overflow: hidden;`
- 所有字体和间距必须使用 `clamp()` 缩放
- 内容放不下时，拆分成多张幻灯片
- 绝不通过缩小字体到不可读来解决溢出
- 幻灯片内部禁止出现滚动条

使用 `STYLE_PRESETS.md` 中的密度限制和必备 CSS 块。

### 第七步：交付

交付时：
1. **主动生成长图**：用户确认 HTML 后，立即调用 `html_to_longimage.py --save-slides` 将演示文稿转为纵向长图，**同时交付 HTML 文件和长图文件**。`--save-slides` 保存每页独立截图，供后续 PPTX 转换复用。长图适合微信/飞书等移动端直接发送和浏览。
2. 删除临时预览文件（除非用户要保留）
3. 用适合当前系统的方式打开文件：
   - macOS：`open file.html`
   - Linux：`xdg-open file.html`
   - Windows：`start "" file.html`
4. 汇总：HTML 路径、长图路径、使用的预设、幻灯片数量、主题定制方法

> **PPT 转换为按需操作**：仅当用户明确要求 `.pptx` 格式时才调用 `html_to_pptx.py`，不要主动转换。

## HTML → 长图转换

用户确认 HTML 演示文稿后，**主动调用**此脚本生成纵向长图，同时交付 HTML 和长图两个文件：

```bash
python3 ./scripts/html_to_longimage.py <pitch-deck.html> [-o output.png] [--width 1920] [--height 1080] [--format png|jpg] [--quality 95] [--gap 0] [--scale 1.0] [--save-slides] [--slides-dir <dir>]
```

脚本功能：
- 在 headless Chromium 中逐页渲染每个 `<section class="slide">`，像素级还原 CSS 效果（自定义属性、clamp()、渐变等）
- 每页以横屏视口（默认 1920×1080）截图，然后从上到下拼成一张长图
- 输出 PNG（无损）或 JPEG（更小体积），可设置页间距 `--gap`
- `--save-slides`：同时保存每页独立截图到 `<name>-slides/` 目录，供后续 PPTX 转换复用（跳过重复渲染）
- 输出 JSON 结果：`{"ok": true, "image_file": "...", "slide_count": 15, "width": 1920, "height": 16200, "slides_dir": "..."}`

**典型用法**：
```bash
# PNG 长图（无损，适合打印/截取细节）
python3 ./scripts/html_to_longimage.py pitch-deck.html

# JPEG 长图（体积更小，适合微信/飞书发送）
python3 ./scripts/html_to_longimage.py pitch-deck.html --format jpg --quality 90

# HiDPI 高清渲染（2x 缩放）
python3 ./scripts/html_to_longimage.py pitch-deck.html --scale 2.0

# 长图 + 保存每页截图（供 PPTX 转换复用）
python3 ./scripts/html_to_longimage.py pitch-deck.html --save-slides
```

**依赖**：`playwright`、`Pillow`（若缺失脚本会提示安装命令，首次使用需 `python3 -m playwright install chromium`）

## HTML → PPTX 转换

当用户需要 PPT 格式（如投资人要求 `.pptx` 文件、微信/邮件附件场景），使用内置脚本将已生成的 HTML 演示文稿转为 PPTX。

**核心思路**：截图即幻灯片——在 headless Chromium 中逐页渲染并截图，每页截图作为全幅图片放入一页 PPTX，像素级保真，CSS 效果零损失。

```bash
# 从 HTML 渲染截图并生成 PPTX
python3 ./scripts/html_to_pptx.py <pitch-deck.html> [-o output.pptx]

# 复用已有截图（跳过渲染，速度更快）
python3 ./scripts/html_to_pptx.py <pitch-deck.html> -o output.pptx --screenshots-dir ./pitch-deck-slides/

# 自定义视口 / HiDPI
python3 ./scripts/html_to_pptx.py <pitch-deck.html> --width 1920 --height 1080 --scale 2.0

# 同时保存每页截图
python3 ./scripts/html_to_pptx.py <pitch-deck.html> --save-screenshots
```

脚本功能：
- 在 headless Chromium 中逐页渲染每个 `<section class="slide">`（与长图流程共用同一渲染管线）
- 每页截图作为全幅图片放入一页 PPTX，**像素级保真**——CSS 渐变、动画终态、复杂布局全部保留
- 支持 `--screenshots-dir` 复用已有截图（如长图流程 `--save-slides` 产出的），跳过重复渲染
- 自动检测截图尺寸设置 PPTX 页面比例（默认 1920×1080 → 16:9）
- 输出 JSON 结果：`{"ok": true, "pptx_file": "...", "slide_count": 15, "reused_screenshots": false}`

**使用时机**：
1. 先按正常工作流生成 HTML pitch-deck
2. 用户要求 PPT 格式时，直接调用此脚本转换
3. 如果之前已生成长图且用了 `--save-slides`，可用 `--screenshots-dir` 复用截图

**依赖**：`python-pptx`、`Pillow`、`playwright`（与 ppt-maker 共用 python-pptx 依赖，若缺失脚本会提示安装命令）

## PPT / PPTX → HTML 转换

```bash
python3 ./scripts/extract_pptx.py <file.pptx> [--images-dir /tmp/pptx_images]
```

脚本输出 JSON，包含每张幻灯片的标题、正文、演讲备注和图片路径（若指定了 `--images-dir`）。

- 若 `python-pptx` 未安装（输出 `error` 字段），询问用户是否安装（`pip install python-pptx`），或降级为手动粘贴流程
- 提取完成后，走与新建演示相同的风格选择流程，保留幻灯片顺序、演讲备注和图片资源

保持跨平台兼容，不依赖 macOS 专有工具。

## 实现要求

### HTML / CSS

- 使用内联 CSS 和 JS（除非用户明确需要多文件项目）
- 字体可来自 Google Fonts 或 Fontshare
- 优先使用抽象形状、渐变、网格、几何图形，而非插图
- 商务演示需传递专业感和可信度；路演需传递自信和野心

### JavaScript

必须包含：
- 键盘导航（← → 方向键 / Space）
- 触控 / 滑动导航
- 鼠标滚轮导航
- 进度指示器或幻灯片索引
- 入场动画触发（Intersection Observer）

### 无障碍

- 使用语义化结构（`main`、`section`、`nav`）
- 保持足够的色彩对比度
- 支持纯键盘导航
- 遵守 `prefers-reduced-motion`

## 内容密度限制

| 幻灯片类型 | 上限 |
|-----------|------|
| 封面 | 1 个大标题 + 1 个副标题 + 可选标语 |
| 内容页 | 1 个标题 + 4–6 条要点或 2 段短文 |
| 功能网格 | 最多 6 张卡片 |
| 数据图表 | 1 个核心指标或 1 张图 |
| 引用 / 客户背书 | 1 条引用 + 来源 |
| 图片页 | 1 张图，高度不超过视口的 60% |

## 反模式

- 廉价的紫色渐变 + Inter 字体的通用模板感
- 子弹点墙（bullet wall）
- 需要滚动才能看完的代码块
- 在高内容密度时缩小字体而不是拆分幻灯片
- 无效的 CSS 取反函数，如 `-clamp(...)` 或 `-min(...)`

## 交付清单

- [ ] 演示文稿可从本地文件直接在浏览器运行
- [ ] 每张幻灯片在视口内完整呈现，无需滚动
- [ ] 风格与目标受众和场景匹配
- [ ] 动效有意义，不喧宾夺主
- [ ] 支持 reduced-motion
- [ ] 长图已生成，与 HTML 一同交付
- [ ] 交付时说明 HTML 路径、长图路径、预设选择、幻灯片数量和定制方法
