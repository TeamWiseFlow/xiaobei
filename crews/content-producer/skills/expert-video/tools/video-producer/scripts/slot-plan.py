#!/usr/bin/env python3
"""Stage 6 — slot-plan：素材 slot 规划。

Usage:
  python3 scripts/slot-plan.py <project_dir>

入：project_dir/storyboard/shot_decompose.json（Stage 4）
出：project_dir/slots/slot-plan.json（每镜对应 slot：template + hero slot + tone→slot 数）

template：slot 模板（如"主角家中—晨光—白T青年"）
hero slot：本场的关键镜头素材，必拍（AIGC 生成或重点搜）
tone→slot 数：档调性的 slot 数档（中文需实测重标定，首版沿用英文相对档位）

落档阈值（首版默认，中文实测后修正）：
- 挽歌 elegy：4.0s/约 15 镜
- 庄重 solemn：3.5s/约 17 镜
- 梦幻 dreamy：3.0s/约 20 镜
- 诙谐 humorous：2.0s/约 30 镜
- 紧迫 urgent：1.2s/约 50 镜
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


TONE_SLOT_TABLE = {
    "elegy": {"shot_duration": 4.0, "slots_per_min": 15},
    "solemn": {"shot_duration": 3.5, "slots_per_min": 17},
    "dreamy": {"shot_duration": 3.0, "slots_per_min": 20},
    "humorous": {"shot_duration": 2.0, "slots_per_min": 30},
    "urgent": {"shot_duration": 1.2, "slots_per_min": 50},
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 6 slot-plan")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--tone", default=None, choices=sorted(TONE_SLOT_TABLE), help="调性，不传走 narrative 默认")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 6):
        return
    if run_if_deck(project, 6):
        return
    decompose_path = project / "storyboard" / "shot_decompose.json"
    if not decompose_path.is_file():
        die(f"前置缺失: shot_decompose.json 不存在")

    plan_path = project / "slots" / "slot-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if plan_path.is_file():
        existing = json.loads(plan_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] slot-plan.json 已存在，沿用：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    tone = args.tone or "solemn"  # 默认庄重；agent 据 Brief 创意/调性传 --tone
    tone_cfg = TONE_SLOT_TABLE[tone]

    stub = {
        "stage": 6,
        "tone": tone,
        "tone_config": tone_cfg,
        "slots": [],
        "instruction": (
            "agent 据 shot_decompose.json 每镜定一个 slot：template（场景描述模板，多镜复用同 template）"
            "+ description（人核语义描述，给素材源搜）+ query（搜索关键词，给 pexels/pixabay API）"
            "+ tone_params.slot_duration + 是否 hero slot。"
            "description 与 query 分职：description 给 agent 人核素材匹配度用，query 给 API 搜索用。"
            "hero slot = 本场关键镜头，必拍或重点搜；非 hero slot 可降级为静图。"
        ),
        "slot_schema": {
            "slot_id": "slot-01",
            "shot_id": "shot-01",
            "template": "（场景模板，如'主角家中—晨光—白T青年'，多镜复用同 template）",
            "description": "（语义描述，给 agent 人核用，含机位/主体/动作/氛围）",
            "query": "（API 搜索关键词，英文给 pexels/pixabay）",
            "tone_params": {"slot_duration": tone_cfg["shot_duration"]},
            "hero_slot": False,
            "fallback": "静图（awk-img-gen）",
        },
    }
    plan_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] slot-plan.json 模板已落：{plan_path}")
    print(f"[next] agent 填 slot schema → 跑 asset-resolve（Stage 7）")


if __name__ == "__main__":
    main()
