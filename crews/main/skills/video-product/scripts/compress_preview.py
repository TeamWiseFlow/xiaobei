#!/usr/bin/env python3
"""Compress a video segment to ≤16MB for chat confirmation.

人物故事模式 A.1 中，每段视频生成后要发给用户确认。聊天发送文件有 16MB 上限，
超过则用本脚本压到 16MB 以内。压缩产物**仅用于给用户确认**，不参与最终合成：
- 输出路径必须放在 previews/（或 tmp/）下，assemble.py 只扫描 artifacts/，自然排除；
- 命名带 _preview 后缀，进一步避免与正式片段混淆。

行为：
  1. 输入 ≤ target MB → 直接拷贝到 --output，exit 0（打印 [ok] under-limit）
  2. 输入 > target MB → 逐级提高压缩力度（CRF↑ + 必要时降分辨率）直到 ≤ target
     - 成功 exit 0，打印 [ok] compressed <size>
     - 全部档位仍超 → exit 1，打印 [fail]（调用方应改发原路径让用户本机查看）

Stdlib + ffmpeg/ffprobe only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TARGET_MB_DEFAULT = 16
SAFE_OUTPUT_DIRS = (Path("previews"), Path("tmp"), Path("output_videos"))

# Compression ladder: (crf, scale_factor). Walked high-quality → aggressive.
# scale None = keep original resolution.
LADDER = [
    (23, None),
    (26, None),
    (28, None),
    (30, 0.85),
    (32, 0.75),
    (34, 0.60),
    (36, 0.50),
]


def die(message: str, code: int = 1) -> None:
    print(f"[error] {message}", file=sys.stderr)
    sys.exit(code)


def log(message: str) -> None:
    print(f"[info] {message}")


def ensure_safe_output(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        die(f"--output must be relative to the workspace: {raw_path}")
    if ".." in path.parts:
        die(f"--output must not contain '..': {raw_path}")
    root = Path.cwd().resolve()
    resolved = (root / path).resolve()
    if not any(
        resolved.is_relative_to((root / base).resolve()) for base in SAFE_OUTPUT_DIRS
    ):
        die(
            f"--output must be under one of: {', '.join(str(d) for d in SAFE_OUTPUT_DIRS)} "
            f"(previews/ recommended — assemble.py 不扫描此处)"
        )
    return resolved


def file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def probe_dimensions(path: Path) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_entries", "stream=width,height", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        info = json.loads(result.stdout)
        st = (info.get("streams") or [{}])[0]
        return int(st.get("width", 0)), int(st.get("height", 0))
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError, KeyError):
        return 0, 0


def ffmpeg_compress(src: Path, dest: Path, crf: int, scale: float | None) -> bool:
    """Encode src → dest with given crf/scale. Returns True on success."""
    vf = []
    if scale is not None:
        w, h = probe_dimensions(src)
        if w > 0 and h > 0:
            # scale keeping aspect, force even dims
            vf.append(f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2")
    vf.append("format=yuv420p")
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", ",".join(vf),
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(dest),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        log(f"crf={crf} scale={scale}: timed out")
        return False
    if result.returncode != 0 or not dest.is_file():
        log(f"crf={crf} scale={scale}: ffmpeg failed")
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把视频压到 ≤16MB 用于聊天确认（产物仅用于确认，不参与合成）。"
    )
    parser.add_argument("input", help="输入视频路径（相对工作区）")
    parser.add_argument("--output", required=True,
                        help="输出预览路径（相对工作区，须在 previews/tmp/output_videos 下）")
    parser.add_argument("--target-mb", type=float, default=TARGET_MB_DEFAULT, dest="target_mb",
                        help="目标上限 MB，默认 16")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.is_file():
        die(f"input video not found: {src}")
    dest = ensure_safe_output(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)

    src_mb = file_size_mb(src)
    target = args.target_mb

    if src_mb <= target:
        shutil.copyfile(src, dest)
        log(f"under-limit: input {src_mb:.2f}MB ≤ {target}MB, copied → {dest}")
        print(f"[ok] under-limit {dest} {file_size_mb(dest):.2f}MB")
        return

    log(f"input {src_mb:.2f}MB > {target}MB, compressing...")
    for crf, scale in LADDER:
        if not ffmpeg_compress(src, dest, crf, scale):
            continue
        out_mb = file_size_mb(dest)
        if out_mb <= target:
            log(f"crf={crf} scale={scale} → {out_mb:.2f}MB ✓")
            print(f"[ok] compressed {dest} {out_mb:.2f}MB")
            return
        log(f"crf={crf} scale={scale} → {out_mb:.2f}MB still over")
        dest.unlink(missing_ok=True)

    die(
        f"全部压缩档位仍超过 {target}MB（输入 {src_mb:.2f}MB）。"
        f"请改发原路径让用户本机查看：{src}"
    )


if __name__ == "__main__":
    main()
