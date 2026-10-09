#!/usr/bin/env python3
"""Stage 7 — asset-resolve：按 slot 拉素材（Fast path）。

Usage:
  python3 scripts/asset-resolve.py <project_dir> [--source pexels|pixabay|both] [--no-confirm]

入：project_dir/slots/slot-plan.json（Stage 6）
出：project_dir/slots/asset-resolve.json（每 slot 选定素材 + rejected_picks 落盘）
    + 素材落 project_dir/raw_materials/

Fast path（不引入 CLIP/torch）：
1. 多源并发搜（pexels-footage + pixabay-footage）
2. 下载候选到 tmp/candidates/<slot>/
3. 生成缩略图 contact sheet
4. **agent 人核**选优胜——不引 CLIP，看 contact sheet 人择

四纪律：
- 按判断挑不按分数挑（无 CLIP 分数，凭语义人核）
- rejected_picks 落盘（每被否候选记 rejected_reason）
- 儿童 source lock（儿童题材素材源锁定，不混成人内容）
- media-use resolve 一动词（不把"选某片"写成"渲染某片"）

本脚本是脚手架：实际多源并发搜 + 缩略图拼装由 agent 调公共 pexels-footage/pixabay-footage 完成，
本脚本只落 asset-resolve.json 模板让 agent 填选优胜结果。
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
    parser = argparse.ArgumentParser(description="Stage 7 asset-resolve")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--source", default="both", choices=["pexels", "pixabay", "both"])
    parser.add_argument("--no-confirm", action="store_true", help="agent 已人核完毕，不再呈交")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 7):
        return
    if run_if_deck(project, 7):
        return
    plan_path = project / "slots" / "slot-plan.json"
    if not plan_path.is_file():
        die(f"前置缺失: slot-plan.json 不存在")

    resolve_path = project / "slots" / "asset-resolve.json"
    raw_dir = project / "raw_materials"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if resolve_path.is_file():
        existing = json.loads(resolve_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] asset-resolve.json 已存在，沿用：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    stub = {
        "stage": 7,
        "source": args.source,
        "raw_materials_dir": str(raw_dir),
        "instruction": (
            "agent 跑 Fast path：① 调公共 pexels-footage + pixabay-footage 按 slot.query 并发搜"
            "② 下载候选到 tmp/candidates/<slot>/ ③ 生成缩略图 contact sheet"
            "④ 看 contact sheet 人核选优胜（不引 CLIP）⑤ 优胜落 raw_materials/<slot>-pick.<ext>"
            "⑥ rejected_picks 落盘：每被否候选记 rejected_reason（语义不符/构图差/分辨率低/...）"
            "⑦ 儿童 source lock：儿童题材素材源锁定不混成人内容"
            "⑧ media-use resolve 一动词：选某片是选某片，不是渲染某片"
            "用户素材必先 probe（分辨率/时长/编码）落 schema，再决定取/弃。"
        ),
        "picks": [],
        "pick_schema": {
            "slot_id": "slot-01",
            "resolved": False,
            "picked_file": "raw_materials/slot-01-pick.mp4",
            "picked_source": "pexels|pixabay|user|aigc-fallback",
            "probe": {"width": None, "height": None, "duration": None, "codec": None},
            "rejected_picks": [{"file": "...", "source": "...", "rejected_reason": "..."}],
        },
    }
    resolve_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] asset-resolve.json 模板已落：{resolve_path}")
    print(f"[next] agent 跑 Fast path 填 picks → 跑 slideshow-risk（Stage 8）")


if __name__ == "__main__":
    main()
