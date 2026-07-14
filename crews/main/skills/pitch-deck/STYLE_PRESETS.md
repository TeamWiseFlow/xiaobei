# Style Presets Reference

`pitch-deck` 技能的视觉风格参考。

本文件用于：
- 视口强制适配的 CSS 基础
- 预设选择与情感映射
- CSS 注意事项和验证规则

只使用抽象形状，除非用户明确要求插图。

## 视口适配是不可妥协的底线

每张幻灯片必须在一个视口内完整呈现。

### 黄金法则

```text
每张幻灯片 = 恰好一个视口高度。
内容太多 = 拆分成更多幻灯片。
幻灯片内部永远不滚动。
```

### 密度限制

| 幻灯片类型 | 最大内容量 |
|-----------|-----------|
| 封面 | 1 个大标题 + 1 个副标题 + 可选标语 |
| 内容页 | 1 个标题 + 4–6 条要点或 2 段短文 |
| 功能网格 | 最多 6 张卡片 |
| 数据图表 | 1 个核心指标或 1 张图 |
| 引用页 | 1 条引用 + 来源 |
| 图片页 | 1 张图，高度不超过 60vh |

## 必备基础 CSS

将以下代码块复制到每个演示文稿，然后在此基础上叠加主题。

```css
/* ===========================================
   视口适配：必备基础样式
   =========================================== */

html, body {
    height: 100%;
    overflow-x: hidden;
}

html {
    scroll-snap-type: y mandatory;
    scroll-behavior: smooth;
}

.slide {
    width: 100vw;
    height: 100vh;
    height: 100dvh;
    overflow: hidden;
    scroll-snap-align: start;
    display: flex;
    flex-direction: column;
    position: relative;
}

.slide-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    max-height: 100%;
    overflow: hidden;
    padding: var(--slide-padding);
}

:root {
    --title-size: clamp(1.5rem, 5vw, 4rem);
    --h2-size: clamp(1.25rem, 3.5vw, 2.5rem);
    --h3-size: clamp(1rem, 2.5vw, 1.75rem);
    --body-size: clamp(0.75rem, 1.5vw, 1.125rem);
    --small-size: clamp(0.65rem, 1vw, 0.875rem);

    --slide-padding: clamp(1rem, 4vw, 4rem);
    --content-gap: clamp(0.5rem, 2vw, 2rem);
    --element-gap: clamp(0.25rem, 1vw, 1rem);
}

.card, .container, .content-box {
    max-width: min(90vw, 1000px);
    max-height: min(80vh, 700px);
}

.feature-list, .bullet-list {
    gap: clamp(0.4rem, 1vh, 1rem);
}

.feature-list li, .bullet-list li {
    font-size: var(--body-size);
    line-height: 1.4;
}

.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr));
    gap: clamp(0.5rem, 1.5vw, 1rem);
}

img, .image-container {
    max-width: 100%;
    max-height: min(50vh, 400px);
    object-fit: contain;
}

@media (max-height: 700px) {
    :root {
        --slide-padding: clamp(0.75rem, 3vw, 2rem);
        --content-gap: clamp(0.4rem, 1.5vw, 1rem);
        --title-size: clamp(1.25rem, 4.5vw, 2.5rem);
        --h2-size: clamp(1rem, 3vw, 1.75rem);
    }
}

@media (max-height: 600px) {
    :root {
        --slide-padding: clamp(0.5rem, 2.5vw, 1.5rem);
        --content-gap: clamp(0.3rem, 1vw, 0.75rem);
        --title-size: clamp(1.1rem, 4vw, 2rem);
        --body-size: clamp(0.7rem, 1.2vw, 0.95rem);
    }

    .nav-dots, .keyboard-hint, .decorative {
        display: none;
    }
}

@media (max-height: 500px) {
    :root {
        --slide-padding: clamp(0.4rem, 2vw, 1rem);
        --title-size: clamp(1rem, 3.5vw, 1.5rem);
        --h2-size: clamp(0.9rem, 2.5vw, 1.25rem);
        --body-size: clamp(0.65rem, 1vw, 0.85rem);
    }
}

@media (max-width: 600px) {
    :root {
        --title-size: clamp(1.25rem, 7vw, 2.5rem);
    }

    .grid {
        grid-template-columns: 1fr;
    }
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.2s !important;
    }

    html {
        scroll-behavior: auto;
    }
}
```

## 视口检查清单

- 每个 `.slide` 有 `height: 100vh`、`height: 100dvh` 和 `overflow: hidden`
- 所有排版使用 `clamp()`
- 所有间距使用 `clamp()` 或视口单位
- 图片有 `max-height` 约束
- 网格用 `auto-fit` + `minmax()` 自适应
- 存在 `700px`、`600px`、`500px` 三个矮屏断点
- 内容感觉拥挤时，拆分幻灯片

## BD 场景与预设映射

| 场景 | 推荐预设 |
|---------|---------|
| 投资人路演 / 融资演讲 | Bold Signal、Electric Studio |
| 科技 / AI 产品 Demo | Neon Cyber、Creative Voltage |
| 高端品牌 / 精品合作 | Dark Botanical、Vintage Editorial |
| 企业级合作提案 | Swiss Modern、Notebook Tabs |
| 通用商务 / 友好产品 | Pastel Geometry、Split Pastel |

## 情感与预设映射

| 情感 | 适合预设 |
|------|---------|
| 权威可信 / 自信 | Bold Signal、Electric Studio、Dark Botanical |
| 创新活力 / 兴奋 | Creative Voltage、Neon Cyber、Split Pastel |
| 专业简洁 / 聚焦 | Notebook Tabs、Paper & Ink、Swiss Modern |
| 高端精致 / 有品位 | Dark Botanical、Vintage Editorial、Pastel Geometry |

## 预设目录

### 1. Bold Signal

- 氛围：自信、高冲击力、主题演讲感
- 最适合：路演、产品发布、战略声明
- 字体：Archivo Black + Space Grotesk
- 配色：炭灰底色、亮橙色焦点卡、纯白文字
- 标志：超大章节编号、深色背景上的高对比卡片

### 2. Electric Studio

- 氛围：干净、大胆、代理商质感
- 最适合：客户演示、战略评审
- 字体：Manrope（单一字体）
- 配色：黑、白、饱和钴蓝强调色
- 标志：双栏分割布局、锐利的编辑排版

### 3. Creative Voltage

- 氛围：充满活力、复古现代、自信玩法
- 最适合：创意工作室、品牌工作、产品故事
- 字体：Syne + Space Mono
- 配色：电蓝、霓虹黄、深海军蓝
- 标志：半调纹理、徽章元素、强对比

### 4. Dark Botanical

- 氛围：优雅、高端、有氛围感
- 最适合：奢侈品牌、深度叙事、高端产品提案
- 字体：Cormorant + IBM Plex Sans
- 配色：近黑、暖象牙白、腮红、金色、赤陶
- 标志：模糊抽象圆、细分割线、克制动效

### 5. Notebook Tabs

- 氛围：编辑感、有条理、质感十足
- 最适合：报告、复盘、结构化叙事
- 字体：Bodoni Moda + DM Sans
- 配色：纸张奶油色底搭炭灰、彩色标签页
- 标志：纸张效果、彩色侧标签、活页细节

### 6. Pastel Geometry

- 氛围：亲切、现代、友好
- 最适合：产品概述、客户引导、轻量品牌
- 字体：Plus Jakarta Sans（单一字体）
- 配色：浅蓝底、奶油卡片、柔粉/薄荷/薰衣草强调
- 标志：竖排胶囊、圆角卡片、柔和阴影

### 7. Split Pastel

- 氛围：活泼、现代、有创意
- 最适合：代理商介绍、工作坊、作品集
- 字体：Outfit（单一字体）
- 配色：桃色 + 薰衣草分割底色搭薄荷徽章
- 标志：分割背景、圆角标签、轻网格叠加

### 8. Vintage Editorial

- 氛围：有个性、有故事感、杂志风
- 最适合：个人品牌、有观点的演讲、叙事型提案
- 字体：Fraunces + Work Sans
- 配色：奶油、炭灰、暖色调强调
- 标志：几何装饰、带边框引用块、有冲击力的衬线标题

### 9. Neon Cyber

- 氛围：未来感、科技感、动感十足
- 最适合：AI、基础设施、开发者工具、"X 的未来"演讲
- 字体：Clash Display + Satoshi
- 配色：午夜海军蓝、青色、洋红
- 标志：发光效果、粒子、网格、数据雷达感

### 10. Swiss Modern

- 氛围：极简、精准、数据导向
- 最适合：企业级、产品战略、分析报告
- 字体：Archivo + Nunito
- 配色：白、黑、信号红
- 标志：可见网格、非对称布局、几何纪律感

### 11. Paper & Ink

- 氛围：文学感、沉思、故事驱动
- 最适合：理念陈述、主旨演讲、宣言式演示
- 字体：Cormorant Garamond + Source Serif 4
- 配色：暖奶油、炭灰、深红强调
- 标志：提引语、首字下沉、优雅分割线

## 直接预设选择

如果用户已知道想要的风格，可直接从上面的预设名称中选取，跳过预览生成。

## 动效感觉映射

| 感觉 | 动效方向 |
|------|---------|
| 戏剧 / 电影感 | 慢淡入、视差、大幅缩放 |
| 科技 / 未来感 | 发光、粒子、网格动效、文字扰码 |
| 活泼 / 友好 | 弹性缓动、圆形、浮动动效 |
| 专业 / 企业级 | 200–300ms 微动效、干净切换 |
| 平静 / 极简 | 极度克制的动效、留白优先 |
| 编辑 / 杂志感 | 强层次感、文字与图片交错入场 |

## CSS 注意事项：取反函数

**不要**写：

```css
right: -clamp(28px, 3.5vw, 44px);
margin-left: -min(10vw, 100px);
```

浏览器会静默忽略这些写法。

**必须**改为：

```css
right: calc(-1 * clamp(28px, 3.5vw, 44px));
margin-left: calc(-1 * min(10vw, 100px));
```

## 验证尺寸

至少在以下分辨率测试：
- 桌面端：`1920x1080`、`1440x900`、`1280x720`
- 平板：`1024x768`、`768x1024`
- 手机：`375x667`、`414x896`
- 横屏手机：`667x375`、`896x414`

## 反模式

不要使用：
- 紫色渐变 + 白底的通用创业模板
- Inter / Roboto / Arial 作为视觉声音（除非用户明确想要中性实用风）
- 子弹点墙、字体过小、需要滚动的代码块
- 当抽象几何能胜任时使用装饰性插图
