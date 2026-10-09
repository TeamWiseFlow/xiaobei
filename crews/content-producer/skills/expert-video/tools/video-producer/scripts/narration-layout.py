#!/usr/bin/env python3
"""narration-layout — 逐句旁白排布：对齐镜头起点 + 防重叠守卫 + 越界断言 + SRT + 可选混音。

原子工具，不写死 Workflow。适用于「逐句 TTS 出独立 mp3」的生产模式
（reversal-ad / 解说类项目常用）；整段旁白一条 narration.mp3 的时间戳对齐
仍归 narration-align，两者互补、不互替。

Usage:
  python3 scripts/narration-layout.py <project_dir> --plan audio/narration_plan.json \
      --srt audio/subtitles.srt --mix audio/mix.wav

plan.json 结构（路径均相对 project_dir，也接受绝对路径）：
  {
    "shots": [                                  # 有序镜头清单（实测 clip 时长累积出镜头起点）
      {"id": "s01", "clip": "render/v4/s01/clip.mp4"},
      ...
    ],
    "narrations": [                             # 逐句清单，按播出顺序
      {"file": "audio/narr/s01.mp3", "text": "注意看，……",
       "shot_id": "s01", "lead_in": 0.25},     # 对齐镜头起点 + lead_in（默认 0.25s）
      {"file": "audio/narr/x.mp3", "text": "……", "abs_start": 12.5}
                                               # 或显式绝对起点（不参与守卫推移，冲突即报错）
    ],
    "bgm": {"file": "...", "volume": 0.22, "fade_in": 0.8, "fade_out": 2.2},  # 可选
    "guards": {"min_gap": 0.15, "tail_margin": 0.1,
               "shot_tolerance": 0.0, "shot_overflow": "error"},              # 可选
    "srt_style": {"font_size": 17,     # 未指定 font_name 时按当前系统选择中文字体
                  "margin_v": 48, "outline": 1.2, "shadow": 0.5, "spacing": 0.5}  # 可选
  }

守卫语义（违反即非零退出并打印全部越界明细，不静默放行）：
  1. 防重叠：shot_id 模式下句起点 = max(镜头起点+lead_in, 前句结束+min_gap)，自动后推；
     abs_start 模式下与前句间隔不足 min_gap 直接报错（显式时间不做主）。
  2. 逐句越界：句尾不得越过对应镜头尾 + shot_tolerance；确需跨镜（桥句）时该句加
     "allow_spill": true，或 guards.shot_overflow 改 "warn"/"off"。
  3. 末句越界：末句结束不得晚于成片总长 - tail_margin。

拼接约束：本工具产物按 hard 直拼（assemble 默认转场）的时间轴排布；fade/dissolve/xfade
类转场每处吃 0.5s 重叠，画面时间轴整体前移而排布/SRT/混音不感知——用了本工具就
`assemble` 不传 --transition（或显式 hard）。

出：
  audio/abs_starts.json   排布结果（镜头起点表 + 每句绝对起止 + force_style），排布即落盘
  --srt 指定路径           SRT（cue 尾提前 0.03s 防闪切），样式参数化进 abs_starts.json
  --mix 指定路径           多轨混音（内部复用 audio-mix 子命令：N 路旁白 adelay + BGM fade）

checkpoint：abs_starts.json / srt / mix 已存在则各自跳过，改了 plan.json 必须 --force 重排。
退出码：0 成功 / 1 参数错或守卫断言失败。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deck-render' / 'scripts'))
from font_policy import font_family

DEFAULT_LEAD_IN = 0.25
DEFAULT_MIN_GAP = 0.15
DEFAULT_TAIL_MARGIN = 0.1
DEFAULT_SHOT_TOLERANCE = 0.0
SRT_END_TRIM = 0.03          # cue 尾提前量，防字幕闪切（v4 已验证）
DEFAULT_SRT_STYLE = {
    "font_name": font_family(),
    "font_size": 17,
    "primary_colour": "&H00FFFFFF",
    "outline_colour": "&HA0000000",
    "border_style": 1,
    "outline": 1.2,
    "shadow": 0.5,
    "margin_v": 48,
    "spacing": 0.5,
}


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"[cmd] {cmd[0]} ... ({len(cmd)} args)")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        die(f"命令失败 (rc={p.returncode}): {p.stderr[:500] or p.stdout[:500]}")
    return p


def probe_duration(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        return 0.0
    try:
        return float(json.loads(p.stdout).get("format", {}).get("duration", 0) or 0)
    except (ValueError, json.JSONDecodeError):
        return 0.0


def resolve(project: Path, raw: str) -> Path:
    """plan 里的路径：绝对路径原样，相对路径挂到 project_dir。"""
    p = Path(raw)
    return p if p.is_absolute() else project / p


def srt_ts(seconds: float) -> str:
    """秒 → SRT 时间戳 HH:MM:SS,mmm。"""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_force_style(style: dict) -> str:
    """srt_style dict → libass force_style 串（供 burn-srt --force-style 直接引用）。"""
    merged = {**DEFAULT_SRT_STYLE, **style}
    return (
        f"FontName={merged['font_name']},FontSize={merged['font_size']},"
        f"PrimaryColour={merged['primary_colour']},OutlineColour={merged['outline_colour']},"
        f"BorderStyle={merged['border_style']},Outline={merged['outline']},"
        f"Shadow={merged['shadow']},MarginV={merged['margin_v']},Spacing={merged['spacing']}"
    )


def load_plan(project: Path, plan_path: Path) -> dict:
    if not plan_path.is_file():
        die(f"plan 不存在: {plan_path}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"plan 不是合法 JSON: {plan_path}（{e}）")
    if not isinstance(plan.get("shots"), list) or not plan["shots"]:
        die("plan.shots 必须是非空有序镜头清单 [{id, clip}, ...]")
    if not isinstance(plan.get("narrations"), list) or not plan["narrations"]:
        die("plan.narrations 必须是非空逐句清单 [{file, text, shot_id|abs_start}, ...]")
    return plan


def probe_shots(project: Path, raw_shots: list) -> tuple[list[dict], float]:
    """实测各镜 clip 时长，累积镜头起点。返回 (shots, total)。"""
    shots: list[dict] = []
    t = 0.0
    for entry in raw_shots:
        if not isinstance(entry, dict) or "id" not in entry or "clip" not in entry:
            die(f"plan.shots 条目须为 {{id, clip}}: {entry!r}")
        clip = resolve(project, entry["clip"])
        if not clip.is_file():
            die(f"镜头 clip 不存在: {clip}（shot {entry['id']}）")
        dur = probe_duration(clip)
        if dur <= 0:
            die(f"镜头 clip 时长探测失败: {clip}（shot {entry['id']}）")
        shots.append({"id": str(entry["id"]), "clip": str(clip),
                      "start": round(t, 3), "end": round(t + dur, 3), "dur": round(dur, 3)})
        t += dur
    return shots, round(t, 3)


def layout(project: Path, plan: dict, shots: list[dict], total: float) -> tuple[list[dict], list[str], list[str]]:
    """逐句排布 + 守卫。返回 (排布结果, errors, warnings)。"""
    guards = plan.get("guards") or {}
    min_gap = float(guards.get("min_gap", DEFAULT_MIN_GAP))
    tail_margin = float(guards.get("tail_margin", DEFAULT_TAIL_MARGIN))
    shot_tolerance = float(guards.get("shot_tolerance", DEFAULT_SHOT_TOLERANCE))
    shot_overflow = guards.get("shot_overflow", "error")
    if shot_overflow not in ("error", "warn", "off"):
        die(f"guards.shot_overflow 只能是 error/warn/off，收到 {shot_overflow!r}")
    shot_by_id = {s["id"]: s for s in shots}

    errors: list[str] = []
    warnings: list[str] = []
    entries: list[dict] = []
    prev_end: float | None = None   # 首句没有前句，min_gap 守卫不适用（None 哨兵）
    for idx, item in enumerate(plan["narrations"], 1):
        if not isinstance(item, dict) or "file" not in item:
            die(f"plan.narrations[{idx}] 缺 file 字段: {item!r}")
        narr = resolve(project, item["file"])
        if not narr.is_file():
            die(f"旁白文件不存在: {narr}（第 {idx} 句）")
        dur = probe_duration(narr)
        if dur <= 0:
            die(f"旁白时长探测失败: {narr}（第 {idx} 句）")

        has_shot = "shot_id" in item
        has_abs = "abs_start" in item
        if has_shot == has_abs:
            die(f"第 {idx} 句必须且只能给 shot_id 或 abs_start 之一: {item!r}")

        if has_shot:
            shot = shot_by_id.get(str(item["shot_id"]))
            if shot is None:
                die(f"第 {idx} 句 shot_id 不在 shots 清单: {item['shot_id']}")
            lead_in = float(item.get("lead_in", DEFAULT_LEAD_IN))
            if lead_in < 0:
                die(f"第 {idx} 句 lead_in 必须 >= 0: {lead_in}")
            start = shot["start"] + lead_in
            if prev_end is not None:
                floor = prev_end + min_gap
                if start < floor:
                    start = floor      # 防重叠守卫：自动后推
        else:
            shot = None
            start = float(item["abs_start"])
            if start < 0:
                die(f"第 {idx} 句 abs_start 必须 >= 0: {start}")
            if prev_end is not None and start < prev_end + min_gap:
                errors.append(
                    f"第 {idx} 句 abs_start={start:.3f} 与前句结束 {prev_end:.3f} "
                    f"间隔不足 min_gap={min_gap}（abs_start 模式不自动推移）"
                )

        end = start + dur
        if shot is not None and not item.get("allow_spill", False) and shot_overflow != "off":
            over = end - (shot["end"] + shot_tolerance)
            if over > 1e-6:
                msg = (f"第 {idx} 句越过镜头 {shot['id']} 尾 {over:.3f}s"
                       f"（句尾 {end:.3f} > 镜尾 {shot['end']:.3f} + 容差 {shot_tolerance}）"
                       f"——改镜头时长 / 加 allow_spill / 调 guards.shot_overflow")
                (warnings if shot_overflow == "warn" else errors).append(msg)

        entries.append({
            "idx": idx, "file": str(narr), "text": item.get("text", ""),
            "shot_id": shot["id"] if shot else None,
            "start": round(start, 3), "end": round(end, 3), "dur": round(dur, 3),
        })
        prev_end = end

    last = entries[-1]
    if last["end"] > total - tail_margin + 1e-6:
        errors.append(
            f"末句结束 {last['end']:.3f} 越过成片尾（总长 {total:.3f} - tail_margin {tail_margin}）"
        )
    return entries, errors, warnings


def write_srt(path: Path, entries: list[dict]) -> None:
    blocks: list[str] = []
    for e in entries:
        text = e["text"]
        if not text:
            die(f"--srt 需要每句 text 字段，第 {e['idx']} 句缺失")
        cue_end = max(e["start"] + 0.05, e["end"] - SRT_END_TRIM)
        blocks.append(f"{e['idx']}\n{srt_ts(e['start'])} --> {srt_ts(cue_end)}\n{text}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")


def mix_audio(project: Path, entries: list[dict], bgm: dict | None,
              total: float, out: Path) -> None:
    """复用 audio-mix 子命令：N 路旁白 adelay + BGM volume/fade，--duration 卡总长。"""
    script = Path(__file__).resolve().with_name("audio-mix.py")
    cmd = [sys.executable, str(script)]
    for e in entries:
        cmd += ["--track", e["file"], "--delay", f"{e['start']:.3f}",
                "--volume", "1.0", "--fadein", "0", "--fadeout", "0"]
    if bgm:
        bgm_file = resolve(project, bgm["file"])
        if not bgm_file.is_file():
            die(f"bgm 文件不存在: {bgm_file}")
        cmd += ["--track", str(bgm_file), "--delay", "0",
                "--volume", str(float(bgm.get("volume", 0.2))),
                "--fadein", str(float(bgm.get("fade_in", 0))),
                "--fadeout", str(float(bgm.get("fade_out", 0)))]
    cmd += ["--output", str(out), "--duration", f"{total:.3f}"]
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="narration-layout 逐句旁白排布 + 守卫 + SRT + 可选混音")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--plan", required=True,
                        help="排布计划 JSON（相对 project_dir 或绝对路径），结构见脚本头注释")
    parser.add_argument("--srt", default=None, help="SRT 输出路径（相对 project_dir 或绝对；不传则不产 SRT）")
    parser.add_argument("--mix", default=None, help="混音输出路径（相对 project_dir 或绝对；不传则不混音）")
    parser.add_argument("--force", action="store_true", help="忽略 checkpoint 强制重排/重产")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if not project.is_dir():
        die(f"项目目录不存在: {project}")
    plan = load_plan(project, resolve(project, args.plan))

    if args.srt:
        for item in plan["narrations"]:
            if not (isinstance(item, dict) and item.get("text")):
                die(f"--srt 需要 plan.narrations 每句带 text 字段: {item!r}")

    audio_dir = project / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    abs_path = audio_dir / "abs_starts.json"

    if abs_path.is_file() and not args.force:
        print(f"[checkpoint] abs_starts.json 已存在：{abs_path}（改了 plan 要 --force 重排）")
        result = json.loads(abs_path.read_text(encoding="utf-8"))
        entries, total = result["narrations"], result["total"]
    else:
        shots, total = probe_shots(project, plan["shots"])
        entries, errors, warnings = layout(project, plan, shots, total)
        for w in warnings:
            print(f"[warn] {w}")
        if errors:
            print(f"[fail] 守卫断言失败 {len(errors)} 处，未落盘任何产物：", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        force_style = build_force_style(plan.get("srt_style") or {})
        result = {
            "total": total,
            "shots": shots,
            "narrations": entries,
            "bgm": plan.get("bgm"),
            "guards": plan.get("guards") or {},
            "force_style": force_style,
        }
        tmp = abs_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(abs_path)
        print(f"[done] 排布落盘：{abs_path}")
        print(f"  - {len(shots)} 镜 / {len(entries)} 句 / 成片总长 {total:.3f}s")
        for e in entries:
            print(f"  [{e['idx']:>2}] {e['start']:>8.3f} → {e['end']:>8.3f}  "
                  f"shot={e['shot_id'] or '-':<6} {Path(e['file']).name}")

    if args.srt:
        srt_out = resolve(project, args.srt)
        if srt_out.is_file() and not args.force:
            print(f"[checkpoint] SRT 已存在：{srt_out}")
        else:
            write_srt(srt_out, entries)
            print(f"[done] SRT 已落：{srt_out}")
            print(f"  - burn-srt 引用样式：--force-style '{result['force_style']}'")

    if args.mix:
        mix_out = resolve(project, args.mix)
        if mix_out.is_file() and not args.force:
            print(f"[checkpoint] 混音已存在：{mix_out}")
        else:
            mix_out.parent.mkdir(parents=True, exist_ok=True)
            mix_audio(project, entries, plan.get("bgm"), total, mix_out)
            print(f"[done] 混音已落：{mix_out}")

    print(f"[next] 拼接走 assemble --manifest（守卫已验帧率/时长后再合成）；"
          f"响度归一成片后仍必须走 normalize，不在本工具内联 loudnorm")


if __name__ == "__main__":
    main()
