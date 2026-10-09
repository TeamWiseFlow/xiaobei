#!/usr/bin/env python3
"""Stage 5 — character-register：角色三视图 + static/dynamic features 拆分。

Usage:
  python3 scripts/character-register.py <project_dir>

入：project_dir/storyboard/shot_decompose.json（Stage 4）+ script.md（Stage 1 出场人物）
出：project_dir/characters/registry.json（每个角色 static/dynamic features）
    + project_dir/characters/<char-id>/front.png + side.png + back.png（调 awk-img-gen）

三视图：front / side / back 三张同角色不同视角的静照，保证后续镜头里角色机位一致性。
static features：跨镜不变的（发色/衣着/体型/年龄感）
dynamic features：随镜变化的（表情/姿势/光影）

best_image_selector 退化模式：不引入 CLIP，走 agent 看 contact sheet 人核。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _collage_stages import run_if_collage
from _deck_stages import run_if_deck


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5 character-register")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 5):
        return
    if run_if_deck(project, 5):
        return
    decompose_path = project / "storyboard" / "shot_decompose.json"
    script_path = project / "script" / "script.md"
    if not decompose_path.is_file() or not script_path.is_file():
        die("前置缺失: shot_decompose.json 或 script.md 不存在")

    registry_path = project / "characters" / "registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if registry_path.is_file():
        existing = json.loads(registry_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] registry.json 已存在，沿用：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    stub = {
        "stage": 5,
        "characters": [],
        "instruction": (
            "agent 据 script.md 出场人物 + shot_decompose.json 列出所有出场角色，每个角色填 schema 并调 "
            "awk-img-gen 生成 front/side/back 三视图落 characters/<char-id>/。"
            "static features 跨镜不变（发色/衣着/体型/年龄感），dynamic features 随镜变（表情/姿势/光影）。"
            "best_image_selector 走 agent 看 contact sheet 人核，不引 CLIP。"
        ),
        "character_schema": {
            "id": "char-1",
            "name": "（角色名/称呼）",
            "static_features": {
                "hair": "（如'黑色短发'）",
                "clothing": "（如'白T恤+牛仔裤'）",
                "build": "（如'瘦高青年'）",
                "age_apparent": "（如'25岁左右'）",
            },
            "dynamic_features": "（随镜变化的，每镜在 shot_decompose 里填）",
            "views": {
                "front": "characters/char-1/front.png",
                "side": "characters/char-1/front.png",
                "back": "characters/char-1/back.png",
            },
            "view_prompt_template": "（agent 填，三视图共用的人物描述 prompt，仅视角词不同）",
        },
    }
    registry_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] registry.json 模板已落：{registry_path}")
    print(f"[next] agent 填角色 schema + 调 awk-img-gen 生成三视图 → GATE A 文本闸门")


if __name__ == "__main__":
    main()
