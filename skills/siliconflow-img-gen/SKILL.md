---
name: siliconflow-img-gen
description: Generate or edit images via 火山方舟 (Volcengine Ark) Seedream API.
  Text-to-image default model doubao-seedream-4.5（fallback doubao-seedream-5.0-lite）;
  image-edit supported via 1-3 reference images. Uses user's AWK_API_KEY
  (client-side only, never sent to server).
metadata:
  openclaw:
    emoji: 🖼️
    requires:
      bins:
      - python3
      env:
      - AWK_API_KEY
    primaryEnv: AWK_API_KEY
    homepage: https://www.volcengine.com/docs/82379/1541523
---

# 火山方舟 Seedream 图像生成

> **凭据**：用户自带 `AWK_API_KEY`（纯客户端，不入 server）。

Generate or edit images using 火山方舟 (Volcengine Ark) Seedream API.

Endpoint: `POST https://ark.cn-beijing.volces.com/api/v3/images/generations`

Two modes:
- **Text-to-image** — default model `doubao-seedream-4.5`（主力不可用时自动 fallback 到 `doubao-seedream-5.0-lite`）
- **Image-edit** — `--image` 触发；4.5+ 支持多图参考（1-3 张）

参考文档：<https://www.volcengine.com/docs/82379/1541523>

---

## Run

Note: Image generation can take 10–60 seconds. Set a higher timeout when invoking via exec (e.g., `exec timeout=120`).

**Do NOT set env vars inline** (e.g., `AWK_API_KEY=... python3 ...`). The env var is already in the system environment; inline assignments break the exec permission check.

通过 PATH 调用 wrapper，无需拼接脚本路径。

```bash
# Text-to-image (default model: doubao-seedream-4.5，失败自动 fallback doubao-seedream-5.0-lite)
siliconflow-img-gen --prompt "your prompt here"

# 指定其他 model（显式指定时不 fallback）
siliconflow-img-gen --prompt "your prompt" --model "doubao-seedream-5.0-lite"
siliconflow-img-gen --prompt "your prompt" --model "doubao-seedream-3-0-t2i-250415"

# Image-edit（1-3 张参考图）
siliconflow-img-gen --prompt "add a lighthouse" --image "https://example.com/source.jpg"
siliconflow-img-gen --prompt "blend" \
  --image "https://example.com/a.jpg" \
  --image2 "https://example.com/b.jpg" \
  --image3 "https://example.com/c.jpg"
```

### Text-to-image examples

```bash
# Square 2K (default)
siliconflow-img-gen --prompt "a futuristic city at dusk"

# Landscape 16:9
siliconflow-img-gen --prompt "mountain lake" --image-size 2848x1600

# Portrait 9:16
siliconflow-img-gen --prompt "mountain lake" --image-size 1600x2848

# Quality preset (火山的 2K / 3K / 4K 方式 1)
siliconflow-img-gen --prompt "4K 超清" --image-size 4K

# Save to specific directory
siliconflow-img-gen --prompt "sunset" --out-dir ./out/images
```

### Image-edit examples

```bash
# 单图生图
siliconflow-img-gen --prompt "make it night time" --image "https://example.com/photo.jpg"

# 多图融合（3 张）
siliconflow-img-gen --prompt "blend these photos" \
  --image  "https://example.com/a.jpg" \
  --image2 "https://example.com/b.jpg" \
  --image3 "https://example.com/c.jpg"
```

---

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt` | required | 图像描述（≤300 汉字 / 600 英文） |
| `--model` | auto | Model ID；默认 `doubao-seedream-4.5`（主力不可用自动 fallback `doubao-seedream-5.0-lite`）；显式指定时不 fallback |
| `--image-size` | `2048x2048` | 文生图尺寸。方式 1: `2K`/`3K`/`4K`；方式 2: `WxH`（如 2048x2048） |
| `--seed` | — | 随机种子 |
| `--watermark` | `false` | 是否加水印（xiaobei 默认不加，避免后续 image 工具处理） |
| `--response-format` | `url` | `url`（链接 24h 有效）/ `b64_json` |
| `--image` | — | 源图 URL 或 Base64（启用 image-edit 模式） |
| `--image2` | — | 第二张参考图（image-edit） |
| `--image3` | — | 第三张参考图（image-edit） |
| `--out-dir` | `./tmp/awk-img-<ts>` | 输出目录 |

### Valid `--image-size` values

> **火山方舟图像生成 size 限制**（参考 [API 文档](https://www.volcengine.com/docs/82379/1541523)）：
> - 方式 1（quality 预设）：`2K` / `3K` / `4K`
> - 方式 2（WxH）：总像素 ∈ [2560×1440=3686400, 4096×4096=16777216]；宽高比 ∈ [1/16, 16]
>
> 无效值会被脚本拒绝并 exit 1，错误信息列出所有合法选项。

**2K 推荐宽高像素值**（默认 quality 档）：

| Value | Ratio |
|-------|-------|
| `2048x2048` | 1:1 (default) |
| `2304x1728` | 4:3 |
| `1728x2304` | 3:4 |
| `2848x1600` | 16:9 |
| `1600x2848` | 9:16 |
| `2496x1664` | 3:2 |
| `1664x2496` | 2:3 |
| `3136x1344` | 21:9 |

---

## Output

- `*.jpg` 图像（火山默认 jpeg 输出；URL 24h 有效，按脚本约定下载到本地）
- `prompts.json` 索引 → prompt + URL + file
- `index.html` 缩略图 gallery

---

## 视频封面/海报最佳实践

适用于**图文混合素材**（短视频封面、社媒海报、信息图配图等）——需要模型一次性渲染文字与画面，而不是后期合成。

### 1. 参数推荐

| 参数 | 推荐值 | 原因 |
|------|--------|------|
| `--model` | `doubao-seedream-4.5` | 4.5 在文字渲染 / 中文支持上稳定 |
| `--image-size` | `2K` 或 `4K` | 高分辨率给文字留细节空间 |
| 比例 | 9:16 / 16:9 / 1:1 按平台选 | 火山 way 2 任意合法比例 |

### 2. Prompt 写法（关键）

**❌ 反例**（泛泛描述）：
> "Generate an attractive short-video cover with a title about AI"

**✅ 正例**（按视觉布局分段写，明确写出要渲染的文字）：
> "A dramatic vertical 9:16 short-video cover. Background: bold red-to-black gradient. Top: glowing AI chip icons with text 'DeepSeek'. Middle: large bold Chinese text '前几周 DeepSeek 还是神一般的存在' in white and gold gradient with sharp shadows. Bottom: dramatic red glowing Chinese text '为什么热度消散得这么快？' with lightning effects. Style: high contrast, modern tech poster, dramatic lighting, professional Chinese typography, sharp text rendering, cinematic, no watermarks."

要点：
- **要写的字直接写完整句子**，不要"加个标题"这种空指令
- **按布局分段**描述（top/middle/bottom 或 左/中/右），让模型知道字放哪
- **指定字体特性**：颜色、渐变、阴影、发光、风格
- **明确要求**："sharp text rendering"、"professional Chinese typography"
- 末尾加 "no watermarks" 排除水印（与脚本 `--watermark false` 双保险）

### 3. 可选设置

- `--watermark false`：必加（xiaobei 默认）
- `--seed N`：需要可复现时设固定值
- `--response-format b64_json`：避免依赖 URL 24h 失效（脚本默认 url）

### 4. 生成后必须验证

1. 用 `image` 工具分析图片，**逐项确认**：
   - ✅ 文字内容是否完全正确（不能错字、漏字、出现乱码字符）
   - ✅ 文字位置/对齐/排版是否符合预期
   - ✅ **没有意外的 logo/水印/UI 元素**（如有，加 `--negative-prompt`-like 描述重生成）
   - ✅ 主体内容符合 prompt
2. 异常则重新生成（最多 3 次），仍异常则标记失败继续

### 5. 输出格式

- 脚本默认 **JPG**（火山 4.5 默认 jpeg；5.0 lite 可选 png）
- 如果目标平台需要 **PNG**（如透明背景场景），调 `--response-format b64_json` + 后续转码
- 任何格式转换都用 PIL，**不做任何像素修改**

### 6. 完整示例

```bash
siliconflow-img-gen \
  --prompt "A dramatic vertical 9:16 short-video cover with bold red and black gradient background, glowing AI chip icons floating in the upper area, and large bold Chinese text '前几周 DeepSeek 还是神一般的存在' in the middle in white and gold gradient with sharp shadows. At the bottom, dramatic glowing red Chinese text '为什么热度消散得这么快？' with lightning-like effects. Visual style: high contrast, modern tech poster, dramatic lighting, professional Chinese typography, sharp text rendering, cinematic, no watermarks" \
  --image-size 1600x2848 \
  --watermark false \
  --out-dir /path/to/output
```

---

## ⚠️ 生成后必须验证

每张图生成后**必须**用 `image` 工具检查（不得跳过）：

- ❌ **异常**：纯色背景 / 文字乱码 / 意外 logo → 重新生成
- ✅ **正常**：符合 prompt 描述 → 继续下一步

最多重试 3 次，仍异常则标记失败并继续后续任务。

---

## Model 选择速查

| Model | 适用场景 | 备注 |
|-------|---------|------|
| `doubao-seedream-4.5` | 默认 / 通用（主力） | 文字渲染稳，多图融合支持；不可用时脚本自动 fallback |
| `doubao-seedream-5.0-lite` | fallback / 组图 / 工具调用 | 主力失败时自动切换；5.0 lite 起支持 tools/web_search |
| `doubao-seedream-3-0-t2i-250415` | 纯文生图（无 image edit） | 3.0 旧版，仅 t2i，需 `--model` 显式指定 |

---

## 🔧 模型开通指引（主力 + fallback 都失败时反馈给用户）

当 `doubao-seedream-4.5`（主力）与 `doubao-seedream-5.0-lite`（fallback）**都无法使用**时（典型表现：HTTP 400/403/404，或脚本 stderr 输出 `[guide] 请到火山引擎后台开通视觉模型`），说明用户的火山方舟账号尚未开通这两个视觉模型。**Agent 应主动把下面的开通步骤反馈给用户**，不要静默失败或反复重试。

### 开通步骤

1. 打开火山引擎方舟后台：<https://console.volcengine.com/ark/>
2. 左侧「**系统管理**」→「**开通管理**」→「**视觉模型**」
3. 在列表中找到 **`doubao-seedream-4.5`** 和 **`doubao-seedream-5.0-lite`** 两项，分别点右侧「**开通服务**」

### ⚠️ 免费额度与付费提醒（务必告知用户）

目前火山方舟 CodePlan 有活动：在上述视觉模型开通页面上方可参加**领取免费资源包**活动。

| 模型 | 免费额度 |
|------|---------|
| `doubao-seedream-4.5` | 送 200 张图 |
| `doubao-seedream-5.0-lite` | 送 50 张图 |

**重要提醒（必须告诉用户）**：

- 免费额度用光之后，**除非手动关闭服务**，否则将**自动进入付费模式**，产生额外费用。
- 这部分图像生成费用**不在 CodePlan 套餐内**，需额外付费。
- 具体收费标准参见视觉模型页面上的定价说明。
- 建议用户按需开通，并在免费额度即将用尽时评估是否继续使用付费模式。

---

## Pitfalls

### pitfall: API key 错误（401）

- **症状**：`HTTPError 401`
- **workaround**：检查 `AWK_API_KEY` 环境变量是否设置；火山 Ark 控制台 (`console.volcengine.com/ark`) 验证 key 有效

### pitfall: size 太小被拒

- **症状**：`HTTPError 400` + 提示 size invalid
- **workaround**：用 `2K` / `3K` / `4K` 预设，或按 [API 文档](https://www.volcengine.com/docs/82379/1541523) 调整 WxH（总像素 ≥ 2560x1440）

### pitfall: URL 24h 失效

- **症状**：生成成功后未及时下载图片，URL 过期
- **workaround**：脚本默认 `response_format=url` 且立刻下载到 `--out-dir`；如需长期保留，用 `--response-format b64_json`

### pitfall: watermark 默认 true（火山端）

- **症状**：图右下角出现"AI 生成"水印
- **workaround**：脚本默认 `--watermark false`；不要漏写
