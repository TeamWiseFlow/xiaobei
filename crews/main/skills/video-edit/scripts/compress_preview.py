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
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from video_version import master_for_review, sha256, write_new

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
    print(f"[info] {message}", file=sys.stderr)


def ensure_safe_output(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        die(f"--output must be relative to the workspace: {raw_path}")
    if ".." in path.parts:
        die(f"--output must not contain '..': {raw_path}")
    root = Path.cwd().resolve()
    resolved = (root / path).resolve()
    under_safe_dir = any(
        resolved.is_relative_to((root / base).resolve()) for base in SAFE_OUTPUT_DIRS
    )
    # 平台运营文件夹约定：允许 <platform>/outputs/...（预览落项目目录下）
    under_platform_outputs = "outputs" in path.parts[:-1]
    if not (under_safe_dir or under_platform_outputs):
        die(
            f"--output must be under one of: {', '.join(str(d) for d in SAFE_OUTPUT_DIRS)}, "
            f"or a platform ops folder <platform>/outputs/ "
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


def make_preview(src: Path, dest: Path, target: float) -> str:
    src_mb = file_size_mb(src)
    if src_mb <= target:
        shutil.copyfile(src, dest)
        log(f"under-limit: input {src_mb:.2f}MB ≤ {target}MB, copied → {dest}")
        return "under-limit"

    log(f"input {src_mb:.2f}MB > {target}MB, compressing...")
    for crf, scale in LADDER:
        if not ffmpeg_compress(src, dest, crf, scale):
            continue
        out_mb = file_size_mb(dest)
        if out_mb <= target:
            log(f"crf={crf} scale={scale} → {out_mb:.2f}MB ✓")
            return "compressed"
        log(f"crf={crf} scale={scale} → {out_mb:.2f}MB still over")
        dest.unlink(missing_ok=True)

    die(
        f"全部压缩档位仍超过 {target}MB（输入 {src_mb:.2f}MB）。"
        f"请改发原路径让用户本机查看：{src}"
    )


def publication_preview(src, dest, target, review_path):
    manifest = dest.with_suffix(dest.suffix + '.preview.json')
    master, review = master_for_review(src, review_path)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix='.preview-') as directory:
        work = Path(directory)
        snapshot = work / ('master' + src.suffix)
        staged = work / ('preview' + dest.suffix)
        shutil.copyfile(src, snapshot)
        if sha256(snapshot) != master['sha256']:
            raise ValueError('VIDEO_VERSION_MISMATCH: 母带正在变化，请重新审核')
        make_preview(snapshot, staged, target)
        preview = {'path': str(dest), 'sha256': sha256(staged)}
        os.link(staged, dest)
        try:
            write_new(manifest, {'version': 1, 'kind': 'video_preview', 'master': master,
                                 'preview': preview, 'review': review})
        except BaseException:
            dest.unlink()
            raise
    print(json.dumps({'ok': True, 'manifest': str(manifest), 'master': master, 'preview': preview},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="把视频压到 ≤16MB 用于聊天确认（产物仅用于确认，不参与合成）。")
    parser.add_argument("input", help="输入视频路径（相对工作区）")
    parser.add_argument("--output", required=True,
                        help="输出预览路径（相对工作区，须在 previews/tmp/output_videos 或 <platform>/outputs/ 下）")
    parser.add_argument("--target-mb", type=float, default=TARGET_MB_DEFAULT, dest="target_mb",
                        help="目标上限 MB，默认 16")
    parser.add_argument('--review', help='母带的 video-review 报告，生成发布用预览版本记录')
    args = parser.parse_args()
    if not math.isfinite(args.target_mb) or args.target_mb <= 0:
        parser.error('--target-mb 必须为有限正数')

    src = Path(args.input).resolve()
    if not src.is_file():
        die(f"input video not found: {src}")
    dest = ensure_safe_output(args.output)
    if src == dest:
        die('预览输出不能覆盖输入')
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if args.review is not None:
            publication_preview(src, dest, args.target_mb, args.review)
        else:
            mode = make_preview(src, dest, args.target_mb)
            print(f"[ok] {mode} {dest} {file_size_mb(dest):.2f}MB")
    except (ValueError, OSError) as exc:
        die(str(exc))


if __name__ == "__main__":
    main()
