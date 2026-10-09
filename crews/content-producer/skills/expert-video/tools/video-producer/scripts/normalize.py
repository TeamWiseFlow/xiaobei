#!/usr/bin/env python3
"""Loudness normalization — 发布平台通用响度归一化。

把成片音频响度归一化到 -14 LUFS（短视频平台通用标准：抖音/视频号/B 站竖屏通用）。
跑在合成后、自检/交付前。这条是必跑步骤——但脚本
本身尊重 --skip 时跳过；是否强制由 caller 决定（通用制作流程 Stage 13c 规定必跑）。

为什么 -14 LUFS：
- 抖音/视频号/B 站竖屏发布通用标准，与平台播放器电平匹配，避免"在我机 sound bar
  听着正"但"在手机刷到时偏轻/偏响"
- industry de-facto for short-form video

ffmpeg 用 loudnorm 双 pass：
- Pass 1：探测当前响度 + 真实峰 + 阈值，落测量 JSON
- Pass 2：按 Pass 1 测量值应用归一化，落成片

干湿分离：输出落 `<project-dir>/output_normalized.mp4`，**不覆盖原 output.mp4**。
caller 决定是 rename 替换还是双轨保留。

Usage:
  video-producer normalize <video.mp4>
  video-producer normalize <video.mp4> --output <out.mp4>
  video-producer normalize <video.mp4> --target-lufs -14 --true-peak -2.0

Exit codes:
  0  ok，归一化完成
  1  参数错 / ffmpeg 缺失 / 输入不存在
  2  ffmpeg loudnorm 失败（含不可恢复的音频畸变）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 平台通用标准——不动这套阈值除非平台规范变了
DEFAULT_TARGET_LUFS = -14.0
DEFAULT_TRUE_PEAK_DB = -2.0      # 留转码余量；已达响度但峰值超标时仍须处理
DEFAULT_LRA = 11.0                # loudness range 目标，短视频通用 7–13，取中
AGGRESSIVE_THRESHOLD = -20.0     # 平滑触发阈，industry de-facto


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        die(f"missing binary: {cmd[0]}")
    except subprocess.TimeoutExpired:
        die(f"timeout running: {' '.join(cmd[:3])}...")


def ffprobe_loudness(video: str, target_lufs: float, true_peak: float, lra: float) -> dict | None:
    """Pass 1: ffmpeg loudnorm 单 pass 测量当前响度。返回测量 dict 或 None."""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", video,
        "-af", f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:"
               f"print_format=json",
        "-f", "null", "-",
    ]
    rc, _, err = run(cmd, timeout=120)
    if rc != 0:
        return None
    # loudnorm 的 JSON 落 stderr 不是 stdout
    try:
        # 找 stderr 里的 { ... } JSON 块
        start = err.index("{")
        end = err.rindex("}") + 1
        return json.loads(err[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


def normalize(video: str, output: str, target_lufs: float,
              true_peak: float, lra: float) -> dict:
    """双 pass loudnorm。Pass 1 测量，Pass 2 应用."""
    m = ffprobe_loudness(video, target_lufs, true_peak, lra)
    if not m:
        die("Pass 1 测量失败——ffmpeg loudnorm 没出 JSON，输入可能无声轨或损坏", code=2)

    # 测量值传给 Pass 2 实现真归一化（不是再跑一遍单 pass）
    input_i = float(m.get("input_i", 0))
    input_tp = float(m.get("input_tp", 0))
    input_lra = float(m.get("input_lra", 0))
    input_thresh = float(m.get("input_thresh", 0))
    output_i = float(m.get("output_i", DEFAULT_TARGET_LUFS))
    output_tp = float(m.get("output_tp", DEFAULT_TRUE_PEAK_DB))
    output_lra = float(m.get("output_lra", DEFAULT_LRA))
    normalization_i = float(m.get("normalization_i", 0))
    normalization_tp = float(m.get("normalization_tp", 0))
    normalization_lra = float(m.get("normalization_lra", 0))

    # 已经达标就不重渲染（省时间、避免不必要重压缩）
    if abs(input_i - target_lufs) < 0.3 and input_tp <= true_peak - .25:
        print(f"[ok] input_i={input_i:.2f} LUFS 且 input_tp={input_tp:.2f} dBTP 已达标，"
              f"跳过归一化直接拷贝")
        shutil.copy2(video, output)
        return {"skipped": True, "input_i": input_i, "reason": "already_at_target"}

    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", video,
        "-af", (
            f"loudnorm="
            f"I={target_lufs}:TP={true_peak}:LRA={lra}:"
            f"measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:"
            f"measured_thresh={input_thresh}:offset={normalization_i}:"
            f"linear=true:print_format=summary"
        ),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output,
    ]
    rc, _, err = run(cmd, timeout=600)
    if rc != 0:
        die(f"Pass 2 归一化渲染失败: {err.strip()[:500]}", code=2)

    return {
        "skipped": False,
        "input_i": input_i,
        "input_tp": input_tp,
        "input_lra": input_lra,
        "output_i": output_i,
        "output_tp": output_tp,
        "output_lra": output_lra,
        "target_i": target_lufs,
        "target_tp": true_peak,
        "target_lra": lra,
        "normalization_i": normalization_i,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loudness normalization to -14 LUFS (短视频平台通用标准)."
    )
    parser.add_argument("video", help="输入视频路径（合成产物 output.mp4）")
    parser.add_argument("--output", default=None,
                        help="输出路径，默认在输入旁加 _normalized 后缀")
    parser.add_argument("--target-lufs", type=float, default=DEFAULT_TARGET_LUFS,
                        help=f"目标响度 LUFS，默认 {DEFAULT_TARGET_LUFS}")
    parser.add_argument("--true-peak", type=float, default=DEFAULT_TRUE_PEAK_DB,
                        help=f"真实峰上限 dB，默认 {DEFAULT_TRUE_PEAK_DB}")
    parser.add_argument("--lra", type=float, default=DEFAULT_LRA,
                        help=f"loudness range 目标，默认 {DEFAULT_LRA}")
    parser.add_argument("--silent-ok", action="store_true",
                        help="明确批准无声交付时核验无音轨、原样输出并记录不适用；有音轨仍正常归一化")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.is_file():
        die(f"输入视频不存在: {video_path}")

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        stem = video_path.stem
        out_path = video_path.with_name(f"{stem}_normalized.mp4")
    if out_path == video_path:
        die("输出不能覆盖输入")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.silent_ok:
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True,
            )
        except FileNotFoundError:
            die("ffprobe 未在 PATH，不能核验无声交付")
        if probe.returncode != 0:
            die("无声音轨核验失败，不能按无声交付放行")
        streams = set(probe.stdout.splitlines())
        if "video" not in streams:
            die("输入没有可识别的视频流")
        if "audio" not in streams:
            shutil.copy2(video_path, out_path)
            record = {"stage": "13c", "status": "not_applicable", "reason": "verified_silent_video",
                      "input": str(video_path), "output": str(out_path)}
            out_path.with_suffix(".normalization.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(record, ensure_ascii=False))
            return

    print(f"[info] input: {video_path}")
    print(f"[info] target: {args.target_lufs} LUFS / {args.true_peak} dB true peak / LRA {args.lra}")
    print(f"[info] output: {out_path}")

    result = normalize(str(video_path), str(out_path),
                       args.target_lufs, args.true_peak, args.lra)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n[done] normalized: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
