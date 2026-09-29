# deck-talk 验证

前置：项目安装器已装 `tools/deck-render/package.json` 里的锁定 Node 依赖；本机有 Node ≥22、Chrome、ffmpeg/ffprobe、Pillow，以及中文字体（Linux/macOS 用 Noto Sans CJK SC，Windows 用系统微软雅黑）。测试不修改 OpenClaw 运行态，不调用 TTS/ASR/数字人 API。

```bash
python3 -m unittest discover -s test/deck-talk -p 'test_*.py' -v
DECK_RENDER_BROWSER_TEST=1 python3 -m unittest discover -s test/deck-talk -p 'test_*.py' -v
python3 test/deck-talk/run_smoke.py --output-dir /tmp/deck-talk-smoke-new
```

- 单元/媒体回归：Brief 识别、逐页脚本与落稿锁定、自检维度、Stage 3–10 裁剪；非法图表/时长；竖屏原生画布、制作来源隔离、非等比缩放拦截；字级标点翻页校验；四角几何、字幕避让、圆角透明；时长报错列出三段长度；24fps 小窗→30fps 合成；频率检测证明唯一音轨；无小窗路径。
- 浏览器测试需显式设 `DECK_RENDER_BROWSER_TEST=1`，补测深色主题、左侧留白、图片本地化与实际 preview；默认跳过该项，不启动 Chrome。
- smoke 用 `deck-spec.json` 的 60 秒四页中文内容（含柱状图），走 scaffold→preview→render→小窗/无小窗→字幕→normalize→video-review→完整解码。`check_animation.py` 另对逐页动画前后抽帧比较正文区像素，避免小窗自身运动掩盖幻灯静止。
- `--output-dir` 必须为空，产物与日志均落该目录；不覆盖旧样片。`--slides /absolute/slides.mp4` 可显式复用已有 60s/1080p30 渲染，仅用于调试后半链路；报告会标记 slides_reused。
- `presenter.mp4` 是运动测试图案，`narration.wav` 是 440Hz 测试音，字幕明确标注测试性质。**这不是口播作品，不验证 TTS/ASR、真人口型、数字人质量或业务内容。**
- 结果：`smoke.json` 各步 wall time、`review/verdict.json`、`review/slides/contact-sheet.jpg`、`review/animation/`、`video.mp4`。`/tmp` 会被系统清理，需要留存时自行指定持久测试目录。
