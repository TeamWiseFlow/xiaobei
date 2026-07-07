#!/usr/bin/env python3
"""
html_to_longimage.py — Convert a pitch-deck HTML file to a long vertical image.

Renders each <section class="slide"> in a headless browser, captures
per-slide screenshots, then stitches them top-to-bottom into a single
tall PNG/JPEG with Pillow.

Each slide is rendered at landscape viewport (default 1920×1080) and
stacked vertically — ideal for sharing on mobile (WeChat, Feishu, etc.)
where scrolling a long image is more natural than flipping slides.

Dependencies:
  pip install playwright Pillow
  python3 -m playwright install chromium

Usage:
  python3 html_to_longimage.py <input.html> [-o output.png] [--width 1920] [--height 1080] [--format png|jpg] [--quality 95]

Features:
  - Pixel-perfect rendering via headless Chromium (CSS custom properties, clamp(), etc.)
  - Per-slide element screenshot (no viewport clipping artifacts)
  - Configurable viewport size and output format
  - JSON result to stdout for programmatic consumption
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Slide CSS selectors to try, in priority order
_SLIDE_SELECTORS = ("section.slide", "section[class*='slide']", ".slide", "section")

# JS to inject before screenshot: force all slides into their "visible" state
# so that IntersectionObserver-driven animations (fade-up, etc.) are fully applied.
# Pitch-deck HTML uses `.slide.visible .fade-up { opacity:1 }` — without this,
# headless screenshots capture slides with opacity:0 (invisible text).
_FORCE_VISIBLE_JS = """
// Add .visible to all slides (triggers CSS animation final states)
document.querySelectorAll('section.slide, .slide').forEach(s => s.classList.add('visible'));
// Also force any other common animation trigger classes
document.querySelectorAll('[data-animate], .animate, .reveal, .fade-in').forEach(
  el => { el.classList.add('visible'); el.classList.add('active'); el.classList.add('shown'); }
);
"""

# Delay after forcing visible state, to let CSS transitions complete
# (pitch-deck uses transition: opacity 0.6s ease, so 700ms is safe)
_TRANSITION_SETTLE_MS = 700

# 等待 CDN 资源（字体/图片）加载的最长时间（ms）。超时则放弃等待（资源被墙/慢），
# 用已加载状态继续截图——避免 networkidle 在 CDN 不通时挂死连接超时。
_RESOURCE_LOAD_TIMEOUT_MS = 8000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_deps() -> None:
    """Print install hint if a dependency is missing."""
    missing = []
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        missing.append("playwright")
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    if missing:
        hint = "pip install " + " ".join(missing)
        if "playwright" in missing:
            hint += " && python3 -m playwright install chromium"
        print(
            f"Missing dependencies: {', '.join(missing)}\n"
            f"Install with: {hint}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Rendering & Stitching
# ---------------------------------------------------------------------------

def _render_slides(
    html_path: str,
    width: int = 1920,
    height: int = 1080,
    scale: float = 1.0,
) -> list[bytes]:
    """Render each slide section to PNG bytes via headless Chromium.

    Returns a list of PNG image bytes, one per slide.
    Raises RuntimeError on browser/render failures.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    abs_html = os.path.realpath(html_path)
    file_url = f"file://{abs_html}"

    images: list[bytes] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            page = context.new_page()
            # 本地 file:// HTML：先等 DOM 解析（必成功），再给 CDN 资源（字体/图片）
            # 最多 _RESOURCE_LOAD_TIMEOUT_MS 加载窗口——加载完则保真，超时（字体被墙/慢）
            # 则放弃等待用已加载状态继续。原 networkidle 在字体 CDN 不通时会等到连接超时挂死。
            page.goto(file_url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("load", timeout=_RESOURCE_LOAD_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                pass  # CDN 资源慢/不通；用当前已加载状态继续截图

            # Find the best selector that matches slides
            selector = _SLIDE_SELECTORS[0]
            slide_count = page.locator(selector).count()
            for alt in _SLIDE_SELECTORS[1:]:
                if slide_count > 0:
                    break
                selector = alt
                slide_count = page.locator(selector).count()

            if slide_count == 0:
                return []

            # Force all slides into visible/animated state before screenshot.
            # Without this, IntersectionObserver-driven animations (e.g. .fade-up
            # with initial opacity:0) remain in their pre-animation state in
            # headless mode, producing dim/invisible text in the output image.
            page.evaluate(_FORCE_VISIBLE_JS)
            page.wait_for_timeout(_TRANSITION_SETTLE_MS)

            # Capture each slide element
            for i in range(slide_count):
                el = page.locator(f"{selector} >> nth={i}")
                img_bytes = el.screenshot(type="png")
                images.append(img_bytes)
        finally:
            browser.close()

    return images


def _stitch_vertical(
    slide_images: list[bytes],
    output_path: str,
    fmt: str = "png",
    quality: int = 95,
    gap: int = 0,
) -> dict[str, Any]:
    """Stitch slide images vertically into one long image.

    Args:
        slide_images: List of PNG bytes, one per slide.
        output_path: Where to save the final image.
        fmt: Output format — "png" or "jpg".
        quality: JPEG quality (1–100), ignored for PNG.
        gap: Pixels of white/transparent gap between slides.

    Returns:
        Dict with dimensions and file info.
    """
    from PIL import Image as PILImage

    pil_images = []
    for img_bytes in slide_images:
        with PILImage.open(io.BytesIO(img_bytes)) as im:
            im.load()  # force full decode into memory
            pil_images.append(im.copy())

    if not pil_images:
        return {"ok": False, "error": "No slide images to stitch"}

    # Calculate total dimensions
    max_width = max(im.width for im in pil_images)
    total_height = sum(im.height for im in pil_images) + gap * (len(pil_images) - 1)

    # Create canvas — use RGBA if any slide has alpha
    has_alpha = any(im.mode in ("RGBA", "LA", "P") for im in pil_images)
    canvas_mode = "RGBA" if has_alpha else "RGB"
    canvas = PILImage.new(canvas_mode, (max_width, total_height))

    # Paste each slide
    y_offset = 0
    for im in pil_images:
        # Convert to match canvas mode if needed
        if im.mode != canvas_mode:
            im = im.convert(canvas_mode)
        # Center horizontally if widths differ
        x_offset = (max_width - im.width) // 2
        canvas.paste(im, (x_offset, y_offset))
        y_offset += im.height + gap

    # Save
    save_kwargs: dict[str, Any] = {}
    if fmt == "jpg":
        # JPEG doesn't support alpha — convert to RGB
        if canvas_mode == "RGBA":
            canvas = canvas.convert("RGB")
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    else:
        save_kwargs["compress_level"] = 6  # balance speed/size

    canvas.save(output_path, format="PNG" if fmt == "png" else "JPEG", **save_kwargs)

    return {
        "ok": True,
        "width": max_width,
        "height": total_height,
        "slide_count": len(pil_images),
        "file_size": os.path.getsize(output_path),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _save_per_slide(slide_images: list[bytes], output_dir: str, prefix: str = "slide") -> str:
    """Save per-slide PNG bytes to disk.

    Files are named: {prefix}_01.png, {prefix}_02.png, ...
    Returns the output directory path.
    """
    os.makedirs(output_dir, exist_ok=True)
    for i, img_bytes in enumerate(slide_images, start=1):
        filepath = os.path.join(output_dir, f"{prefix}_{i:02d}.png")
        with open(filepath, "wb") as f:
            f.write(img_bytes)
    return output_dir


def convert(
    html_path: str,
    output_path: str | None = None,
    width: int = 1920,
    height: int = 1080,
    scale: float = 1.0,
    fmt: str = "png",
    quality: int = 95,
    gap: int = 0,
    save_slides: bool = False,
    slides_dir: str | None = None,
) -> dict[str, Any]:
    """Convert an HTML pitch-deck to a long vertical image. Returns a result dict.

    Args:
        html_path: Path to the HTML pitch-deck file.
        output_path: Output image path (default: <name>-long.png).
        width: Viewport width in pixels.
        height: Viewport height in pixels.
        scale: Device scale factor for HiDPI.
        fmt: Output format — "png" or "jpg".
        quality: JPEG quality (1–100).
        gap: Pixels of gap between slides.
        save_slides: If True, save per-slide PNGs for reuse (e.g. by html_to_pptx.py).
        slides_dir: Directory for per-slide PNGs (default: <html_dir>/<name>-slides/).
    """
    # Validate input
    html_path = os.path.realpath(html_path)
    if not os.path.isfile(html_path):
        return {"ok": False, "error": f"File not found: {html_path}"}
    if not html_path.lower().endswith((".html", ".htm")):
        return {"ok": False, "error": f"Not an HTML file: {html_path}"}

    # Validate parameters
    if width < 100 or height < 100:
        return {"ok": False, "error": f"Viewport too small: {width}x{height} (min 100x100)"}
    if width > 7680 or height > 4320:
        return {"ok": False, "error": f"Viewport too large: {width}x{height} (max 7680x4320)"}
    if scale <= 0:
        return {"ok": False, "error": f"scale must be positive, got {scale}"}
    if scale > 4:
        return {"ok": False, "error": f"scale exceeds maximum (4), got {scale}"}
    if not 1 <= quality <= 100:
        return {"ok": False, "error": f"quality must be 1-100, got {quality}"}

    html_dir = os.path.dirname(html_path)
    base_name = os.path.splitext(os.path.basename(html_path))[0]

    if not output_path:
        ext = "jpg" if fmt == "jpg" else "png"
        output_path = os.path.join(html_dir, f"{base_name}-long.{ext}")
    else:
        output_path = os.path.abspath(output_path)

    # Step 1: Render each slide
    try:
        slide_images = _render_slides(html_path, width=width, height=height, scale=scale)
    except Exception as e:
        return {"ok": False, "error": f"Rendering failed: {e}"}

    if not slide_images:
        return {"ok": False, "error": "No slides found in HTML (expected <section class='slide'>)"}

    # Step 1.5: Optionally save per-slide screenshots
    saved_slides_dir: str | None = None
    if save_slides:
        if not slides_dir:
            slides_dir = os.path.join(html_dir, f"{base_name}-slides")
        saved_slides_dir = _save_per_slide(slide_images, slides_dir)

    # Step 2: Stitch vertically
    try:
        result = _stitch_vertical(slide_images, output_path, fmt=fmt, quality=quality, gap=gap)
    except Exception as e:
        return {"ok": False, "error": f"Stitching failed: {e}"}

    if not result.get("ok"):
        return result

    out: dict[str, Any] = {
        "ok": True,
        "html_file": html_path,
        "image_file": os.path.abspath(output_path),
        "slide_count": result["slide_count"],
        "width": result["width"],
        "height": result["height"],
        "file_size": result["file_size"],
        "viewport": f"{width}x{height}",
    }
    if saved_slides_dir:
        out["slides_dir"] = saved_slides_dir

    return out


def main() -> None:
    _ensure_deps()

    parser = argparse.ArgumentParser(
        description="Convert a pitch-deck HTML file to a long vertical image"
    )
    parser.add_argument("html", help="Path to the HTML pitch-deck file")
    parser.add_argument("-o", "--output", default=None, help="Output image path (default: <name>-long.png)")
    parser.add_argument("--width", type=int, default=1920, help="Viewport width in pixels (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Viewport height in pixels (default: 1080)")
    parser.add_argument("--scale", type=float, default=1.0, help="Device scale factor for HiDPI (default: 1.0)")
    parser.add_argument("--format", choices=["png", "jpg"], default="png", help="Output format (default: png)")
    parser.add_argument("--quality", type=int, default=95, help="JPEG quality 1-100 (default: 95)")
    parser.add_argument("--gap", type=int, default=0, help="Pixel gap between slides (default: 0)")
    parser.add_argument(
        "--save-slides", action="store_true",
        help="Save per-slide PNG screenshots for reuse (e.g. by html_to_pptx.py)",
    )
    parser.add_argument(
        "--slides-dir", default=None,
        help="Directory for per-slide PNGs (default: <html_dir>/<name>-slides/)",
    )
    args = parser.parse_args()

    result = convert(
        args.html,
        args.output,
        width=args.width,
        height=args.height,
        scale=args.scale,
        fmt=args.format,
        quality=args.quality,
        gap=args.gap,
        save_slides=args.save_slides,
        slides_dir=args.slides_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
