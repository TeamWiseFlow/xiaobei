---
name: wechat-channels-publish
description: 通过 camoufox-cli 持久化 session wechat-channel 发布视频到微信视频号，支持视频上传、封面上传、视频描述与短标题填写、即时发布。
---

# wechat-channels-publish — 工具说明

> 本文是 `expert-wx-channel` 专家包内的工具说明书，不独立出现在技能列表中。由相关 Workflow 指引调用。

通过 **camoufox-cli** 持久化 session `wechat-channel`（有且只有一个，fail-first 队列：同 session 已有命令在跑时新命令直接 fail）在微信视频号创作者中心发布视频。视频号创作者中心使用 **wujie 微前端**，所有表单元素在 `<wujie-app>::shadow-root` 内。

**业务页 `snapshot` 一律加 `-s "wujie-app"` 作用域**（下文简写 `snapshot -s`）：wujie 页面里主文档与子应用各有一个 body，整页 `snapshot` 会报 `locator('body') resolved to 2 elements` strict violation，拿不到任何 ref。只有登录页（无 wujie）可整页 snapshot。`click` / `fill` / `type` 按 ref 操作；`upload` 支持 ref 或 CSS 选择器（底层 Playwright setInputFiles，穿透 shadow DOM），无需 CDP hack。

**输入**：本地视频文件（`.mp4` / `.mov` / `.avi` / `.webm`）、**视频描述**（含话题标签，约 300 字为建议值——实测 409 字符平台照常接受，以页面输入框实际限制为准）、**短标题**（6-16 字，**不得含标点符号，只能用空格分隔**——见 Step 6 硬约束）。发布页改版后两项都能填，官方明确「填写短标题会获得更多流量」，因此**两项都必须填**，都由 main agent 拟定后交给本工具。
**输出**：视频号已发布作品。本工具**不抓取作品公开链接**——管理后台分享面板路线实践中不可靠（审核 / 转码中常不可用），链接由用户后补，调用方入库时升级（见文末「入库衔接约束」）。

> **短标题只在发布页存在**：作品管理页与 `wx-channel-engagement` 抓取都拿不到短标题，所以入库与匹配一律只用视频描述（见文末「入库衔接约束」）。

> **主力后端 = `target=camoufox`**。下方命令 / 示例只针对 `target=camoufox`。
> **`target=host` / `target=node`**：只按本说明书的「流程 + 提示事项」走——全部无头 / 频率限制 / 错误处理约定是**后端无关**的，照本说明书执行。不要照搬 `camoufox-cli ...` 命令，用你当前后端自带的浏览器工具语义调用即可。

---

## 前置条件

1. 持久化 session `wechat-channel` 已登录（登录态存 session profile 里）。本工具自管探活 + 登录，**不导出 cookie/UA 落中央存储**。登录和发布**全部走无头模式**（camoufox-cli 默认即 headless）。
2. 首次使用 / 登录态失效时，走**无头截图扫码**登录流：
   - `camoufox-cli --session wechat-channel --persistent --json open "https://channels.weixin.qq.com/platform/home"`
   - 等登录页 QR 二维码 `<img>` 注入完成（轮询 `eval` 检查 `document.querySelectorAll('img')` 有 `src` 以 `data:image` 开头的元素，最多等 10s）
   - `camoufox-cli --session wechat-channel --persistent --json screenshot /tmp/qr-wechat-channel.png` 截 QR PNG
   - 发 QR PNG 给用户，告知「**微信视频号** 登录已失效，请用微信扫码确认，完成后回复"已扫码"」
   - **Stop and wait**，用户回复后轮询当前 URL（`camoufox-cli --session wechat-channel --json url`），确认已跳走登录页（URL 含 `platform/home` 且不含 `login`）即登录就位
   - 登录后**close session**——登录态落磁盘 profile，不留进程占内存；下次 `--session wechat-channel --persistent` 重起无头即恢复，用完再 close。

> **不导出 cookie/UA**——登录态只在 session profile 里闭环，不落 `~/.openclaw/logins/`。本工具不调用 `cookies export` / `identity export`。

---

## 发布流程

### Step 1: 导航到发布页

```
camoufox-cli --session wechat-channel --persistent --json open "https://channels.weixin.qq.com/platform/post/create"
```

等待 **5 秒**（wujie 需要额外时间初始化 shadow DOM）。

### Step 2: 检查登录态

```
camoufox-cli --session wechat-channel --json url
```

URL 含 `login` → 走前置条件的无头截图扫码登录流。需要看页面内容时：登录页可整页 `snapshot`；发布页（wujie 已加载）必须 `snapshot -s "wujie-app"`。

### Step 3: 上传视频

```
camoufox-cli --session wechat-channel --persistent --json upload "input[type=file]" <video.mp4>
```

- 发布页常驻一个隐藏 `<input type="file">`，**直接用选择器 upload，不要先 click 上传按钮**——click 触发按钮后 snapshot 里并不会出现 file input ref，「click → snapshot 拿 ref → upload ref」路线走不通。
- 此时页面只有这一个 file input，裸选择器 `input[type=file]` 唯一命中。**封面弹窗打开后页面会有两个 file input**，裸选择器 strict violation——视频上传必须在打开封面弹窗之前完成（封面见 Step 5）。

### Step 4: 等待上传+转码完成

每 3 秒 `snapshot -s "wujie-app"` 检查一次页面状态：
- 上传中：shadow DOM 内存在 `[class*="uploading"]` 或 `[class*="progress"]`
- 转码中：`[class*="transcoding"]`
- 完成：出现 `<video>` 预览或 `[class*="preview-video"]` 或文本"上传成功"/"转码完成"
- 失败：`[class*="upload-fail"]` 或文本"上传失败"
- **最长等待 3 分钟**（大视频转码可能较慢）

### Step 5: 设置封面（有定稿封面图时默认执行）

转码完成后、填描述前做。发布页右侧「封面预览」区有两个封面入口，流程相同：

- `编辑 个人主页卡片 3:4`（作品主页展示卡）
- `编辑 分享卡片 4:3`（朋友圈/聊天分享卡）

```
1. 优先 eval dispatchEvent 点击目标卡片的「编辑」按钮（编辑按钮是缩略图上的悬浮层
   DIV.edit-btn，snapshot 拿到的 ref click 常点到文本容器上超时），按卡片名区分两个
   入口（个人主页卡 3:4 / 分享卡 4:3——个人主页卡片入口把 '分享卡片' 换成 '个人主页卡片'）：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{let t=null;const walk=(r)=>{if(!r||t)return;if(r.nodeType===1){const x=(r.innerText||'').trim();if(x.indexOf('编辑')===0&&x.indexOf('分享卡片')>=0){t=x;r.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));r.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));r.click();return;}if(r.shadowRoot)walk(r.shadowRoot);}for(const c of r.children||[])walk(c);};walk(document);return t?'clicked':'not found';})()"
   - 悬浮层按钮只认完整事件序列：mousedown + mouseup + click 三连 dispatch，单 r.click() 可能不触发
   - eval 返回 not found 或点击无效（弹窗没弹出）时，降级 snapshot -s "wujie-app" 拿「编辑」按钮 ref → click
2. 封面编辑弹窗打开（标题如「编辑分享卡片」，副标题「将会用在朋友圈、聊天等场景」），两种封面来源：
   - 从视频中选择封面：一排视频帧缩略图（胶片条），click 选一帧
   - 上传封面：先点「上传封面」入口（`+` 号方框按钮；ref click，或 eval 递归匹配
     innerText 含「上传封面」的节点 click——写法同 1 的 fallback，匹配条件换成
     x.indexOf('上传封面')>=0&&x.length<30）
3. 上传封面图——必须带 accept 限定选择器：
   camoufox-cli --session wechat-channel --persistent --json upload 'input[type=file][accept*="image"]' <cover.jpg>
   - 封面 file input 的 accept 为 image/jpeg,image/jpg,image/png
   - ❌ upload "input[type=file]" —— 弹窗打开后页面有视频+封面两个 file input，裸选择器 strict violation
4. 上传后封面显示在裁剪框（虚线选区可拖动调整构图），右侧「效果预览」实时同步（朋友圈/聊天模拟卡）
5. snapshot -s "wujie-app" 找弹窗底部右侧「确认」按钮 ref → click 保存返回发布页（「取消」= 放弃本次封面设置）
6. 两个卡片入口都要设置时，重复 1-5（同一张源图在各自裁剪框里分别调构图）
```

### Step 6: 填写视频描述 + 短标题（两项都必填）

**视频描述**——描述框是 `div[data-placeholder="添加描述"]`，`contenteditable` 属性为空串，aria snapshot 里**没有独立 textbox ref**（合并进「视频描述 添加描述 #话题 @视频号 短标题」一行 text），`click ref → type` 走不通。全程用 eval，四步：

```
1. 聚焦（递归穿透 shadow DOM 找描述框 → scrollIntoView + focus + click）：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{let t=null;const walk=(r)=>{if(!r||t)return;if(r.nodeType===1){if(r.getAttribute&&r.getAttribute('data-placeholder')==='添加描述'){t=r;return;}if(r.shadowRoot)walk(r.shadowRoot);}for(const c of r.children||[])walk(c);};walk(document);if(!t)return 'not found';t.scrollIntoView({block:'center'});t.focus();t.click();return 'focused';})()"
   - 返回 focused 才能继续；not found → 等 2 秒 wujie 初始化后重试
   - ❌ 不要按 contenteditable='true' 过滤——该属性是空串，按 data-placeholder 定位
2. 插正文（execCommand 在当前焦点处插入，真实触发 input 事件；话题标签直接写在描述中；约 300 字为建议值，不因字数疑虑截断文案——以页面输入框实际限制为准，插入后第 4 步 eval 校验长度）：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{const ok=document.execCommand('insertText',false,'<正文>');return ok?'inserted':'execCommand failed';})()"
3. 换行 + 逐段插署名/话题标签（insertParagraph 与 insertText 交替）：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{document.execCommand('insertParagraph');document.execCommand('insertText',false,'<署名段>');document.execCommand('insertParagraph');document.execCommand('insertParagraph');document.execCommand('insertText',false,'<#话题标签段>');return 'done';})()"
   - ❌ 不要把 \n 塞进 insertText 指望换行——编辑器不一定转成段落，必须 insertParagraph
   - 引号安全：JS 串用单引号；文案内单引号写成 \'；文案含 $ 或反引号时 shell 双引号会触发替换——发布文案定稿时避免这两类字符
4. 校验（读 innerText 长度与头尾，对照定稿文案）：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{let t=null;const walk=(r)=>{if(!r||t)return;if(r.nodeType===1){if(r.getAttribute&&r.getAttribute('data-placeholder')==='添加描述'){t=r;return;}if(r.shadowRoot)walk(r.shadowRoot);}for(const c of r.children||[])walk(c);};walk(document);if(!t)return 'not found';const txt=t.innerText||'';return {len:txt.length,head:txt.slice(0,40),tail:txt.slice(-60)};})()"
   - 校验不过（缺段/串位）：重跑 1 聚焦后 execCommand('selectAll') + execCommand('delete') 清空，再从 2 重插
```

> **话题标签段格式（硬约束）**：标签段只能是半角 `#` + 空格分隔的 `#标签` 项，整行不得出现任何其他字符——不加前缀或分组标题（如「【三层标签】」）、不加分隔符（／、/、—、顿号）、不用全角 `＃`。混入这些字符会导致**整行标签全部不被视频号识别渲染（失效）**。DNA 的分层/分组标签策略只用于挑标签，结构标记不进正文。
>
> - ✅ `#AI员工 #开源工具 #影视解说 #Wiseflow #一人成团 #Agent327`
> - ❌ `【三层标签】＃影视解说 ＃反转 ＃悬疑短片 ／ ＃露营装备 ＃周末徒步 ＃户外路线 ／ ＃遗憾 ＃十年`
>
> 定稿文案已含违规字符时，先清洗成纯标签行再插入，不要照插。

**短标题**——真实 `<input>`（placeholder 含「短标题」，官方提示形如「填写短标题有机会获得更多流量」），aria snapshot 有独立 ref，直接填：

```
1. snapshot -s "wujie-app" 拿短标题 textbox ref
2. camoufox-cli --session wechat-channel --persistent --json fill <短标题-ref> "<短标题文本>"
   - fill = 清空 + 输入；6-16 字，不与视频描述重复堆砌
   - 页面对短标题有字数上限提示时按页面为准裁到上限内
3. 校验必须 eval 读 .value——填完后 aria snapshot 里该框仍显示占位文本，snapshot 复核不可信：
   camoufox-cli --session wechat-channel --persistent --json eval "(()=>{let t=null;const walk=(r)=>{if(!r||t)return;if(r.nodeType===1){if(r.tagName==='INPUT'&&r.placeholder&&r.placeholder.indexOf('短标题')>=0){t=r;return;}if(r.shadowRoot)walk(r.shadowRoot);}for(const c of r.children||[])walk(c);};walk(document);return t?('value:'+(t.value||'')):'not found';})()"
   - value 与短标题一致 → 过；为空 → 重新 fill 再校验
```

> **短标题不得含标点符号（硬约束）**：短标题里不能出现任何标点（逗号、顿号、问号、感叹号、冒号、引号等），分隔只能用空格——该字段按纯文本处理，标点会被平台拒掉或截断。
>
> - ✅ `兔子睁眼 恶霸慌了`
> - ❌ `兔子睁眼，恶霸慌了`（逗号去掉后直接填会变 `兔子睁眼恶霸慌了` 短语粘连——标点要**替换成空格**，不是删除）
>
> 定稿文案已含标点时，先清洗（标点→空格、连续空格压成一个）再 fill，不要照填。

> 改版后发布页字段名与提示文案可能微调：**以 snapshot -s 读到的实际 placeholder / 标签文本为准**定位，不要写死选择器。找不到短标题字段时（页面回滚或灰度未开），只填视频描述并在回报里注明「短标题字段未出现」，不要把它塞进描述。

### Step 7: 发布

> 视频号发布不必勾选"原创声明"，发布后用户会在手机端补充。

```
1. snapshot -s "wujie-app" 拿到"发表"按钮 ref（文本为"发表"或"发布"，在 shadow DOM 内）
2. 确认按钮不是 disabled 状态（snapshot -s 看）
3. camoufox-cli --session wechat-channel --persistent --json click <发表-ref>
4. 若弹出"原创声明弹窗"，snapshot -s 拿"直接发表"按钮 ref → click
```

### Step 8: 确认发布成功

等待 4 秒后检查（`url` 命令 + `snapshot -s "wujie-app"`）：
- 页面自动跳转到视频管理列表页
- 或 URL 变为 `https://channels.weixin.qq.com/platform/post/list`
- 刚发表的作品通常在第一个；处于转码中（封面缩略图灰色、转圈）属正常，不影响发布成功判定，**不必等转码完成**。

> 管理页若 `-s "wujie-app"` 报作用域不存在/为空（该页未走 wujie 容器），退回整页 snapshot。

确认发布成功后 close session 并回报。**不要尝试在管理后台抓取作品链接**——分享面板路线实践中不可靠（审核 / 转码中常不可用），已从本流程移除。回报时告知用户作品已提交，请其后续在手机端或后台「分享」中获取作品链接（`https://weixin.qq.com/sph/xxxx`）提供给我们，由调用方按「入库衔接约束」补录升级。

---

## 保存草稿

在 Step 7 中 snapshot -s "wujie-app" 找"存草稿"按钮 ref → click（而非"发表"）。

---

## 手动模式

如果需要人工检查表单后再发布：
1. 完成到 Step 6（封面、视频描述、短标题都已设置并校验通过）
2. **不自动 click 发表**，告知用户在浏览器中手动检查并点击
3. 注意：不操作时标签页约 30 秒后可能被重置为空白页

---

## 必做约束

- **用完即 close 持久化 session `wechat-channel`**——登录态 + 指纹冻结在磁盘 profile，不留进程占内存；下次发布 `--session wechat-channel --persistent` 重起无头即恢复。只在 session 卡死时 `camoufox-cli --session wechat-channel --json close` teardown。
- 同 session 已有命令在跑时，新命令 fail-first（返回 `session wechat-channel 正忙，请等待当前操作完成后再试`）——读到这条文本就等当前操作完成再重试，不要盲试。

---

## Session 共享约束（与 `wx-channel-engagement` 共管）

本工具与 `wx-channel-engagement` **共用同一个 `wechat-channel` 持久化 session**，靠 session 名字符串约定共享同一 profile 目录与登录态——任一工具登录后另一个不需重登，反之亦然。单一 session、单一 IP、单一 profile，避免多 session 多 IP 的风控风险。

- **fail-first 队列**：同 session 已有命令在跑时，新命令直接 fail。读到 `session wechat-channel 正忙` → exit 3，调用方（agent）等待当前操作完成后再试，不自动排队、不自动 close 正在跑的 session。
- **登录态闭环**：不导出 cookie/UA/token——登录态在 `wechat-channel` session profile 里就位即可。失效时走本工具前置条件的无头截图扫码重登流，或由 `wx-channel-engagement` 自己的重登流触发。
- **不走 login-manager**：本工具自管 `wechat-channel` session 的探活 + 登录 + 重登。

---

## Pitfalls

### pitfall: wujie_shadow_dom

- **触发**：访问创作者中心任何页面
- **症状**：常规 DOM 选择器找不到表单元素
- **workaround**：`camoufox-cli snapshot -s "wujie-app"` 穿透 shadow DOM 拿 ref，后续 `click` / `fill` / `type` 按 ref 操作。fallback 才需要 `eval` 里手写递归 walk（见 Step 5/6 代码片段，`document.querySelector('wujie-app').shadowRoot` 单层写法不够——表单在更深层嵌套 shadow root 里）

### pitfall: snapshot_double_body

- **触发**：对创作者中心业务页（wujie 已加载）做整页 `snapshot`
- **症状**：`locator('body') resolved to 2 elements` strict violation，拿不到任何 ref
- **workaround**：一律 `snapshot -s "wujie-app"` 限定作用域；只有登录页（无 wujie）可整页 snapshot

### pitfall: desc_box_no_aria_ref

- **触发**：填视频描述（Step 6）
- **症状**：描述框 `div[data-placeholder="添加描述"]` 的 `contenteditable` 属性为空串，aria snapshot 里没有独立 textbox ref（合并进「视频描述 添加描述 #话题 @视频号 短标题」一行 text），`click ref → type` 走不通
- **workaround**：Step 6 的 eval 四步——递归定位 focus() → `execCommand('insertText')` / `('insertParagraph')` → 读 innerText 校验

### pitfall: short_title_placeholder_stale

- **触发**：短标题 fill 后想用 snapshot 复核
- **症状**：aria snapshot 里该框仍显示占位文本「填写短标题有机会获得更多流量」，无法确认是否已填入
- **workaround**：eval 递归找 placeholder 含「短标题」的 INPUT 读 `.value` 校验（Step 6 代码）

### pitfall: cover_upload_strict_violation

- **触发**：封面弹窗打开后 upload 封面图
- **症状**：`upload "input[type=file]"` 报 strict violation——页面同时存在视频上传与封面上传两个 file input
- **workaround**：封面用 `upload 'input[type=file][accept*="image"]' <图>`；视频上传（Step 3）在封面弹窗打开前做，裸选择器才唯一命中

### pitfall: video_transcode_timeout

- **触发**：大视频文件上传后转码
- **症状**：等待超过 3 分钟仍未完成
- **workaround**：增加等待时间，或检查视频格式是否兼容

### pitfall: login_qr_only

- **触发**：访问视频号页面未登录
- **症状**：跳转到扫码登录页，无用户名/密码选项
- **workaround**：走前置条件的无头截图扫码流程（screenshot QR PNG → 发用户扫码 → 轮询 URL 确认登录就位）

### pitfall: short_title_punctuation_rejected

- **触发**：短标题文案含标点（逗号、顿号、问号、感叹号等）
- **症状**：平台拒掉或截断短标题，或发布后短标题显示异常
- **workaround**：短标题只能是「文字 + 空格」——标点**替换成空格**（不是删除，删了短语会粘连），连续空格压成一个再 fill

### pitfall: short_title_field_missing

- **触发**：发布页填写短标题时
- **症状**：snapshot 里找不到「短标题」输入框（页面灰度未开或改版回滚）
- **workaround**：只填视频描述并发布，回报里注明「短标题字段未出现」；不要把短标题拼进视频描述，也不要把描述截断当短标题

### pitfall: form_reset_on_idle

- **触发**：填写完表单后长时间不操作（旧版 camoufox-cli daemon idle 60s 自退后新起 daemon，page 变空白；2026-08-22 起已默认关闭 idle 自退，此 pitfall 应不再复现）
- **症状**：标签页被重置为空白页
- **workaround**：填完表单后尽快发布；若仍复现，检查 daemon 是否被并发上限（6 个）驱逐或被 `close --all` 误伤

---

## 错误处理

| 情况 | 处理 |
|------|------|
| 未登录 | 走前置条件的无头截图扫码登录流，重试一次 |
| snapshot 报 `body resolved to 2 elements` | 整页 snapshot 撞上 wujie 双 body，改用 `snapshot -s "wujie-app"` |
| 上传失败 | 检查视频格式（mp4/mov/avi/webm），重试一次 |
| upload 报 strict violation | 页面有两个 file input：视频用裸 `input[type=file]`（封面弹窗打开前），封面用 `input[type=file][accept*="image"]` |
| execCommand 返回 failed / 描述没插入 | 焦点丢了——重跑 Step 6 的聚焦 eval（返回 focused）后再插 |
| 转码超时 | 增加超时时间，或告知用户稍后在创作者中心检查 |
| 发表按钮 disabled | 检查必填字段是否已填写（视频是否上传完成、视频描述与短标题是否都通过 eval 校验） |
| shadow DOM 元素找不到 | 等待更长时间让 wujie 初始化，或刷新页面 |
| session 正忙（fail-first） | 等当前操作完成再重试，不要盲试 |

---

## 入库衔接约束

本工具只管发布到视频号后台，**不做发布记录入库**；入库由 Content Production Workflow 编排（调 `published-track record`）。调用方必须注意：

> **`published-track record --platform wx_channel --title` 必须传 Step 6 填的完整视频描述**（含 hashtag，约 300 字为建议值，实际以页面输入框为准）；**短标题不入库**。

原因：作品管理页只展示视频描述，`wx-channel-engagement` 抓取匹配用的也是视频描述。`pub_wx_channel.title` 是数据库字段名，语义为完整视频描述；把短标题写进去会导致后续抓取匹配失败。短标题只留在作品目录的 `publish-copy.md` 里备查。

> **首次入库不传 `--publish-url`**：本工具不抓取作品链接，链接由用户后补（同 `wx-mp-publisher` 的 URL 升级机制）。用户提供链接后，用相同 `--source-folder` 重跑 `published-track record` 补 `--publish-url`——upsert 语义升级记录，不重复插行。`wx-channel-engagement` 抓取不依赖 `publish_url`，留空不影响日常数据采集。
