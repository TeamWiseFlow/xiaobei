#!/usr/bin/env python3
"""PIL post-process generated images: convert PNG to JPG, slight sharpening, copy to article folder."""

from PIL import Image, ImageEnhance, ImageFilter
import shutil
from pathlib import Path

WORKDIR = Path("/home/wukong/.openclaw/workspace-media-operator")
ARTICLE_DIR = WORKDIR / "output_articles" / "freelancer-776-days"
ARTICLE_IMAGES = ARTICLE_DIR / "images"
ARTICLE_IMAGES.mkdir(parents=True, exist_ok=True)

# (source_dir, target_name)
SOURCES = [
    (WORKDIR / "tmp" / "freelancer776_cover" / "00.png", "cover.jpg", "cover"),
    (WORKDIR / "tmp" / "freelancer776_img1" / "00.png", "img1.jpg", "income"),
    (WORKDIR / "tmp" / "freelancer776_img2" / "00.png", "img2.jpg", "time"),
    (WORKDIR / "tmp" / "freelancer776_img3" / "00.png", "img3.jpg", "platforms"),
    (WORKDIR / "tmp" / "freelancer776_img4" / "00.png", "img4.jpg", "milestone"),
]

def post_process(src: Path, dst: Path) -> tuple[int, int]:
    """Open PNG, apply slight sharpen, save as JPG quality 92."""
    img = Image.open(src).convert("RGB")
    # Slight unsharp mask to clean AI softness
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
    # Slight contrast boost
    img = ImageEnhance.Contrast(img).enhance(1.05)
    # Save as JPG
    img.save(dst, "JPEG", quality=92, optimize=True)
    w, h = img.size
    return w, h

print("=== Post-processing images ===\n")
for src, name, label in SOURCES:
    if not src.exists():
        print(f"  ❌ {label}: source missing {src}")
        continue
    # in-article images go to images/, cover to root
    if name == "cover.jpg":
        dst = ARTICLE_DIR / name
    else:
        dst = ARTICLE_IMAGES / name
    w, h = post_process(src, dst)
    size_kb = dst.stat().st_size / 1024
    print(f"  ✅ {label}: {w}x{h}, {size_kb:.0f}KB → {dst.relative_to(WORKDIR)}")

print("\n=== Done ===")
