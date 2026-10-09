#!/usr/bin/env python3
"""Optional Stage 10 i2v batch for any workflow that needs generated motion.

每个 job 字段：
  prompt         aigc-video-gen --prompt（中文声画同出描述）
  first_frame    首帧路径（纯色空场，720x1280）
  last_frame     尾帧路径（确认静帧裁到 720x1280，720P）
  output         输出 MP4 路径（相对 workspace，须在 output_videos/ 或 <platform>/outputs/ 下——aigc-video-gen 的 ensure_safe_output 要求）
  ratio          默认 9:16
  resolution     默认 720P
  duration       默认 5
  mute           true 时在落盘后复用 ffmpeg 无损去掉生成音轨，拼贴 B-roll 默认应设 true

aigc-video-gen wrapper 内部已带候选链 fallback + decisions.log 落盘，本脚本只做批量调度——
串行调（视频生成是异步轮询任务，并行调会撞平台并发限）。

Usage:
  video-producer batch-i2v --batch <project>/render/gen-jobs.json
  video-producer batch-i2v --batch <project>/render/gen-jobs.json --dry-run

Exit codes:
  0  全部 job 跑通
  1  参数错 / gen-jobs.json 不存在 / 格式错 / aigc-video-gen wrapper 不在 PATH
  2  部分 job 失败（stderr 报失败清单，已跑通的保留）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# 公共 wrapper——aigc-video-gen（PATH 化调用，不裸引用其下 scripts/gen.py）
WRAPPER = "aigc-video-gen"


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def strip_audio(output: Path) -> tuple[bool, str]:
    silent = output.with_name(output.stem + '.silent.mp4')
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                                '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(output)],
                               capture_output=True, text=True, timeout=30)
        if probe.returncode:
            return False, f'输出文件无法探测音轨：{probe.stderr[-500:]}'
        if not probe.stdout.strip():
            return True, f'checkpoint: {output} 已无音轨，跳过'
        result = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(output),
                                 '-map', '0:v:0', '-c:v', 'copy', '-an', str(silent)],
                                capture_output=True, text=True, timeout=120)
        if result.returncode or not silent.is_file() or silent.stat().st_size == 0:
            return False, f'去音轨失败：{result.stderr[-500:]}'
        silent.replace(output)
        return True, f'已无损去音轨 → {output}'
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f'去音轨失败：{exc}'
    finally:
        silent.unlink(missing_ok=True)


def run_one(job: dict, job_id: int, dry_run: bool) -> tuple[bool, str]:
    """调 aigc-video-gen wrapper i2v 跑一个 job. 返 (ok, detail)."""
    for required in ("prompt", "first_frame", "last_frame", "output"):
        if not job.get(required):
            return False, f"job {job_id} missing field: {required}"

    cmd = [
        WRAPPER,
        "--prompt", job["prompt"],
        "--image", job["first_frame"],        # i2v 首帧
        "--last-frame", job["last_frame"],    # i2v 尾帧
        "--ratio", job.get("ratio", "9:16"),
        "--resolution", job.get("resolution", "720P"),
        "--duration", str(job.get("duration", 5)),
        "--output", job["output"],
    ]

    if dry_run:
        print(f"[dry-run] job {job_id}: {' '.join(cmd[:4])} ... --output {job['output']} mute={job.get('mute', False)}")
        return True, "dry-run skipped"

    output = Path(job["output"])
    if output.is_file() and output.stat().st_size > 0:
        if job.get('mute', False):
            return strip_audio(output)
        return True, f"checkpoint: {output} 已存在，跳过"

    print(f"[info] job {job_id}: aigc-video-gen i2v → {job['output']}")
    try:
        r = subprocess.run(cmd, timeout=1200)
        if r.returncode == 0:
            if job.get('mute', False):
                return strip_audio(output)
            return True, f"ok exit 0 → {job['output']}"
        return False, f"aigc-video-gen exit {r.returncode} for job {job_id}（查 wrapper stderr + decisions.log）"
    except subprocess.TimeoutExpired:
        return False, f"aigc-video-gen timeout 1200s for job {job_id}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 10 render 批量调度——读 gen-jobs.json 逐条调公共 aigc-video-gen wrapper 走 i2v（首尾帧插值）."
    )
    parser.add_argument("--batch", required=True, help="gen-jobs.json 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印不真调")
    args = parser.parse_args()

    if not shutil.which(WRAPPER):
        die(f"wrapper 不在 PATH: {WRAPPER}（确认公共 aigc-video-gen 已通过 apply-addons.sh 软链到 ~/.openclaw/bin）")

    batch_path = Path(args.batch).resolve()
    if not batch_path.is_file():
        die(f"gen-jobs.json 不存在: {batch_path}")

    try:
        jobs = json.loads(batch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"gen-jobs.json 格式错: {e}")

    if not isinstance(jobs, list) or not jobs:
        die("gen-jobs.json 顶层必须为非空数组")
    for i, job in enumerate(jobs):
        if not isinstance(job, dict) or any(not job.get(key) for key in ("prompt", "first_frame", "last_frame", "output")):
            die(f"job {i} 缺 prompt/first_frame/last_frame/output")
        if any(not isinstance(job[key], str) for key in ("prompt", "first_frame", "last_frame", "output")):
            die(f"job {i} 的路径和 prompt 必须是字符串")
        if not isinstance(job.get('mute', False), bool):
            die(f"job {i} 的 mute 必须是布尔值")

    print(f"[info] batch: {batch_path} ({len(jobs)} jobs)")

    failures: list[tuple[int, str]] = []
    for i, job in enumerate(jobs):
        ok, detail = run_one(job, i, args.dry_run)
        print(detail)
        if not ok:
            failures.append((i, detail))

    if failures:
        print(f"\n[fail] {len(failures)} job(s) failed:", file=sys.stderr)
        for jid, det in failures:
            print(f"  job {jid}: {det}", file=sys.stderr)
        sys.exit(2)

    print(f"\n[ok] all {len(jobs)} jobs completed")


if __name__ == "__main__":
    main()
