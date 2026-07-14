#!/usr/bin/env python3
"""Assemble a video fragment: combine video + audio into one MP4.

Usage:
  python3 ./skills/fragment-assembly/scripts/assemble.py <artifacts_dir> [--output <output_path>]

Expects artifacts_dir to contain:
  - One or more video files (.mp4/.mov/.webm)
  - Optionally one audio file (.mp3/.wav/.opus)

Audio handling:
  - No external audio file → preserve each video segment's own audio track (声画同出
    AI 片段直接拼接，每段音轨保留；无音轨的片段补静音以保持拼接布局一致).
  - External audio file present (e.g. speech.mp3) → it replaces the video's audio
    track (Stock Footage + TTS 模式).
Output defaults to <artifacts_dir>/assembled.mp4.
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

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".opus", ".ogg", ".flac", ".pcm"}


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def _sort_key(filename: str) -> tuple[int, str]:
    """Sort key: files with numeric prefix (01_*.mp4) sort by number first,
    then by full name. Files without prefix sort after all prefixed files.

    This ensures script-ordered materials like 01_hook.mp4, 02_value.mp4,
    03_cta.mp4 are concatenated in narrative order rather than pure lexicographic.
    """
    stem = os.path.splitext(filename)[0]
    match = re.match(r"^(\d+)[_\-\s]", stem)
    if match:
        return (int(match.group(1)), filename)
    # No numeric prefix → sort after all prefixed files (use large sentinel)
    return (999999, filename)


def find_files(directory: str, extensions: set[str], exclude: set[str] | None = None) -> list[str]:
    """Find files matching given extensions in script-order (numeric prefix first)."""
    excluded = {os.path.abspath(path) for path in (exclude or set())}
    files: list[str] = []
    for name in os.listdir(directory):
        filepath = os.path.join(directory, name)
        if os.path.abspath(filepath) in excluded:
            continue
        if os.path.isfile(filepath) and os.path.splitext(name)[1].lower() in extensions:
            files.append(filepath)
    files.sort(key=lambda p: _sort_key(os.path.basename(p)))
    return files


def find_audio_file(directory: str, exclude: set[str] | None = None) -> str | None:
    """Prefer speech.* audio, then fall back to the first audio file."""
    audio_files = find_files(directory, AUDIO_EXTS, exclude=exclude)
    for filepath in audio_files:
        if Path(filepath).stem == "speech":
            return filepath
    if audio_files:
        return audio_files[0]
    return None


def get_duration(filepath: str) -> float:
    """Get media duration via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", filepath],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return 0.0


def get_video_dimensions(filepath: str) -> tuple[int, int]:
    """Get video dimensions via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-select_streams", "v:0", "-show_streams", filepath],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            if width > 0 and height > 0:
                return width, height
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        pass
    return 1080, 1920


def even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def _segment_has_audio(path: str) -> bool:
    """Return True if the media file has at least one audio stream."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        return bool(result.stdout.strip())
    except subprocess.SubprocessError:
        return False


def assemble_single_video(video_file: str, audio_file: str | None, output_path: str) -> list[str]:
    cmd: list[str] = ["ffmpeg", "-y", "-i", video_file]
    if audio_file:
        cmd.extend(["-i", audio_file])

    cmd.extend(["-c:v", "copy"])
    if audio_file:
        cmd.extend(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-map", "0:v", "-map", "0:a?", "-c:a", "copy"])

    cmd.extend(["-movflags", "+faststart", "-pix_fmt", "yuv420p", output_path])
    return cmd


def _normalize_and_concat_batch(video_files: list[str], width: int, height: int,
                                output_path: str, tmp_dir: str,
                                drop_audio: bool = False, batch_size: int = 3) -> str:
    """Normalize a batch of videos, then concat with ffmpeg concat demuxer.

    Processes videos in small batches to keep memory bounded (~300-500MB per ffmpeg run)
    instead of one giant filter_complex that opens all inputs simultaneously.

    Audio handling:
    - drop_audio=True (external audio will replace): strip audio with -an.
    - drop_audio=False (preserve per-segment audio, e.g. 声画同出 AI 片段): re-encode each
      segment's audio to a uniform aac/48k/stereo so concat -c copy works. Segments with
      no audio get a silent track (anullsrc) so the concat stream layout stays uniform.
    """
    tmp_files: list[str] = []
    vf_filter = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                 f"setsar=1,fps=30,format=yuv420p")
    audio_encode = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

    # Step 1: normalize each video individually (scale/pad/fps/format + audio)
    for i, vf in enumerate(video_files):
        tmp_out = os.path.join(tmp_dir, f"norm_{i:04d}.mp4")
        if drop_audio:
            cmd: list[str] = [
                "ffmpeg", "-y", "-i", vf, "-vf", vf_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                "-threads", "1", "-an", "-movflags", "+faststart", tmp_out,
            ]
        elif _segment_has_audio(vf):
            cmd = [
                "ffmpeg", "-y", "-i", vf, "-vf", vf_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                *audio_encode, "-threads", "1", "-movflags", "+faststart", tmp_out,
            ]
        else:
            # No audio in this segment but we're preserving → add a silent track so all
            # normalized files share the same (v+a) layout for concat -c copy.
            cmd = [
                "ffmpeg", "-y", "-i", vf,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-vf", vf_filter, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                *audio_encode, "-shortest", "-threads", "1",
                "-movflags", "+faststart", tmp_out,
            ]
        _run_ffmpeg(cmd, f"normalize [{i+1}/{len(video_files)}]")
        tmp_files.append(tmp_out)
        # Release memory held by the ffmpeg subprocess buffers
        gc.collect()

    # Step 2: concat all normalized files via concat demuxer (stream copy, no re-encode)
    concat_list = os.path.join(tmp_dir, "_concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for tf in tmp_files:
            abs_tf = os.path.abspath(tf)
            escaped = abs_tf.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
        "-c", "copy", "-movflags", "+faststart", output_path,
    ]
    _run_ffmpeg(cmd, "concat")
    return output_path


def _run_ffmpeg(cmd: list[str], label: str, timeout: int = 600) -> None:
    # Pin to core 0 + low priority to prevent system freeze on resource-constrained hosts
    wrapped_cmd = ["taskset", "-c", "0", "nice", "-n", "10"] + cmd
    print(f"[info] {label}: {' '.join(os.path.basename(c) if '/' in c else c for c in cmd)}")
    # Stream stderr to a temp file instead of buffering in memory.
    # ffmpeg outputs progress line-by-line to stderr which can grow very large.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as stderr_f:
        stderr_path = stderr_f.name
    try:
        with open(stderr_path, "w") as stderr_fh:
            result = subprocess.run(
                wrapped_cmd, stdout=subprocess.DEVNULL, stderr=stderr_fh, text=True, timeout=timeout,
            )
        if result.returncode != 0:
            # Read only the tail of stderr for the error message
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
    """Read the last N characters of a file without loading the whole thing."""
    try:
        size = os.path.getsize(path)
        if size <= max_chars:
            with open(path, "r", errors="replace") as f:
                return f.read()
        with open(path, "rb") as f:
            f.seek(size - max_chars)
            f.readline()  # skip partial first line
            return f.read().decode(errors="replace")
    except OSError:
        return ""


def assemble_multiple_videos(video_files: list[str], audio_file: str | None, output_path: str) -> None:
    width, height = get_video_dimensions(video_files[0])
    width = even(width)
    height = even(height)

    # Use a temp dir for intermediate files, clean up on success
    tmp_dir = os.path.join(os.path.dirname(output_path) or ".", "_assemble_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        # Step 1: normalize + concat. When external audio will replace, drop per-segment
        # audio during normalize; otherwise preserve each segment's audio (声画同出).
        video_only = os.path.join(tmp_dir, "video_only.mp4")
        _normalize_and_concat_batch(
            video_files, width, height, video_only, tmp_dir,
            drop_audio=bool(audio_file),
        )

        # Step 2: mux audio if present
        if audio_file:
            cmd = [
                "ffmpeg", "-y", "-i", video_only, "-i", audio_file,
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", output_path,
            ]
            _run_ffmpeg(cmd, "mux audio")
        else:
            # No external audio → the concat already preserved per-segment audio.
            os.replace(video_only, output_path)
    finally:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def assemble(artifacts_dir: str, output_path: str) -> None:
    excluded = {output_path}
    video_files = find_files(artifacts_dir, VIDEO_EXTS, exclude=excluded)
    if not video_files:
        die(f"No video file found in {artifacts_dir}")

    audio_file = find_audio_file(artifacts_dir, exclude=excluded)

    print(f"[info] Assembling: videos={', '.join(os.path.basename(path) for path in video_files)}")
    if audio_file:
        print(f"       audio={os.path.basename(audio_file)}")

    if len(video_files) == 1:
        cmd = assemble_single_video(video_files[0], audio_file, output_path)
        _run_ffmpeg(cmd, "assemble single")
    else:
        assemble_multiple_videos(video_files, audio_file, output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        die("Output file is missing or empty")

    duration = get_duration(output_path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[done] Assembled: {output_path}")
    print(f"       duration={duration:.2f}s  size={size_mb:.1f}MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble video fragment: video + audio → MP4")
    parser.add_argument("artifacts_dir", help="Directory containing video/audio artifacts")
    parser.add_argument("--output", default=None, help="Output MP4 path (default: <artifacts_dir>/assembled.mp4)")
    args = parser.parse_args()

    if not os.path.isdir(args.artifacts_dir):
        die(f"Not a directory: {args.artifacts_dir}")

    output_path = args.output or os.path.join(args.artifacts_dir, "assembled.mp4")
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    assemble(args.artifacts_dir, output_path)


if __name__ == "__main__":
    main()
