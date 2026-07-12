---
name: web-form-fill
description: 网络表单填报技能 — 从信息搜集到浏览器填报的完整工作流，确保框架受控组件正确写入、页面切换前暂存、最终提交由用户确认。
metadata:
  openclaw:
    emoji: 📝
---

# Web Form Fill — 网络表单填报技能

面向在线表单填报场景：申报系统、比赛报名、补贴申请、信息登记等。核心原则：**先看后填、模拟真人、切页必存、提交由人**。

**依赖技能**：`browser-guide`（浏览器操作最佳实践）

> **主力后端 = `target=camoufox`**（`camoufox-cli`）。下方「§3 浏览器填报」的命令 / 示例 / 控件填写方法只针对 `target=camoufox`。
> **`target=host` / `target=node`**：§1 信息搜集 / §2 字段清单 / §4 提交前确认 这些后端无关的步骤照本 skill 执行；§3 浏览器填报只按「流程 + 提示事项」走，不要照搬 `camoufox-cli ...` 命令——用你当前后端自带的浏览器工具语义调用即可。「逐字 type」「切页必暂存」「提交由人」这些约定是后端无关的，照本 skill 执行。

---

## 工作流程

### Step 1：全量信息搜集

**打开浏览器后，先完整浏览整个表单，不要急着填。**

1. 从第一个页面/栏位开始，逐页点击所有 tab/步骤/栏位
2. 每到一个新页面，记录：
   - 页面/栏位名称
   - 所有字段的 **label、类型、是否必填、字数限制、格式要求**
   - 需要上传的附件类型和格式要求
   - 任何特殊控件（下拉单选/多选、日期选择器、级联选择、富文本编辑器等）
3. 随时将搜集结果写入一个 markdown 文件（建议命名为 `form-fields-{项目简称}.md`），保持与表单相同的页面/段落结构
4. 浏览过程中 **不要填写任何内容**，只看和记

**markdown 文件结构示例**：

```markdown
# XX大赛申报 — 字段清单

## 概要
- 项目名称 [必填] [text] [限50字]
- 行业分类 [必填] [级联下拉] 一级→二级
- 科技创新领域 [必填] [下拉单选]
- 参赛渠道 [必填] [下拉多选]
- 以投代评 [必填] [radio: 是/否]
- 服务需求 [多选] 最多3项
- 期望融资金额 [必填] [number] 万元
- 股权释放比例 [必填] [number] %

## 参赛项目情况
- 项目名称 [必填] [text] （概要中已填，此处联动）
- 前沿技术热点归属 [必填] [text] 最多5个关键词，逗号分隔
- 项目主要技术、产品及服务 [必填] [富文本] 2000字以内，可插入图片
- 项目产品市场分析及竞争优势 [必填] [富文本] 2000字以内
- 商业模式 [必填] [富文本] 1000字以内

## 企业基本信息表
...

## 附件
- 营业执照 [必填] [PDF/图片]
- ...
```

### Step 2：填写字段清单

回到 markdown 文件，逐项填写准备好的内容：

1. 根据已有资料（MEMORY.md、工作区文件、用户之前提供的信息）直接填入
2. 缺失的信息 **主动问用户**，不要自己编造
3. 找不到且用户也未指定的附件，列出清单请用户准备
4. 每个富文本字段，先写纯文本内容，后续在浏览器中输入

**问用户的典型场景**：
- "XX字段应该选择哪个选项？"
- "XX附件文件在工作区中未找到，请提供文件路径或上传。"
- "XX选项选是还是否？"

### Step 3：浏览器填报

信息齐全后，开 camoufox-cli session 逐页填报。

**session 约定**：申报系统这类**不涉及平台登录态长期化**的站点走临时性 session（不带 `--persistent`，每次随机指纹，关闭自清）。如果该表单本身需登录（如某政务网账号），先按 login-manager 流程登录态就绪，再开 session 导入 cookie/UA。

```bash
SESSION="formfill-$(date +%s)"
camoufox-cli --session "$SESSION" --headless --json open "<表单首页 URL>"
# …snapshot / click / type / select / upload 填报…
# 任务结束 close
camoufox-cli --session "$SESSION" --json close
```

> 涉及扫码 / 短信 / 验证码的申报站点必须 `--headed`（browser-guide 原则 2），用户能在浏览器里手动过。

#### 3-A. 填报顺序

1. 回到表单第一页/栏位
2. 按 markdown 文件中的顺序逐字段填写
3. 每填完一页/栏位，检查是否有 **暂存/保存** 按钮，有则 `click` 点暂存
4. 切换到下一页/栏位前，**必须确认当前页已暂存**
5. 重复直到所有页面填完

#### 3-B. 字段填写方法

**核心原则：统一用 camoufox-cli 的 `type` 子命令逐字符输入，对所有站点、所有输入框一视同仁。**

##### 文本输入字段（input / textarea / contenteditable）

**唯一方法：`camoufox-cli --session <s> --json type <ref> "<文本>"`**

- `type` 走浏览器真实输入管线（逐字符 `keydown` → `char` → `keyup`），与真人键盘输入完全一致
- snapshot ref 优先：先 `snapshot` 拿到输入元素的 ref（如 `@e7`），再 `type @e7 "<文本>"`。不要自己 hack CSS selector
- **推荐节奏**：默认 delay 即可兼顾速度与拟人效果；防机器人检测场景调慢（见下方「防机器人」）

**填写流程**：

```
对每个文本字段：
  1. snapshot 拿到该字段的 ref
  2. click <ref> 聚焦（顺带 scrollIntoView）
  3. 清空已有内容（见下方清空方式）
  4. camoufox-cli --session <s> --json type <ref> "要填入的文本"
  5. 验证写入是否生效（见 3-C 节）
  6. 如果验证失败：
     a. 清空内容
     b. 重新聚焦后重试一次 type
     c. 仍然失败 → 记录该字段为"无法自动填写"，继续下一个字段
```

**为什么 `type` 就够了**：

| 场景 | `type` 是否生效 | 原因 |
|------|---------------------|------|
| 原生 input/textarea | ✅ | 逐字符 keydown/char/keyup 走浏览器真实输入管线 |
| Vue/React v-model 受控组件 | ✅ | 框架监听 input 事件，type 触发的 keydown → input 事件链完整 |
| Slate/wangEditor/Tiptap 编辑器 | ✅ | 逐字符 keydown 会触发浏览器的 `beforeinput` 事件，Slate 监听的就是这个 |
| 有输入 mask 的字段 | ✅ | 逐字符输入让 mask 逻辑逐字处理，不会跳过格式化 |
| 防机器人检测的站点 | ✅ | 默认 delay 模拟真人节奏，不触发异常检测 |

**禁止的方式**：
- ❌ `eval` 直接设 `innerHTML` / `textContent` — 框架不感知，placeholder 不消失，暂存后内容丢失
- ❌ `eval` 直接赋值 `el.value = "xxx"` 不发事件 — 框架完全无感知
- ❌ 不聚焦就直接写值 — 不会触发任何事件
- ❌ `camoufox-cli fill <ref> "<文本>"` — 一次性塞入整段文本，不触发逐字事件链，受控组件和 mask 字段容易出问题

##### 下拉选择（select）

逐级尝试：

| 级别 | 方法 |
|------|------|
| A | `snapshot` 拿到 select 的 ref → `click <ref>` 打开下拉面板 → snapshot 拿目标选项 ref → `click <选项-ref>` |
| B | `click <ref>` 打开 → `press <ref> "ArrowDown"` 方向键选择 → `press <ref> "Enter"` 确认 |
| C | fallback：`eval` 设 native setter + dispatchEvent('change') |

自定义下拉（非原生 `<select>`，如 Element Plus el-select、Ant Design Select）：
- 需要先 `click` 触发按钮打开弹层
- 在弹层中 `snapshot` 找目标选项 `click`
- 部分组件支持键盘搜索：聚焦 → 输入关键字过滤 → 选择

##### Radio / Checkbox

1. `snapshot` 拿到目标选项 ref → `click <ref>`
2. snapshot 验证选中状态
3. 如果点击无效，尝试用键盘：`click <ref>` 聚焦 → `press <ref> "Space"` 切换

##### 日期选择器

逐级尝试：

| 级别 | 方法 |
|------|------|
| A | `click` 日期输入框 → `snapshot` 拿日历面板里年/月/日 ref → 逐个 `click` |
| B | `click` 日期输入框聚焦 → `type` 输入日期字符串 |
| C | fallback：`eval` 设 native setter + dispatchEvent |

##### 文件上传

1. `snapshot` 拿到 `<input type="file">` 或上传按钮的 ref
2. `camoufox-cli --session <s> --json upload <ref> <file-path>`（fork 加的 upload 命令，底层 Playwright `setInputFiles`，穿透 shadow DOM）
3. 多文件可一次传：`upload <ref> <file1> <file2> <file3>`
4. 文件不在本机时，告知用户手动上传

#### 3-C. 填写验证

| 控件类型 | 验证方式 | 通过条件 |
|---------|---------|---------|
| 普通 input | `snapshot` 看 ref 的 value / placeholder 可见性 | value 包含预期内容 且 placeholder 不可见 |
| contenteditable / Slate 编辑器 | `snapshot` 看 `textContent` 和 placeholder 元素 | `textContent` 包含预期内容 且 placeholder 元素 `display: none`。**延迟 50ms 再验证** — Slate DOM 更新有延迟 |
| 下拉 select | snapshot 看选中项文本 | 选中项文本与预期一致 |
| radio/checkbox | snapshot 看选中状态 | 选中状态符合预期 |

**验证失败的处理**：
1. 清空当前字段内容（避免残留脏数据）
2. 重新聚焦后重试一次 `type`
3. 仍然失败 → 记录到"无法自动填写"清单，继续填下一个字段

#### 3-D. 页面切换规则

**切换页面/栏位前，必须执行**：

1. `snapshot` 检查当前页面是否有 **暂存 / 保存 / 保存草稿** 按钮
2. 如果有，`click` 点暂存，等待"保存成功"提示
3. 暂存后，验证关键字段值是否还在（防止暂存失败丢数据）
4. 然后再 `click` 切换页面

**如果当前页没有暂存按钮**：
- 检查是否有自动保存指示（"已自动保存"提示、保存状态图标等）
- 如果没有自动保存，截图告知用户当前页无保存机制，请用户确认是否继续

### Step 4：提交前确认

**所有页面填写完成后**：

1. 从第一页开始，逐页 `snapshot` 检查所有字段值是否正确
2. `camoufox-cli --session <s> --json screenshot /tmp/final-form.png` 截图，或 `eval` 导出表单内容，发送给用户审阅
3. 明确告知用户：**"所有内容已填写完毕，请检查确认后手动提交，或明确告知我提交。"**
4. **禁止自动 `click` "提交"按钮**，必须等用户明确指令

---

## 常见问题与对策

### 问题：填入内容后 placeholder 不消失

**原因**：框架内部状态未更新。

**解决**：确保用 `type` 逐字输入（会触发完整事件链），而非直接操作 DOM。type 失败时重新聚焦重试。

### 问题：暂存后切换页面，内容丢失

**原因**：框架内部状态为空，暂存提交的是空值。

**验证方法**：暂存后，导航到其他页面再回来，检查字段是否仍有值。

### 问题：Slate/wangEditor 编辑器填入后验证显示为空

**原因**：Slate 处理 `beforeinput` 后，文本已写入数据模型但 DOM 还没渲染完。

**解决**：验证前延迟 50ms+，等 Slate 微任务队列跑完再读 `textContent`。

### 问题：富文本编辑器无法输入

**对策**：
1. 确认 `click` 的是编辑器内容区域（`[contenteditable="true"]`），而非工具栏
2. 确认 `document.activeElement` 是编辑器或其子节点（`eval` 看）
3. 如果 type 无效，尝试先 `click` 工具栏按钮（如加粗）激活编辑器，再重新 type

### 问题：下拉选项不在视口中

**对策**：
1. 先 `scroll` 下拉面板使目标选项可见
2. 或用键盘导航：聚焦 select → `press` 方向键选择目标项 → `press` "Enter" 确认

### 问题：表单有防机器人检测

**对策**：
1. `type` 节奏调慢（在 camoufox-cli 默认基础上手动多停顿：每个字段间 `sleep 0.5-1`）
2. 字段间等待 0.5-1 秒
3. 如果触发验证码，按 `browser-guide` 的 CAPTCHA 处理流程操作

---

## 速查：填写操作模板

### 聚焦元素

```
1. snapshot 拿到目标元素的 ref（如 @e7）
2. camoufox-cli --session <s> --json click @e7   （顺带 scrollIntoView + 聚焦）
```

### 清空已有内容 — 普通 input/textarea

```
1. click <ref> 聚焦
2. camoufox-cli --session <s> --json press <ref> "Control+a"   （全选）
3. camoufox-cli --session <s> --json press <ref> "Backspace"   （删除）
4. snapshot 验证：ref 的 value 为空
```

### 清空已有内容 — contenteditable / Slate 编辑器

```
1. click <ref> 聚焦编辑器
2. camoufox-cli --session <s> --json press <ref> "Control+a"
3. camoufox-cli --session <s> --json press <ref> "Backspace"
4. sleep 0.05
5. snapshot 验证：编辑器 textContent 为空
```

### 文本输入（所有字段统一方法）

```
1. 聚焦 + 清空
2. camoufox-cli --session <s> --json type <ref> "要填入的内容"
3. 验证（见 3-C 节）
```

防机器人检测场景，节奏调慢：每输入一段 `sleep 0.3-1`，字段间 `sleep 1`。

### 文件上传

```
1. snapshot 拿到 <input type="file"> 或上传按钮 ref
2. camoufox-cli --session <s> --json upload <ref> <file-path> [<更多文件>...]
3. snapshot 验证缩略图 / "上传成功" 文本出现
```
