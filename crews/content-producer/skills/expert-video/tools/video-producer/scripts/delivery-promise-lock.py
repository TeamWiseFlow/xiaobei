#!/usr/bin/env python3
"""Stage 9 — delivery-promise-lock：交付承诺八类锁定 + motion_ratio 预估。

Usage:
  python3 scripts/delivery-promise-lock.py <project_dir>

入：project_dir/storyboard/storyboard.json + script/brief.md
出：project_dir/slots/delivery-promise.json（八类锁 + motion_ratio 预估）

八类交付承诺（成片里须兑付，后续 motion-audit Stage 13b 查兑付）：
1. has_dialogue：有对白
2. has_narration：有旁白
3. has_bgm：有 BGM
4. has_subtitles：有字幕
5. motion_ratio：动镜头占比承诺（如"≥60% 镜头有运动"）
6. shot_count：镜数承诺
7. duration：时长承诺
8. cover_has_title：封面含标题文字

锁定后即承诺——后续 motion-audit 不兑付即违约，必返工。
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
    parser = argparse.ArgumentParser(description="Stage 9 delivery-promise-lock")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 9):
        return
    if run_if_deck(project, 9):
        return
    board_path = project / "storyboard" / "storyboard.json"
    if not board_path.is_file():
        die(f"前置缺失: storyboard.json 不存在")

    promise_path = project / "slots" / "delivery-promise.json"
    promise_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if promise_path.is_file():
        existing = json.loads(promise_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] delivery-promise.json 已存在：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    stub = {
        "stage": "9",
        "promises": {
            "has_dialogue": None,
            "has_narration": None,
            "has_bgm": None,
            "has_subtitles": None,
            "motion_ratio": {"promised_min": None, "unit": "动镜头数/总镜数"},
            "shot_count": None,
            "duration": None,
            "cover_has_title": True,
        },
        "instruction": (
            "agent 据 storyboard.json + brief.md 填八类承诺（True/False/数值）。"
            "motion_ratio.promised_min 是动镜头占比下限（如 0.6 = ≥60% 镜有运动），"
            "后续 motion-audit（Stage 13b）查成片兑付，不兑付即违约必返工。"
            "cover_has_title 默认 True——封面必含标题文字，否则 make-cover 重做。"
        ),
    }
    promise_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] delivery-promise.json 模板已落：{promise_path}")
    print(f"[next] GATE B 素材闸门：呈交 slot/素材/slide-risk/promise 摘要 → 用户批 → 跑 render-shot（Stage 10）")


if __name__ == "__main__":
    main()
