---
name: awk-img-gen
description: 阿里云百炼图像生成与编辑。支持显式选择 DashScope 业务空间或 Agent Plan；默认优先业务空间，两种模式均默认 qwen-image-3.0-pro，Agent Plan 可回退 wan2.7-image。文生图默认，1-3 张参考图触发编辑/多图融合。直出带字封面海报。
metadata:
  openclaw:
    emoji: 🖼️
    requires:
      bins:
        - python3
    homepage: https://docs.bailian.console.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference
---

# 图像生成（awk-img-gen）

走百炼同步 `multimodal-generation` 接口生成/编辑图片，落盘 PNG + `prompts.json` 索引 + `index.html` 缩略图 gallery。

> **凭据**（默认 `--platform auto`；可用 `--platform dashscope` / `--platform plan` 固定模式）：
>
> | 模式 | 触发条件 | 端点 | 模型候选链 |
> |------|---------|------|-----------|
> | DashScope 业务空间 | `WORKSPACE_ID` + `MODELSTUDIO_API_KEY`（或 `DASHSCOPE_API_KEY`） | `https://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/api/v1` | `qwen-image-3.0-pro` → `qwen-image-3.0` → `qwen-image-2.0-pro-2026-06-22` |
> | Agent Plan | `AWK_API_KEY` | `https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1` | `qwen-image-3.0-pro` → `wan2.7-image-pro` → `wan2.7-image` |
>
> `auto` 优先使用完整的业务空间凭据，否则使用 Agent Plan。显式指定 `dashscope` / `plan` 时只使用对应端点、凭据和候选链；缺少对应凭据就报错，不切换模式。`--model` 只覆盖模型，不改变模式。
> 候选链自动 fallback（模型未开通/未找到/无权限时切下一个）；`--model` 显式指定时关闭 fallback。
> 所有凭据都缺 → exit 1 并打印配置指引；实拍图兜底改走 `pexels-footage` / `pixabay-footage`。
> 应该 spawn IT engineer subagent 配置环境变量，**不要自己写环境变量文件**。

## Run

Note: 图像生成可能耗时 10–120 秒（qwen-image-3.0-pro 更慢）。exec 调用时把 timeout 设高（如 `exec timeout=300`）。

**Do NOT set env vars inline**（例如 `AWK_API_KEY=... python3 ...`）。env var 已在系统环境里，inline 赋值会破坏 exec 权限检查。

通过 PATH 调用 wrapper，无需拼接脚本路径：

```bash
# Text-to-image（模式/模型/候选链全自动，默认 2048x2048）
awk-img-gen --prompt "your prompt here"

# 竖版 9:16（短视频封面）
awk-img-gen --prompt "..." --image-size 1536x2688

# 固定使用 DashScope 业务空间（需 WORKSPACE_ID + 业务空间 key）
awk-img-gen --platform dashscope --prompt "your prompt here"

# 固定使用 Agent Plan（只读 AWK_API_KEY，即使已有业务空间凭据）
awk-img-gen --platform plan --prompt "your prompt here"

# 指定模型（显式指定时不 fallback）
awk-img-gen --prompt "..." --platform dashscope --model "qwen-image-2.0-pro-2026-06-22"

# Image-edit（1-3 张参考图；URL / data URI / 本地路径均可）
awk-img-gen --prompt "add a lighthouse" --image "https://example.com/source.jpg"
awk-img-gen --prompt "blend" \
  --image ./tmp/ref-a.png \
  --image2 ./tmp/ref-b.png \
  --image3 ./tmp/ref-c.png
```

## Parameters

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt` | required | 图像描述；要渲染的文字**直接写完整句子** |
| `--platform` | auto | `auto` / `dashscope` / `plan`；`dashscope` 固定业务空间，`plan` 固定 Agent Plan，缺对应凭据时报错；`--model` 不改变模式 |
| `--model` | auto | Model ID；缺省按模式走候选链自动 fallback，显式指定时不 fallback |
| `--image-size` | `2048x2048` | `WxH` 或 `auto`，编辑模式缺省跟随输入图 |
| `--seed` | — | 随机种子 [0, 2147483647] |
| `--watermark` | `false` | 是否加水印（xiaobei 默认不加，避免后续 image 工具处理） |
| `--prompt-extend` | off | 允许百炼自动扩写 prompt（API 默认开；本脚本默认**关**，保证封面文字/布局指令精确；氛围图想要更丰富细节时可开） |
| `--image` | — | 参考图 1（启用编辑模式） |
| `--image2` / `--image3` | — | 参考图 2 / 3（多图融合） |
| `--out-dir` | `./tmp/awk-img-<ts>` | 输出目录 |

### 百炼推荐尺寸（qwen-image 文档推荐值）

| Value | Ratio |
|-------|-------|
| `2048x2048` | 1:1（默认） |
| `2688x1536` | 16:9 |
| `1536x2688` | 9:16 |
| `2368x1728` | 4:3 |
| `1728x2368` | 3:4 |

> 总像素须在 512×512 ~ 2048×2048 之间，宽高比 1:8 ~ 8:1；无效值脚本拒绝并 exit 1 列出推荐值。

## Output

- `*.png` 图像（脚本下载到本地）
- `prompts.json` 索引 → prompt + model + provider_mode + URL + file
- `index.html` 缩略图 gallery

## 视频封面/海报最佳实践

适用于**图文混合素材**（短视频封面、社媒海报、信息图配图等）——需要模型一次性渲染文字与画面，而不是后期合成。

### 1. 参数推荐

| 参数 | 推荐值 | 原因 |
|------|--------|------|
| `--model` | 缺省（走候选链主力） | 两种模式均默认 qwen-image-3.0-pro；回退模型见凭据表 |
| `--image-size` | 按平台比例选推荐尺寸 | 9:16 用 `1536x2688`，16:9 用 `2688x1536` |
| `--prompt-extend` | 不加（保持默认关） | 扩写会改写你精心排版的文字与布局指令 |

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

### 3. 生成后必须验证

1. 用 `image` 工具分析图片，**逐项确认**：
   - ✅ 文字内容是否完全正确（不能错字、漏字、出现乱码字符）
   - ✅ 文字是否清晰可读（无模糊、无变形）
   - ✅ 布局是否符合预期
2. 文字渲染错误 → 调整 prompt 重新生成（百炼可加 `--seed` 辅助复现构图再微调文字），**不要**交付错字封面

## Environment Variables

| Variable | Description |
|----------|-------------|
| `WORKSPACE_ID` | 百炼业务空间 ID；`auto` 时配齐业务空间 key 就优先使用；`dashscope` 模式必需 |
| `MODELSTUDIO_API_KEY` / `DASHSCOPE_API_KEY` | 业务空间 API key（与 `WORKSPACE_ID` 配对） |
| `AWK_API_KEY` | 百炼 Agent Plan key；`plan` 模式必需，`auto` 时在无完整业务空间凭据时使用 |
