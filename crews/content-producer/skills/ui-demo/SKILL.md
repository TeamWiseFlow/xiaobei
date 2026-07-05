---
name: ui-demo
description: 录制精美的产品 UI demo 视频。当用户需要录制演示视频、功能演示、操作教程或利益相关方展示视频时使用。输出带可见鼠标、自然节奏和专业字幕的
  WebM 视频。
metadata:
  openclaw:
    emoji: 🎥
    requires:
      bins:
      - node
---

# UI Demo Video Recorder

使用 patchright `recordVideo` + 注入的鼠标覆盖层、字幕和自然节奏，录制精美的 Web 应用演示视频。

> **CDP 模式**：通过 patchright 连接 本机已安装 Chrome （不准自行安装无头浏览器），若本机未安装Chrome，则提示用户先进行安装，退出执行。
>
> **Patchright 1.60+ 替代方案**：Screencast API（`page.screencast`）提供内置录制+动作标注+章节+自定义 overlay，可替代手动注入 cursor/subtitle。详见下方「Screencast API 方案」章节。

## When to Use

- 用户需要"演示视频"、"产品录屏"、"功能演示"或"操作教程"
- 需要制作用于文档、用户引导或投资人/客户展示的视频

## Three-Phase Process

**Discover → Rehearse → Record**。禁止跳过直接录制。

---

## Phase 1: Discover（browser tool）

在写录制脚本之前，用 **browser tool** 逐一导航到流程中的每个页面，了解真实的页面结构。

**目标：建立每个页面的字段映射表**，用于 Phase 3 脚本中的选择器。

每个页面重点关注：

- **表单字段类型**：是 `<input>`、`<textarea>`、`<select>` 还是自定义 combobox / contenteditable？
- **Select 选项**：确认实际选项值。Placeholder 选项（通常 value 为 `""` 或 `"0"`）看起来非空但实际无效，跳过。
- **按钮精确文本**：如 `"Submit"`、`"Submit Request"`、`"Save"`。
- **必填字段**：尝试提交空表单，观察验证报错。
- **动态字段**：填写某字段后，确认是否有新字段出现。
- **登录态**：如需登录，先通过 browser-guide 完成登录，再进行 Discovery。

**输出**：整理每个页面的字段映射，例如：

```
/purchase-requests/new:
  - Budget Code: <select>（4 个真实选项，第一个是 placeholder）
  - Desired Delivery: <input type="date">
  - Context: <textarea>（不是 input）
  - Submit: <button> text="Submit Request"
```

---

## Phase 2: Rehearse（browser tool）

不录制，在 browser tool 中**手动走一遍完整流程**，验证每一步都能顺利完成。

- 按照 Phase 1 的字段映射，逐步导航、填写、点击
- 每个操作后确认页面状态符合预期
- 发现不符时，修正字段映射再重试
- 全流程无误后，才进入 Phase 3 写录制脚本

> Phase 2 的价值在于消灭"脚本假设"——字段顺序、选择器、等待时机，都在这里确认，不留到录制时爆。

---

## Phase 3: Record（Node.js 脚本）

Phase 1/2 确认后，编写录制脚本。`recordVideo` 必须通过 patchright Node.js 脚本完成，无法通过 browser tool 实现。

### Recording Principles

#### 1. Storytelling Flow

将视频规划为一个故事，默认结构：

- **Entry**：登录或导航到起始点
- **Context**：浏览周围环境让观众先定向
- **Action**：执行主要工作流步骤
- **Variation**：展示次要功能（可选）
- **Result**：展示结果或最终状态

#### 2. Pacing（节奏）

| 时机 | 等待时长 |
|------|---------|
| 登录后 | 4s |
| 导航后 | 3s |
| 点击按钮后 | 2s |
| 主要步骤之间 | 1.5-2s |
| 最后一个动作后 | 3s |
| 打字延迟 | 25-40ms / 字符 |

#### 3. Cursor Overlay（鼠标覆盖层）

注入 SVG 箭头光标，每次导航后重新注入（导航会销毁覆盖层）：

```javascript
async function injectCursor(page) {
  await page.evaluate(() => {
    if (document.getElementById('demo-cursor')) return;
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="white" stroke="black" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`;
    cursor.style.cssText = `
      position: fixed; z-index: 999999; pointer-events: none;
      width: 24px; height: 24px; transition: left 0.1s, top 0.1s;
      filter: drop-shadow(1px 1px 2px rgba(0,0,0,0.3));
    `;
    cursor.style.left = '0px'; cursor.style.top = '0px';
    document.body.appendChild(cursor);
    document.addEventListener('mousemove', e => {
      cursor.style.left = e.clientX + 'px';
      cursor.style.top = e.clientY + 'px';
    });
  });
}
```

#### 4. Mouse Movement（鼠标移动）

禁止光标瞬移，点击前先平滑移动到目标：

```javascript
async function moveAndClick(page, locator, label, opts = {}) {
  const { postClickDelay = 800, ...clickOpts } = opts;
  const el = typeof locator === 'string' ? page.locator(locator).first() : locator;
  try {
    await el.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    const box = await el.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 10 });
      await page.waitForTimeout(400);
    }
    await el.click(clickOpts);
  } catch (e) {
    console.error(`WARNING: moveAndClick failed on "${label}": ${e.message}`);
    return false;
  }
  await page.waitForTimeout(postClickDelay);
  return true;
}
```

#### 5. Typing（打字）

可见打字，不要瞬间填充：

```javascript
async function typeSlowly(page, locator, text, label, charDelay = 35) {
  const el = typeof locator === 'string' ? page.locator(locator).first() : locator;
  await moveAndClick(page, el, label);
  await el.fill('');
  await el.pressSequentially(text, { delay: charDelay });
  await page.waitForTimeout(500);
  return true;
}
```

**重要：富文本编辑器处理**

对于 `contenteditable` 富文本编辑器（如 Quill、TinyMCE 等）：

- **禁止使用 `fill()` 填充内容**！`fill()` 会导致编辑器无法识别内容，提交时可能丢失
- 正确做法：先 `click()` 聚焦，再 `pressSequentially()` 逐字输入
- 清空内容可用 `fill('')`，但填充内容必须用 `pressSequentially()`
- 示例选择器：`div.ql-editor`、`div[contenteditable="true"]`

```javascript
// ✅ 正确：富文本编辑器输入
const editor = page.locator('div.ql-editor');
await editor.click();
await editor.fill(''); // 清空
await editor.pressSequentially('正文内容...', { delay: 35 });

// ❌ 错误：会导致编辑器无法识别内容
await editor.fill('正文内容...');
```

#### 6. Subtitles（字幕）

在视口底部注入字幕条，每次导航后重新注入：

```javascript
async function injectSubtitleBar(page) {
  await page.evaluate(() => {
    if (document.getElementById('demo-subtitle')) return;
    const bar = document.createElement('div');
    bar.id = 'demo-subtitle';
    bar.style.cssText = `
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 999998;
      text-align: center; padding: 12px 24px;
      background: rgba(0,0,0,0.75); color: white;
      font-family: -apple-system, "Segoe UI", sans-serif;
      font-size: 16px; font-weight: 500; letter-spacing: 0.3px;
      transition: opacity 0.3s; pointer-events: none;
    `;
    bar.textContent = ''; bar.style.opacity = '0';
    document.body.appendChild(bar);
  });
}

async function showSubtitle(page, text) {
  await page.evaluate(t => {
    const bar = document.getElementById('demo-subtitle');
    if (!bar) return;
    bar.textContent = t; bar.style.opacity = t ? '1' : '0';
  }, text);
  if (text) await page.waitForTimeout(800);
}
```

字幕规范：不超过 60 字符，使用 `Step N - 动作` 格式，UI 已能说明问题时清空。

#### 7. Smooth Scroll

```javascript
await page.evaluate(() => window.scrollTo({ top: 400, behavior: 'smooth' }));
await page.waitForTimeout(1500);
```

### Script Template

```javascript
'use strict';
const { chromium } = require('patchright');
const path = require('path');
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const CDP_URL  = process.env.CDP_URL  || 'http://localhost:9222';
const VIDEO_DIR = path.join(__dirname, 'output');
const OUTPUT_NAME = 'demo-FEATURE.webm';

// 在此粘贴 injectCursor、injectSubtitleBar、showSubtitle、moveAndClick、typeSlowly 函数

(async () => {
  const browser = await chromium.connectOverCDP(CDP_URL, { noDefaults: true });

  // 从 openclaw 现有 context 继承登录态（避免录制视频出现登录流程）
  const existingContexts = browser.contexts();
  const cookies = existingContexts.length > 0
    ? await existingContexts[0].cookies()
    : [];

  const context = await browser.newContext({
    recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 720 } },
    viewport: { width: 1280, height: 720 }
  });
  if (cookies.length > 0) await context.addCookies(cookies);

  const page = await context.newPage();

  try {
    await injectCursor(page);
    await injectSubtitleBar(page);

    // Step 1 - 登录（cookies 已注入，通常直接跳过；若目标应用跨域或 cookie 失效则执行表单登录）
    await page.goto(`${BASE_URL}/login`);
    await page.waitForTimeout(2000);
    const alreadyLoggedIn = await page.locator('[data-testid="user-avatar"], .user-menu, .avatar').first().isVisible().catch(() => false);
    if (!alreadyLoggedIn) {
      await showSubtitle(page, 'Step 1 - 登录');
      await typeSlowly(page, 'input[name="email"]',    'demo@example.com', 'Email');
      await typeSlowly(page, 'input[name="password"]', 'demo-password',    'Password');
      await moveAndClick(page, 'button[type="submit"]', 'Login');
      await page.waitForTimeout(4000);
      await showSubtitle(page, '');
    }

    await page.goto(`${BASE_URL}/dashboard`);
    await injectCursor(page);
    await injectSubtitleBar(page);
    await showSubtitle(page, 'Step 2 - 概览');
    // 巡览 dashboard

    await showSubtitle(page, 'Step 3 - 主要流程');
    // 操作序列

    await showSubtitle(page, 'Step 4 - 结果');
    await page.waitForTimeout(3000);
    await showSubtitle(page, '');

  } catch (err) {
    console.error('DEMO ERROR:', err.message);
  } finally {
    await context.close();
    const video = page.video();
    if (video) {
      const src = await video.path();
      const dest = path.join(VIDEO_DIR, OUTPUT_NAME);
      fs.copyFileSync(src, dest);
      console.log('Video saved:', dest);
    }
    // 不调用 browser.close() — Chrome 由 xiaobei 管理
  }
})();
```

运行：

```bash
node demo-script.cjs
```

---

## Screencast API 方案（Patchright 1.60+）

Screencast API 是 Patchright 1.59+ 引入的原生录制能力，**内置动作标注、章节标题和自定义 overlay**，可替代手动注入 cursor SVG 和 subtitle bar。

### 优势对比

| 特性 | 手动注入方案（上方） | Screencast API |
|------|-------------------|----------------|
| 鼠标光标 | 需手动注入 SVG + mousemove 监听 | `showActions()` 内置动作标注（高亮被点击元素+动作标题） |
| 字幕 | 需手动注入 DOM + textContent | `showChapter()` / `showOverlay()` 内置 |
| 导航后重注入 | 每次导航后必须重新调用 | 自动持久，无需重注入 |
| 实时帧流 | 不支持 | `onFrame` 回调可流式输出 JPEG 帧（AI vision 用） |
| 视频格式 | WebM（recordVideo） | WebM（screencast.start） |
| 代码量 | 多（injectCursor + injectSubtitleBar + showSubtitle） | 少（screencast.start + showActions + showChapter） |

### Screencast 脚本模板

```javascript
'use strict';
const { chromium } = require('patchright');
const path = require('path');
const fs = require('fs');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const CDP_URL  = process.env.CDP_URL  || 'http://localhost:9222';
const VIDEO_DIR = path.join(__dirname, 'output');
const OUTPUT_NAME = 'demo-FEATURE.webm';

(async () => {
  // noDefaults: true — 不干扰用户浏览器状态
  const browser = await chromium.connectOverCDP(CDP_URL, { noDefaults: true });

  const existingContexts = browser.contexts();
  const cookies = existingContexts.length > 0
    ? await existingContexts[0].cookies()
    : [];

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  if (cookies.length > 0) await context.addCookies(cookies);

  const page = await context.newPage();

  // 开始录制 + 动作标注
  await page.screencast.start({ path: path.join(VIDEO_DIR, OUTPUT_NAME) });
  await page.screencast.showActions({ position: 'top-right' });

  try {
    // Step 1 - 登录
    await page.goto(`${BASE_URL}/login`);
    await page.waitForTimeout(2000);
    const alreadyLoggedIn = await page.locator('[data-testid="user-avatar"], .user-menu, .avatar').first().isVisible().catch(() => false);
    if (!alreadyLoggedIn) {
      await page.screencast.showChapter('Step 1 - 登录', { duration: 2000 });
      // 登录操作...
      await page.waitForTimeout(4000);
    }

    // Step 2 - 概览
    await page.goto(`${BASE_URL}/dashboard`);
    await page.screencast.showChapter('Step 2 - 概览', { duration: 2000 });
    // 巡览 dashboard...

    // Step 3 - 主要流程
    await page.screencast.showChapter('Step 3 - 主要流程', { duration: 1500 });
    // 操作序列（showActions 会自动标注每次点击/输入）

    // Step 4 - 结果
    await page.screencast.showChapter('Step 4 - 结果', { duration: 3000 });

  } catch (err) {
    console.error('DEMO ERROR:', err.message);
  } finally {
    await page.screencast.stop();
    await context.close();
    // 不调用 browser.close() — Chrome 由 xiaobei 管理
  }
})();
```

### 何时选 Screencast vs 手动注入

- **Screencast**：需要动作标注、章节标题、代码简洁、或需要实时帧流（AI vision）时
- **手动注入**：需要完全自定义光标样式、非标准 overlay 位置、或需要兼容 Patchright < 1.59 时
- **可混合使用**：Screencast 录制 + 手动注入自定义 overlay（Screencast 不排斥页面上的 DOM 元素）

---

## Checklist Before Recording

- [ ] Phase 1 完成，每个页面字段映射已确认
- [ ] Phase 2 完成，全流程手动走通无报错
- [ ] 脚本选择器来自 Phase 1/2 的实际观察，无假设
- [ ] 每次导航后重新调用 `injectCursor` 和 `injectSubtitleBar`
- [ ] 所有点击使用 `moveAndClick`（含描述性 label）
- [ ] 可见输入使用 `typeSlowly`
- [ ] 滚动使用 smooth 模式
- [ ] 关键过渡点有 `showSubtitle`

## Common Pitfalls

1. 导航后光标消失 → 重新注入
2. 视频速度太快 → 增加停顿
3. 光标瞬移 → 点击前先 `moveAndClick`
4. Select placeholder 看起来非空 → Phase 1 时确认 value 是否为 `""` 或 `"0"`
5. 弹窗感觉突兀 → 确认前增加阅读停顿
6. 视频文件路径随机 → `copyFileSync` 到固定名称
7. **富文本编辑器用 `fill()` 填充** → 会导致编辑器无法识别内容，必须用 `pressSequentially()`
8. **混淆标题和正文输入框** → Phase 1 必须明确区分，标题和正文通常是独立的元素

---

## Browser Operation Best Practices（浏览器操作最佳实践）

以下经验来自实际项目验证，适用于 Phase 1/2 使用 browser tool 探查页面时：

### 1. 超时错误处理

当 browser tool 或 patchright 遇到超时错误时：

- **不要立即重启浏览器或放弃任务**
- 等待 30 秒后在原页面继续操作
- 若仍无法操作，再等待 30 秒
- 只有在等待 60 秒后仍报错，才考虑关闭浏览器重开
- 关闭重开后仍报错才是真的出错，需停止并反馈用户

### 2. 文件上传处理（browser tool）

若在 Phase 1/2 需要通过 browser tool 上传文件（如测试上传功能）：

- 文件必须先复制到 `/tmp/openclaw/uploads/` 目录（沙箱限制）
- `browser upload` 返回超时错误**不代表上传失败**
- **禁止通过 `input.files.length === 0` 判断上传是否失败**
- 正确做法：上传后用 `snapshot` 检查页面状态（进度条、缩略图、处理状态文字）
- 等待策略：30s → snapshot → 失败再等 60s → snapshot → 最多 3 次

### 3. 表单字段映射

在 Phase 1 建立字段映射时，特别注意：

- **标题和正文通常是独立的输入框**，必须分别定位和操作
- 标题通常是 `<input>` 或 `<textarea>`
- 正文可能是富文本编辑器（`contenteditable`），需要特殊处理
- Select 组件要区分 placeholder 选项和真实选项
- 提交按钮可能有多个（如"保存"、"提交"、"发布"），通过精确文本匹配

### 4. 内容输入最佳实践

- 使用 `type` + `slowly: true` 或 `pressSequentially()` 进行可见输入
- 对于富文本编辑器，**禁止使用 `fill()` 填充内容**
- 输入前确认元素已聚焦（可通过点击或 `focus()`）
- 长文本分段输入，避免一次性输入过多内容

### 5. 页面状态检查

操作后检查页面状态的方式：

- 使用 `snapshot` 而非 `waitForSelector`（更稳定）
- 检查关键元素是否存在、可见、可点击
- 检查是否有错误提示或验证消息
- 检查 URL 是否变化（导航成功）

---
