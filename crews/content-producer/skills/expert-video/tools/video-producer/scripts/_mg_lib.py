# -*- coding: utf-8 -*-
"""_mg_lib — motion-graphics 基础设施库（非子命令，wrapper 不暴露）。

收编自 three-year-search v4 已验证的 _v4_animlib：easing / 字体缓存 / 调色板 /
径向辉光 / 暗底网格 / 帧落盘 / 低载编码。所有函数无副作用（除显式落盘），
motion-graphics.py 与 _mg_templates.py 共用。
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------- 常量 ----------
DEFAULT_W, DEFAULT_H, DEFAULT_FPS = 1920, 1080, 25
FRAME_QUALITY = 92          # JPEG 帧质量（v4 验证值）
DUR_TOLERANCE = 0.12        # 成片时长 vs 计划容差（秒）

# 品牌调色板（spec 里可按名引用）
PALETTE = {
    "GREEN": (7, 193, 96),
    "CYAN": (53, 208, 255),
    "GOLD": (255, 194, 77),
    "RED": (255, 77, 94),
    "INK": (10, 17, 32),
    "WHITE": (240, 246, 255),
    "MUTED": (150, 165, 188),
}

# 旧渲染器沿用当前系统的中文字体；Windows 使用系统微软雅黑。
FONT_DIR_CANDIDATES = [
    "/usr/share/fonts/opentype/noto-sc",
    "/usr/share/fonts/opentype/noto",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/noto-cjk",
]
if os.name == 'nt':
    FONT_DIR_CANDIDATES.insert(0, str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'))
FONT_FILES = {
    "black": ["NotoSansSC-Black.otf", "NotoSansCJKsc-Black.otf", "msyhbd.ttc"],
    "bold": ["NotoSansSC-Bold.otf", "NotoSansCJKsc-Bold.otf", "msyhbd.ttc"],
    "med": ["NotoSansSC-Medium.otf", "NotoSansCJKsc-Medium.otf", "msyh.ttc"],
    "reg": ["NotoSansSC-Regular.otf", "NotoSansCJKsc-Regular.otf", "msyh.ttc"],
}


class MgError(Exception):
    """spec/环境错误，motion-graphics.py 捕获后按退出码约定退出。"""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# ---------- easing ----------
def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def seg(t: float, t0: float, t1: float) -> float:
    """t 在 [t0,t1] 窗口内的归一化进度（窗口外 0/1 饱和）。"""
    if t1 <= t0:
        return 1.0 if t >= t0 else 0.0
    return clamp((t - t0) / (t1 - t0))


def ease_linear(t: float) -> float:
    return clamp(t)


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_back(t: float, k: float = 1.6) -> float:
    t = clamp(t)
    t -= 1
    return 1 + t * t * ((k + 1) * t + k)


EASINGS = {
    "linear": ease_linear,
    "out_cubic": ease_out_cubic,
    "in_out": ease_in_out,
    "out_back": ease_out_back,
}


def get_ease(name: str):
    if name not in EASINGS:
        raise MgError(f"未知 easing: {name}（可选 {'/'.join(EASINGS)}）")
    return EASINGS[name]


def pulse(t: float, freq: float) -> float:
    """0→1→0 正弦脉冲（freq 为 Hz）。"""
    return 0.5 + 0.5 * math.sin(2 * math.pi * t * freq)


def rng(seed: int):
    """确定性伪随机数发生器（帧间稳定，粒子/数据流用）。"""
    state = seed

    def f() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return f


# ---------- 颜色 ----------
def parse_color(raw, default: tuple[int, int, int] | None = None):
    """spec 颜色：调色板名（"GREEN"）或 [r,g,b]。"""
    if raw is None:
        if default is not None:
            return default
        raise MgError("颜色缺失且无默认值")
    if isinstance(raw, str):
        key = raw.upper()
        if key not in PALETTE:
            raise MgError(f"未知颜色名: {raw}（可选 {'/'.join(PALETTE)} 或 [r,g,b]）")
        return PALETTE[key]
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        return tuple(int(c) for c in raw)
    raise MgError(f"颜色格式错误: {raw!r}（应为调色板名或 [r,g,b]）")


def with_alpha(color: tuple, alpha: int) -> tuple:
    return (color[0], color[1], color[2], int(clamp(alpha, 0, 255)))


# ---------- 字体 ----------
class FontBank:
    """字体缓存：四档字重（black/bold/med/reg），目录按候选序探测。"""

    def __init__(self, font_dir: str | None = None):
        self.dir = self._find_dir(font_dir)
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    @staticmethod
    def _find_dir(font_dir: str | None) -> Path:
        candidates = ([font_dir] if font_dir else []) + \
            ([os.environ["MG_FONT_DIR"]] if os.environ.get("MG_FONT_DIR") else []) + \
            FONT_DIR_CANDIDATES
        for cand in candidates:
            d = Path(cand)
            if d.is_dir() and any((d / f).is_file() for names in FONT_FILES.values() for f in names):
                return d
        raise MgError(
            "找不到中文字体目录（探测过: " + ", ".join(candidates) +
            "）；Linux/macOS 安装 Noto Sans CJK，Windows 检查微软雅黑，或在 spec 传 font_dir / 设 MG_FONT_DIR", code=2)

    def get(self, weight: str, size: int) -> ImageFont.FreeTypeFont:
        if weight not in FONT_FILES:
            raise MgError(f"未知字重: {weight}（可选 {'/'.join(FONT_FILES)}）")
        key = (weight, size)
        if key not in self._cache:
            for fname in FONT_FILES[weight]:
                p = self.dir / fname
                if p.is_file():
                    self._cache[key] = ImageFont.truetype(str(p), size)
                    return self._cache[key]
            raise MgError(f"字重 {weight} 在 {self.dir} 下无对应字体文件", code=2)
        return self._cache[key]


# ---------- 绘制基元 ----------
def vgrad(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """纵向渐变底。"""
    base = Image.new("RGB", (1, h))
    px = base.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (int(lerp(top[0], bottom[0], t)),
                    int(lerp(top[1], bottom[1], t)),
                    int(lerp(top[2], bottom[2], t)))
    return base.resize((w, h))


def radial_glow(size: int, color: tuple, max_alpha: int = 140) -> Image.Image:
    """软径向辉光 RGBA（中心亮、边缘透明）。"""
    g = Image.radial_gradient("L").resize((size, size))
    inv = g.point(lambda v: int(255 - v))
    layer = Image.new("RGBA", (size, size), (color[0], color[1], color[2], 0))
    layer.putalpha(inv.point(lambda v: int(v * max_alpha / 255)))
    return layer


def safe_composite(base: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """alpha_composite 的安全版：负坐标/超出画幅自动裁剪，完全在画外则跳过。

    PIL 的 alpha_composite 不接受负 dest 坐标；小画幅或元素越界时会炸，这里统一兜底。
    """
    x, y = int(x), int(y)
    if x >= base.width or y >= base.height:
        return
    if x < 0 or y < 0 or x + layer.width > base.width or y + layer.height > base.height:
        x0, y0 = max(0, -x), max(0, -y)
        x1, y1 = min(layer.width, base.width - x), min(layer.height, base.height - y)
        if x1 <= x0 or y1 <= y0:
            return
        layer = layer.crop((x0, y0, x1, y1))
        x, y = max(0, x), max(0, y)
    base.alpha_composite(layer, (x, y))


def paste_glow(base: Image.Image, center: tuple, size: int, color: tuple, alpha: int) -> None:
    gl = radial_glow(size, color, alpha)
    safe_composite(base, gl, int(center[0] - size / 2), int(center[1] - size / 2))


def dark_bg(w: int, h: int, grid: bool = True) -> Image.Image:
    """标准暗色科技底（纵向渐变 + 细网格），RGBA。"""
    img = vgrad(w, h, (9, 15, 28), (16, 27, 48)).convert("RGBA")
    if grid:
        d = ImageDraw.Draw(img)
        step = max(48, w // 20)
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=(255, 255, 255, 7))
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=(255, 255, 255, 7))
    return img


def text_shadow(d: ImageDraw.ImageDraw, xy: tuple, s: str, font,
                fill: tuple = (240, 246, 255, 255),
                anchor: str = "mm", shadow=(0, 0, 0, 180), off: int = 2) -> None:
    d.text((xy[0] + off, xy[1] + off), s, font=font, fill=shadow, anchor=anchor)
    d.text(xy, s, font=font, fill=fill, anchor=anchor)


def photo_circle(path: Path, size: int) -> Image.Image:
    """圆形裁剪头像 RGBA（4x 超采样抗锯齿）。"""
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    img.putalpha(mask)
    return img


def load_base_image(path: Path, w: int, h: int, fit: str = "fill",
                    dim: float = 0.0, blur: float = 0.0) -> Image.Image:
    """底图装载：fit=fill（拉满裁切）/ contain（保比黑边），可压暗与模糊。"""
    img = Image.open(path).convert("RGB")
    if fit == "fill":
        img = img.resize((w, h), Image.LANCZOS)
    elif fit == "contain":
        img.thumbnail((w, h), Image.LANCZOS)
        canvas = Image.new("RGB", (w, h), (0, 0, 0))
        canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
        img = canvas
    else:
        raise MgError(f"未知 background.fit: {fit}（可选 fill/contain）")
    if dim > 0:
        img = Image.eval(img, lambda v: int(v * (1 - clamp(dim, 0, 1))))
    if blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img


# ---------- 帧与编码 ----------
def nframes(dur: float, fps: float) -> int:
    return max(2, int(round(dur * fps)))


def save_frame_jpg(img: Image.Image, fdir: Path, idx: int) -> Path:
    p = fdir / f"f_{idx:04d}.jpg"
    img.convert("RGB").save(p, quality=FRAME_QUALITY)
    return p


def save_frame_png(img: Image.Image, fdir: Path, idx: int) -> Path:
    p = fdir / f"f_{idx:04d}.png"
    img.save(p)
    return p


def frame_exists(fdir: Path, idx: int) -> bool:
    for ext in (".jpg", ".png"):
        p = fdir / f"f_{idx:04d}{ext}"
        if p.is_file() and p.stat().st_size > 0:
            return True
    return False


def encode_frames(fdir: Path, out_mp4: Path, fps: float, crf: str, preset: str,
                  threads: str, nice: str | None, base_video: Path | None = None) -> None:
    """帧序列 → mp4（低载编码，tmp 落盘后原子替换）。

    base_video 传入时为 overlay 模式：帧序列须是 PNG（RGBA 覆盖层），
    与底视频用 ffmpeg overlay 合成。
    """
    pattern = "f_%04d.png" if base_video else "f_%04d.jpg"
    tmp = out_mp4.with_suffix(".tmp.mp4")
    cmd = (["nice", "-n", nice] if nice else []) + ["ffmpeg", "-y", "-v", "error"]
    if base_video:
        cmd += ["-i", str(base_video), "-framerate", str(fps), "-i", str(fdir / pattern),
                "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p",
                "-c:v", "libx264", "-crf", crf, "-preset", preset, "-threads", threads,
                "-an", str(tmp)]
    else:
        cmd += ["-framerate", str(fps), "-i", str(fdir / pattern),
                "-vf", "format=yuv420p",
                "-c:v", "libx264", "-crf", crf, "-preset", preset, "-threads", threads,
                str(tmp)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise MgError(f"编码失败 (rc={p.returncode}): {p.stderr[:500]}")
    os.replace(tmp, out_mp4)


def probe_duration(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        return 0.0
    try:
        return float(json.loads(p.stdout).get("format", {}).get("duration", 0) or 0)
    except (ValueError, json.JSONDecodeError):
        return 0.0


def probe_frame_rate(path: Path) -> str | None:
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return p.stdout.strip() or None


def probe_size(path: Path) -> tuple[int, int] | None:
    """探测成片宽×高。overlay 模式输出尺寸跟底视频走，spec 断言要用。"""
    p = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    out = p.stdout.strip()
    if not out:
        return None
    try:
        w, h = out.split(",")
        return (int(w), int(h))
    except (ValueError, IndexError):
        return None


def fit_video_blur_pad(src: Path, dst: Path, w: int, h: int, fps: float,
                       crf: str, preset: str, threads: str, nice: str | None,
                       start: float = 0.0, duration: float | None = None) -> Path:
    """竖版/异规格视频入横屏管线：模糊底放大裁切 + 前景等比居中叠加（v4 VF_PROD 已验证）。

    start/duration 同时完成裁段（-ss/-t），产物与帧序列等长。
    """
    if dst.is_file() and dst.stat().st_size > 0:
        return dst
    fg_h = h - 100  # 前景略小于画幅，四周露模糊底
    vf = (f"split=2[bg][fg];"
          f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=28[bg2];"
          f"[fg]scale=-2:{fg_h}[fg2];"
          f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={fps},format=yuv420p")
    cmd = (["nice", "-n", nice] if nice else []) + ["ffmpeg", "-y", "-v", "error"]
    if start > 0:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-filter_complex", vf,
            "-an", "-c:v", "libx264", "-crf", crf, "-preset", preset, "-threads", threads,
            str(dst)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise MgError(f"底视频归一失败 (rc={p.returncode}): {p.stderr[:500]}")
    return dst
