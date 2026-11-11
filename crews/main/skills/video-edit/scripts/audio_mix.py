#!/usr/bin/env python3
"""给已有视频加旁白/BGM；先固定各轨格式和时间轴，再混音并核验输出。

旁白默认替换原音轨；BGM 默认增益 0.25，可选取并循环指定段落。
退出码：0 成功；1 参数、媒体或处理失败；3 ffmpeg/ffprobe 缺失。
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


RATE = 44100
TOLERANCE = 0.1


def die(msg: str, code: int = 1) -> None:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise ValueError(f"{cmd[0]} 失败: {r.stderr[-1000:]}")
    return r


def probe(path: str | Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                           "-of", "json", str(path)]).stdout)


def span(data: dict, kind: str) -> dict | None:
    stream = next((s for s in data.get("streams", []) if s.get("codec_type") == kind), None)
    if stream is None:
        return None
    try:
        start = float(stream.get("start_time", 0))
        raw = stream.get("duration")
        duration = float(raw) if raw not in (None, "N/A") else (
            float(stream["duration_ts"]) * float(Fraction(stream["time_base"])))
        if not math.isfinite(start) or not math.isfinite(duration) or duration <= 0:
            raise ValueError()
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        raise ValueError(f"无法确定 {kind} 流起止时间；请先转换为含完整流时长的 MP4/WAV")
    return {"start": start, "duration": duration, "end": start + duration, "stream": stream}


def nonnegative(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("必须为有限非负数")
    return result


def render_stem(source: Path, output: Path, *, start: float, duration: float,
                normalize: bool) -> float:
    # Materialize before amix: dynamic loudnorm can buffer frames and change PTS.
    filters = [f"atrim=start={start}:duration={duration}", "asetpts=PTS-STARTPTS",
               f"aformat=channel_layouts=stereo:sample_rates={RATE}"]
    if normalize:
        filters.append("loudnorm=I=-16:TP=-2:LRA=9")
    filters += [f"aresample={RATE}", "asetpts=N/SR/TB"]
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
         "-map", "0:a:0", "-af", ",".join(filters), "-c:a", "pcm_f32le", str(output)])
    actual = span(probe(output), "audio")["duration"]
    if abs(actual - duration) > TOLERANCE:
        raise ValueError(f"音轨处理后时长异常: {source}，预期 {duration:.3f}s，实际 {actual:.3f}s")
    return actual


def measure_peak(path: Path) -> float:
    stats = run(["ffmpeg", "-nostdin", "-v", "info", "-i", str(path), "-map", "0:a:0", "-af",
                 "astats=measure_perchannel=none:measure_overall=Peak_level:reset=0", "-f", "null", "-"])
    peaks = re.findall(r"Peak level dB:\s*([-+\w.]+)", stats.stderr)
    if not peaks:
        raise ValueError("无法测量混音峰值")
    peak = float(peaks[-1])
    if math.isnan(peak) or peak == math.inf:
        raise ValueError("混音包含无效样本")
    return peak


def mix(args: argparse.Namespace) -> dict:
    source = Path(args.input)
    output = Path(args.output) if args.output else source.with_name(source.stem + "_mixed.mp4")
    sources = [source] + [Path(p) for p in (args.narration, args.bgm) if p]
    for path in sources:
        if not path.is_file():
            raise ValueError(f"输入不存在: {path}")
        if path.resolve() == output.resolve() or (output.exists() and os.path.samefile(path, output)):
            raise ValueError("输出不能覆盖输入媒体")
    data = probe(source)
    video = span(data, "video")
    if video is None:
        raise ValueError("输入没有视频流")
    duration = video["duration"]
    original = span(data, "audio")
    orig_vol = args.original_volume if args.original_volume is not None else (0.0 if args.narration else 1.0)
    if not args.bgm and (args.bgm_start or args.bgm_duration is not None):
        raise ValueError("BGM 选段参数需要 --bgm")
    if args.bgm_duration is not None and args.bgm_duration <= 0:
        raise ValueError("--bgm-duration 必须大于 0")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".audio-mix-", dir=output.parent) as temp:
        work = Path(temp)
        tracks = []
        bgm_segment = None
        if args.narration:
            path = Path(args.narration)
            voice = span(probe(path), "audio")
            if voice is None:
                raise ValueError("旁白文件没有音轨")
            if voice["duration"] > duration + TOLERANCE:
                raise ValueError(f"旁白 {voice['duration']:.3f}s 长于画面 {duration:.3f}s；请先调整旁白或画面，禁止自动截末句")
            stem = work / "narration.wav"
            render_stem(path, stem, start=0, duration=voice["duration"], normalize=args.normalize_inputs)
            tracks.append((stem, args.narration_volume, 0.0, False))
        if original and orig_vol > 0:
            stem = work / "original.wav"
            offset = original["start"] - video["start"]
            trim = max(0.0, -offset)
            length = min(original["duration"] - trim, duration - max(0.0, offset))
            if length <= 0:
                raise ValueError("原音轨与视频时间轴无重叠")
            render_stem(source, stem, start=trim, duration=length, normalize=args.normalize_inputs)
            tracks.append((stem, orig_vol, max(0.0, offset), False))
        if args.bgm:
            path = Path(args.bgm)
            music = span(probe(path), "audio")
            if music is None:
                raise ValueError("BGM 文件没有音轨")
            remaining = music["duration"] - args.bgm_start
            length = args.bgm_duration if args.bgm_duration is not None else min(remaining, duration)
            if remaining <= 0 or length > remaining + TOLERANCE:
                raise ValueError("BGM 选段超出曲目时长")
            length = min(length, remaining)
            stem = work / "bgm.wav"
            actual = render_stem(path, stem, start=args.bgm_start, duration=length, normalize=args.normalize_inputs)
            bgm_segment = {"start": args.bgm_start, "duration": actual}
            tracks.append((stem, args.bgm_volume, 0.0, True))
        if not tracks:
            raise ValueError("无可用音频源")

        cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
        filters = []
        for i, (path, volume, delay, looping) in enumerate(tracks):
            if looping:
                cmd += ["-stream_loop", "-1"]
            cmd += ["-i", str(path)]
            chain = ["asetpts=N/SR/TB", f"volume={volume}"]
            if delay:
                chain.append(f"adelay={round(delay * 1000)}:all=1")
            chain += [f"apad=whole_dur={duration}", f"atrim=duration={duration}"]
            if looping:
                fade_in = min(args.bgm_intro_fade, duration)
                fade_out = min(args.bgm_outro_fade, duration)
                if fade_in:
                    chain.append(f"afade=t=in:st=0:d={fade_in}")
                if fade_out:
                    chain.append(f"afade=t=out:st={duration - fade_out}:d={fade_out}")
            filters.append(f"[{i}:a]" + ",".join(chain) + f"[a{i}]")
        labels = "".join(f"[a{i}]" for i in range(len(tracks)))
        filters.append(labels + f"amix=inputs={len(tracks)}:duration=longest:dropout_transition=0:normalize=0[aout]")
        mixed = work / "mix.wav"
        run(cmd + ["-filter_complex", ";".join(filters), "-map", "[aout]", "-t", str(duration),
                   "-ar", str(RATE), "-ac", "2", "-c:a", "pcm_f32le", str(mixed)])

        # Measure float PCM, then apply one common static attenuation if needed.
        # This protects against summation clipping without changing stem ratios.
        peak = measure_peak(mixed)
        gain_db = min(0.0, -1.5 - peak)
        staged = work / "output.mp4"
        # AAC can overshoot the PCM peak, especially at abrupt segment boundaries.
        # Re-encode from the same float mix with common attenuation, at most 3 times.
        for attempt in range(3):
            run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source), "-i", str(mixed),
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", f"volume={gain_db}dB",
                 "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", "2", "-t", str(duration),
                 "-movflags", "+faststart", str(staged)])
            encoded_peak = measure_peak(staged)
            if encoded_peak <= -1.5 + 0.05:
                break
            if attempt == 2:
                raise ValueError(f"AAC 编码后峰值仍过高: {encoded_peak:.2f} dBFS")
            gain_db -= encoded_peak + 1.6
        produced = probe(staged)
        vout, aout = span(produced, "video"), span(produced, "audio")
        if vout is None or aout is None or abs(vout["duration"] - duration) > TOLERANCE:
            raise ValueError("输出视频时长异常")
        gap = max(abs(aout["start"] - vout["start"]), abs(aout["end"] - vout["end"]))
        if gap > TOLERANCE + 1e-6:
            raise ValueError(f"输出音视频时间轴不一致，最大偏差 {gap:.3f}s")
        os.replace(staged, output)
    return {"ok": True, "output": str(output), "duration": vout["duration"],
            "audio_duration": aout["duration"], "audio_video_gap": round(gap, 6),
            "sample_rate": RATE, "channels": 2, "narration": args.narration, "bgm": args.bgm,
            "bgm_segment": bgm_segment, "original_volume": orig_vol,
            "inputs_normalized": args.normalize_inputs, "peak_attenuation_db": round(gain_db, 4),
            "encoded_peak_dbfs": round(encoded_peak, 4) if math.isfinite(encoded_peak) else None}


def main() -> None:
    parser = argparse.ArgumentParser(description="给已有视频加旁白/BGM，输出立体声并核验时间轴")
    parser.add_argument("input", help="输入视频")
    parser.add_argument("--narration", help="旁白文件（默认替换原音轨，超长拒绝截断）")
    parser.add_argument("--bgm", help="BGM 文件（循环所选片段到视频结尾）")
    parser.add_argument("--bgm-start", type=nonnegative, default=0, help="BGM 选段起点，秒")
    parser.add_argument("--bgm-duration", type=nonnegative, help="选段长度，秒；默认取到曲尾或视频时长")
    parser.add_argument("--bgm-intro-fade", type=nonnegative, default=0, help="BGM 淡入秒数，默认 0")
    parser.add_argument("--bgm-outro-fade", type=nonnegative, default=2, help="BGM 淡出秒数，默认 2")
    parser.add_argument("--bgm-volume", type=nonnegative, default=0.25, help="BGM 源增益，默认 0.25；不是相对人声电平")
    parser.add_argument("--narration-volume", type=nonnegative, default=1.0)
    parser.add_argument("--original-volume", type=nonnegative, help="原音轨增益；无旁白默认 1，有旁白默认 0")
    parser.add_argument("--normalize-inputs", action="store_true", help="先将各轨校准至 -16 LUFS，再按所设增益混合")
    parser.add_argument("--output", help="输出 MP4（默认 <input>_mixed.mp4）")
    args = parser.parse_args()
    if not args.narration and not args.bgm:
        die("--narration 与 --bgm 至少给一个")
    for name in ("ffmpeg", "ffprobe"):
        if not shutil.which(name):
            die(f"{name} 未安装", 3)
    try:
        result = mix(args)
    except (ValueError, OSError, KeyError) as exc:
        die(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
