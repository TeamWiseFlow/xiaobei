#!/usr/bin/env bash
# video-producer.sh — video-producer 工具 wrapper（薄转发，子命令范式；expert-video 包内工具）
# 让 agent 用 `video-producer <子命令> [参数...]` 走 PATH，零路径拼接。
# 子命令即 scripts/ 下同名 .py，wrapper 转发到对应脚本，不改语义。
# 子命令入出参见本工具 SKILL.md；制作流程（阶段链 / 两闸门 / 各类型 workflow）
# 见 expert-video 包内 SKILL.md 与 workflows/。产物文件存在性即 checkpoint（不引状态机）。
set -euo pipefail
SELF="${BASH_SOURCE[0]}"
# Resolve symlink (wrapper is ln -sfn'd into ~/.openclaw/bin) so SCRIPT_DIR points at the real skill dir.
while [ -L "$SELF" ]; do SELF="$(readlink -f "$SELF")"; done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"

SUBCMD="${1:?用法: video-producer <子命令> [参数...]}"
shift
case "$SUBCMD" in
  -h|--help|help)
    cat <<'HELP'
video-producer — 视频制作原子能力（wrapper，expert-video 包内工具）

用法:
  video-producer <子命令> [参数...]      跑对应阶段的原子脚本
  video-producer help                    列可用子命令

流程:
  通用制作流程（expert-video SKILL.md 的 Stage 0→15 + 两闸门）是做**任何**视频都要遵循的基准，
  不是"没指定类型时的备选"。Brief 指定 workflow 时，先读包内 workflows/<workflow>.md，
  按它生产 script 并按它自检（其制作约定在该类型上生效）；未指定时只按通用制作流程走。Brief 创意不足以直接写剧本时，
  先走 story-develop intake workflow（workflows/story-develop.md）与甲方收敛 Brief，再进 script-write。

子命令（按阶段序）:
  reference-concepts   可选     吃甲方给的参考拆解报告出 2–3 差异化概念
  script-write         Stage 1  Brief 创意 → 分场剧本（含 enhancement_cues + delivery_cues）
  script-self-eval     Stage 2  脚本自评 N 维打分
  storyboard-build     Stage 3  剧本 → 镜头表
  shot-decompose       Stage 4  每镜拆首尾帧 + 运动描述 + variation_type
  character-register   Stage 5  角色三视图 + static/dynamic features 拆分
  slot-plan            Stage 6  素材 slot 规划
  asset-resolve        Stage 7  按 slot 拉素材（Fast path 人核缩略图）
  slideshow-risk       Stage 8  六维幻灯风险打分（pre-compose 闸门）
  delivery-promise-lock Stage 9 交付承诺八类锁定
  render-shot          Stage 10 按 slot 渲染（AIGC i2v / 静图）
  visual-render        Stage 10 HTML/GSAP 视觉片段：scaffold/check/preview/render（HyperFrames）
  motion-graphics      新项目转交 visual-render；旧 JSON/Pillow spec 兼容入口
  batch-i2v           Stage 10 特殊生成式镜头批量调公共 aigc-video-gen（可选）
  mix-audio            Stage 11 旁白（awk-tts）+ BGM + 字幕
  narration-align      Stage 11 旁白字级时间戳对齐（整段 narration.mp3 模式；复用 awk-tts 原生时间戳，缺失回退火山 ASR）
  deck-boundaries      Deck Talk 根据字级标点时间戳建议翻页点并校验 deck-spec
  narration-layout     Stage 11 逐句旁白排布 + 防重叠守卫 + 越界断言 + SRT + 可选混音（逐句 mp3 模式）
  clip-trim            Stage 12 精确切素材段（入点/出点/倍速/归一化/调色/多窗/定帧缓推）
  deck-compose        三模式 deck-talk 合成（实拍 / 数字人 / 仅音频）
  pip-compose          Stage 12 幻灯底视频 + 可选口播小窗 + 唯一音轨（四角/圆角/描边/字幕安全区/干跑守卫）
  audio-mix            Stage 12 多轨混音（每轨独立延时、音量与淡入淡出）
  timeline-compose     Stage 12 按时间轴 JSON 合成片段（内部调 clip-trim + audio-mix）
  scene-compose        Stage 12 单 Scene 分段合成（片段+旁白+对白 → 一个 Scene 片段）
  assemble             Stage 12 按镜顺序拼接成片 + 转场 + 规格归一化 + 守卫断言（--manifest/--verify-fps/--expect-durations）
  add-silent-audio     Stage 12 给无音频的视频片段补静音音轨（concat 前置）
  make-outro           Stage 12 片尾制作（HyperFrames 排版/文字淡入 + 静音轨）
  motion-audit         Stage 13b motion_led 抽查（补公共 video-review）
  normalize            Stage 13c 响度归一化到 -14 LUFS（**必跑**）
  make-cover           Stage 14 封面（awk-img-gen，必含封面主文案）

后期处理（可选，全部干湿分离：输出落 <stem>_<处理名>.mp4，不覆盖输入）:
  burn-srt             libass 把 SRT 硬烧进画面（甲方要字幕时）
  duck                 sidechaincompress 让旁白触发 BGM 自动压低（要专业混音且可分轨时）
  denoise              afftdn / arnndn 去环境噪声（仅甲方素材音质差时）
  interp               minterpolate 补帧到 30/60fps（仅低 fps 源材）

闸门不是子命令——GATE A（Stage 5 后文本闸门）与 GATE B（Stage 9 后素材闸门）由 agent
按 expert-video SKILL.md 执行：呈交摘要 → 结束本轮回复 → 等甲方（main agent 或用户）逐闸门批准。

产物文件存在性即 checkpoint：每个子命令先查产物文件是否存在，存在则 load 不重生成。
HELP
    ;;
  *)
    SCRIPT="$SCRIPT_DIR/scripts/${SUBCMD}.py"
    if [ ! -f "$SCRIPT" ]; then
      echo "未知子命令: $SUBCMD" >&2
      echo "用 video-producer help 查可用子命令" >&2
      exit 1
    fi
    exec python3 "$SCRIPT" "$@"
    ;;
esac
