#!/usr/bin/env python3
"""Stage 8 — slideshow-risk：六维幻灯风险打分（pre-compose 闸门）。

Usage:
  python3 scripts/slideshow-risk.py <project_dir>

入：project_dir/slots/asset-resolve.json（Stage 7，素材齐）
出：project_dir/slots/slideshow-risk.json（六维分 + verdict）

六维（每维 0–10，加权总分 ≥4.0 才许进 compose，<4.0 fail 必换素材）：
1. motion_density：动镜头占比（静图不算）
2. shot_variation：镜种多样性（特写/中景/远景/航拍/手持混）
3. transition_variation：转场多样性（硬切/淡入/dissolve/...）
4. pacing：节奏曲线（按 tone_params 检查快慢段分布）
5. coverage：素材覆盖计划镜头数（缺镜率高扣分）
6. aigc_ratio：AIGC 生成片段占比（过高扣分，需控制）

> 给静图加转场**不算**动态——motion_density 只认真有运动的镜头。
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


RISK_DIMS = [
    ("motion_density", "动镜头占比", "静图不算", 0.25),
    ("shot_variation", "镜种多样性", "特写/中景/远景/航拍/手持混", 0.15),
    ("transition_variation", "转场多样性", "硬切/淡入/dissolve", 0.10),
    ("pacing", "节奏曲线", "按 tone_params 检查快慢段分布", 0.20),
    ("coverage", "素材覆盖计划镜头数", "缺镜率高扣分", 0.20),
    ("aigc_ratio", "AIGC 占比", "过高扣分，需控制", 0.10),
]
FAIL_THRESHOLD = 4.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 8 slideshow-risk")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if run_if_collage(project, 8):
        return
    if run_if_deck(project, 8):
        return
    resolve_path = project / "slots" / "asset-resolve.json"
    if not resolve_path.is_file():
        die(f"前置缺失: asset-resolve.json 不存在")

    risk_path = project / "slots" / "slideshow-risk.json"
    risk_path.parent.mkdir(parents=True, exist_ok=True)

    # checkpoint
    if risk_path.is_file():
        existing = json.loads(risk_path.read_text(encoding="utf-8"))
        print(f"[checkpoint] slideshow-risk.json 已存在：")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return

    stub = {
        "stage": "8",
        "dims": [
            {"key": k, "name": n, "criteria": c, "weight": w, "score": None, "note": ""}
            for k, n, c, w in RISK_DIMS
        ],
        "weighted_total": None,
        "verdict": None,
        "fail_threshold": FAIL_THRESHOLD,
        "instruction": (
            "agent 据每维 criteria 给 0–10 分，note 写扣分理由。脚本算 weighted_total = Σ(score*weight)。"
            f"verdict: pass（≥{FAIL_THRESHOLD}）/fail（<{FAIL_THRESHOLD}）。fail 不许进 compose，必换素材重跑 asset-resolve。"
            "注意：给静图加转场不算动态——motion_density 只认真有运动的镜头。"
        ),
    }
    risk_path.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] slideshow-risk.json 模板已落：{risk_path}")
    print(f"[next] agent 填六维分 → fail 必返工 → pass 跑 delivery-promise-lock（Stage 9）")


if __name__ == "__main__":
    main()
