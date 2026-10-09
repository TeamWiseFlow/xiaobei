"""Collage B-roll 的 Stage 3–10 产物脚手架；保持通用阶段顺序。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from _brief import parse_workflow, read_brief


STAGES = {
    3: ("script/script.md", "storyboard/storyboard.json", {
        "shots": [],
        "shot_schema": {
            "id": "shot-01", "script_item": "隐喻清单第 1 条", "source_line": "甲方锁定文稿",
            "narrative_purpose": "观众需要看懂的单一隐喻", "camera_id": "fixed-A",
            "visible_action": "纸片逐件进入画面", "duration": 5.0,
        },
        "instruction": "每条文稿至少一镜，明确视觉命题、固定构图、逐件进入顺序和时长；不得把文稿逐字画进视频。",
    }),
    4: ("storyboard/storyboard.json", "storyboard/shot_decompose.json", {
        "decompose": [],
        "decompose_schema": {
            "shot_id": "shot-01", "first_frame": "空色场及纸面纹理",
            "last_frame": "3–6 个纸片组装后的最终构图", "motion": "各组进入时刻、方向、卡位动作",
            "variation_type": "dynamic", "render_method": "visual-render",
        },
        "instruction": "描述首帧、末帧和每层真实运动；逐件组装可用 HyperFrames，特殊变形才用 batch-i2v。",
    }),
    5: ("storyboard/shot_decompose.json", "characters/registry.json", {
        "characters": [], "paper_subjects": [],
        "paper_subject_schema": {
            "id": "paper-01", "source_shot": "shot-01", "subject": "人物或物件剪贴",
            "static_features": "跨镜不变的半调外观/服饰/轮廓", "asset_reference": None,
            "authorization": None,
        },
        "instruction": "登记需要跨镜一致的人物/物件纸片、素材与授权；无角色时 characters 明确为空。需跨镜一致的生成角色仍制作参考视图。GATE A 在本阶段后。",
    }),
    6: ("characters/registry.json", "slots/slot-plan.json", {
        "slots": [],
        "slot_schema": {
            "slot_id": "slot-01", "shot_id": "shot-01", "element_id": "paper-01",
            "description": "独立可移动纸片的语义和构图", "asset_type": "image|shape|texture",
            "hero_slot": False, "fallback": "可复用的本地纸片或 CSS 形状",
        },
        "instruction": "逐镜规划 3–6 个独立纸片素材槽；记录角色/物件、色场、层级、入场位置和缺口，不生成整张海报。",
    }),
    7: ("slots/slot-plan.json", "slots/asset-resolve.json", {
        "picks": [],
        "pick_schema": {
            "slot_id": "slot-01", "resolved": False, "picked_file": None,
            "picked_source": "user|licensed|awk-img-gen|css", "authorization": None,
            "prompt": None, "model": None, "generated_at": None,
            "rejected_picks": [],
        },
        "instruction": "每层单独取材或生成并记录来源、授权、prompt、模型和时间；优先人核已有素材，禁止整张完成画面充当纸片。",
    }),
    8: ("slots/asset-resolve.json", "slots/slideshow-risk.json", {
        "dims": [
            {"key": key, "criteria": criterion, "score": None, "note": ""}
            for key, criterion in (
                ("metaphor", "隐喻可一眼看懂，3–6 个纸片主体清晰"),
                ("independent_layers", "纸片独立可动，不是整图淡入或 Ken Burns"),
                ("motion", "入场顺序、位置和末帧定格时间可实现"),
                ("source", "素材来源与授权、生成记录齐全"),
                ("visual_safety", "无假字、水印、越界和关键元素遮挡"),
            )
        ],
        "verdict": None,
        "instruction": "Stage 8 合成前风险审核：用素材、构图及预览证据逐维判断；fail 返工后才能锁定承诺。",
    }),
    9: ("slots/slideshow-risk.json", "slots/delivery-promise.json", {
        "promises": {
            "items": [], "default_silent": True, "duration_per_item": None,
            "frame_size": None, "fps": None, "cover_has_title": True,
            "motion": "每个纸片组独立入场，末帧稳定", "source_traceable": True,
        },
        "instruction": "逐条锁定时长、色场、3–6 个纸片、入场时刻、素材来源、声轨政策、封面和交付路径；Stage 13b 逐条核验。GATE B 在本阶段后。",
    }),
    10: ("slots/delivery-promise.json", "render/collage-render-plan.json", {
        "items": [],
        "item_schema": {
            "id": "item-01", "composition": "render/item-01/composition",
            "preview": "render/item-01/preview-v1", "output": "render/item-01/final.mp4",
            "render_method": "visual-render", "duration": 5.0,
        },
        "instruction": "GATE B 后按预览批准范围逐条渲染；常规组装用 visual-render，特殊变形用 batch-i2v。此文件是计划，不是成片证明。",
    }),
}


def run_if_collage(project: Path, stage: int) -> bool:
    if parse_workflow(read_brief(project)) != "collage-broll":
        return False
    previous, target, content = STAGES[stage]
    if not (project / previous).is_file():
        raise SystemExit(f"[error] Stage {stage} 前置缺失: {previous}")
    output = project / target
    if output.is_file():
        print(f"[checkpoint] Stage {stage} collage-broll 已有产物：{output}")
        return True
    output.parent.mkdir(parents=True, exist_ok=True)
    stub = {"stage": stage, "workflow": "collage-broll", "source": previous, **deepcopy(content)}
    output.write_text(json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] Stage {stage} collage-broll 产物模板：{output}")
    return True
