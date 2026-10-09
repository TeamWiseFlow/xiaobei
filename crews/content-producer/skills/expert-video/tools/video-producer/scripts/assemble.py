#!/usr/bin/env python3
"""assemble — 按序拼接已就绪的段 + 可选转场。

原子工具，不写死 Workflow。仅做一件事：把 render/ 下各 shot 的段按序拼成成片。
切素材/调速/混音/字幕/分辨率归一化由其他原子工具负责（clip-trim / audio-mix / timeline-compose），
agent 按 SKILL.md 场景化组合调用。

Usage:
  python3 scripts/assemble.py <project_dir> [--transition hard|fade|dissolve|xfade] [--width 1080] [--fps 30]

  # 显式段清单（手写管线/非常规命名产物，绕开目录发现约定）+ 拼接后帧率断言 + 逐段时长校验
  python3 scripts/assemble.py <project_dir> --manifest render/segments.json \
      --verify-fps 25 --expect-durations slots/shotdur.json

入：project_dir/render/ 各 shot-NN/gen*.mp4（段已就绪，assemble 不再切段）
   或 --manifest 显式有序段清单（JSON 列表，条目为路径字符串或 {"name","path"}，
   路径相对 project_dir 或绝对；name 缺省取文件 stem，stem 为 clip 时取父目录名）
出：project_dir/video.mp4（按序拼接的成片）

可选归一化：段尺寸/帧率不一时传 --width/--fps 统一（scale + pad 16:9 + sar + fps）。
段就绪约定：render/shot-NN/ 下应有 gen*.mp4 或 multi-best*.mp4，assemble 自动识别变体取最新。
守卫断言：--verify-fps N 拼接后断言 avg_frame_rate==N/1；--expect-durations plan.json
逐段实测时长 vs 计划 ±容差（--duration-tolerance，默认 0.12s），违反即非零退出打印明细。
plan.json 兼容三种形态：[{"id","dur"}...] / {"segments":[...]} / {"beats":[...]}（shotdur.json 直用）。
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import _brief

VALID_TRANSITIONS = {"hard", "fade", "dissolve", "xfade"}
XFADE_TYPES = {"fade": "fade", "dissolve": "dissolve", "xfade": "fade"}


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
    except Exception:
        return 0.0


def probe_audio(path: Path) -> tuple[int, int] | None:
    """探测音频流的 (sample_rate, channels)。无音频流返回 None。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    out = p.stdout.strip()
    if not out:
        return None
    try:
        sr, ch = out.split(",")
        return (int(sr), int(ch))
    except (ValueError, IndexError):
        return None


def has_audio(path: Path) -> bool:
    """ffprobe 探测是否有音频流。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return p.stdout.strip() == "audio"


def parse_audio_format(s: str) -> tuple[int, str]:
    """解析 --audio-format 'SR/CH'（如 '24000/mono'）→ (sample_rate, channel_layout)。"""
    try:
        sr_str, ch_str = s.split("/")
        sr = int(sr_str)
        ch = "mono" if ch_str.lower() in ("mono", "1") else "stereo"
        return (sr, ch)
    except (ValueError, IndexError):
        die(f"--audio-format 格式错误: {s}（应为 SR/CH，如 24000/mono）")


def pick_latest(shot_dir: Path, patterns: list[str]) -> Path | None:
    """自动识别 gen*.mp4 / multi-best*.mp4 变体，按版本号取最新。"""
    candidates: list[Path] = []
    for pat in patterns:
        candidates.extend(shot_dir.glob(pat))
    if not candidates:
        return None

    def version_key(p: Path) -> tuple[int, int]:
        m = re.search(r"[v-](\d+)", p.stem)
        return (1, int(m.group(1))) if m else (0, 0)

    return sorted(candidates, key=version_key)[-1]


def encode_opts(low_memory: bool) -> tuple[str, str]:
    """返回 (preset, crf)。--low-memory 时 ultrafast + crf 28（轻量、低内存机器友好）。"""
    if low_memory:
        return ("ultrafast", "28")
    return ("fast", "23")


def normalize_segment(src: Path, dst: Path, width: int, fps: int, preset: str, crf: str) -> float:
    """分辨率归一化：scale 到目标宽度 + pad 16:9 + sar 归一 + fps 统一。返回时长。"""
    height = round(width * 9 / 16)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps},format=yuv420p"
    )
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-c:a", "aac", "-b:a", "128k", "-r", str(fps),
        str(dst),
    ])
    return probe_duration(dst)


def unify_audio(
    src: Path, dst: Path, target_sr: int, target_ch: str,
    video_dur: float, preset: str, crf: str,
) -> None:
    """统一音频格式到 (target_sr, target_ch)：无音频段补静音，有音频段重采样。

    无音频 → anullsrc 生成静音 lavfi 源，合流到视频。
    有音频但规格不符 → aresample=target_sr, aformat=channel_layouts=target_ch。
    规格已符 → 直接 copy 输出（idempotent，避免无谓重编码）。

    audio_dur 用 -t 限制静音轨时长（--audio-duration 或视频时长），-shortest 对齐视频。
    """
    audio_info = probe_audio(src)
    has_vid = has_video(src)
    actual_dur = video_dur if video_dur > 0 else probe_duration(src)

    # 规格已符 → 直接 copy（idempotent）
    if audio_info is not None:
        cur_sr, cur_ch = audio_info
        target_ch_n = 1 if target_ch == "mono" else 2
        if cur_sr == target_sr and cur_ch == target_ch_n:
            run(["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(dst)])
            return

    if audio_info is None:
        # 无音频 → 补静音
        layout = target_ch
        src_inputs = ["-i", str(src)]
        silent_inputs = [
            "-f", "lavfi", "-t", f"{actual_dur:.3f}",
            "-i", f"anullsrc=channel_layout={layout}:sample_rate={target_sr}",
        ]
        af = None
        map_args = ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        # 有音频但规格不符 → 重采样
        src_inputs = ["-i", str(src)]
        silent_inputs = []
        af = f"aresample={target_sr},aformat=channel_layouts={target_ch}"
        map_args = ["-map", "0:v:0", "-map", "0:a:0"]

    cmd = ["ffmpeg", "-y"]
    cmd.extend(src_inputs)
    cmd.extend(silent_inputs)
    cmd.extend(map_args)
    if has_vid:
        cmd.extend(["-c:v", "libx264", "-preset", preset, "-crf", crf])
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    if af:
        cmd.extend(["-af", af])
    cmd.extend(["-shortest", str(dst)])
    run(cmd)


def has_video(path: Path) -> bool:
    """用 ffprobe 看是否有视频流。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return p.stdout.strip() == "video"


def probe_video(path: Path) -> tuple[int, int, int] | None:
    """探测视频流的 (width, height, fps)。无视频流返回 None。

    fps 取 avg_frame_rate，转为整数（常见 24/25/30）。
    """
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    out = p.stdout.strip()
    if not out:
        return None
    try:
        w, h, fr = out.split(",")
        # avg_frame_rate 形如 "30/1" 或 "30000/1001"
        num, den = fr.split("/")
        fps_num = int(num)
        fps_den = int(den) if int(den) != 0 else 1
        fps = fps_num // fps_den if fps_num % fps_den == 0 else round(fps_num / fps_den)
        return (int(w), int(h), fps)
    except (ValueError, IndexError, ZeroDivisionError):
        return None


def probe_frame_rate(path: Path) -> str | None:
    """探测视频流 avg_frame_rate 原始串（如 "25/1"、"30000/1001"）。无视频流返回 None。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    out = p.stdout.strip()
    return out or None


def load_manifest(project: Path, manifest_path: Path) -> list[tuple[str, Path]]:
    """显式有序段清单：条目为路径字符串或 {"name","path"}；相对路径挂 project_dir。"""
    if not manifest_path.is_file():
        die(f"manifest 不存在: {manifest_path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"manifest 不是合法 JSON: {manifest_path}（{e}）")
    if not isinstance(raw, list) or not raw:
        die("manifest 必须是非空 JSON 列表（路径字符串或 {name, path} 对象）")
    segments: list[tuple[str, Path]] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            name, path = None, entry
        elif isinstance(entry, dict) and "path" in entry:
            name, path = entry.get("name"), entry["path"]
        else:
            die(f"manifest[{i}] 条目须为路径字符串或 {{name, path}}: {entry!r}")
        p = Path(path)
        p = p if p.is_absolute() else project / p
        if not p.is_file():
            die(f"manifest[{i}] 段文件不存在: {p}")
        if not name:
            name = p.parent.name if p.stem == "clip" else p.stem
        segments.append((str(name), p))
    return segments


def load_duration_plan(plan_path: Path) -> dict[str, float]:
    """时长计划：兼容 [{"id","dur"}...] / {"segments":[...]} / {"beats":[...]}。"""
    if not plan_path.is_file():
        die(f"时长计划不存在: {plan_path}")
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"时长计划不是合法 JSON: {plan_path}（{e}）")
    if isinstance(raw, dict):
        raw = raw.get("segments") or raw.get("beats")
        if not isinstance(raw, list):
            die("时长计划 dict 形态须含 segments 或 beats 列表")
    if not isinstance(raw, list) or not raw:
        die("时长计划必须是非空列表 [{id, dur}, ...]")
    plan: dict[str, float] = {}
    for entry in raw:
        if not isinstance(entry, dict) or "id" not in entry or "dur" not in entry:
            die(f"时长计划条目须含 id 与 dur: {entry!r}")
        plan[str(entry["id"])] = float(entry["dur"])
    return plan


def check_expect_durations(segments: list[tuple[str, Path]], plan: dict[str, float],
                           tolerance: float) -> None:
    """逐段实测时长 vs 计划 ± 容差。收集全部违例后统一退出，不只报第一处。"""
    violations: list[str] = []
    checked = 0
    for name, path in segments:
        if name not in plan:
            print(f"[warn] 段 {name} 不在时长计划中，跳过校验")
            continue
        actual = probe_duration(path)
        expect = plan[name]
        checked += 1
        if abs(actual - expect) > tolerance:
            violations.append(
                f"{name}: 实测 {actual:.3f}s vs 计划 {expect:.3f}s（偏差 {actual - expect:+.3f}s > ±{tolerance}s）"
            )
    unused = set(plan) - {name for name, _ in segments}
    for name in sorted(unused):
        print(f"[warn] 时长计划里的 {name} 没有对应段（计划过期？）")
    if violations:
        print(f"[fail] 逐段时长校验失败 {len(violations)} 处：", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        sys.exit(1)
    print(f"[guard] 逐段时长校验通过：{checked} 段全部在 ±{tolerance}s 内")


def verify_output_fps(video_out: Path, expect_fps: int) -> None:
    """拼接后帧率断言：avg_frame_rate 必须等于 expect_fps/1。"""
    afr = probe_frame_rate(video_out)
    if afr is None:
        die(f"成片无视频流，无法验帧率: {video_out}")
    want = f"{expect_fps}/1"
    if afr != want:
        die(f"成片帧率断言失败: avg_frame_rate={afr}，期望 {want}（{video_out}）")
    print(f"[guard] 帧率断言通过：avg_frame_rate={afr}")


def concat_hard(segments: list[tuple[str, Path]], out: Path) -> None:
    """hard 转场：concat demuxer 直拼。concat_list.txt 里 file 行用绝对路径，避免 cwd 解析歧义。"""
    list_file = out.parent / "concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{seg.resolve()}'" for _, seg in segments),
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", str(out),
    ])
    list_file.unlink(missing_ok=True)


def concat_xfade(segments: list[tuple[str, Path, float]], out: Path, transition: str, preset: str, crf: str) -> None:
    """fade/dissolve/xfade 转场：链式 xfade。过渡时长 0.5s，不足 1s 的段硬切。"""
    if len(segments) == 1:
        shutil.copy2(segments[0][1], out)
        return

    xfade_type = XFADE_TYPES.get(transition, "fade")
    transition_dur = 0.5

    inputs: list[str] = []
    filter_parts: list[str] = []
    prev_label = "[0:v]"
    accum_dur = 0.0
    for i, (_, seg, dur) in enumerate(segments):
        inputs.extend(["-i", str(seg)])
        if i == 0:
            accum_dur = dur
            continue
        offset = max(0, accum_dur - transition_dur)
        cur_label = f"[v{i}]"
        filter_parts.append(
            f"{prev_label}[{i}:v]xfade=transition={xfade_type}:duration={transition_dur}:offset={offset:.3f}{cur_label}"
        )
        prev_label = cur_label
        accum_dur += dur - transition_dur

    # normalize=0 禁用 amix 自动除以轨道数，与 audio-mix.py 保持一致，避免音量稀释
    amix_parts = [f"[{i}:a]" for i in range(len(segments))]
    amix_parts.append(f"amix=inputs={len(segments)}:duration=longest:dropout_transition=0:normalize=0[aout]")
    filter_parts.append("".join(amix_parts))

    filter_complex = ";".join(filter_parts)
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", prev_label, "-map", "[aout]",
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-c:a", "aac", "-b:a", "128k", str(out),
    ])
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 12 assemble 按序拼接")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--source-dir", default=None, help="段目录（默认 render/；timeline-compose 调时传 artifacts/timeline/）")
    parser.add_argument("--output", default="video.mp4", help="输出名（相对 project_dir，默认 video.mp4）")
    parser.add_argument("--transition", default="hard", choices=sorted(VALID_TRANSITIONS))
    parser.add_argument("--width", type=int, default=None, help="归一化目标宽度（不传则不归一化，直 concat）")
    parser.add_argument("--fps", type=int, default=None, help="归一化帧率（不传则不归一化）")
    parser.add_argument("--low-memory", action="store_true", help="低内存机器：用 ultrafast preset + crf 28（默认 fast/crf 23）")
    parser.add_argument("--preview-duration", type=float, default=None, help="额外输出前 N 秒预览到 <output-stem>-preview.mp4，用于试听")
    parser.add_argument("--audio-format", default="24000/mono",
                        help="concat 前统一音频格式（采样率/声道，默认 24000/mono，与 awk-tts 对齐）")
    parser.add_argument("--audio-duration", type=float, default=None,
                        help="静音轨时长（秒，默认取视频时长对齐）")
    parser.add_argument("--manifest", default=None,
                        help="显式有序段清单 JSON（相对 project_dir 或绝对），绕开目录发现约定")
    parser.add_argument("--verify-fps", type=int, default=None,
                        help="拼接后断言成片 avg_frame_rate==N/1（如 25），不符非零退出")
    parser.add_argument("--expect-durations", default=None,
                        help="逐段时长计划 JSON（[{'id','dur'}] / {'segments'} / {'beats'} 三形态兼容）")
    parser.add_argument("--duration-tolerance", type=float, default=0.12,
                        help="--expect-durations 校验容差（秒，默认 0.12）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    workflow = _brief.parse_workflow(_brief.read_brief(project))
    source_dir = project / args.source_dir if args.source_dir else project / "render"
    preset, crf = encode_opts(args.low_memory)
    audio_sr, audio_ch = parse_audio_format(args.audio_format)

    # 收段：--manifest 显式清单优先；否则走目录发现约定
    # - render/：按 shot-NN/ 子目录收，每目录取最新 gen*.mp4 / multi-best*.mp4
    # - 其他目录（如 artifacts/timeline/）：直接收目录下的 clip-NN.mp4 或 *.mp4，按文件名序
    segments: list[tuple[str, Path]] = []
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest_path = manifest_path if manifest_path.is_absolute() else project / manifest_path
        segments = load_manifest(project, manifest_path)
        print(f"[manifest] 显式段清单 {len(segments)} 段：{manifest_path}")
    elif source_dir.name == "render":
        # 收段：shot-NN/ 子目录 + 命名子目录（outro/、intro/ 等）
        # shot-NN/ 走 multi-best*.mp4 / gen*.mp4 变体识别
        # 命名子目录直接收目录下的 *.mp4（按文件名序）
        shot_dirs = sorted(source_dir.glob("shot-*"))
        named_dirs = sorted(
            d for d in source_dir.iterdir()
            if d.is_dir() and not d.name.startswith("shot-") and not d.name.startswith(".")
        )
        for shot_dir in shot_dirs:
            pick = pick_latest(shot_dir, ["multi-best*.mp4", "gen*.mp4"])
            if pick and pick.is_file():
                segments.append((shot_dir.name, pick))
        for named_dir in named_dirs:
            for pick in sorted(named_dir.glob("*.mp4")):
                if pick.is_file():
                    segments.append((f"{named_dir.name}/{pick.stem}", pick))
    else:
        for pick in sorted(source_dir.glob("*.mp4")):
            if pick.is_file():
                segments.append((pick.stem, pick))

    if not segments:
        die(f"{source_dir}/ 下无任何段（render/ 走 shot-NN/gen*.mp4；其他目录走 *.mp4；"
            f"非常规命名产物走 --manifest 显式清单），先跑 render-shot 或 timeline-compose")

    # 逐段时长守卫（fail-fast：拼接前对源段校验，重跑命中 checkpoint 时同样生效）
    if args.expect_durations:
        plan_path = Path(args.expect_durations)
        plan_path = plan_path if plan_path.is_absolute() else project / plan_path
        check_expect_durations(segments, load_duration_plan(plan_path), args.duration_tolerance)

    if workflow == "collage-broll":
        if not args.manifest or len(segments) != 1 or args.transition != "hard":
            die("collage-broll Stage 12 每次用 --manifest 指定恰好一条独立成片，转场须为 hard")
        audio_plan = project / "audio" / "collage-audio-plan.json"
        if not audio_plan.is_file():
            die("collage-broll Stage 11 前置缺失: audio/collage-audio-plan.json")
        policy = json.loads(audio_plan.read_text(encoding="utf-8")).get("sound_policy")
        if policy not in {"silent", "user-voice", "approved-tts"}:
            die("collage-broll Stage 11 sound_policy 尚未核定")
        source = segments[0][1]
        if policy == "silent" and has_audio(source):
            die(f"collage-broll 无声交付承诺与源片音轨冲突: {source}")
        if policy != "silent" and not has_audio(source):
            die(f"collage-broll 有声交付缺少源片音轨: {source}")
        target = project / args.output
        if source.resolve() == target.resolve():
            die("Stage 12 输出不能覆盖输入")
        if args.width is not None or args.fps is not None or args.audio_duration is not None:
            die("collage-broll 单段直交不做规格/音轨转换；先在 Stage 10/11 处理")
        if args.verify_fps is not None:
            verify_output_fps(source, args.verify_fps)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            print(f"[checkpoint] Stage 12 collage-broll 成片已存在：{target}")
            return
        shutil.copy2(source, target)
        print(f"[done] Stage 12 collage-broll 单段成片：{target}")
        return

    video_out = project / args.output
    if video_out.is_file():
        if args.verify_fps is not None:
            verify_output_fps(video_out, args.verify_fps)
        print(f"[checkpoint] {args.output} 已存在：{video_out}")
        return

    print(f"[plan] 共 {len(segments)} 段，转场={args.transition}")

    # 音频格式统一（concat 前置）：无音频段补静音，规格不符段重采样到目标规格。
    # 默认 24000/mono（与 awk-tts 输出对齐）。输出到 artifacts/unified-audio/。
    audio_work = project / "artifacts" / "unified-audio"
    audio_work.mkdir(parents=True, exist_ok=True)
    unified: list[tuple[str, Path]] = []
    for idx, (name, src) in enumerate(segments, 1):
        # 段名可能含 /（manifest 自由命名 / 命名子目录 "outro/clip-01"），落盘名打平
        dst = audio_work / f"{idx:02d}_{name.replace('/', '-')}.mp4"
        vid_dur = args.audio_duration if args.audio_duration is not None else probe_duration(src)
        if not dst.is_file():
            print(f"[auni] {name} → {dst.name} (sr={audio_sr}, ch={audio_ch})")
            unify_audio(src, dst, audio_sr, audio_ch, vid_dur, preset, crf)
        unified.append((name, dst))
    segments = unified
    print(f"  - 音频统一：{audio_sr}Hz {audio_ch}")

    # 归一化判定：显式传 --width/--fps 用之；否则自动探测各段规格，
    # 不一时统一到最低公共规格（最小宽度、最低帧率），避免 concat demuxer 报错。
    auto_w, auto_fps = None, None
    if args.width is None or args.fps is None:
        specs = [probe_video(s) for _, s in segments]
        widths = sorted({w for w, _, _ in specs if w})
        fpses = sorted({f for _, _, f in specs if f})
        if len(widths) > 1 or len(fpses) > 1:
            auto_w = min(widths) if widths else None
            auto_fps = min(fpses) if fpses else None
            if args.width is not None:
                auto_w = args.width
            if args.fps is not None:
                auto_fps = args.fps
            print(f"[auto] 检测到段规格差异 widths={widths} fpses={fpses}，统一到 {auto_w}x{round(auto_w*9/16)}@{auto_fps}fps")
        else:
            # 规格一致，无需归一化
            pass

    # 归一化目标：显式优先，否则用自动探测结果（auto_w/auto_fps 可能仍为 None）
    norm_w = args.width if args.width is not None else auto_w
    norm_fps = args.fps if args.fps is not None else auto_fps

    if norm_w is not None and norm_fps is not None:
        work_dir = project / "artifacts" / "normalized"
        work_dir.mkdir(parents=True, exist_ok=True)
        normalized: list[tuple[str, Path, float]] = []
        for idx, (name, src) in enumerate(segments, 1):
            dst = work_dir / f"{idx:02d}_{name}.mp4"
            if not dst.is_file():
                print(f"[norm] {name} → {dst.name} (scale={norm_w}, fps={norm_fps})")
                dur = normalize_segment(src, dst, norm_w, norm_fps, preset, crf)
            else:
                dur = probe_duration(dst)
            normalized.append((name, dst, dur))

        print(f"[concat] 拼接 {len(normalized)} 段，转场={args.transition}")
        if args.transition == "hard":
            concat_hard([(n, d) for n, d, _ in normalized], video_out)
        else:
            concat_xfade(normalized, video_out, args.transition, preset, crf)
        print(f"  - 归一化：{norm_w}x{round(norm_w*9/16)}@{norm_fps}fps")
    else:
        # 不归一化，直 concat（要求各段已同尺寸/帧率；否则 ffmpeg 会失败，agent 应先归一化）
        print(f"[concat] 直拼 {len(segments)} 段（未归一化，要求段已同尺寸/帧率）")
        if args.transition == "hard":
            concat_hard(segments, video_out)
        else:
            # xfade 需要时长信息
            with_dur = [(n, s, probe_duration(s)) for n, s in segments]
            concat_xfade(with_dur, video_out, args.transition, preset, crf)

    # 拼接后帧率断言（brief 常要求的守卫：混拼不同帧率源时兜底）
    if args.verify_fps is not None:
        verify_output_fps(video_out, args.verify_fps)

    # 可选预览：截前 N 秒到 <output-stem>-preview.mp4，用于试听
    if args.preview_duration is not None:
        preview_out = video_out.with_name(f"{video_out.stem}-preview{video_out.suffix}")
        run([
            "ffmpeg", "-y", "-i", str(video_out),
            "-t", str(args.preview_duration),
            "-c", "copy", str(preview_out),
        ])
        print(f"[preview] 前 {args.preview_duration}s 已落：{preview_out}")

    print(f"[done] 成片已落：{video_out}")
    print(f"  - 段数：{len(segments)}，转场：{args.transition}")
    if args.low_memory:
        print(f"  - 低内存模式：preset={preset}, crf={crf}")


if __name__ == "__main__":
    main()
