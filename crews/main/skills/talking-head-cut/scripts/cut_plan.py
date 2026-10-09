#!/usr/bin/env python3
"""cut_plan.py — 去口气词/高光剪辑：检测生 cut_plan.json。

用法：
  python3 cut_plan.py <input.mp4> [--mode filler|highlight|both] [--language zh|en]
                       [--silence-gap 0.6] [--stutter-repeat 4]
                       [--similarity-threshold 0.6] [--output cut_plan.json]

流程：
  1. ffmpeg 抽 16kHz mono WAV
  2. 调公共 ASR 路由（skills/_shared/asr.py：火山极速版 → 百炼业务空间 → 百炼 agent plan）
     拿 utterance + word 级时间戳
     （凭据：VOLC_ASR_* 或 WORKSPACE_ID+MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY 或 AWK_API_KEY）
  3. 多层检测（按 --mode 决定保留策略）：
     - fillers：语气词清单匹配（zh: 嗯/呃/额/唔/哎/诶/欸；en: um/uh/uhm/er）
     - silence：word gap > --silence-gap 秒
     - stutters：单字重复 ≥ --stutter-repeat 次（如"我我我我"）
     - false_starts：短句（< 0.3s）后接同义长句
     - repeats：句级文本相似度 > --similarity-threshold（Jaccard）
  4. --mode filler（默认）：上述五类都标 remove，其余 keep
     --mode highlight：反过来——只 keep 高光段（语音密度高 + 语速快 + 关键词命中 + 与全片文本相似度低的"新颖段"）
     --mode both：先 filler 剪，再在保留段里 highlight 标次要 keep
  5. 输出 cut_plan.json：[{keep: bool, start: float, end: float, reason: "filler"/"silence"/"stutter"/"false_start"/"repeat"/"highlight"/"normal"}]

依赖：
  - ffmpeg/ffprobe（系统）
  - ASR 凭据（VOLC_ASR_* / WORKSPACE_ID+MODELSTUDIO_API_KEY / AWK_API_KEY 任一组）
  - requests（Python 包，仓根 requirements.txt 已声明）

无第三方 ASR/VAD 包——不引入 faster-whisper / Silero VAD，与 main stdlib + ffmpeg 范式一致。

退出码：
  0 = 成功
  1 = 参数错误 / 文件不存在
  2 = ASR 凭据未配置（提示用户走 viral-chaser 开通流程配火山，或配百炼 key）
  3 = ffmpeg/ffprobe 不存在
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 优先按仓库 realpath 导入；拷贝部署时使用 managed skills 下的公共共享库。
shared_dir = Path(__file__).resolve().parents[5] / "skills" / "_shared"
if not (shared_dir / "asr.py").is_file():
    shared_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw")).expanduser() / "skills" / "_shared"
sys.path.insert(0, str(shared_dir))
from asr import asr  # noqa: E402

# 语气词清单
FILLERS_ZH = {"嗯", "呃", "额", "唔", "哎", "诶", "欸", "啊", "呀", "嘛", "呢", "吧"}
FILLERS_EN = {"um", "uh", "uhm", "er", "erm", "eh", "ah"}


def extract_wav(video_path: str, out_wav: str) -> bool:
    """ffmpeg 抽 16kHz mono WAV。"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ar", "16000", "-ac", "1",
        "-f", "wav", out_wav,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def jaccard(a: set, b: set) -> float:
    """两集合的 Jaccard 相似度。"""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def detect_fillers(words: list, language: str) -> list:
    """返语气词段 [{start, end, reason: filler}]。"""
    fillers = FILLERS_ZH if language == "zh" else FILLERS_EN
    out = []
    for w in words:
        t = w.get("text", "").strip()
        if not t:
            continue
        # 去标点后单字匹配
        t_clean = t.strip("。,，!！?？")
        if not t_clean:
            continue
        if t_clean in fillers:
            out.append({
                "start": w["start"],
                "end": w["end"],
                "reason": "filler",
            })
    return out


def detect_silence(words: list, utterances: list, gap_sec: float) -> list:
    """返静音段 [{start, end, reason: silence}]——相邻 word gap > gap_sec。"""
    out = []
    prev_end = 0.0
    for w in words:
        if w["start"] - prev_end > gap_sec:
            out.append({
                "start": prev_end,
                "end": w["start"],
                "reason": "silence",
            })
        prev_end = max(prev_end, w["end"])
    return out


def detect_stutters(words: list, repeat: int) -> list:
    """返结巴段——单字重复 ≥ repeat 次（如"我我我我"）。"""
    out = []
    if len(words) < repeat:
        return out
    i = 0
    while i < len(words):
        j = i + 1
        while j < len(words) and words[j].get("text", "").strip().strip("。,，!！?？") == \
                words[i].get("text", "").strip().strip("。,，!！?？"):
            j += 1
        if j - i >= repeat:
            out.append({
                "start": words[i]["start"],
                "end": words[j - 1]["end"],
                "reason": "stutter",
            })
        i = j
    return out


def detect_false_starts(utterances: list) -> list:
    """返假起头段——短句（< 0.3s）后接同义长句。"""
    out = []
    for i, u in enumerate(utterances):
        dur = u["end"] - u["start"]
        if dur >= 0.3 or dur <= 0:
            continue
        # 找下一句
        if i + 1 >= len(utterances):
            continue
        nxt = utterances[i + 1]
        # Jaccard 字符集相似度 > 0.5 视为同义
        a = set(u["text"])
        b = set(nxt["text"])
        if jaccard(a, b) > 0.5 and len(nxt["text"]) > len(u["text"]):
            out.append({
                "start": u["start"],
                "end": u["end"],
                "reason": "false_start",
            })
    return out


def detect_repeats(utterances: list, sim_thresh: float) -> list:
    """返重复句段——句间 Jaccard > sim_thresh。"""
    out = []
    for i in range(len(utterances)):
        for j in range(i + 1, min(i + 5, len(utterances))):  # 窗口 5 句
            a = set(utterances[i]["text"])
            b = set(utterances[j]["text"])
            if jaccard(a, b) > sim_thresh:
                out.append({
                    "start": utterances[j]["start"],
                    "end": utterances[j]["end"],
                    "reason": "repeat",
                })
                break  # 一句只标一次
    return out


def detect_highlight(utterances: list, words: list) -> list:
    """返高光段——语音密度高 + 语速快 + 与全片文本相似度低的"新颖段"。
    判据：
    - 密度：utterance 字数 / 时长 > 4 字/秒（zh）/ 3 词/秒（en）
    - 新颖：与全片文本 Jaccard < 0.3
    """
    out = []
    if not utterances:
        return out
    # 全片文本字符集
    full_text = "".join(u["text"] for u in utterances)
    full_set = set(full_text)
    for u in utterances:
        dur = u["end"] - u["start"]
        if dur <= 0:
            continue
        chars = len(u["text"])
        density = chars / dur  # 字/秒
        novelty = 1.0 - jaccard(set(u["text"]), full_set)  # 新颖度
        if density > 4.0 and novelty > 0.7:
            out.append({
                "start": u["start"],
                "end": u["end"],
                "reason": "highlight",
            })
    return out


def build_plan(words: list, utterances: list, mode: str, language: str,
               silence_gap: float, stutter_repeat: int, sim_thresh: float) -> list:
    """按 mode 生 [{keep, start, end, reason}]。"""
    fillers = detect_fillers(words, language)
    silences = detect_silence(words, utterances, silence_gap)
    stutters = detect_stutters(words, stutter_repeat)
    false_starts = detect_false_starts(utterances)
    repeats = detect_repeats(utterances, sim_thresh)
    highlights = detect_highlight(utterances, words)

    # 合并所有标记段
    removes = fillers + silences + stutters + false_starts + repeats
    highlights_sorted = sorted(highlights, key=lambda x: x["start"])

    if not utterances:
        return []

    # 时间轴扫 utterance，按 reason 标 keep
    plan = []
    for u in utterances:
        s, e = u["start"], u["end"]
        # 找该 utterance 落在哪个 highlight 段
        reason = "normal"
        keep = True
        if mode == "filler":
            # 检查是否落入任一 remove 段
            for r in removes:
                if r["start"] <= s and e <= r["end"]:
                    reason = r["reason"]
                    keep = False
                    break
            if keep:
                reason = "normal"
        elif mode == "highlight":
            # 只 keep 高光段
            in_hl = False
            for h in highlights_sorted:
                if h["start"] <= s and e <= h["end"]:
                    in_hl = True
                    break
                if h["start"] > e:
                    break
            if in_hl:
                reason = "highlight"
                keep = True
            else:
                reason = "normal"
                keep = False
        elif mode == "both":
            # 先按 filler 规则标 remove
            in_remove = False
            for r in removes:
                if r["start"] <= s and e <= r["end"]:
                    reason = r["reason"]
                    keep = False
                    in_remove = True
                    break
            if not in_remove:
                # 再看是否 highlight
                in_hl = False
                for h in highlights_sorted:
                    if h["start"] <= s and e <= h["end"]:
                        in_hl = True
                        break
                    if h["start"] > e:
                        break
                if in_hl:
                    reason = "highlight"
                    keep = True
                else:
                    reason = "normal"
                    keep = False
        plan.append({"keep": keep, "start": round(s, 3), "end": round(e, 3), "reason": reason})

    # 兜底：若 utterances 为空但有 words，按 word 切段
    if not plan and words:
        for w in words:
            plan.append({
                "keep": mode != "filler" or w.get("text", "").strip() not in
                        (FILLERS_ZH if language == "zh" else FILLERS_EN),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "reason": "normal",
            })

    return plan


def _reason_for(removes: list, s: float, e: float) -> str:
    """给 (start, end) 找落入了哪个 remove 段，返 reason；未落入返 'normal'。"""
    for r in removes:
        if r["start"] <= s and e <= r["end"]:
            return r["reason"]
    return "normal"


def main() -> None:
    parser = argparse.ArgumentParser(description="去口气词/高光剪辑 — 检测生 cut_plan.json")
    parser.add_argument("input", help="源视频/音频路径")
    parser.add_argument("--mode", choices=["filler", "highlight", "both"], default="filler",
                        help="filler 去口气词 / highlight 高光剪辑 / both 先 filler 再 highlight")
    parser.add_argument("--language", choices=["zh", "en"], default="zh",
                        help="语气词清单选择")
    parser.add_argument("--silence-gap", type=float, default=0.6,
                        help="静音段判据：相邻 word gap > 此秒数")
    parser.add_argument("--stutter-repeat", type=int, default=4,
                        help="结巴段判据：单字重复 ≥ 此次数")
    parser.add_argument("--similarity-threshold", type=float, default=0.6,
                        help="重复句段判据：句间 Jaccard > 此阈值")
    parser.add_argument("--output", default="cut_plan.json",
                        help="cut_plan.json 输出路径")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(json.dumps({"ok": False, "error": f"输入文件不存在: {args.input}"}),
              file=sys.stderr)
        sys.exit(1)

    # 检查 ffmpeg
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        print(json.dumps({"ok": False, "error": "ffmpeg 未安装"}), file=sys.stderr)
        sys.exit(3)

    # 1. 抽 WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name
    if not extract_wav(args.input, wav_path):
        print(json.dumps({"ok": False, "error": "ffmpeg 抽 WAV 失败"}), file=sys.stderr)
        try:
            os.unlink(wav_path)
        except OSError:
            pass
        sys.exit(3)

    # 2. ASR 路由（火山 → 百炼业务空间 → 百炼 agent plan）
    asr_result = asr(wav_path)
    try:
        os.unlink(wav_path)
    except OSError:
        pass

    if not asr_result.get("ok"):
        err = asr_result.get("error", "")
        print(json.dumps({"ok": False, "error": err}), file=sys.stderr)
        # ASR env 未配 → 退出码 2
        if "VOLC_ASR" in err or "凭证未配置" in err:
            sys.exit(2)
        sys.exit(1)

    text = asr_result.get("text", "")
    utterances = asr_result.get("utterances", [])
    words = asr_result.get("words", [])

    if not utterances and not words:
        print(json.dumps({"ok": False, "error": "ASR 未返回任何 utterance/word"}), file=sys.stderr)
        sys.exit(1)

    # 3. 检测 + 生 plan
    plan = build_plan(
        words, utterances, args.mode, args.language,
        args.silence_gap, args.stutter_repeat, args.similarity_threshold,
    )

    # 4. 计算源时长（用最后一 word/utterance end 兜底）
    duration = 0.0
    if utterances:
        duration = utterances[-1]["end"]
    elif words:
        duration = words[-1]["end"]

    # 5. 落盘
    output_data = {
        "ok": True,
        "source": os.path.basename(args.input),
        "duration": round(duration, 3),
        "mode": args.mode,
        "plan": plan,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # 6. stdout 报告
    keep_segs = [p for p in plan if p.get("keep")]
    remove_segs = [p for p in plan if not p.get("keep")]
    keep_dur = sum(p["end"] - p["start"] for p in keep_segs)
    remove_dur = sum(p["end"] - p["start"] for p in remove_segs)

    # 按 reason 分组统计
    by_reason = {}
    for p in plan:
        r = p.get("reason", "normal")
        by_reason.setdefault(r, {"count": 0, "duration": 0.0})
        by_reason[r]["count"] += 1
        by_reason[r]["duration"] += p["end"] - p["start"]

    report = {
        "ok": True,
        "source": os.path.basename(args.input),
        "duration": round(duration, 3),
        "mode": args.mode,
        "plan_path": args.output,
        "summary": {
            "keep_segments": len(keep_segs),
            "keep_duration": round(keep_dur, 3),
            "remove_segments": len(remove_segs),
            "remove_duration": round(remove_dur, 3),
        },
        "by_reason": {
            r: {"count": v["count"], "duration": round(v["duration"], 3)}
            for r, v in sorted(by_reason.items())
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
