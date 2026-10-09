#!/usr/bin/env python3
"""Stage 3 — storyboard-build：剧本 → 镜头表。

Usage:
  python3 scripts/storyboard-build.py <project_dir>

入：project_dir/script/script.md（Stage 1，self-eval 全维 ≥3）
出：project_dir/storyboard/storyboard.json（镜头表，每镜叙事目的/机位复用/位置朝向/不写不可见）

硬规则六条：
1. 每镜叙事目的明示
2. 机位复用：同场景机位复用同 ID（camera-A/camera-B...），不复用就新 ID
3. 位置朝向：人物在画面中的位置（左/中/右）与朝向（面镜头/背镜头/侧）
4. 不写不可见：分镜只写镜头能看到的，心理活动外化成动作
5. 每镜每角色最多一句对白
6. 自包含：每镜能独立渲染，不依赖邻镜上下文（AIGC 单镜生成模式）
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
    parser = argparse.ArgumentParser(description="Stage 3 storyboard-build")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 3):
        return
    if run_if_deck(project, 3):
        return
    script_path = project / "script" / "script.md"
    if not script_path.is_file():
        die(f"前置缺失: script.md 不存在")

    board_path = project / "storyboard" / "storyboard.json"
    board_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if board_path.is_file():
        existing = json.loads(board_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] storyboard.json 已存在，沿用：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    stub = {
        "stage": 3,
        "shots": [],
        "instruction": "agent 据剧本拆镜，每镜按下 schema 填。",
        "shot_schema": {
            "id": "shot-01",
            "scene": 1,
            "narrative_purpose": "建立主角日常",
            "camera_id": "camera-A",
            "camera reused_from": "（如复用，填源镜 id；不复用留空）",
            "subject_position": "中",
            "subject_facing": "面镜头",
            "characters": [{"id": "char-1", "position": "中", "facing": "面镜头", "dialog": "「（最多一句）」"}],
            "visible_action": "（只写镜头能看到的，心理外化成动作）",
            "duration": 3.0,
            "self_contained": True,
        },
    }
    board_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] storyboard.json 模板已落：{board_path}")
    print(f"[next] agent 填镜头表 → 跑 shot-decompose（Stage 4）")


if __name__ == "__main__":
    main()
