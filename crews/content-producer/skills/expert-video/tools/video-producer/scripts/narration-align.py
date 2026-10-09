#!/usr/bin/env python3
"""Stage 11 — narration-align：旁白时间戳对齐。

Usage:
  python3 scripts/narration-align.py <project_dir>

入：project_dir/audio/narration.mp3（Stage 11 场景 B 一次性 TTS 生成的整段旁白）
    + project_dir/audio/narration.subtitle.json（awk-tts --enable-subtitle 落盘的 TTS 原生字级时间戳，优先复用）
出：project_dir/audio/narration-segments.json
    {
      "text": "全文",
      "segments": [{"start": 0.0, "end": 2.3, "text": "第一句"}, ...],
      "source": "tts-native" | "asr"
    }

路径优先级：
  1. TTS 原生字级时间戳（narration.subtitle.json 存在时直接复用，零额外调用）
  2. 公共 ASR 路由回退（narration.subtitle.json 缺失时，base64 直传 narration.mp3，
     拿 utterance/word 级真实时间戳）

ASR 供应商路由（公共 skills/_shared/asr.py）：火山极速版 → 百炼业务空间 → 百炼 agent plan。
凭据：VOLC_ASR_*（火山）或 WORKSPACE_ID+MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY
（百炼业务空间）或 AWK_API_KEY（百炼 agent plan），任一组即可。

agent 拿到 segments 后，按各 shot 时长把旁白切片对应到镜。
"""

import argparse
import json
import os
import sys
from pathlib import Path

# 优先按仓库 realpath 导入；拷贝部署时使用 managed skills 下的公共共享库。
shared_dir = Path(__file__).resolve().parents[7] / "skills" / "_shared"
if not (shared_dir / "asr.py").is_file():
    shared_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw")).expanduser() / "skills" / "_shared"
sys.path.insert(0, str(shared_dir))
from asr import asr, load_env_file  # noqa: E402


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def try_tts_native(narration: Path, subtitle_arg: str | None, out_path: Path) -> bool:
    """优先路径：复用 awk-tts --enable-subtitle 落盘的 <audio-stem>.subtitle.json。

    TTS 原生字级时间戳结构（awk-tts 落盘）：
      {"sentences": [{"text": "...", "words": [{"word": "大", "startTime": 0.155, "endTime": 0.265, "confidence": 0.98}, ...], "phonemes": []}, ...]}

    转成 <audio-stem>-segments.json 统一格式：
      segments[i] = {start: words[0].startTime, end: words[-1].endTime, text: sentence.text}

    subtitle_arg 显式指定时用 subtitle_arg；否则默认 <narration-stem>.subtitle.json。
    返回 True 表示成功落盘，False 表示需要回退 ASR。
    """
    audio_dir = narration.parent
    if subtitle_arg:
        subtitle_path = audio_dir / subtitle_arg if "/" not in subtitle_arg else Path(subtitle_arg).resolve()
    else:
        subtitle_path = audio_dir / f"{narration.stem}.subtitle.json"
    if not subtitle_path.is_file():
        return False

    try:
        sub = json.loads(subtitle_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[warn] {subtitle_path.name} 解析失败 ({e})，回退 ASR")
        return False

    sentences = sub.get("sentences") or []
    if not sentences:
        print(f"[warn] {subtitle_path.name} 无 sentences，回退 ASR")
        return False

    segs = []
    for sent in sentences:
        words = sent.get("words") or []
        text = sent.get("text", "") or ""
        if not words:
            continue
        try:
            start = float(words[0].get("startTime", 0))
            end = float(words[-1].get("endTime", start))
        except (TypeError, ValueError):
            continue
        segs.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        })

    if not segs:
        print(f"[warn] {subtitle_path.name} 无有效 words，回退 ASR")
        return False

    out = {
        "text": "".join(s["text"] for s in segs),
        "segments": segs,
        "source": "tts-native",
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def fallback_asr(narration: Path, out_path: Path) -> None:
    """回退路径：调公共 ASR 路由（火山 → 百炼），拿 word 级真实时间戳。

    统一走公共 skills/_shared/asr.py，与 talking-head-cut / viral-chaser / awk-tts 共一份逻辑。
    原先本函数只拿 utterance 级，现统一拿 word 级（更精细对齐）。
    """
    print(f"[info] {narration.stem}.subtitle.json 缺失，调公共 ASR 路由转写 {narration.name} ...")
    result = asr(str(narration))
    if not result.get("ok"):
        die(f"ASR 失败: {result.get('error', '未知错误')}")

    words = result.get("words") or []
    if not words:
        # word 级为空时兜底用 utterance 级
        utterances = result.get("utterances") or []
        if not utterances:
            die("ASR 未返回 utterances/words，无法对齐")
        segs = [
            {"start": round(u["start"], 3), "end": round(u["end"], 3), "text": u["text"]}
            for u in utterances
        ]
    else:
        segs = [
            {"start": round(w["start"], 3), "end": round(w["end"], 3), "text": w["text"]}
            for w in words
        ]

    out = {
        "text": result.get("text", "") or "",
        "segments": segs,
        "source": "asr",
    }
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    load_env_file()

    parser = argparse.ArgumentParser(description="Stage 11 narration-align")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument(
        "--audio",
        default=None,
        help="旁白音频文件名（默认 audio/narration.mp3；可传 narration-v2.mp3 等新版）",
    )
    parser.add_argument(
        "--subtitle",
        default=None,
        help="TTS 字级时间戳文件名（默认 audio/<audio-stem>.subtitle.json；可显式指定）",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出 segments 文件名（默认 audio/<audio-stem>-segments.json）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已存在的输出文件（默认跳过已存在的）",
    )
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    audio_dir = project / "audio"

    # 解析音频路径：默认 narration.mp3，可传 --audio narration-v2.mp3
    if args.audio:
        narration = audio_dir / args.audio if "/" not in args.audio else Path(args.audio).resolve()
    else:
        narration = audio_dir / "narration.mp3"
    if not narration.is_file():
        die(f"前置缺失: {narration} 不存在，先一次性 TTS 生成整段旁白")

    # 输出路径：默认 <audio-stem>-segments.json，可传 --out 显式指定
    out_path = audio_dir / (args.out if args.out else f"{narration.stem}-segments.json")
    if out_path.is_file() and not args.force:
        print(f"[checkpoint] {out_path.name} 已存在：{out_path}（--force 覆盖）")
        return

    # 优先路径：TTS 原生字级时间戳
    if try_tts_native(narration, args.subtitle, out_path):
        print(f"[done] {out_path.name} 已落（TTS 原生字级时间戳）：{out_path}")
    else:
        # 回退路径：公共 ASR 路由（火山 → 百炼）
        fallback_asr(narration, out_path)
        print(f"[done] {out_path.name} 已落（ASR 回退）：{out_path}")

    # 统一打印结果摘要
    result = json.loads(out_path.read_text(encoding="utf-8"))
    segs = result.get("segments") or []
    print(f"  - 共 {len(segs)} 段，source={result.get('source')}")
    if segs:
        print(f"  - 首段: {segs[0]['start']}-{segs[0]['end']}s  「{segs[0]['text'][:40]}」")
        print(f"  - 末段: {segs[-1]['start']}-{segs[-1]['end']}s  「{segs[-1]['text'][:40]}」")
    print(f"[next] agent 按 shot 时长把 segments 切片对应到镜，assemble 时混入")


if __name__ == "__main__":
    main()
