#!/usr/bin/env python3
"""Stage 10 — render-shot：按 slot 渲染。

Usage:
  python3 scripts/render-shot.py <project_dir> [--shot-id shot-01] [--dry-run]

入：project_dir/storyboard/shot_decompose.json + characters/ + slots/asset-resolve.json
出：project_dir/render/shot-NN/ 下产物：
    first-frame.png（首帧静照，调 awk-img-gen 生成或素材裁切）
    last-frame.png（尾帧静照）
    gen*.mp4（aigc-video-gen i2v 产物，首尾帧插值；实际产出名不固定，gen.mp4 / gen-run-v01.mp4 / gen-v2.mp4 等，assemble 自动识别取最新）
    settings.log

按 variation_type 传参考图：
- static：传 1 张（first=last）
- dynamic：传 2 张（first + last）
- transition：跨机位慎用，传 2 张但可能跳镜
"""

import argparse
import json
import sys
from pathlib import Path

from _collage_stages import run_if_collage
from _deck_stages import run_if_deck


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 10 render-shot")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--shot-id", default=None, help="只渲某镜，不传则提示 agent 逐镜跑")
    parser.add_argument("--dry-run", action="store_true", help="只打印调用计划不真渲")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 10):
        return
    if run_if_deck(project, 10):
        return
    decompose_path = project / "storyboard" / "shot_decompose.json"
    resolve_path = project / "slots" / "asset-resolve.json"
    if not decompose_path.is_file() or not resolve_path.is_file():
        die("前置缺失: shot_decompose.json 或 asset-resolve.json 不存在")

    render_dir = project / "render"
    render_dir.mkdir(parents=True, exist_ok=True)

    decompose = json.loads(decompose_path.read_text(encoding="utf-8"))
    shots_to_render = decompose.get("decompose", [])
    if args.shot_id:
        shots_to_render = [s for s in shots_to_render if s.get("shot_id") == args.shot_id]
        if not shots_to_render:
            die(f"未在 shot_decompose.json 找到 shot_id={args.shot_id}")

    if not shots_to_render:
        print(f"[info] shot_decompose.json 暂无镜头数据，agent 先填 storyboard/shot_decompose.json")
        return

    for shot in shots_to_render:
        sid = shot.get("shot_id")
        if not sid:
            continue
        shot_dir = render_dir / sid
        shot_dir.mkdir(parents=True, exist_ok=True)

        # checkpoint：产物齐则跳
        gen_mp4 = shot_dir / "gen-run-v01.mp4"
        if gen_mp4.is_file():
            print(f"[checkpoint] {sid} 已渲：{gen_mp4}")
            continue

        variation = shot.get("variation_type", "dynamic")
        plan = {
            "shot_id": sid,
            "first_frame_prompt": shot.get("first_frame"),
            "last_frame_prompt": shot.get("last_frame"),
            "variation_type": variation,
            "reference_images": 1 if variation == "static" else 2,
            "calls": [
                "awk-img-gen → first-frame.png",
                "awk-img-gen → last-frame.png" if variation != "static" else "(skip, same as first)",
                "aigc-video-gen i2v --first first-frame.png --last last-frame.png → gen-run-v01.mp4",
            ],
        }
        (shot_dir / "settings.log").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[plan] {sid} 渲染计划已落 {shot_dir}/settings.log")
        print(f"  - variation={variation} reference_images={plan['reference_images']}")
        if args.dry_run:
            print(f"  [dry-run] 不真调")
        else:
            print(f"  [next] agent 调 awk-img-gen + aigc-video-gen 落产物到 {shot_dir}/")


if __name__ == "__main__":
    main()
