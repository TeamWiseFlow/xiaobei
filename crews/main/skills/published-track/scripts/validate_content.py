#!/usr/bin/env python3
"""
Platform content validator — check and auto-fix content against platform constraints.

Data source: AiToEarn v2.4 draft-generation-platforms.ts + our own publishing experience.

Usage:
    python3 validate_content.py --platform twitter --title "..." --desc "..." --topics "a,b,c"
    python3 validate_content.py --platform bilibili --title "..." --desc "..." --video-duration 120
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextConstraint:
    title_max: Optional[int] = None
    title_required: bool = False
    desc_max: Optional[int] = None
    desc_required: bool = False
    topics_max: Optional[int] = None
    topics_min: Optional[int] = None


@dataclass
class VideoConstraint:
    min_duration: Optional[int] = None
    max_duration: Optional[int] = None
    supported_ratios: list = field(default_factory=list)


@dataclass
class MediaConstraint:
    video: Optional[VideoConstraint] = None
    image_max: Optional[int] = None


# ── Platform constraint tables ──────────────────────────────────────────

TEXT_CONSTRAINTS: dict[str, TextConstraint] = {
    "tiktok":       TextConstraint(desc_max=2200, topics_max=5),
    "instagram":    TextConstraint(desc_max=2200),
    "douyin":       TextConstraint(title_max=30, topics_max=5),
    "bilibili":     TextConstraint(title_max=80, title_required=True, desc_max=250, topics_max=10, topics_min=1),
    "youtube":      TextConstraint(title_max=100, title_required=True, desc_max=5000, desc_required=True),
    "twitter":      TextConstraint(desc_max=280, desc_required=True),
    "facebook":     TextConstraint(desc_max=5000),
    "threads":      TextConstraint(desc_max=500, desc_required=True),
    "pinterest":    TextConstraint(title_required=True),
    "kuaishou":     TextConstraint(topics_max=4),
    "xhs":          TextConstraint(title_max=20, title_required=True, desc_max=1000, topics_max=10),
    "linkedin":     TextConstraint(title_max=200, desc_max=3000),
    # Our own additions (not from AiToEarn)
    "wx_mp":        TextConstraint(title_max=64, title_required=True, desc_max=20000, desc_required=True),
    "wx_channel":   TextConstraint(title_max=30, title_required=True, desc_max=1000),
    "toutiao":      TextConstraint(title_max=30, title_required=True),
    "juejin":       TextConstraint(title_max=128, title_required=True),
    "zhihu":        TextConstraint(title_required=True),
}

MEDIA_CONSTRAINTS: dict[str, MediaConstraint] = {
    "tiktok":       MediaConstraint(video=VideoConstraint(min_duration=3, max_duration=600), image_max=10),
    "instagram":    MediaConstraint(video=VideoConstraint(min_duration=5, max_duration=900), image_max=10),
    "douyin":       MediaConstraint(video=VideoConstraint(max_duration=900, supported_ratios=["9:16","16:9","1:1"]), image_max=9),
    "bilibili":     MediaConstraint(video=VideoConstraint()),
    "youtube":      MediaConstraint(video=VideoConstraint(max_duration=43200)),
    "twitter":      MediaConstraint(image_max=4),
    "facebook":     MediaConstraint(video=VideoConstraint(min_duration=3, max_duration=14400), image_max=10),
    "threads":      MediaConstraint(video=VideoConstraint(max_duration=300), image_max=20),
    "pinterest":    MediaConstraint(video=VideoConstraint(min_duration=4, max_duration=15)),
    "kuaishou":     MediaConstraint(video=VideoConstraint(min_duration=15, max_duration=180, supported_ratios=["9:16"])),
    "xhs":          MediaConstraint(video=VideoConstraint(max_duration=900, supported_ratios=["9:16","3:4","1:1","16:9"]), image_max=18),
    "wx_mp":        MediaConstraint(image_max=10),
    "wx_channel":   MediaConstraint(video=VideoConstraint(max_duration=1800, supported_ratios=["9:16","16:9"]), image_max=9),
    "linkedin":     MediaConstraint(video=VideoConstraint(), image_max=None),
}


def validate(platform: str,
             title: Optional[str] = None,
             desc: Optional[str] = None,
             topics: Optional[list[str]] = None,
             video_duration: Optional[int] = None,
             video_ratio: Optional[str] = None,
             image_count: Optional[int] = None) -> dict:
    """Validate and auto-fix content for a platform. Returns result dict."""

    errors: list[str] = []
    warnings: list[str] = []

    # ── Text constraints ──
    tc = TEXT_CONSTRAINTS.get(platform)
    if tc:
        # Title required
        if tc.title_required and not (title and title.strip()):
            errors.append(f"title is required for {platform}")

        # Title max length → truncate
        if tc.title_max and title and len(title) > tc.title_max:
            title = title[:tc.title_max - 1] + "…"
            warnings.append(f"title truncated to {tc.title_max} chars")

        # Desc required
        if tc.desc_required and not (desc and desc.strip()):
            errors.append(f"description is required for {platform}")

        # Desc max length → truncate
        if tc.desc_max and desc and len(desc) > tc.desc_max:
            desc = desc[:tc.desc_max - 6] + "…[已截断]"
            warnings.append(f"desc truncated to {tc.desc_max} chars")

        # Topics min
        if tc.topics_min and topics and len(topics) < tc.topics_min:
            errors.append(f"need at least {tc.topics_min} topics, got {len(topics)}")

        # Topics max → trim
        if tc.topics_max and topics and len(topics) > tc.topics_max:
            original = len(topics)
            topics = topics[:tc.topics_max]
            warnings.append(f"topics trimmed from {original} to {tc.topics_max}")

    # ── Media constraints ──
    mc = MEDIA_CONSTRAINTS.get(platform)
    if mc:
        # Video duration
        if mc.video and video_duration is not None:
            if mc.video.min_duration and video_duration < mc.video.min_duration:
                errors.append(f"video too short: {video_duration}s < {mc.video.min_duration}s min")
            if mc.video.max_duration and video_duration > mc.video.max_duration:
                errors.append(f"video too long: {video_duration}s > {mc.video.max_duration}s max")

        # Video ratio
        if mc.video and video_ratio and mc.video.supported_ratios:
            if video_ratio not in mc.video.supported_ratios:
                errors.append(f"aspect ratio {video_ratio} not supported (allowed: {', '.join(mc.video.supported_ratios)})")

        # Image count → trim
        if mc.image_max is not None and image_count is not None and image_count > mc.image_max:
            original = image_count
            image_count = mc.image_max
            warnings.append(f"image_count trimmed from {original} to {mc.image_max}")

    result = {"ok": len(errors) == 0}
    if title is not None:
        result["title"] = title
    if desc is not None:
        result["desc"] = desc
    if topics is not None:
        result["topics"] = topics
    if video_duration is not None:
        result["video_duration"] = video_duration
    if video_ratio is not None:
        result["video_ratio"] = video_ratio
    if image_count is not None:
        result["image_count"] = image_count
    if warnings:
        result["warnings"] = warnings
    if errors:
        result["errors"] = errors

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate content against platform constraints")
    parser.add_argument("--platform", required=True, help="Platform ID (e.g. twitter, bilibili, xhs)")
    parser.add_argument("--title", default=None, help="Content title")
    parser.add_argument("--desc", default=None, help="Content description/caption")
    parser.add_argument("--topics", default=None, help="Comma-separated topics/tags")
    parser.add_argument("--video-duration", type=int, default=None, help="Video duration in seconds")
    parser.add_argument("--video-ratio", default=None, help="Video aspect ratio (e.g. 9:16)")
    parser.add_argument("--image-count", type=int, default=None, help="Number of images")
    args = parser.parse_args()

    topics = args.topics.split(",") if args.topics else None

    result = validate(
        platform=args.platform,
        title=args.title,
        desc=args.desc,
        topics=topics,
        video_duration=args.video_duration,
        video_ratio=args.video_ratio,
        image_count=args.image_count,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
