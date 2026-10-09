#!/usr/bin/env python3
"""Stage 4 — shot-decompose：每镜拆首帧静照 / 尾帧静照 / 运动描述。

Usage:
  python3 scripts/shot-decompose.py <project_dir>

入：project_dir/storyboard/storyboard.json（Stage 3）
出：project_dir/storyboard/shot_decompose.json（每镜 first_frame/last_frame 文字描述 + motion + variation_type）

variation_type 三档（定传给 aigc-video-gen 的参考图数）：
- static：首帧=尾帧，传 1 张参考图
- dynamic：首帧≠尾帧，传 2 张参考图（i2v 首尾插值）
- transition：首帧与尾帧是不同机位/场景（罕见，慎用）

运动描述禁角色名用外观特征：不写"小明走向门口"，改写"穿白T恤的青年走向门口"（AIGC 不识角色名）。
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


VALID_VARIATIONS = {"static", "dynamic", "transition"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 4 shot-decompose")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 4):
        return
    if run_if_deck(project, 4):
        return
    board_path = project / "storyboard" / "storyboard.json"
    if not board_path.is_file():
        die(f"前置缺失: storyboard.json 不存在，先跑 storyboard-build（Stage 3）")

    decompose_path = project / "storyboard" / "shot_decompose.json"
    decompose_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if decompose_path.is_file():
        existing = json.loads(decompose_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] shot_decompose.json 已存在，沿用：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    board = json.loads(board_path.read_text(encoding="utf-8"))
    shots = board.get("shots", [])

    stub = {
        "stage": 4,
        "decompose": [],
        "instruction": "agent 为 storyboard.json 每镜拆首尾帧文字描述 + 运动 + variation_type。运动描述禁角色名用外观特征。",
        "decompose_schema": {
            "shot_id": "shot-01",
            "first_frame": "（文字描述，AIGC 生成首帧静照的 prompt；不含角色名，用外观特征）",
            "last_frame": "（文字描述，AIGC 生成尾帧静照的 prompt）",
            "motion": "（运动描述，不含角色名，如'白T青年从沙发走向门口'）",
            "variation_type": "static|dynamic|transition",
            "note": "static=首尾同镜传1张参考图；dynamic=首尾异镜传2张（i2v 插值）；transition=跨机位慎用",
        },
        "valid_variation_types": sorted(VALID_VARIATIONS),
    }
    decompose_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] shot_decompose.json 模板已落：{decompose_path}")
    print(f"[next] agent 填每镜首尾帧+运动+variation_type → 跑 character-register（Stage 5）")


if __name__ == "__main__":
    main()
