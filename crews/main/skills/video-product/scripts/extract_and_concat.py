#!/usr/bin/env python3
"""Extract segments from MP4(s) and optionally concatenate them into one MP4.

Output normalization (matches assemble.py / gen.py defaults):
  - 30 fps, yuv420p
  - 720x1280 (portrait HD; override with --width / --height, or pass --keep-resolution
    to keep the first input's dimensions)
  - aac 192k stereo @ 48kHz (or silenced with --no-audio)
  - +faststart

Usage — single segment:

  python3 ./skills/video-product/scripts/extract_and_concat.py \\
      --input foo.mp4 --mode head --seconds 6 --output head6.mp4
  python3 ./skills/video-product/scripts/extract_and_concat.py \\
      --input foo.mp4 --mode tail --seconds 4 --output tail4.mp4
  python3 ./skills/video-product/scripts/extract_and_concat.py \\
      --input foo.mp4 --mode slice --start 2 --end 8 --output mid.mp4

Usage — multi-segment + concat (preferred for "剪 A 前 6s + 剪 B 后 4s" 类需求):

  python3 ./skills/video-product/scripts/extract_and_concat.py \\
      --segment input=foo.mp4 mode=head seconds=6 \\
      --segment input=bar.mp4 mode=tail seconds=4 \\
      --output final.mp4

  For slice segments inside a multi-segment call:
      --segment input=foo.mp4 mode=slice start=2 end=8

Audio:
  - Default: 保留每段原音轨（concat 时每段用各自 audio，拼后自然顺接）.
  - --no-audio: 关闭音频输出。
  - --audio speech.mp3: 用外部音频替换（与 assemble.py 一致）.

Notes:
  - ffmpeg `-sseof -N` 用于 tail 模式，按"距离末尾 N 秒"精确定位（无需先 ffprobe 时长）。
  - head / slice 使用 `-ss` + `-t`，配合下方 re-encode 保证帧边界对齐。
"""

import argparse
import gc
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280
DEFAULT_FPS = 30
DEFAULT_AUDIO_BITRATE = "192k"
DEFAULT_AUDIO_RATE = "48000"
DEFAULT_AUDIO_CHANNELS = "2"
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "ultrafast"
VIDEO_CRF = "26"


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def log(msg: str) -> None:
    print(f"[info] {msg}")


def _run_ffmpeg(cmd: list[str], label: str, timeout: int = 600) -> None:
    """Run an ffmpeg command with taskset+nice like assemble.py does, streaming
    stderr to a temp file (not memory) so very chatty ffmpeg runs don't OOM."""
    wrapped_cmd = ["taskset", "-c", "0", "nice", "-n", "10"] + cmd
    # Cosmetic command echo: abspath → basename, keep flags & values as-is.
    pretty: list[str] = []
    for i, c in enumerate(cmd):
        if i > 0 and cmd[i - 1] in {"-i", "-vf", "-filter_complex", "-metadata", "-map"}:
            pretty.append(c)  # keep filter / input path intact
        elif c.startswith("-") or "/" not in c:
            pretty.append(c)
        else:
            pretty.append(os.path.basename(c))
    print(f"[info] {label}: {' '.join(pretty)}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
        stderr_path = f.name
    try:
        with open(stderr_path, "w") as stderr_fh:
            result = subprocess.run(
                wrapped_cmd, stdout=subprocess.DEVNULL, stderr=stderr_fh,
                text=True, timeout=timeout,
            )
        if result.returncode != 0:
            tail = _tail_file(stderr_path, 2000)
            die(f"ffmpeg {label} failed (exit {result.returncode}):\n{tail}")
    except subprocess.TimeoutExpired:
        die(f"ffmpeg {label} timed out after {timeout}s")
    finally:
        try:
            os.unlink(stderr_path)
        except OSError:
            pass


def _tail_file(path: str, max_chars: int) -> str:
    try:
        size = os.path.getsize(path)
        if size <= max_chars:
            with open(path, "r", errors="replace") as f:
                return f.read()
        with open(path, "rb") as f:
            f.seek(size - max_chars)
            f.readline()
            return f.read().decode(errors="replace")
    except OSError:
        return ""


def ffprobe_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0) or 0)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return 0.0


def ffprobe_dimensions(path: str) -> tuple[int, int]:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-select_streams", "v:0", "-show_streams", path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )
            w = int(stream.get("width", 0))
            h = int(stream.get("height", 0))
            if w > 0 and h > 0:
                return w, h
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return DEFAULT_WIDTH, DEFAULT_HEIGHT


def ffprobe_has_audio(path: str) -> bool:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        return bool(result.stdout.strip())
    except subprocess.SubprocessError:
        return False


def even(v: int) -> int:
    return v if v % 2 == 0 else v - 1


def parse_seconds(raw: str, *, what: str) -> float:
    """Accept plain float ('6') or '6s' / '6.5s' / '1m30s' shorthand."""
    if raw is None:
        die(f"--{what} requires a value")
    s = str(raw).strip().lower()
    m = re.fullmatch(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?", s)
    if not m or (not m.group(1) and not m.group(2)):
        die(f"invalid --{what} value: {raw!r} (use e.g. 6, 6s, 1m30s)")
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    total = minutes * 60 + seconds
    if total <= 0:
        die(f"--{what} must be > 0, got {raw!r}")
    return total


# ---- segment spec parsing ---------------------------------------------------

class SegmentSpec:
    """One segment to extract from an input file.

    mode='head'  → keep first `seconds` (or [start, end] if start/end given).
    mode='tail'  → keep last  `seconds`.
    mode='slice' → keep [start, end] (seconds).
    """

    __slots__ = ("input", "mode", "seconds", "start", "end")

    def __init__(self, input_path: str, mode: str, *,
                 seconds: float | None = None,
                 start: float | None = None,
                 end: float | None = None) -> None:
        self.input = input_path
        self.mode = mode
        self.seconds = seconds
        self.start = start
        self.end = end
        self._validate()

    def _validate(self) -> None:
        if self.mode not in {"head", "tail", "slice"}:
            die(f"invalid mode {self.mode!r} (expected head|tail|slice)")
        if not self.input:
            die("segment is missing input=path")
        if self.mode == "head":
            if self.start is None and self.end is None and self.seconds is None:
                die(f"head segment needs seconds= or start=+end= ({self.input})")
        elif self.mode == "tail":
            if self.seconds is None:
                die(f"tail segment needs seconds= ({self.input})")
            if self.start is not None or self.end is not None:
                die(f"tail segment ignores start/end ({self.input})")
        elif self.mode == "slice":
            if self.start is None or self.end is None:
                die(f"slice segment needs both start= and end= ({self.input})")
            if self.end <= self.start:
                die(f"slice end must be > start ({self.input})")

    def resolve(self) -> tuple[float, float]:
        """Return (start, end) in seconds after clipping to input duration."""
        duration = ffprobe_duration(self.input)
        if duration <= 0:
            die(f"cannot read duration of {self.input}")
        if self.mode == "head":
            end = self.end if self.end is not None else self.seconds
            start = self.start if self.start is not None else 0.0
        elif self.mode == "tail":
            end = duration
            start = max(0.0, duration - self.seconds)
        else:  # slice
            start, end = self.start, self.end
        # Clip to duration (ffmpeg is forgiving, but be explicit)
        start = max(0.0, min(start, duration))
        end = max(start, min(end, duration))
        if end - start <= 0.001:
            die(f"segment resolves to ≤ 0s after clipping: {self.input} "
                f"(duration={duration:.2f}s, requested [{start:.2f}, {end:.2f}])")
        return start, end

    def describe(self) -> str:
        s, e = self.resolve()
        return f"{os.path.basename(self.input)}[{self.mode} → {s:.2f}..{e:.2f}s ({e - s:.2f}s)]"


def parse_segment_argv(tokens: list[str]) -> SegmentSpec:
    """Parse a single `--segment` payload, e.g. ['input=foo.mp4', 'mode=head', 'seconds=6']."""
    input_path: str | None = None
    mode: str | None = None
    seconds: float | None = None
    start: float | None = None
    end: float | None = None
    for tok in tokens:
        if "=" not in tok:
            die(f"--segment token must be key=value, got: {tok!r}")
        key, _, val = tok.partition("=")
        key = key.strip().lower()
        val = val.strip()
        if key == "input" or key == "i":
            input_path = val
        elif key == "mode" or key == "m":
            mode = val
        elif key in ("seconds", "sec", "s", "duration", "dur"):
            seconds = parse_seconds(val, what=f"segment[{tokens}].{key}")
        elif key in ("start", "st", "from"):
            start = parse_seconds(val, what=f"segment[{tokens}].{key}")
        elif key in ("end", "e", "to"):
            end = parse_seconds(val, what=f"segment[{tokens}].{key}")
        else:
            die(f"unknown --segment key: {key!r} (allowed: input, mode, seconds, start, end)")
    if not mode:
        die(f"--segment missing mode= (in {tokens})")
    return SegmentSpec(input_path or "", mode, seconds=seconds, start=start, end=end)


def build_single_segment(args: argparse.Namespace) -> SegmentSpec:
    """Build a SegmentSpec from the legacy single-segment flags."""
    return SegmentSpec(
        args.input,
        args.mode,
        seconds=args.seconds,
        start=args.start,
        end=args.end,
    )


# ---- ffmpeg command builders ------------------------------------------------

def build_cut_cmd(spec: SegmentSpec, output_path: str,
                  width: int, height: int, fps: int, *, no_audio: bool) -> list[str]:
    """Cut a segment out of an input and re-encode to the normalized spec.

    head/slice use input-seek (`-ss` before `-i`) for speed; tail uses `-sseof`
    for built-in 'last N seconds' handling. Output is always re-encoded so all
    concat'd files share an identical stream layout (codec/fps/pix_fmt/sar/w/h).
    """
    start, end = spec.resolve()
    duration = end - start
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
          f"setsar=1,fps={fps},format=yuv420p")
    audio_encode = ["-c:a", "aac", "-b:a", DEFAULT_AUDIO_BITRATE,
                    "-ar", DEFAULT_AUDIO_RATE, "-ac", DEFAULT_AUDIO_CHANNELS]

    cmd: list[str] = ["ffmpeg", "-y"]
    if spec.mode == "tail":
        # `-sseof -N` = seek N seconds before EOF, then take all remaining.
        # Use `-t` to cap to the requested window in case input is longer.
        cmd += ["-sseof", f"-{duration:.3f}", "-i", spec.input]
    else:
        cmd += ["-ss", f"{start:.3f}", "-i", spec.input]
        if spec.mode == "head":
            # `seconds` already encoded as end-start
            cmd += ["-t", f"{duration:.3f}"]
        else:  # slice
            cmd += ["-t", f"{duration:.3f}"]

    cmd += ["-vf", vf,
            "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", VIDEO_CRF]

    if no_audio:
        cmd += ["-an"]
    elif spec.mode == "tail" or ffprobe_has_audio(spec.input):
        cmd += ["-map", "0:v:0", "-map", "0:a:0?", *audio_encode, "-shortest"]
    else:
        # No audio in input → emit a silent stereo track so all normalized files
        # share the same (v+a) layout for downstream concat -c copy.
        cmd += [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0", "-map", "1:a:0", *audio_encode, "-shortest",
        ]

    cmd += ["-movflags", "+faststart", "-threads", "1", output_path]
    return cmd


def build_concat_cmd(parts: list[str], output_path: str,
                     *, external_audio: str | None, no_audio: bool) -> list[str]:
    """Concat pre-normalized parts via concat demuxer, optionally muxing audio."""
    concat_list = os.path.join(os.path.dirname(parts[0]) or ".", "_concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in parts:
            abs_p = os.path.abspath(p)
            esc = abs_p.replace("'", "'\\''")
            f.write(f"file '{esc}'\n")

    cmd: list[str] = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                      "-i", concat_list, "-c", "copy",
                      "-movflags", "+faststart", output_path]
    if external_audio:
        # Re-run with audio replacement
        cmd2: list[str] = ["ffmpeg", "-y", "-i", output_path, "-i", external_audio,
                           "-map", "0:v", "-map", "1:a",
                           "-c:v", "copy", "-c:a", "aac", "-b:a", DEFAULT_AUDIO_BITRATE,
                           "-movflags", "+faststart",
                           output_path + ".mux.mp4"]
        return cmd2  # caller will run cmd first, then cmd2
    if no_audio:
        # Strip audio stream (parts may still carry audio from normalization)
        cmd2 = ["ffmpeg", "-y", "-i", output_path, "-an",
                "-c:v", "copy", "-movflags", "+faststart",
                output_path + ".noaudio.mp4"]
        return cmd2
    return cmd


def build_mux_audio_cmd(video_path: str, audio_path: str, output_path: str) -> list[str]:
    return [
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", DEFAULT_AUDIO_BITRATE,
        "-movflags", "+faststart", output_path,
    ]


# ---- main flow --------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    output_path = args.output
    if not output_path:
        die("--output is required")
    output_abs = os.path.abspath(output_path)
    out_dir = os.path.dirname(output_abs) or "."
    os.makedirs(out_dir, exist_ok=True)

    # Resolve segments
    if args.segment:
        segments = [parse_segment_argv(toks) for toks in args.segment]
    elif args.input:
        segments = [build_single_segment(args)]
    else:
        die("nothing to do: pass --input + --mode, or one or more --segment")

    for s in segments:
        if not os.path.isfile(s.input):
            die(f"input not found: {s.input}")

    # Resolve target dimensions
    if args.keep_resolution:
        w0, h0 = ffprobe_dimensions(segments[0].input)
        width, height = even(w0), even(h0)
    else:
        width = args.width or DEFAULT_WIDTH
        height = args.height or DEFAULT_HEIGHT
    width, height = even(width), even(height)
    fps = args.fps or DEFAULT_FPS

    no_audio = bool(args.no_audio)
    external_audio = args.audio  # may be None

    log(f"target: {width}x{height} @ {fps}fps, "
        f"audio={'off' if no_audio else (external_audio or 'preserve')}")
    log(f"segments:")
    for s in segments:
        log(f"  - {s.describe()}")

    # Step 1: cut + normalize each segment to a temp file
    tmp_dir = tempfile.mkdtemp(prefix="extract_concat_", dir=out_dir)
    try:
        parts: list[str] = []
        for i, seg in enumerate(segments):
            part_path = os.path.join(tmp_dir, f"part_{i:04d}.mp4")
            cmd = build_cut_cmd(seg, part_path, width, height, fps, no_audio=no_audio)
            _run_ffmpeg(cmd, f"cut[{i+1}/{len(segments)}]")
            if not os.path.isfile(part_path) or os.path.getsize(part_path) == 0:
                die(f"part {i+1} produced empty file: {part_path}")
            parts.append(part_path)
            gc.collect()

        if len(parts) == 1 and not external_audio and not no_audio:
            # Fast path: single segment, no audio override → just rename.
            shutil.move(parts[0], output_abs)
        elif len(parts) == 1 and (external_audio or no_audio):
            # Single segment with audio override → re-mux the one part.
            if external_audio:
                if not os.path.isfile(external_audio):
                    die(f"--audio file not found: {external_audio}")
                cmd = build_mux_audio_cmd(parts[0], external_audio, output_abs)
                _run_ffmpeg(cmd, "mux external audio")
            else:  # no_audio
                cmd = ["ffmpeg", "-y", "-i", parts[0], "-an",
                       "-c:v", "copy", "-movflags", "+faststart", output_abs]
                _run_ffmpeg(cmd, "drop audio")
        else:
            # Multi-segment: concat demuxer (stream copy), then optional audio override.
            tmp_concat = os.path.join(tmp_dir, "concat.mp4")
            cmd = build_concat_cmd(parts, tmp_concat,
                                   external_audio=None, no_audio=False)
            _run_ffmpeg(cmd, "concat")
            if external_audio:
                if not os.path.isfile(external_audio):
                    die(f"--audio file not found: {external_audio}")
                cmd = build_mux_audio_cmd(tmp_concat, external_audio, output_abs)
                _run_ffmpeg(cmd, "mux external audio")
            elif no_audio:
                cmd = ["ffmpeg", "-y", "-i", tmp_concat, "-an",
                       "-c:v", "copy", "-movflags", "+faststart", output_abs]
                _run_ffmpeg(cmd, "drop audio")
            else:
                shutil.move(tmp_concat, output_abs)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not os.path.isfile(output_abs) or os.path.getsize(output_abs) == 0:
        die("output file is missing or empty")
    duration = ffprobe_duration(output_abs)
    size_mb = os.path.getsize(output_abs) / (1024 * 1024)
    log(f"done: {output_abs}")
    log(f"      duration={duration:.2f}s  size={size_mb:.2f}MB")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Extract segments from MP4(s) and concatenate them.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Output
    p.add_argument("--output", "-o", required=True, help="Output MP4 path")

    # Single-segment mode (legacy / simple)
    p.add_argument("--input", "-i", help="Input MP4 (single-segment mode)")
    p.add_argument("--mode", choices=["head", "tail", "slice"],
                   help="Extraction mode (single-segment mode)")
    p.add_argument("--seconds", type=lambda v: parse_seconds(v, what="seconds"),
                   help="Window size in seconds (head/tail). Accepts 6 / 6s / 1m30s.")
    p.add_argument("--start", type=lambda v: parse_seconds(v, what="start"),
                   help="Start second (head with --end, or slice). Accepts 6 / 6s / 1m30s.")
    p.add_argument("--end", type=lambda v: parse_seconds(v, what="end"),
                   help="End second (slice, or head with --start). Accepts 6 / 6s / 1m30s.")

    # Multi-segment mode
    p.add_argument("--segment", action="append", nargs="+", default=[],
                   metavar="KEY=VAL",
                   help="Repeatable. Tokens: input=path mode=head|tail|slice "
                        "seconds=N start=S end=E. "
                        "Example: --segment input=a.mp4 mode=head seconds=6")

    # Output normalization
    p.add_argument("--width", type=int, default=None,
                   help=f"Target width in px (default {DEFAULT_WIDTH})")
    p.add_argument("--height", type=int, default=None,
                   help=f"Target height in px (default {DEFAULT_HEIGHT})")
    p.add_argument("--keep-resolution", action="store_true",
                   help="Keep first input's resolution (still forces 30fps/yuv420p).")
    p.add_argument("--fps", type=int, default=None,
                   help=f"Target fps (default {DEFAULT_FPS})")

    # Audio
    p.add_argument("--no-audio", action="store_true",
                   help="Drop audio (output is video-only).")
    p.add_argument("--audio", default=None,
                   help="Replace per-segment audio with this file (e.g. speech.mp3).")
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.segment and args.input:
        die("use either --input/--mode (single segment) OR --segment (one or more), not both")
    if args.segment:
        for toks in args.segment:
            if not toks:
                die("--segment requires at least one key=value token")
    else:
        if not args.input or not args.mode:
            die("single-segment mode requires --input and --mode")

    run(args)


if __name__ == "__main__":
    main()