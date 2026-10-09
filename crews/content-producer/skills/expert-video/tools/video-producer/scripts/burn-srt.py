#!/usr/bin/env python3
"""Burn SRT subtitles into MP4 — optional, user-requested only.

把 SRT 字幕硬烧进视频画面（不可关、跟着成片走）。跟软字幕（.srt 外挂、
平台播放器可开关）不同——硬烧适合"平台不支持外挂字幕"或"想保证画面字
一定显示"的场景。

⚠️ 可选步骤，不是必跑。通用制作流程默认不烧字幕
（assemble.py / exportMp4 都不烧）；**仅当用户明确说"要字幕"/"烧字幕"/
"hardcode subtitles"时才跑**。

落点：合成产物（output.mp4 或 output_normalized.mp4）之后、交付前。
干湿分离：输出 `<stem>_burned.mp4`，不覆盖输入。

ffmpeg subtitles 滤镜要点：
- 用 `subtitles=filename='...'` 滤镜，需 libass 编译进去（Ubuntu 默认 ffmpeg 带）
- 字体：默认 libass 拿 fontconfig 找，中文字幕要 `force_style='FontName=...'` 强制
- 字幕样式由 SRT 内 cue style 或 force_style 覆盖，本脚本默认给一套可读样式

Usage:
  video-producer burn-srt <video.mp4> <subs.srt>
  video-producer burn-srt <video.mp4> <subs.srt> --output <out.mp4>
  video-producer burn-srt <video.mp4> <subs.srt> --font-name "<已安装中文字体>" --font-size 24

Exit codes:
  0  ok，字幕烧完
  1  参数错 / ffmpeg 缺失 / 输入不存在 / ffmpeg 不带 libass
  2  ffmpeg 渲染失败（SRT 损坏 / 字体缺 / 渲染中断）
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'deck-render' / 'scripts'))
from font_policy import font_family

# 默认字幕样式——黑白配 + 半透底框，短视频通用可读样式
DEFAULT_FONT_NAME = font_family()
DEFAULT_FONT_SIZE = 24
DEFAULT_FORCE_STYLE = (
    "FontName={font},FontSize={size},"
    "PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
    "BackColour=&H80000000&,BorderStyle=4,"
    "Outline=2,Shadow=1,Alignment=2,MarginV=40"
)


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        die(f"missing binary: {cmd[0]}")
    except subprocess.TimeoutExpired:
        die(f"timeout running: {' '.join(cmd[:3])}...")


def check_libass() -> None:
    """ffmpeg subtitles 滤镜依赖 libass。启动时探一次，没带则报错不白跑."""
    rc, out, _ = run(["ffmpeg", "-hide_banner", "-filters"], timeout=30)
    if rc != 0:
        die("ffmpeg -filters 探测失败，ffmpeg 异常")
    if "subtitles" not in out:
        die("ffmpeg 不带 libass（subtitles 滤镜缺席），无法烧字幕；换 ffmpeg-full 完整版")


def validate_srt(srt_path: str) -> None:
    """基本 SRT 校验：非空 + 至少一条 cue + timestamp 格式."""
    try:
        content = Path(srt_path).read_text(encoding="utf-8").strip()
    except OSError as e:
        die(f"读 SRT 失败: {e}")
    if not content:
        die("SRT 文件空")
    # 至少含一个 "-->" 时间戳分隔符（SRT 格式的硬标志）
    if "-->" not in content:
        die("SRT 不含任何 `-->` 时间戳分隔符，格式错")


def burn(video: str, srt: str, output: str, font_name: str,
         font_size: int, force_style: str | None) -> dict:
    """ffmpeg subtitles 滤镜烧 SRT. 返回渲染元数据."""
    style = (
        force_style if force_style is not None
        else DEFAULT_FORCE_STYLE.format(font=font_name, size=font_size)
    )
    # ffmpeg subtitles 滤镜里 filename 要单引号包裹，且整个 -vf 字串里单引号要转义
    # 用 shlex.quote 处理路径，再包单引号
    srt_escaped = shlex.quote(srt)
    vf = f"subtitles=filename={srt_escaped}:force_style='{style}'"

    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", video,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",                  # 音轨原样不动
        "-movflags", "+faststart",
        output,
    ]
    rc, _, err = run(cmd, timeout=900)
    if rc != 0:
        die(f"ffmpeg subtitles 渲染失败: {err.strip()[:500]}", code=2)

    return {
        "input": video,
        "srt": srt,
        "output": output,
        "font_name": font_name,
        "font_size": font_size,
        "force_style": style,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Burn SRT subtitles into MP4 (optional, user-requested only)."
    )
    parser.add_argument("video", help="输入视频（合成产物，含声轨）")
    parser.add_argument("srt", help="SRT 字幕文件路径")
    parser.add_argument("--output", default=None,
                        help="输出路径，默认在输入旁加 _burned 后缀")
    parser.add_argument("--font-name", default=DEFAULT_FONT_NAME,
                        help=f"字体名，默认 {DEFAULT_FONT_NAME}")
    parser.add_argument("--font-size", type=int, default=DEFAULT_FONT_SIZE,
                        help=f"字体大小，默认 {DEFAULT_FONT_SIZE}")
    parser.add_argument("--force-style", default=None,
                        help="Override libass force_style 字串（覆盖默认样式）")
    args = parser.parse_args()

    video_path = Path(args.video).resolve()
    if not video_path.is_file():
        die(f"输入视频不存在: {video_path}")

    srt_path = Path(args.srt).resolve()
    if not srt_path.is_file():
        die(f"SRT 文件不存在: {srt_path}")

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        stem = video_path.stem
        out_path = video_path.with_name(f"{stem}_burned.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    check_libass()
    validate_srt(str(srt_path))

    print(f"[info] input:   {video_path}")
    print(f"[info] srt:     {srt_path}")
    print(f"[info] output:  {out_path}")
    print(f"[info] font:    {args.font_name} @ {args.font_size}px")

    result = burn(str(video_path), str(srt_path), str(out_path),
                  args.font_name, args.font_size, args.force_style)

    print(f"\n[done] burned: {out_path}", file=sys.stderr)
    print(f"[info] style used: {result['force_style'][:80]}...", file=sys.stderr)


if __name__ == "__main__":
    main()
