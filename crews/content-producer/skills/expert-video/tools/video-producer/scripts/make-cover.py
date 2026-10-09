#!/usr/bin/env python3
"""Stage 14 — make-cover：封面（awk-img-gen，必含封面主文案）。

Usage:
  python3 scripts/make-cover.py <project_dir> --title "..."

入：project_dir/brief.md（封面主文案）+ storyboard 关键帧
出：project_dir/cover.jpg（含封面主文案的封面图）

封面硬约束：必含封面主文案。主文案由甲方在 Brief 中给出（有平台标题时用标题，视频号用短标题）；Brief 未给时回退核心传达。awk-img-gen 不一定能把中文封面主文案烤进图，
agent 生成后用 image 工具看，确认封面主文案可见——不可见就用 ImageMagick/Pillow 烧字上去。
"""

import argparse
import json
import sys
from pathlib import Path


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 14 make-cover")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--title", default=None, help="封面主文案，不传则从 brief.md 抽")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    cover = project / "cover.jpg"
    if cover.is_file():
        print(f"[checkpoint] cover.jpg 已存在：{cover}")
        return

    title = args.title
    if not title:
        brief = project / "brief.md"
        if brief.is_file():
            content = brief.read_text(encoding="utf-8")
            # 抽第一个 # 标题作为封面主文案，或取前 50 字兜底
            for line in content.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            if not title:
                title = content[:50].strip()
        if not title:
            die("需 --title 或 brief.md 含 # 封面主文案标题行")

    stub = {
        "cover_copy": title,
        "instruction": (
            "agent 调公共 awk-img-gen 生成封面图，prompt 必含封面主文案指令。"
            "生成后用 image 工具看，确认封面主文案可见——不可见就用 ImageMagick/Pillow 烧字上去。"
            "落 cover.jpg 到项目根。"
        ),
        "cover_path": str(cover),
    }
    print(f"[plan] cover.jpg 封面主文案：{title}")
    print(f"[next] agent 调 awk-img-gen 生成 → 确认封面主文案可见 → 落 {cover}")


if __name__ == "__main__":
    main()
