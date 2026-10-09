"""Deck Talk 的 Stage 3–10 脚手架；保留通用阶段顺序与两道闸门。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from _brief import deck_fields, parse_workflow, read_brief


STAGES = {
    3: ("script/deck-script.md", "storyboard/storyboard.json", {
        "shots": [],
        "shot_schema": {
            "id": "shot-01", "script_section": "第 1 页/段", "narrative_purpose": "本页/段的单一命题",
            "visual_source": "slides|broll", "camera_or_layout": "幻灯版式或素材镜头构图",
            "presenter_position": "小窗位置；audio 模式填无", "voice_segment": "锁定口播原文或录音句段",
            "duration": None,
        },
        "instruction": "按页/段填写 shots；镜头表必须覆盖脚本，描述画面构图、叙事目的、口播对应关系和小窗位置。",
    }),
    4: ("storyboard/storyboard.json", "storyboard/shot_decompose.json", {
        "decompose": [],
        "decompose_schema": {
            "shot_id": "shot-01", "first_frame": "进入本页/段时的画面状态",
            "last_frame": "离开本页/段时的画面状态", "motion": "元素入场/图表演进或实拍动作",
            "render_method": "deck-render|clip-trim", "voice_start": None, "voice_end": None,
        },
        "instruction": "逐镜描述首尾视觉状态与实际运动；时间戳来自同源音频，不为版式拉伸原声。",
    }),
    5: ("storyboard/shot_decompose.json", "characters/registry.json", {
        "presenter_source": None, "presenter_media": None, "authorization": None,
        "audio_source": None, "presenter_position": None, "characters": [],
        "instruction": "登记真人/数字人素材身份、授权、同源音轨和小窗位置；audio 模式明确无人物。画面若另含需跨镜一致的生成角色，仍登记其特征与参考图。GATE A 在本阶段后。",
    }),
    6: ("characters/registry.json", "slots/slot-plan.json", {
        "slots": [],
        "slot_schema": {
            "slot_id": "slot-01", "shot_id": "shot-01", "visual_source": "slides|broll",
            "required_asset": "图表数据/图片/视频及来源", "voice_segment": "同源音频句段",
            "duration": None, "hero_slot": False, "fallback": "缺素材时的方案",
        },
        "instruction": "按 storyboard 镜头规划素材槽；保留逐页/段口播对应与素材来源。",
    }),
    7: ("slots/slot-plan.json", "slots/asset-resolve.json", {
        "picks": [],
        "pick_schema": {
            "slot_id": "slot-01", "resolved": False, "picked_file": None,
            "picked_source": "user|licensed|generated|chart-data", "authorization": None,
            "probe": {"width": None, "height": None, "duration": None, "codec": None},
            "rejected_picks": [],
        },
        "instruction": "用户素材先 probe 并记录授权；缺口才搜索/生成。幻灯数据也须记录单位、日期范围和来源。",
    }),
    8: ("slots/asset-resolve.json", "slots/slideshow-risk.json", {
        "dims": [
            {"key": key, "criteria": criterion, "score": None, "note": ""}
            for key, criterion in (
                ("readability", "每页文字/图表清晰且字幕、小窗不遮挡"),
                ("timing", "句边界翻页，页/段时长与同源音频一致"),
                ("coverage", "所有镜头的画面与素材槽均已落实"),
                ("motion", "幻灯元素真实动画或 B-roll 真实画面动作；静态停留如实登记"),
                ("source", "素材与图表数据来源、授权已核对"),
            )
        ],
        "verdict": None,
        "instruction": "Stage 8 仍做合成前风险审核；逐维记录证据和 pass/fail，不沿用通用动镜头占比阈值。fail 须返工，不能进 Stage 9。",
    }),
    9: ("slots/slideshow-risk.json", "slots/delivery-promise.json", {
        "promises": {
            "duration": None, "has_subtitles": None, "has_bgm": None,
            "cover_has_title": True, "audio_source": None, "presenter_source": None,
            "visual_source": None, "segments": [], "animation_mode": "html_scene|broll|mixed",
        },
        "instruction": "逐页/段锁定成片、音频、小窗、素材与实际动效承诺；Stage 13b 逐项核验。GATE B 在本阶段后。",
    }),
    10: ("slots/delivery-promise.json", "render/deck-render-plan.json", {
        "segments": [], "presenter_source": None, "visual_source": None,
        "base_video": None, "presenter_video": None, "audio_source": None,
        "instruction": "按承诺渲染底画面：slides 用 deck-render，broll 用 clip-trim/assemble，mixed 两者拼接；avatar 用 liveportrait 生成小窗。记录实际路径与时长，再进 Stage 11。此文件是渲染计划，不是已渲染成功的证明。",
    }),
}


def run_if_deck(project: Path, stage: int) -> bool:
    """生成 Deck Talk 对应阶段产物；非 Deck Talk 返回 False。"""
    brief = read_brief(project)
    if parse_workflow(brief) != "deck-talk":
        return False
    previous, target, content = STAGES[stage]
    source = project / previous
    if not source.is_file():
        raise SystemExit(f"[error] Stage {stage} 前置缺失: {previous}")
    output = project / target
    if output.is_file():
        print(f"[checkpoint] Stage {stage} 已有产物，沿用：{output}")
        return True
    fields = deck_fields(brief)
    stub = {"stage": stage, "workflow": "deck-talk", "source": previous, **deepcopy(content)}
    for key in ("presenter_source", "visual_source", "audio_source"):
        if key in stub:
            value = fields.get("audio" if key == "audio_source" else key)
            if value:
                stub[key] = value
    if stage == 9:
        stub["promises"]["presenter_source"] = fields.get("presenter_source")
        stub["promises"]["visual_source"] = fields.get("visual_source")
        stub["promises"]["audio_source"] = fields.get("audio")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(stub, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[done] Stage {stage} deck-talk 产物模板：{output}")
    return True
