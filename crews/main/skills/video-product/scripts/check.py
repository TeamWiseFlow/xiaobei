#!/usr/bin/env python3
"""Content check for content-producer artifacts.

Checks media files via ffprobe and calculates duration gap against target.
Target duration is determined by:
  1. If artifacts/speech.json exists with a "duration" field → target = speech duration + 1s
  2. Else if --target-duration is provided → target = that value
  3. Else if fragment/requirement.md contains a target duration → target = that value
  4. Else → no duration target check

ASR/TTS verification has been moved to the siliconflow-tts skill itself.

Usage:
  python3 ./skills/content-check/scripts/check.py <fragment_or_artifacts_dir> [--target-duration <seconds>]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
AUDIO_EXTS = {".mp3", ".wav", ".opus", ".pcm", ".ogg", ".flac"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
SRT_EXT = ".srt"
TTS_BUFFER_SECONDS = 1.0
EXCESS_DURATION_SECONDS = 5  # flag when actual > target + this value (silent gap too long)
BLACK_FRAME_THRESHOLD = 0.02  # fraction of pixels below luma 32 to consider "black"
BLACK_SAMPLE_COUNT = 5  # number of keyframes to sample for blank detection


def die(msg: str) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def resolve_fragment_paths(input_dir: str) -> tuple[Path, Path]:
    """Accept either a fragment directory or its artifacts directory."""
    path = Path(input_dir)
    if path.name == "artifacts":
        return path, path.parent

    artifacts_dir = path / "artifacts"
    if artifacts_dir.is_dir():
        return artifacts_dir, path

    return path, path.parent


# ── Media probing ──────────────────────────────────────────────────────

def probe_video(filepath: str) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", filepath],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"file": os.path.basename(filepath), "error": f"ffprobe exit {result.returncode}"}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        video_stream = None
        audio_stream = None
        for s in streams:
            if s.get("codec_type") == "video" and video_stream is None:
                video_stream = s
            elif s.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = s

        info: dict = {
            "file": os.path.basename(filepath),
            "duration": round(float(fmt.get("duration", 0)), 2),
            "size_bytes": int(fmt.get("size", 0)),
        }
        if video_stream:
            info["video"] = {
                "codec": video_stream.get("codec_name", "unknown"),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "fps": video_stream.get("r_frame_rate", "unknown"),
                "pix_fmt": video_stream.get("pix_fmt", "unknown"),
            }
        if audio_stream:
            info["audio"] = {
                "codec": audio_stream.get("codec_name", "unknown"),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
            }

        issues: list[str] = []
        if video_stream:
            w = int(video_stream.get("width", 0))
            h = int(video_stream.get("height", 0))
            if w < 720 or h < 720:
                issues.append(f"low resolution: {w}x{h}")
            pix_fmt = video_stream.get("pix_fmt", "")
            if pix_fmt and "420" not in pix_fmt and w > 0:
                issues.append(f"non-standard pixel format: {pix_fmt}")
        if info["duration"] < 1.0:
            issues.append("very short duration")

        # Blank frame detection for videos >= 2s
        if info["duration"] >= 2.0:
            blank_result = detect_blank_frames(filepath, info["duration"])
            if blank_result:
                info["blank_frame_check"] = blank_result
                if blank_result["status"] == "mostly_blank":
                    issues.append(f"mostly blank frames ({blank_result['blank_count']}/{blank_result['sampled']} sampled)")

        if issues:
            info["issues"] = issues
        return info

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ValueError) as e:
        return {"file": filepath, "error": str(e)}


def probe_audio(filepath: str) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", filepath],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"file": os.path.basename(filepath), "error": f"ffprobe exit {result.returncode}"}

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        info: dict = {
            "file": os.path.basename(filepath),
            "duration": round(float(fmt.get("duration", 0)), 2),
        }
        if audio_stream:
            info["codec"] = audio_stream.get("codec_name", "unknown")
            info["sample_rate"] = int(audio_stream.get("sample_rate", 0))
            info["channels"] = int(audio_stream.get("channels", 0))
        if info["duration"] < 0.5:
            info.setdefault("issues", []).append("very short duration")
        return info

    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError) as e:
        return {"file": filepath, "error": str(e)}


def check_image(filepath: str) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", filepath],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"file": os.path.basename(filepath), "error": "ffprobe failed"}

        data = json.loads(result.stdout)
        img_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        info: dict = {"file": os.path.basename(filepath)}
        if img_stream:
            w = int(img_stream.get("width", 0))
            h = int(img_stream.get("height", 0))
            info.update(width=w, height=h, codec=img_stream.get("codec_name", "unknown"))
            if w < 1080 or h < 1080:
                info["issues"] = [f"resolution below 1080p: {w}x{h}"]
        else:
            info["error"] = "no image stream found"
        return info

    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"file": filepath, "error": str(e)}


def check_srt(filepath: str) -> dict:
    """Basic SRT validation: non-empty and has at least one timestamp line."""
    info: dict = {"file": os.path.basename(filepath)}
    try:
        content = Path(filepath).read_text(encoding="utf-8").strip()
        if not content:
            info["issues"] = ["empty SRT file"]
        elif "-->" not in content:
            info["issues"] = ["no timestamp markers found"]
        else:
            cue_count = content.count("-->")
            info["cue_count"] = cue_count
    except OSError as e:
        info["error"] = str(e)
    return info


# ── Blank/Black Frame Detection ────────────────────────────────────────

def detect_blank_frames(filepath: str, duration: float) -> dict | None:
    """Sample keyframes from a video and detect blank/black frames.

    Uses ffmpeg's blackframe filter to check if sampled timestamps are
    predominantly black (near-uniform low-luma content).

    Returns a dict with:
      - sampled: number of timestamps checked
      - blank_count: number of blank frames detected
      - blank_ratio: fraction of sampled frames that are blank
      - status: "ok" or "mostly_blank"
    Or None if duration is too short to sample.
    """
    if duration < 2.0:
        return None

    # Calculate evenly-spaced sample timestamps
    n_samples = min(BLACK_SAMPLE_COUNT, max(2, int(duration / 2)))
    step = duration / (n_samples + 1)
    timestamps = [round(step * (i + 1), 2) for i in range(n_samples)]

    blank_count = 0
    for ts in timestamps:
        try:
            # Use ffmpeg blackframe filter: detect frames with >98% pixels below luma 32
            result = subprocess.run(
                ["ffmpeg", "-ss", str(ts), "-i", filepath,
                 "-vframes", "1", "-vf", "blackframe=amount=0.98:threshold=32",
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=15,
            )
            # blackframe filter prints lines like "frame:1 pblack:99 ..."
            if "pblack:" in result.stderr:
                # Extract the highest pblack value
                import re
                pblack_values = [int(m) for m in re.findall(r"pblack:(\d+)", result.stderr)]
                max_pblack = max(pblack_values) if pblack_values else 0
                if max_pblack >= 98:
                    blank_count += 1
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    blank_ratio = blank_count / n_samples if n_samples > 0 else 0
    return {
        "sampled": n_samples,
        "blank_count": blank_count,
        "blank_ratio": round(blank_ratio, 2),
        "status": "mostly_blank" if blank_ratio >= 0.6 else "ok",
    }


# ── Target Duration Calculation ────────────────────────────────────────

def read_speech_target(artifacts_dir: Path, fragment_dir: Path) -> tuple[float, str] | None:
    candidates = unique_paths([
        artifacts_dir / "speech.json",
        fragment_dir / "artifacts" / "speech.json",
        fragment_dir / "speech.json",
    ])
    for speech_json_path in candidates:
        if not speech_json_path.is_file():
            continue
        try:
            data = json.loads(speech_json_path.read_text(encoding="utf-8"))
            speech_dur = data.get("duration", 0)
            if isinstance(speech_dur, (int, float)) and speech_dur > 0:
                target = float(speech_dur) + TTS_BUFFER_SECONDS
                print(f"[info] Target duration from TTS: {speech_dur:.3f}s + {TTS_BUFFER_SECONDS}s buffer = {target:.3f}s")
                return target, str(speech_json_path)
        except (json.JSONDecodeError, OSError):
            continue
    return None


def parse_duration_seconds(raw: str) -> float | None:
    text = raw.lower()
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if not numbers:
        return None

    value = float(numbers[0])
    if "分钟" in text or "minute" in text or re.search(r"\bmin\b", text):
        return value * 60
    return value


def read_requirement_target(fragment_dir: Path) -> tuple[float, str] | None:
    requirement_path = fragment_dir / "requirement.md"
    if not requirement_path.is_file():
        return None

    duration_keywords = (
        "目标时长",
        "时长要求",
        "视频时长",
        "target duration",
        "duration",
    )
    try:
        for line in requirement_path.read_text(encoding="utf-8").splitlines():
            normalized = line.strip().lower()
            if not any(keyword in normalized for keyword in duration_keywords):
                continue
            if "自动" in normalized or "配音时长" in normalized or "speech" in normalized or "tts" in normalized:
                continue
            duration = parse_duration_seconds(normalized)
            if duration and duration > 0:
                print(f"[info] Target duration from requirement.md: {duration:.3f}s")
                return duration, str(requirement_path)
    except OSError:
        return None

    return None


def determine_target_duration(artifacts_dir: Path, fragment_dir: Path, cli_target: float | None) -> tuple[float | None, str | None]:
    """Determine the target video duration for duration gap calculation.

    Priority:
      1. speech.json in artifacts_dir with "duration" → speech_duration + 1s buffer
      2. --target-duration CLI argument
      3. requirement.md target duration
      4. None (no target check)
    """
    speech_target = read_speech_target(artifacts_dir, fragment_dir)
    if speech_target is not None:
        return speech_target

    if cli_target is not None and cli_target > 0:
        print(f"[info] Target duration from CLI: {cli_target}s")
        return cli_target, "--target-duration"

    requirement_target = read_requirement_target(fragment_dir)
    if requirement_target is not None:
        return requirement_target

    return None, None


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Content check for content-producer artifacts")
    parser.add_argument("input_dir", help="Fragment directory or its artifacts directory")
    parser.add_argument("--target-duration", type=float, default=None, dest="target_duration",
                        help="Target video duration in seconds (fallback if no speech.json)")
    args = parser.parse_args()

    artifacts_dir, fragment_dir = resolve_fragment_paths(args.input_dir)
    if not artifacts_dir.is_dir():
        die(f"Not a directory: {artifacts_dir}")

    videos: list[dict] = []
    audios: list[dict] = []
    images: list[dict] = []
    srts: list[dict] = []

    for name in sorted(os.listdir(artifacts_dir)):
        filepath = artifacts_dir / name
        if not filepath.is_file():
            continue
        ext = os.path.splitext(name)[1].lower()

        if ext in VIDEO_EXTS:
            videos.append(probe_video(str(filepath)))
        elif ext in AUDIO_EXTS:
            info = probe_audio(str(filepath))
            audios.append(info)
        elif ext in IMAGE_EXTS:
            images.append(check_image(str(filepath)))
        elif ext == SRT_EXT:
            srts.append(check_srt(str(filepath)))

    # Determine target duration and calculate gap
    target_duration, target_source = determine_target_duration(artifacts_dir, fragment_dir, args.target_duration)
    duration_gap: dict | None = None

    if target_duration is not None:
        total_video_duration = sum(v.get("duration", 0) for v in videos if "error" not in v)
        total_image_duration = 0.0
        # Images need agent-specified durations; we can't determine them here
        # Only count video durations for gap calculation
        actual_duration = total_video_duration + total_image_duration
        gap = round(target_duration - actual_duration, 2)
        duration_gap = {
            "target": round(target_duration, 2),
            "actual_video": round(actual_duration, 2),
            "gap": gap,
            "status": "sufficient" if gap <= 0 else "deficit",
        }
        if gap > 0:
            duration_gap["status"] = "deficit"
            print(f"[info] Duration gap: need {gap:.2f}s more video material (target={target_duration:.2f}s, actual={actual_duration:.2f}s)")
        elif actual_duration > target_duration + EXCESS_DURATION_SECONDS:
            duration_gap["status"] = "excess"
            excess_s = round(actual_duration - target_duration, 2)
            print(f"[warn] Duration excess: {actual_duration:.2f}s >> target {target_duration:.2f}s (exceeds by {excess_s}s, over {EXCESS_DURATION_SECONDS}s silent gap). Delete oversized clips and re-download to match the gap.")
        else:
            duration_gap["status"] = "sufficient"
            print(f"[info] Duration sufficient: {actual_duration:.2f}s >= target {target_duration:.2f}s")

    # Collect all issues
    all_issues: list[str] = []
    if not videos:
        all_issues.append("no video material found")
    for v in videos:
        if "error" in v:
            all_issues.append(f"video {v['file']}: {v['error']}")
        elif v.get("issues"):
            all_issues.append(f"video {v['file']}: {'; '.join(v['issues'])}")
    for a in audios:
        if "error" in a:
            all_issues.append(f"audio {a['file']}: {a['error']}")
        elif a.get("issues"):
            all_issues.append(f"audio {a['file']}: {'; '.join(a['issues'])}")
    for img in images:
        if "error" in img:
            all_issues.append(f"image {img['file']}: {img['error']}")
        elif img.get("issues"):
            all_issues.append(f"image {img['file']}: {'; '.join(img['issues'])}")
    for s in srts:
        if "error" in s:
            all_issues.append(f"srt {s['file']}: {s['error']}")
        elif s.get("issues"):
            all_issues.append(f"srt {s['file']}: {'; '.join(s['issues'])}")

    # Duration deficit is an issue
    if duration_gap and duration_gap["status"] == "deficit":
        all_issues.append(f"video duration deficit: need {duration_gap['gap']:.2f}s more (target={duration_gap['target']:.2f}s, actual={duration_gap['actual_video']:.2f}s)")
    
    # Duration excess is also an issue — agent should delete oversized clips
    if duration_gap and duration_gap["status"] == "excess":
        excess_s = round(duration_gap["actual_video"] - duration_gap["target"], 2)
        all_issues.append(f"video duration excess: {excess_s:.2f}s over target (target={duration_gap['target']:.2f}s, actual={duration_gap['actual_video']:.2f}s). Delete clips that are too long and re-download footage matching the needed gap.")

    # Overall verdict
    has_critical = any("error" in item for item in videos + audios + images + srts)
    verdict = "needs_rework" if (has_critical or len(all_issues) > 0) else "accepted"

    report = {
        "artifacts_dir": str(artifacts_dir),
        "fragment_dir": str(fragment_dir),
        "verdict": verdict,
        "target_source": target_source,
        "video_count": len(videos),
        "audio_count": len(audios),
        "image_count": len(images),
        "srt_count": len(srts),
        "videos": videos,
        "audios": audios,
        "images": images,
        "srts": srts,
        "duration_gap": duration_gap,
        "issues": all_issues,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
