#!/usr/bin/env python3
"""timeline-compose — 时间轴合成：按 JSON 指令调 clip-trim + audio-mix 合成片段。

原子工具，不写死 Workflow。agent 按 SKILL.md 场景化组合调用。

Usage:
  python3 scripts/timeline-compose.py <project_dir> --timeline timeline.json [--output video.mp4]

时间轴 JSON 结构：
{
  "segments": [
    {
      "source": "render/shot-01/gen.mp4",     # 素材路径（相对 project_dir）
      "start": 0.5,                            # 入点（秒，默认 0）
      "end": 2.3,                              # 出点（秒，默认=素材全长）
      "speed": 1.5,                            # 倍速（默认 1.0）
      "sync_audio": true,                      # 视频倍速时同步音频倍速（默认 false）
      "audio_tracks": [                        # 该段额外音轨（可选，叠加到段音轨）
        {"source": "audio/narration.mp3", "start": 0.0, "end": 1.8, "delay": 0, "volume": 1.0}
      ]
    },
    ...
  ],
  "audio_globals": [                           # 全段音轨（可选，按 delay 跨段叠加）
    {"source": "audio/bgm.mp3", "delay": 0, "volume": 0.15}
  ],
  "audio_mode": "mix",                         # mix（默认，走 amix）/ concat（各段音轨静音填充后 concat 成连续轨）
  "width": 1080,                              # 归一化宽度（可选，默认不归一化）
  "fps": 30                                   # 归一化帧率（可选，默认不归一化）
}

输出：
  project_dir/artifacts/timeline/ 下各段切好的片段（clip-NN.mp4）
  project_dir/<output>（默认 video.mp4）：最终合成片段（按段序 concat + 各段音轨 + 全段音轨混入）

本脚本内部调 clip-trim.py 切段 + audio-mix.py 混音，不裸写 ffmpeg filter。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"[cmd] {cmd[0]} ... ({len(cmd)} args)")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        die(f"命令失败 (rc={p.returncode}): {p.stderr[:500] or p.stdout[:500]}")
    return p


def probe_duration(path: Path) -> float:
    """ffprobe 取时长（秒）。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        return 0.0
    try:
        return float(json.loads(p.stdout).get("format", {}).get("duration", 0) or 0)
    except Exception:
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="timeline-compose 时间轴合成")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--timeline", required=True, help="时间轴 JSON 路径（相对 project_dir 或绝对）")
    parser.add_argument("--output", default="video.mp4", help="输出合成片段名（相对 project_dir，默认 video.mp4）")
    parser.add_argument("--transition", default="hard", choices=["hard", "fade", "dissolve", "xfade"])
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    tl_path = Path(args.timeline)
    if not tl_path.is_absolute():
        tl_path = project / args.timeline
    if not tl_path.is_file():
        die(f"时间轴不存在: {tl_path}")

    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    segments = tl.get("segments") or []
    if not segments:
        die("时间轴无 segments")

    audio_mode = tl.get("audio_mode", "mix")
    if audio_mode not in ("mix", "concat"):
        die(f"audio_mode 须为 mix / concat，收到 {audio_mode}")

    work_dir = project / "artifacts" / "timeline"
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. 每段调 clip-trim 切素材
    print(f"[plan] 共 {len(segments)} 段，audio_mode={audio_mode}，切段中...")
    clip_paths: list[Path] = []
    for i, seg in enumerate(segments, 1):
        src = Path(seg["source"])
        if not src.is_absolute():
            src = project / seg["source"]
        if not src.is_file():
            die(f"段 {i} 素材不存在: {src}")

        clip_dst = work_dir / f"clip-{i:02d}.mp4"
        cmd = [
            sys.executable, str(SCRIPT_DIR / "clip-trim.py"),
            "--input", str(src),
            "--output", str(clip_dst),
        ]
        if seg.get("start") is not None:
            cmd.extend(["--start", str(seg["start"])])
        if seg.get("end") is not None:
            cmd.extend(["--end", str(seg["end"])])
        if seg.get("speed") is not None and seg["speed"] != 1.0:
            cmd.extend(["--speed", str(seg["speed"])])
            if seg.get("sync_audio"):
                cmd.append("--sync-audio")
        print(f"[clip] 段 {i}: {src.name}")
        run(cmd)
        clip_paths.append(clip_dst)

    if audio_mode == "mix":
        # mix 模式（默认）：各段 audio_tracks 跑 audio-mix 叠到段音轨
        for i, seg in enumerate(segments, 1):
            audio_tracks = seg.get("audio_tracks") or []
            if not audio_tracks:
                continue
            clip = work_dir / f"clip-{i:02d}.mp4"
            mixed = work_dir / f"clip-{i:02d}-mixed.mp4"
            cmd = [sys.executable, str(SCRIPT_DIR / "audio-mix.py")]
            cmd.extend(["--track", str(clip), "--delay", "0", "--volume", "1.0"])
            for tr in audio_tracks:
                tsrc = Path(tr["source"])
                if not tsrc.is_absolute():
                    tsrc = project / tr["source"]
                cmd.extend(["--track", str(tsrc)])
                cmd.extend(["--delay", str(tr.get("delay", 0))])
                cmd.extend(["--volume", str(tr.get("volume", 1.0))])
            cmd.extend(["--output", str(mixed)])
            print(f"[mix] 段 {i} 音轨混入")
            run(cmd)
            clip_paths[i - 1] = mixed  # 替换为混音后的版本

    # 3. 拼接各段（走 assemble.py 做按序 concat + 可选转场）
    out_path = project / args.output
    width = tl.get("width")
    fps = tl.get("fps")
    norm_msg = f"，归一化={width}x{round(width*9/16)}@{fps}fps" if width and fps else "，未归一化"
    print(f"[compose] 拼接 {len(clip_paths)} 段，转场={args.transition}{norm_msg}")
    cmd = [
        sys.executable, str(SCRIPT_DIR / "assemble.py"),
        str(project),
        "--source-dir", "artifacts/timeline",
        "--output", args.output,
        "--transition", args.transition,
    ]
    if width is not None and fps is not None:
        cmd.extend(["--width", str(width), "--fps", str(fps)])
    run(cmd)

    if audio_mode == "concat":
        # concat 模式：各段音轨静音填充后 concat 成一条连续轨，避免 amix 断续/稀释
        # 1. 每段音轨 adelay 到该段在整个 timeline 的起始时刻 + apad 填充到整片总时长
        # 2. 各段音轨 concat 成一条整片音轨
        # 3. 与视频合成
        # 段起始时刻 = 前面所有段时长之和（每段时长 = clip 时长 / speed）
        # 整片总时长 = 所有段时长之和
        seg_start_times: list[float] = []
        seg_durations: list[float] = []
        accum = 0.0
        for i, seg in enumerate(segments, 1):
            seg_start_times.append(accum)
            clip = work_dir / f"clip-{i:02d}.mp4"
            seg_dur = probe_duration(clip)
            seg_durations.append(seg_dur)
            accum += seg_dur
        total_dur = accum

        # 各段音轨：该段 clip 的音轨 + 该段 audio_tracks（旁白等）
        seg_audio_paths: list[Path] = []
        for i, seg in enumerate(segments, 1):
            clip = work_dir / f"clip-{i:02d}.mp4"
            audio_tracks = seg.get("audio_tracks") or []
            # 该段音轨 = clip 音轨 + audio_tracks 混合
            # 但 concat 模式下，clip 音轨本身也是段的一部分
            # 简化：该段音轨 = clip 音轨（如有）+ audio_tracks 混合，然后 adelay 到段起始 + apad 到总时长
            if audio_tracks:
                mixed = work_dir / f"clip-{i:02d}-mixed.mp4"
                mix_cmd = [sys.executable, str(SCRIPT_DIR / "audio-mix.py")]
                mix_cmd.extend(["--track", str(clip), "--delay", "0", "--volume", "1.0"])
                for tr in audio_tracks:
                    tsrc = Path(tr["source"])
                    if not tsrc.is_absolute():
                        tsrc = project / tr["source"]
                    mix_cmd.extend(["--track", str(tsrc)])
                    mix_cmd.extend(["--delay", str(tr.get("delay", 0))])
                    mix_cmd.extend(["--volume", str(tr.get("volume", 1.0))])
                mix_cmd.extend(["--output", str(mixed)])
                print(f"[mix] 段 {i} 音轨混入（concat 模式）")
                run(mix_cmd)
                seg_audio_src = mixed
            else:
                seg_audio_src = clip

            # 提取该段音轨，adelay 到段起始 + apad 填充到整片总时长
            seg_audio = work_dir / f"seg-audio-{i:02d}.wav"
            delay_ms = int(seg_start_times[i - 1] * 1000)
            af = f"adelay={delay_ms},apad=whole_dur={total_dur:.3f}"
            run([
                "ffmpeg", "-y", "-i", str(seg_audio_src),
                "-vn", "-af", af,
                "-c:a", "pcm_s16le", str(seg_audio),
            ])
            seg_audio_paths.append(seg_audio)

        # 各段音轨 concat 成一条整片音轨
        concat_list = work_dir / "audio-concat-list.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in seg_audio_paths),
            encoding="utf-8",
        )
        full_audio = work_dir / "full-audio.wav"
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:a", "pcm_s16le", str(full_audio),
        ])

        # 与视频合成
        tmp_with_audio = work_dir / "with-audio.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(out_path),
            "-i", str(full_audio),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(tmp_with_audio),
        ]
        print(f"[concat] 各段音轨 concat 成连续轨，与视频合成")
        run(cmd)
        tmp_with_audio.replace(out_path)

    # 4. 全段音轨（audio_globals）混入最终片段
    globals_audio = tl.get("audio_globals") or []
    if globals_audio:
        tmp_with_globals = work_dir / "with-globals.mp4"
        cmd = [sys.executable, str(SCRIPT_DIR / "audio-mix.py")]
        cmd.extend(["--track", str(out_path), "--delay", "0", "--volume", "1.0"])
        for tr in globals_audio:
            tsrc = Path(tr["source"])
            if not tsrc.is_absolute():
                tsrc = project / tr["source"]
            cmd.extend(["--track", str(tsrc)])
            cmd.extend(["--delay", str(tr.get("delay", 0))])
            cmd.extend(["--volume", str(tr.get("volume", 1.0))])
        cmd.extend(["--output", str(tmp_with_globals)])
        print(f"[mix] 全段音轨混入")
        run(cmd)
        tmp_with_globals.replace(out_path)

    print(f"[done] 时间轴合成已落：{out_path}")
    print(f"  - {len(segments)} 段，转场 {args.transition}，audio_mode={audio_mode}")
    if globals_audio:
        print(f"  - 全段音轨 {len(globals_audio)} 条已混入")


if __name__ == "__main__":
    main()
