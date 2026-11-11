#!/usr/bin/env python3
"""scene-compose — 单个 Scene 的分段合成。

原子工具，不写死 Workflow。agent 按 SKILL.md 场景化组合调用。

实际制作中，每个 Scene 需要独立合成（拼视频片段 + 混旁白 + 混对白），
然后所有 Scene 再拼接成成片。本子命令封装"一个 Scene 内的多段合成"。

与 timeline-compose 的区别：
  - scene-compose：一个 Scene 内的多段合成（片段列表 + 旁白 + 对白）
  - timeline-compose：整片时间轴合成（所有段 + 全段音轨）

Usage:
  python3 scripts/scene-compose.py <project_dir> --scene scene.json [--output scene-01.mp4]

Scene JSON 结构：
  {
    "clips": [                              # 视频片段列表（按序拼接）
      {
        "source": "render/shot-01/gen.mp4",  # 素材路径（相对 project_dir）
        "start": 0.5,                        # 入点（秒，默认 0）
        "end": 2.3,                          # 出点（秒，默认=素材全长）
        "speed": 1.5,                        # 倍速（默认 1.0）
        "sync_audio": true                   # 视频倍速时同步音频倍速（默认 false）
      },
      ...
    ],
    "narration": {                          # 旁白（可选）
      "source": "audio/narration.mp3",      # 旁白音频路径（相对 project_dir）
      "start": 0.0,                         # 该 Scene 旁白起始秒（默认 0）
      "end": 5.0,                           # 该 Scene 旁白结束秒（默认=素材全长）
      "delay": 0,                           # 该 Scene 内旁白延时（秒，默认 0）
      "volume": 1.0                         # 旁白音量（默认 1.0）
    },
    "dialogue": {                           # 对白（可选）
      "source": "audio/dialogue-01.mp3",    # 对白音频路径
      "delay": 0,                           # 对白延时（秒，默认 0）
      "volume": 1.0                         # 对白音量（默认 1.0）
    },
    "width": 1080,                          # 归一化宽度（可选，默认不归一化）
    "fps": 30                               # 归一化帧率（可选，默认不归一化）
  }

输出：
  project_dir/artifacts/scenes/ 下各 Scene 合成的完整片段
  本脚本内部调 clip-trim.py 切段 + audio-mix.py 混旁白/对白 + assemble.py 拼段
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


def main() -> None:
    parser = argparse.ArgumentParser(description="scene-compose 单 Scene 分段合成")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--scene", required=True, help="Scene JSON 路径（相对 project_dir 或绝对）")
    parser.add_argument("--output", default=None,
                        help="输出 Scene 片段名（相对 project_dir；默认从 scene JSON 推导）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    scene_path = Path(args.scene)
    if not scene_path.is_absolute():
        scene_path = project / args.scene
    if not scene_path.is_file():
        die(f"Scene JSON 不存在: {scene_path}")

    scene = json.loads(scene_path.read_text(encoding="utf-8"))
    clips = scene.get("clips") or []
    if not clips:
        die("Scene JSON 无 clips")

    # 输出名：--output 优先；否则用 scene JSON 的 stem（如 scene-01.json → scene-01.mp4）
    if args.output:
        out_name = args.output
    else:
        out_name = f"{scene_path.stem}.mp4"
    out_path = project / out_name

    work_dir = project / "artifacts" / "scenes" / scene_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. 调 clip-trim 切各视频片段
    print(f"[plan] 共 {len(clips)} 个片段")
    clip_paths: list[Path] = []
    for i, clip in enumerate(clips, 1):
        src = Path(clip["source"])
        if not src.is_absolute():
            src = project / clip["source"]
        if not src.is_file():
            die(f"片段 {i} 素材不存在: {src}")

        clip_dst = work_dir / f"clip-{i:02d}.mp4"
        cmd = [
            sys.executable, str(SCRIPT_DIR / "clip-trim.py"),
            "--input", str(src),
            "--output", str(clip_dst),
        ]
        if clip.get("start") is not None:
            cmd.extend(["--start", str(clip["start"])])
        if clip.get("end") is not None:
            cmd.extend(["--end", str(clip["end"])])
        if clip.get("speed") is not None and clip["speed"] != 1.0:
            cmd.extend(["--speed", str(clip["speed"])])
            if clip.get("sync_audio"):
                cmd.append("--sync-audio")
        print(f"[clip] 片段 {i}: {src.name}")
        run(cmd)
        clip_paths.append(clip_dst)

    # 2. 拼接各片段（走 assemble.py 做按序 concat + 音频统一 + 归一化）
    # assemble 需要目录结构：把切好的片段放进 work_dir/clips/，assemble 用 --source-dir
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    for i, clip_path in enumerate(clip_paths, 1):
        dst = clips_dir / f"clip-{i:02d}.mp4"
        if not dst.exists():
            clip_path.rename(dst)

    # assemble 用临时 project 目录结构（work_dir/clips/ 当 render/ 用）
    # 实际上 assemble 的 --source-dir 指向 clips_dir，里面是 clip-NN.mp4
    print(f"[compose] 拼接 {len(clips)} 片段")
    cmd = [
        sys.executable, str(SCRIPT_DIR / "assemble.py"),
        str(project),
        "--source-dir", str(clips_dir.relative_to(project)),
        "--output", out_name,
        "--transition", "hard",
    ]
    width = scene.get("width")
    fps = scene.get("fps")
    if width is not None and fps is not None:
        cmd.extend(["--width", str(width), "--fps", str(fps)])
    run(cmd)

    # 3. 混入旁白（narration）和对白（dialogue）——如有
    narration = scene.get("narration")
    dialogue = scene.get("dialogue")
    extra_tracks = []

    if narration:
        narr_src = Path(narration["source"])
        if not narr_src.is_absolute():
            narr_src = project / narration["source"]
        if not narr_src.is_file():
            die(f"旁白音频不存在: {narr_src}")
        # 旁白切段：start~end 秒
        narr_clip = work_dir / "narration-clip.mp3"
        narr_cmd = [
            sys.executable, str(SCRIPT_DIR / "clip-trim.py"),
            "--input", str(narr_src),
            "--output", str(narr_clip),
        ]
        if narration.get("start") is not None:
            narr_cmd.extend(["--start", str(narration["start"])])
        if narration.get("end") is not None:
            narr_cmd.extend(["--end", str(narration["end"])])
        print(f"[narration] 切旁白段 {narration.get('start', 0)}~{narration.get('end', '?')}s")
        run(narr_cmd)
        extra_tracks.append({
            "source": str(narr_clip),
            "delay": narration.get("delay", 0),
            "volume": narration.get("volume", 1.0),
        })

    if dialogue:
        dial_src = Path(dialogue["source"])
        if not dial_src.is_absolute():
            dial_src = project / dialogue["source"]
        if not dial_src.is_file():
            die(f"对白音频不存在: {dial_src}")
        extra_tracks.append({
            "source": str(dial_src),
            "delay": dialogue.get("delay", 0),
            "volume": dialogue.get("volume", 1.0),
        })

    if extra_tracks:
        # 把成片 + 旁白 + 对白混音，输出到临时文件再覆盖
        mixed = work_dir / "scene-mixed.mp4"
        mix_cmd = [sys.executable, str(SCRIPT_DIR / "audio-mix.py")]
        mix_cmd.extend(["--track", str(out_path), "--delay", "0", "--volume", "1.0"])
        for tr in extra_tracks:
            mix_cmd.extend(["--track", tr["source"]])
            mix_cmd.extend(["--delay", str(tr["delay"])])
            mix_cmd.extend(["--volume", str(tr["volume"])])
        mix_cmd.extend(["--output", str(mixed)])
        print(f"[mix] 混入旁白/对白")
        run(mix_cmd)
        mixed.replace(out_path)

    print(f"[done] Scene 片段已落：{out_path}")
    print(f"  - {len(clips)} 个片段")
    if narration:
        print(f"  - 旁白已混入")
    if dialogue:
        print(f"  - 对白已混入")


if __name__ == "__main__":
    main()
