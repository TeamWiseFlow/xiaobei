---
name: video-edit
description: 对已有视频素材做加工与拼接——抽段/合并、补片头片尾、加背景音乐/旁白、烧字幕、按画面精彩程度剪集锦、按编号合成成片。素材不足可经 AIGC 或免费素材库补充。仅做已有素材的后处理，不从零生产完整视频（出脚本、端到端制作找 content-producer）。
metadata:
  openclaw:
    emoji: "🎬"
    requires:
      bins:
      - python3
      - ffmpeg
      - ffprobe
---

# 素材加工与拼接（video-edit）

## 适用场景

用户提供（或指定复用）已有视频素材，要求做**简单后处理**：

- 抽取素材片段、把几段素材合并成一片、补片头片尾
- 给素材加背景音乐、旁白配音
- 烧录字幕
- 看**画面**挑精彩片段剪成集锦（画面集锦）
- 把编号好的片段合成最终成片

不适用：

- 从零生产一个完整视频（出脚本、规划分镜、端到端制作）→ 委托 content-producer
- 口播/演讲类视频按**说话内容**去口气词或剪高光 → 走 `talking-head-cut`
- 录制产品操作视频 → 走 `ui-demo`

所有子命令统一走 `video-edit <子命令> [参数...]`，每个子命令支持 `--help` 查看完整参数。

---

## 工作区目录准备

平台内容直接用对应平台运营项目目录 `<platform>/outputs/<video-name>/` 作为 project-dir（平台专家包 workflow 已建好）；其他零散任务在 `output_videos/` 下创建项目文件夹，如 `output_videos/<topic-en-slug>/`。

工作区结构：

```
<project-dir>/
├── raw_materials/        # 用户提供的原始内容，或者从别处拷贝过来的复用素材
├── downloads/            # 下载的内容
├── generations/          # AIGC产物
├── frames/               # 画面集锦抽帧产物（仅画面集锦流程用）
├── artifacts/            # 最终定稿需要使用的素材片段
│   ├── 01_xxx.mp4        # 按编号排序的视频片段
│   ├── 02_xxx.mp4
│   └── ...
├── previews/              # 逐段确认用压缩预览（仅用于发聊天确认，不参与合成）
│   └── NN_xxx_preview.mp4
└── video.mp4              # 最终成品
```

只按实际用到的能力建对应子目录，不必全建。

---

## 素材补充（按需）

仅当用户素材不足、且补充是为了完成本次组装时才补：

- **AIGC 生成**：使用公共 `aigc-video-gen` 技能（百炼/火山声画同出，详见其 SKILL.md）
- **Stock Footage**：AIGC 不可用或用户要求不用 AIGC 时，用公共 `pexels-footage` 搜索下载（9:16 竖屏优先），无结果再用 `pixabay-footage`

**素材下载规则**：

- 一次只下载一个视频
- 时长精准匹配（按目标片段时长设置 `--min-duration` / `--max-duration`）
- 下载后按片段编号重命名，放入 `artifacts/`

---

## 能力一：抽段与拼接（extract）

从视频（MP4/WebM 等）抽片段（head/tail/slice）、全片转 MP4（full）并可选多段拼接为一片。补片头片尾也走这里（片头/正片/片尾按序作为多段拼接）。

```bash
# 单段抽取：取开头 6 秒
video-edit extract -i input.mp4 --mode head --seconds 6 -o out.mp4

# 完整 WebM 转 MP4：保留分辨率、输出无声 H.264/yuv420p/faststart 素材
video-edit extract -i demo.webm --mode full --keep-resolution --no-audio -o demo.mp4

# 多段拼接：a 的开头 6s + b 的 10-20s + 完整片尾
video-edit extract \
    --segment input=a.mp4 mode=head seconds=6 \
    --segment input=b.mp4 mode=slice start=10 end=20 \
    --segment input=outro.mp4 mode=head seconds=999 \
    -o out.mp4
```

要点：

- `--mode`：`head` 开头 / `tail` 结尾 / `slice` 中段（`start`/`end`）/ `full` 全片（不传时长或起止点，脚本自动读取）
- 默认统一到 720x1280@30fps；`--keep-resolution` 保持首段分辨率
- `--audio speech.mp3` 可在拼接时替换音轨；`--no-audio` 出无声片
- 时间量支持 `6` / `6s` / `1m30s` 写法

## 能力二：按编号合成成片（assemble）

把 `artifacts/` 下按数字前缀排序的片段拼成最终成片。

**⚠️ 合成前必须先清理废弃片段**：逐段确认过程中产生的废弃版本（如 `02_choose_path.v1_bad.mp4`）**和正式片段共用同一数字前缀**，会被当成对应段一起拼进去，导致成片重复/错乱。合成前先删除或移出 `artifacts/`：

```bash
# 把废弃版本移到 artifacts/_deprecated/ 子目录（assemble 非递归扫描，子目录不参与拼接）
mkdir -p <project-dir>/artifacts/_deprecated
mv <project-dir>/artifacts/*.v*_*.mp4 <project-dir>/artifacts/_deprecated/ 2>/dev/null
```

清理后确认 `artifacts/` 顶层只剩 `01_*.mp4 … NN_*.mp4` 每段一个正式片段，再合成：

```bash
video-edit assemble <project-dir>/artifacts/ --output <project-dir>/video.mp4
```

合成规则：

- 按文件名数字前缀（`01_`、`02_`…）顺序拼接，同一前缀内按文件名字典序
- **无外部音频文件**：保留每段视频自带音轨拼接；个别无音轨的片段自动补静音，不会把成片变无声
- **有外部音频文件**（`speech.mp3` 等）：外部音频替换视频原音轨
- `--transition crossfade` 可开段间交叉淡化（默认 `none` 硬切）
- 不烧录字幕（需要字幕的话合成后走能力四）

合成后确认 `video.mp4` 存在且非空。

## 能力三：配音配乐（audio-mix）

给已有视频加旁白和/或背景音乐：

```bash
# 加 BGM（循环/裁剪到视频时长，默认 0.25 音量垫底，结尾 2s 淡出）
video-edit audio-mix input.mp4 --bgm music.mp3 --output out.mp4

# 加旁白（默认替换原音轨；--original-volume 0.3 可保留原音轨垫底）
video-edit audio-mix input.mp4 --narration speech.mp3 --output out.mp4

# 旁白 + BGM
video-edit audio-mix input.mp4 --narration speech.mp3 --bgm music.mp3 --output out.mp4
```

旁白音频的生成：

1. **优先使用 OpenClaw 内置 TTS 工具**（`tts_generate` 或 agent 内置语音合成能力）
2. 内置 TTS 不可用时，使用公共 `awk-tts` 技能（多供应商：火山豆包 2.0 → 百炼业务空间 → 百炼 agent plan，凭据在哪家走哪家）
3. 旁白时长必须与视频时长匹配（TTS 语速可微调以适配），混音前先核对两者时长

BGM（`--bgm` 文件）的来源：

- ✅ **优先公共 `bgm-library` 技能**：ccMixter 免版税曲库（CC BY / CC BY-SA，商用安全），免 key、自动署名。`bgm-library pick "<主题>" --output <project-dir>/audio/` 选曲下载后传给 `--bgm`
- 需要定制风格 / ccMixter 无匹配时，用公共 `aigc-video-gen music`（MiniMax 生成，需 `MINIMAX_API_KEY`）
- 用户自带曲目直接用；成片发布时必须把 `bgm-library` 产出的 `ATTRIBUTION.txt` 附到视频简介（CC 协议法律要求）

## 能力四：字幕烧录（subtitles）

```bash
video-edit subtitles input.mp4 subs.srt --output out.mp4
```

- 接受 `.srt`（统一样式：白字黑描边，`--font-size` / `--margin-v` / `--position bottom|top` 可调）或 `.ass`（自带样式）
- 字幕文件来源：用户提供；用户只给文案没给时间轴时，由 agent 按片段时长手写 SRT（时间轴与画面/旁白对齐后再烧）
- 视频会重编码，音频不动

## 能力五：画面精彩集锦（frames + apply-cut）

对**无人声或以画面为主**的素材（运动、旅拍、活动记录、游戏录屏等），看画面挑精彩片段剪成集锦。口播/演讲类按说话内容剪的活不走这里，走 `talking-head-cut`。

### Step 1：抽帧

```bash
video-edit frames <source.mp4> --interval 3 --output-dir <project-dir>/frames
```

- 每 `--interval` 秒抽一帧（默认 3s），超过 `--max-frames`（默认 100）自动放大间隔
- 产物：`frames/frame_NNNN_<t>s.jpg`（帧名带时间戳）+ `frames/index.json`

### Step 2：看图定精彩窗口，写 cut_plan.json

用 `Read` 工具逐帧看图（帧名里的时间戳就是该帧在源视频中的位置），识别精彩窗口：动作高潮、场景切换、情绪峰值、构图出彩的段落。然后把结论写成 `<project-dir>/cut_plan.json`：

```json
{
  "ok": true,
  "source": "source.mp4",
  "duration": 300.0,
  "mode": "visual-highlight",
  "plan": [
    {"keep": true,  "start": 21.0, "end": 33.0, "reason": "highlight"},
    {"keep": false, "start": 33.0, "end": 87.0, "reason": "normal"},
    {"keep": true,  "start": 87.0, "end": 99.0, "reason": "highlight"},
    ...
  ]
}
```

写 plan 的要求：

- 段边界取抽帧时间戳附近的整数秒即可；精彩动作两侧各留 1–2s 余量，避免掐头去尾
- 全部段（keep + remove）必须首尾相接覆盖 0 → duration，不留空洞
- keep 段总时长贴近用户目标时长；差距 >20% 时调整窗口选择，或用更小 `--interval` 重抽再定
- `reason` 只用 `highlight`（keep=true）/ `normal`（keep=false）

### Step 3：用户确认 plan（关键闸门）

cut_plan.json 落盘后**必须先让用户确认**再剪：报告 keep 段数、各段起止与挑选理由（画面内容）、keep 段总时长。用户认 plan 后才剪。

### Step 4：剪拼 + 自检

```bash
video-edit apply-cut <source.mp4> <project-dir>/cut_plan.json \
    --output <project-dir>/highlight.mp4 --fade-ms 40
video-review <project-dir>/highlight.mp4
```

## 逐段确认预览（preview）

需要把大文件发聊天让用户逐段确认时，先压预览（产物仅用于确认，不参与合成）：

```bash
video-edit preview <input.mp4> --output <project-dir>/previews/<NN>_preview.mp4
```

默认压到 ≤16MB，`--target-mb` 可调。

---

## 成片自检（强制闸门）

任何成片（assemble / apply-cut / audio-mix / subtitles 的最终产物）交付前**必须**跑：

```bash
video-review <project-dir>          # 审 <project-dir>/video.mp4 + artifacts/ 段一致性
video-review <final.mp4>            # 或直接审单个成片文件
```

verdict=pass 才交付；fail 按 critical 项修复后重审；warn 向用户复述由其决定。详见 `video-review` 技能 SKILL.md。

---

## 制作封面

每个成片视频都必须配封面图。封面要求：

- **必须包含视频标题文字**，不允许纯图片封面
- 标题文字必须有设计感（字体选择、排版布局、颜色搭配）
- 竖屏封面 1080x1920
- 可以使用视频关键画面作为背景，但文字是必须元素

使用公共 `awk-img-gen` 技能制作封面，保存为 `<project-dir>/cover.jpg`。

> 仅对交付成片的项目做封面；中间加工产物（如只是帮用户给一段素材加 BGM）不需要封面。

---

## 用户确认

向用户展示：

- 成品视频（发文件本体）
- 封面图（发文件本体，如有）
- 关键参数（时长、分辨率、片段数）

用户确认后，流程结束。后续发布由各平台发布技能执行。

---

## 子命令清单

| 子命令 | 用途 | 退出码 |
|--------|------|--------|
| `video-edit extract` | 抽段（head/tail/slice）+ 可选多段拼接 | 0 成功 / 非 0 失败 |
| `video-edit assemble` | artifacts/ 按数字前缀拼成成片 | 0 成功 / 非 0 失败 |
| `video-edit audio-mix` | 加旁白/BGM 混音 | 0 成功 / 1 参数错 / 3 ffmpeg 不存在 |
| `video-edit subtitles` | 烧录 SRT/ASS 字幕 | 0 成功 / 1 参数错 / 3 ffmpeg 不存在 |
| `video-edit frames` | 按间隔抽帧（画面分析用） | 0 成功 / 1 参数错 / 3 ffmpeg 不存在 |
| `video-edit apply-cut` | 按 cut_plan.json 剪拼 | 0 成功 / 1 参数错 / 3 ffmpeg 不存在 |
| `video-edit preview` | 压 ≤16MB 聊天预览 | 0 成功 / 非 0 失败 |

---

## 禁止事项（强制）

违反以下任何一条都会导致系统死机或产出异常，**必须严格遵守**：

- **禁止直接写 ffmpeg 命令**：不得在 exec 中直接调用 ffmpeg/ffprobe，也不得写 Python 脚本内嵌 ffmpeg 调用。所有视频处理一律通过 `video-edit` 子命令完成
- **禁止从静态图生成视频**：不得将 JPEG/PNG 等静态图片转为 MP4。用户提供的静态图片仅作为 AIGC 参考图或搜索风格参考
- **禁止跳过 video-review 交付**：成片交付前必须自检，verdict=pass 才交付
- **禁止代用户出脚本**：本技能不写视频脚本、不规划分镜；用户要从零做视频时转介 content-producer
