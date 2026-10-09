#!/usr/bin/env python3
"""Stage 1 — script-write：按 Brief（及其指定的 workflow）生产 script（分场剧本）。

Usage:
  python3 scripts/script-write.py <project_dir>

入：project_dir/brief.md（甲方 Brief）
出：project_dir/script/script.md（按 workflow 变体）

变体（脚手架读 Brief 的 workflow 字段与口播交付自动选择）：
- 未指定 workflow            → 通用分场剧本（可拍化描述 + enhancement_cues 六型 + delivery_cues）
- 未指定 workflow + 口播稿/真人录音 → 通用流程，原稿/录音锁定
- reversal-ad                → 三段结构反转剧本（解说旁白由我写）
- collage-broll              → 隐喻清单（本类型的 script）
- deck-talk                  → script/deck-script.md 逐页幻灯脚本，口播原稿锁定

Brief 创意不足以直接写剧本 → 先走 story-develop intake workflow 与甲方收敛 Brief。
"""

import argparse
import sys
from pathlib import Path

import _brief


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


GENERIC_STUB = """# 分场剧本（Stage 1 · 通用）

> 据 Brief 创意拆成可拍化分场剧本。每场含：场景描述、出场人物、对白、动作、enhancement_cues、delivery_cues。

## 场 1：（场名，如"主角家中—清晨"）

### 场景描述
> agent 填。可拍化——只写镜头能看到的。不写"她想起了童年"（不可见），改写"她抚摸旧照片，眼神放空"。

### 出场人物
- （人物）：（本场动作）

### 对白与动作
> agent 填。对白用引号「」统一格式。动作写括号内。
主角：「（对白）」（动作：抚摸照片）

### enhancement_cues（六型，agent 据本场填）
> 六型：动作 / 表情 / 环境 / 心理外化 / 节奏 / 视觉锚点
- 动作：（agent 填，如"缓慢翻页"）
- 表情：（agent 填，如"眼神放空"）
- 环境：（agent 填，如"晨光透过窗帘"）
- 心理外化：（agent 填，如"重复抚摸同张照片"）
- 节奏：（agent 填，如"慢板，停顿多"）
- 视觉锚点：（agent 填，如"旧照片特写"）

### delivery_cues（旁白指令，后续 awk-tts / 内置 TTS 用）
> agent 填。语气 / 语速 / 重音 / 情感控制。

## 场 2（如有）
（agent 同上填）
"""

RECORDING_STUB = """# 口播录音合成计划（Stage 1 · 通用流程 · 真人录音形态）

> 甲方口播录音已定稿（口播稿落稿锁定，不重写）；Stage 11 场景 D 跑 narration-align
> 拿 utterance 级真实时间戳，按时间戳排画面——不重配旁白、不改录音内容。

## 时间轴（agent 填：句 → 时间段 → 对应画面）
| 句 | 起止（ASR 后回填） | 画面 slot / 素材 |
|----|--------------------|------------------|
| 1  |                    |                  |
"""

REVERSAL_STUB = """# 反转植入剧本（Stage 1 · reversal-ad）

> 解说旁白由我写（旁白归 CP），第三人称解说体：避免问句、感叹号、第二人称与促销信号词；
> 句长 10–15 字，语速 7–8 字/秒。反转点落在总时长 55%–76%；反转前零产品提及。
> GATE A 四问（script-self-eval 同查）：铺垫可信吗 / 幅度够吗 / 接入因果一句话可复述吗 / CTA 是剧情动机吗。

## 解说正文（63%–76%：自洽、有冲突、有悬念；段尾停在求助/任务/待发/冲突节点）
（agent 填）

## 反转过渡（3%–13%：一句话或一帧把剧情指向产品，双关或因果可追，口播明写因果）
（agent 填）

## 产品植入（15%–27%：3–4 句单点深打，覆盖 Brief 允许的 ≥3 个价值点，每点有对应画面）
（agent 填）

## 片尾 CTA（优先二次反转剧情化承载）
（agent 填）
"""

COLLAGE_STUB = """# 隐喻清单（Stage 1 · collage-broll——本类型的 script）

> 把每条文稿压成一个 sharp visual idea：一条文稿只做一个隐喻，3–6 个关键物件；
> 不要把文稿逐字放进画面。色彩按语义色场表选。逐条格式：

1. 核心意思：（观众最终要看懂什么）
   视觉隐喻：（一句话视觉命题）
   关键物件：（3–6 个）
   色彩：（底色 + 点色，按语意）
   组装顺序：（元素滑入次序）

自检通过后继续 Stage 3–5：按条填写分镜、首尾视觉状态、需要跨镜一致的人物/纸片登记；GATE A 在 Stage 5 后。
"""


DECK_STUB = """# 幻灯脚本（Stage 1 · deck-talk）

模式：待按 Brief 填 footage / avatar / audio（兼容 none）。
底画面：slides / broll / mixed；音频讲解模式可只用 B-roll。
音频来源：待填 recorded / cloned / designed / stock-tts 与路径；footage 沿用 main 已剪视频原声，avatar 使用 LivePortrait 的原驱动音频，audio 保留用户/main 提供音频。

## 第 1 页
- 单一命题：
- 版式 / 图表类型：
- 数据 / 单位 / 日期范围 / 来源：
- 图片槽 / 绝对路径 / 授权：
- 对应口播原文或录音段落（锁定稿不改写）：
- 预计时长（3–30 秒，GATE A 后按句边界时间戳回填）：
- 小窗避让 / 字幕安全区：
- 元素入场 / 图表演进及局部时刻：

按页重复。纯旁白由 CP 写并提交 GATE A；口播稿由甲方提供，不重写。
自检后继续 Stage 3–5 完成逐页分镜、画面状态与人物登记，再过 GATE A。
"""

DECK_BROLL_STUB = """# B-roll 讲解脚本（Stage 1 · deck-talk）

## 第 1 段
- 对应口播原文或录音段落（锁定稿不改写）：
- 画面命题与素材来源 / 绝对路径 / 授权：
- 画面动作、入出点与对应句边界：
- 图表数据 / 单位 / 日期范围 / 来源（如有）：
- 预计时长（GATE A 后按真实音频时间戳回填）：
- 字幕安全区与小窗避让（如有）：

按句边界分段重复。纯旁白由 CP 写并提交 GATE A；用户/main 提供的口播原声保持不变。
自检后继续 Stage 3–5 完成逐段分镜、画面状态与人物登记，再过 GATE A。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1 script-write（按 Brief 的 workflow 变体）")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    brief_path = project / "brief.md"
    if not brief_path.is_file():
        die(f"前置缺失: brief.md 不存在，先完成 Stage 0 Brief intake（创意模糊时走 story-develop intake workflow）")
    brief_text = brief_path.read_text(encoding="utf-8")

    workflow = _brief.parse_workflow(brief_text)
    vo_mode, vo_path = _brief.detect_voiceover(project, brief_text)

    script_path = project / "script" / ("deck-script.md" if workflow == "deck-talk" else "script.md")
    script_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if script_path.is_file():
        print(f"[checkpoint] {script_path.name} 已存在，沿用：{script_path}")
        print("[hint] 要改就手改或删掉重跑本命令（产物文件存在性即 checkpoint）")
        return

    if workflow == "deck-talk":
        fields = _brief.deck_fields(brief_text)
        content = DECK_BROLL_STUB if fields.get('visual_source') == 'broll' else DECK_STUB
        locked = '\n'.join(f'- {key}: {fields[key]}' for key in
                           ('presenter_source', 'visual_source', 'audio_origin', 'presenter', 'audio') if fields.get(key))
        if locked:
            content = content.replace('\n## 第 1 ', '\n## Brief 锁定输入\n' + locked + '\n\n## 第 1 ', 1)
        if vo_mode == "voiceover":
            content += "\n## 甲方口播原稿（落稿锁定）\n\n" + vo_path.read_text(encoding="utf-8")
        elif vo_mode == "recording":
            content += f"\n同源录音：{vo_path}\n"
        script_path.write_text(content, encoding="utf-8")
        print(f"[done] deck-talk 逐页脚本模板：{script_path}")
        print("[next] 填逐页/段设计与原文对应 → script-self-eval → Stage 3–5 → GATE A")
        return

    if workflow is None and vo_mode == "voiceover":
        # 口播稿原样落稿锁定：不重写、不优化、不增删卖点
        content = vo_path.read_text(encoding="utf-8")
        script_path.write_text(content, encoding="utf-8")
        print(f"[mode] 通用流程 · 口播稿（甲方交付 {vo_path.name}）——原样落稿锁定")
        print(f"[done] 口播稿已原样拷入：{script_path}（不重写、不顺手优化、不增删卖点）")
        print("[next] 跑 script-self-eval（Stage 2）——落稿锁定模式只检查不改写；再完成 Stage 3–5，GATE A 在 Stage 5 后")
        return

    if workflow is None and vo_mode == "recording":
        print("[mode] 通用流程 · 真人录音——录音即定稿，本文件只记排布计划")
        script_path.write_text(RECORDING_STUB, encoding="utf-8")
        print(f"[done] 录音排布计划模板已落：{script_path}")
        print("[next] agent 填时间轴（时间戳待 Stage 11 场景 D ASR）→ 跑 script-self-eval（Stage 2）")
        return

    if workflow == "reversal-ad":
        print("[mode] reversal-ad——解说旁白由我写，按三段结构出剧本；GATE A 附四问答案")
        script_path.write_text(REVERSAL_STUB, encoding="utf-8")
        print(f"[done] 反转植入剧本模板已落：{script_path}")
        print("[next] agent 按三段结构填剧本 → 跑 script-self-eval（Stage 2，四问质检）→ GATE A 交审")
        return

    if workflow == "collage-broll":
        print("[mode] collage-broll——script 即隐喻清单（见 workflows/collage-broll.md）")
        script_path.write_text(COLLAGE_STUB, encoding="utf-8")
        print(f"[done] 隐喻清单模板已落：{script_path}")
        print("[next] agent 填隐喻清单 → script-self-eval（Stage 2）→ Stage 3–5 → GATE A")
        return

    print("[mode] 未指定 workflow——通用分场剧本；叙事 / 动效 / 蒙太奇手法由我据创意自定")
    script_path.write_text(GENERIC_STUB, encoding="utf-8")
    print(f"[done] script.md 模板已落：{script_path}")
    print("[next] agent 填剧本 → 跑 script-self-eval（Stage 2）")


if __name__ == "__main__":
    main()
