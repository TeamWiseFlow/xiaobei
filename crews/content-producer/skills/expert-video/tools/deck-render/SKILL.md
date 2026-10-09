---
name: deck-render
description: 幻灯讲解视频的本地 HTML 确定性渲染工具：环境检查、逐页脚手架、质量检查、静帧联系表、MP4 渲染。
metadata:
  openclaw:
    requires:
      bins:
        - python3
        - node
        - ffmpeg
        - ffprobe
---

# deck-render

这是 expert-video 包内原子工具；制作流程读 `workflows/deck-talk.md`。通过 PATH 调 `deck-render`，不拼接脚本路径，不调用上游创作 workflow。

## 命令

```bash
deck-render check-setup
deck-render scaffold /absolute/project/composition --spec /absolute/project/script/deck-spec.json
deck-render check /absolute/project/composition
deck-render preview /absolute/project/composition --output /absolute/project/review/slides-v1
deck-render render /absolute/project/composition --output /absolute/project/render/slides.mp4 --workers 2 --quality delivery
```

- `check-setup` 检查 Node ≥22、ffmpeg/ffprobe、锁定 npm 依赖、Playwright Chromium headless shell 和当前系统默认中文字体（Windows 微软雅黑；Linux/macOS Noto Sans CJK SC），并运行 HF doctor。doctor 中 Whisper/Kokoro/MusicGen 属可选；本工具不用它们。
- `scaffold` 只写空目录。产物是根 `index.html`、每页一个 `compositions/scene-NN.html`、本地 GSAP 与图片副本、`deck-spec.json`。先按时间戳确定时长，再生成；之后直接编辑 HTML，不用 scaffold 覆盖设计。
- 指定 1080×1920 等竖屏尺寸时，`.page` 直接按竖屏画布生成；不可把横屏 HTML 用 `scale(x,y)` 非等比拉伸。`check` 会拦截 `.page` 的非等比缩放。
- `check` 顺序执行 HF lint 和 check（runtime/layout/contrast）。错误阻断；警告必须人工查看，不能把退出码 0 当作视觉验收通过。
- `preview` 先 check，再 snapshot，落 PNG 与 `contact-sheet.jpg`，**不是常驻 HTTP 服务**。默认按 spec 每页中点取图；手改 HTML 时序后必须同步 spec 或传 `--at 2,12,24`。输出目录必须为空，改版用新目录。
- `render` 每次先 check，再渲染；`--workers 1–24`，质量 draft/looks/delivery。输出 MP4 必须与 HTML 根的宽高、fps、duration 一致；结果与耗时落同名 `.render.json`。已有产物需明确 `--force`；临时输出通过校验才替换，不覆盖输入。
- wrapper 全部 HF 子进程使用 `HYPERFRAMES_NO_TELEMETRY=1`，不改用户全局设置；静帧禁用 Gemini 自动描述，不触发模型付费调用。
- 退出码：0 成功；1 参数/质量检查/渲染失败；2 依赖/环境缺失，交 IT engineer。每条外部命令超时 20 分钟。

## spec 契约

```json
{
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "theme": "light",
  "pip": "bottom-right",
  "scenes": [
    {"type": "title", "title": "一个清晰的命题", "subtitle": "对应口播第一段", "duration": 8, "points": ["第一条要点"]},
    {"type": "chart", "title": "示例数据，不代表业务事实", "duration": 10, "source": "演示数据", "caption": "演示数据", "data": [{"label": "甲", "value": 12}, {"label": "乙", "value": 18}]}
  ]
}
```

- `theme` = light/dark。`pip` = top-left/top-right/bottom-left/bottom-right/none；有小窗时整侧留白，底部另留字幕带。默认与 1080p 的 `pip-compose` 参数匹配；改小窗尺寸/画幅时复核并调整版式。
- `scenes` 非空；每页 `duration` 为 3–30 秒，页时长之和必须对应唯一口播音轨；翻页取句边界。工具不自动改稿/合页/伸缩音频。
- 每页标题最多 32 字；`points` 最多 4 条、每条最多 48 字。`subtitle` 与 `source` 要简短，超出版式须重排，通过 check 与目检。
- `type` = title/points/chart/image。chart 是正数柱状图（1–6 项，label 最多 8 字），必须给制作溯源 `source` 和面向观众标明数据来源的 `caption`；负数/零/折线等改写 scene SVG，不伪造数据迁就模板。
- image 页给 `image` 绝对路径、`source` 来源与授权，图片复制进 assets。`source` 仅留制作溯源，不渲染；仅 `caption` 会显示给观众。`caption` 不写“原图已裁净”“内部素材”等制作备注。
- 默认 1920×1080 / 30fps；宽高为至少 360 的偶数，fps 为 1–60 整数。竖屏用原生版式脚手架，生成后仍须重排与逐页目检。

## HTML 纪律

- 根仅编排 scene；子合成 `<template>` 内用局部时间轴，从 0 起，注册 paused GSAP timeline。每页都声明 `@font-face`。内容和 GSAP 放本地，禁外部字体/CDN，禁止 `Date.now()`、随机数、实时时钟驱动动画。
- 每页至少有可解释的元素入场或图表动画；读字停留段允许静止。不能用全屏静图缩放充当图表动画。
- ✅ 用 scene 的 data-start/data-duration 做有限时间轴视频。
- ❌ 用 `/slideshow` 或 `present` 做可导航 deck 后直接 render；此路径可能只输出第一页。
- `preview` 产物必须人工检查遮挡、中文、图表、翻页，GATE B 批准后再 render；工具 check 不代替内容审片与甲方闸门。

依赖在本目录 package.json 精确锁定 hyperframes 0.8.50、gsap 3.14.2、playwright-core 1.61.1。安装/更新通过 `scripts/install-deck-render.sh`（Windows 为同名 `.ps1`）装 npm 包与 Chromium headless shell；Linux/macOS 安装 Noto，Windows 使用系统微软雅黑；容器构建时预装进镜像。不要运行 npx 临时下载或自动 upgrade。渲染 CLI 参考：[HyperFrames rendering](https://github.com/heygen-com/hyperframes/blob/main/docs/guides/rendering.mdx)，具体参数以本包锁定版本为准。
