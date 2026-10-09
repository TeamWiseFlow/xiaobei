#!/usr/bin/env python3
"""motion-graphics — 旧 JSON/Pillow 逐帧动态图形兼容入口。

新项目使用 `video-producer visual-render scaffold/check/preview/render` 的
HTML/GSAP + HyperFrames 路径；这里的 JSON spec 只用于已制作的旧项目。

声明式 JSON spec 驱动 PIL 逐帧绘制 + ffmpeg 低载编码，只产出**单个**动态图形片段
clip.mp4（默认 1920x1080@25fps，帧级 checkpoint + 时长/帧率校验）。
不做拼接、不做混音、不做字幕——那是 assemble / audio-mix / burn-srt 的活。

Usage:
  python3 scripts/motion-graphics.py <project_dir> --spec slots/mg-s17.json
  python3 scripts/motion-graphics.py <project_dir> --spec slots/mg-s17.json --out render/v4/s17/clip.mp4
  python3 scripts/motion-graphics.py <project_dir> --spec slots/mg-s19.json --force

spec.json 结构（路径相对 spec 文件或绝对；颜色可写调色板名 GREEN/CYAN/GOLD/RED/INK/WHITE/MUTED 或 [r,g,b]）：
  {
    "duration": 5.2,                    // 必填（或 CLI --duration 覆盖）
    "fps": 25, "width": 1920, "height": 1080,
    "font_dir": null,                   // 可选：中文字体目录覆盖；Windows 可用系统微软雅黑
    "background": {"type": "dark_grid"}                       // 暗色科技底（默认）
                  | {"type": "gradient", "top": [r,g,b], "bottom": [r,g,b], "grid": false}
                  | {"type": "image", "path": "...", "fit": "fill"|"contain", "dim": 0.42, "blur": 3}
                  | {"type": "video", "path": "...", "start": 0, "fit": "blur_pad"|"none"},
    // 二选一：
    "template": "dimension_grid|scroll_cards|crew_panel|rec_highlight", "params": {...},
    "elements": [ {...}, ... ]          // 基础元素按序叠画（z 序 = 数组序）
  }

基础元素公共字段（enter/exit/pulse 均可选）：
  "enter": {"at": 0.5, "dur": 0.55, "anim": "fade|rise|rise_back|scale_in", "ease": "out_cubic|out_back|in_out|linear", "dy": 130}
  "exit":  {"at": 4.0, "dur": 0.5, "anim": "fade|sink", "dy": 50}
  "pulse": {"freq": 1.4, "amount": 0.25, "on": "color|outline"}

元素类型：
  text           {"text","x","y","font":"black|bold|med|reg","size":60,"color","anchor":"mm","shadow":true}
  card           {"x","y","w","h","radius":28,"fill":[22,30,52],"fill_alpha":235,"outline","outline_width":3,
                  "bar":true,"title","title_font":"bold","title_size":56,"sub":[行],"sub_size":34}   // x,y=左上角
  photo_circle   {"path","x","y","size":160,"ring":"GREEN","ring_width":4}                            // x,y=圆心
  glow           {"x","y","size":600,"color":"GREEN","alpha":60}                                     // x,y=中心
  band           {"image","x":0,"y":0}                     // 整幅叠加图（如绿横带 PNG），透明度走 enter
  highlight_zone {"box":[x0,y0,x1,y1],"label","dim":110,"zone_color","corner_color","radius":26}
  progress_bar   {"x","y","w","h":12,"color":"GREEN","from":0.5,"to":null}       // to 缺省 = duration-0.4
  custom         {"plugin":"draw_x.py","params":{...}}     // 逃生舱：plugin 暴露 draw(img, t, ctx)，
                                                            // ctx 含 params/fonts/lib/w/h/fps/dur/state/spec_dir；
                                                            // 编码/checkpoint/时长校验仍在本子命令，plugin 只画帧

模板 params 详见 _mg_templates.py 各 prepare_*（四件套收编自 v4 已验证组件）。
rec_highlight 模板必须配 background.type=video；其余模板/元素配非 video 底或 video 底均可
（video 底自动走覆盖层合成：元素画 PNG 透明层，ffmpeg overlay 到底视频）。

checkpoint：<out>/frames/ 帧已存在即跳过重画（断点续渲）；clip.mp4 已存在整段跳过。
改了 spec 必须 --force 全量重渲（帧目录一并清掉）。
退出码：0 成功 / 1 spec 或参数错 / 2 环境缺失（字体、ffmpeg）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# New visual work uses the shared HyperFrames renderer. Keep the historical
# JSON/Pillow path callable for already authored projects until they migrate.
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in {"scaffold", "check", "preview", "render"}:
    os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name("visual-render.py")), *sys.argv[1:]])

import argparse
import importlib.util
import json
import shutil
import subprocess

import _mg_lib as L
import _mg_templates as T
from PIL import Image, ImageDraw

ELEMENT_TYPES = {"text", "card", "photo_circle", "glow", "band",
                 "highlight_zone", "progress_bar", "custom"}
# 每类元素的必填字段（load_spec 统一 die，避免渲到一半 KeyError 或静默不画）
REQUIRED_FIELDS = {
    "text": ("text", "x", "y"),
    "card": ("x", "y", "w", "h"),
    "photo_circle": ("path", "x", "y"),
    "glow": ("x", "y"),
    "band": ("image",),
    "highlight_zone": ("box",),
    "progress_bar": ("x", "y", "w"),
    "custom": ("plugin",),
}
FRAME_TEMPLATES = {name for name, (_, _, mode) in T.TEMPLATES.items() if mode == "frame"}


def die(msg: str, code: int = 1) -> None:
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(code)


def resolve_from(raw, base_dir: Path) -> Path:
    p = Path(str(raw))
    return p if p.is_absolute() else base_dir / p


# ============================================================ spec 装载与校验
def load_spec(spec_path: Path, cli_duration: float | None) -> dict:
    if not spec_path.is_file():
        die(f"spec 不存在: {spec_path}")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"spec 不是合法 JSON: {spec_path}（{e}）")
    if cli_duration is not None:
        spec["duration"] = cli_duration
    if not spec.get("duration") or float(spec["duration"]) <= 0:
        die("spec.duration 必填且 > 0（秒），或 CLI 传 --duration")
    has_tpl = "template" in spec
    has_els = "elements" in spec
    if has_tpl == has_els:
        die("spec 必须且只能给 template 或 elements 之一")
    if has_tpl and spec["template"] not in T.TEMPLATES:
        die(f"未知模板: {spec['template']}（可选 {'/'.join(T.TEMPLATES)}）")
    if has_els:
        if not isinstance(spec["elements"], list) or not spec["elements"]:
            die("spec.elements 必须是非空列表")
        for i, el in enumerate(spec["elements"]):
            if not isinstance(el, dict) or el.get("type") not in ELEMENT_TYPES:
                die(f"elements[{i}] 未知类型: {el.get('type') if isinstance(el, dict) else el!r}"
                    f"（可选 {'/'.join(sorted(ELEMENT_TYPES))}）")
            missing = [f for f in REQUIRED_FIELDS[el["type"]] if f not in el]
            if missing:
                die(f"elements[{i}]（{el['type']}）缺必填字段: {'/'.join(missing)}")
    bg = spec.get("background") or {"type": "dark_grid"}
    if bg.get("type") not in ("dark_grid", "gradient", "image", "video"):
        die(f"未知 background.type: {bg.get('type')}（可选 dark_grid/gradient/image/video）")
    if has_tpl and spec["template"] == "rec_highlight" and bg.get("type") != "video":
        die("rec_highlight 模板必须配 background.type=video（圈选高亮叠在录屏底上）")
    if has_tpl and spec["template"] in FRAME_TEMPLATES and bg.get("type") == "video":
        die(f"{spec['template']} 是满帧模板，不能配 video 底（要叠录屏用 rec_highlight 或 elements）")
    if bg.get("type") in ("image", "video"):
        if not bg.get("path"):
            die(f"background.type={bg['type']} 必须给 path")
    return spec


def load_plugin(el: dict, spec_dir: Path):
    """custom 元素逃生舱：按路径加载 plugin 模块，校验 draw 可调用。"""
    if not el.get("plugin"):
        die("custom 元素必须给 plugin 路径")
    p = resolve_from(el["plugin"], spec_dir)
    if not p.is_file():
        die(f"custom plugin 不存在: {p}")
    mod_spec = importlib.util.spec_from_file_location(f"mg_plugin_{p.stem}", p)
    if mod_spec is None or mod_spec.loader is None:
        die(f"custom plugin 必须是可加载的 .py 文件: {p}")
    mod = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    if not callable(getattr(mod, "draw", None)):
        die(f"custom plugin 必须暴露 draw(img, t, ctx): {p}")
    return mod


# ============================================================ 动画状态
def pulse_mod(el: dict, t: float) -> float:
    """pulse 振荡值 0..1（无 pulse 恒 0）。"""
    pl = el.get("pulse")
    return L.pulse(t, float(pl["freq"])) if pl else 0.0


def pulse_amount(el: dict) -> float:
    pl = el.get("pulse") or {}
    return float(pl.get("amount", 0.25))


# ============================================================ 元素绘制
def draw_text(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    fonts = ctx["fonts"]
    text = str(el.get("text", ""))
    if not text or a <= 0:
        return
    font = fonts.get(el.get("font", "bold"), int(el.get("size", 60)))
    color = L.parse_color(el.get("color", "WHITE"))
    osc = pulse_mod(el, t)
    if (el.get("pulse") or {}).get("on", "color") == "color" and osc:
        m = L.lerp(1 - pulse_amount(el), 1.0, osc)
        color = tuple(int(c * m) for c in color)
    fill = L.with_alpha(color, 255 * a)
    x, y = float(el["x"]), float(el["y"]) + dy
    if abs(sc - 1.0) > 0.001:
        # scale_in：画到临时层再缩放（v4 s16 已验证做法）
        bbox = font.getbbox(text)
        tw, th = bbox[2] - bbox[0] + 40, bbox[3] - bbox[1] + 40
        layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        dl = ImageDraw.Draw(layer)
        anchor = el.get("anchor", "mm")
        dl.text((tw / 2, th / 2), text, font=font, fill=fill, anchor=anchor)
        layer = layer.resize((max(1, int(tw * sc)), max(1, int(th * sc))), Image.LANCZOS)
        L.safe_composite(img, layer, int(x - layer.width / 2), int(y - layer.height / 2))
    else:
        d = ImageDraw.Draw(img)
        if el.get("shadow", True):
            shadow = (0, 0, 0, int(180 * a))
            d.text((x + 2, y + 2), text, font=font, fill=shadow, anchor=el.get("anchor", "mm"))
        d.text((x, y), text, font=font, fill=fill, anchor=el.get("anchor", "mm"))


def draw_card(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    if a <= 0:
        return
    fonts = ctx["fonts"]
    x, y = float(el["x"]), float(el["y"]) + dy
    w, h = int(el["w"]), int(el["h"])
    radius = int(el.get("radius", 28))
    fill = L.with_alpha(L.parse_color(el.get("fill", [22, 30, 52])),
                        int(el.get("fill_alpha", 235)) * a)
    outline = L.parse_color(el.get("outline", "CYAN"))
    ow = int(el.get("outline_width", 3))
    osc = pulse_mod(el, t)
    if (el.get("pulse") or {}).get("on") == "outline" and osc:
        ow_a = int((160 + 90 * osc) * a)
    else:
        ow_a = int(255 * a)
    if abs(sc - 1.0) > 0.001:
        w, h = int(w * sc), int(h * sc)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill,
                        outline=L.with_alpha(outline, ow_a), width=ow)
    if el.get("bar", True):
        d.rounded_rectangle([28, 30, w - 28, 44], radius=7,
                            fill=L.with_alpha(outline, int(220 * a)))
    title = el.get("title")
    if title:
        tsize = int(el.get("title_size", 56))
        ty = 150 if h >= 400 else h * 0.34
        d.text((w / 2, ty), str(title), font=fonts.get(el.get("title_font", "bold"), tsize),
               fill=L.with_alpha(L.PALETTE["WHITE"], 255 * a), anchor="mm")
    sub = el.get("sub")
    if sub:
        lines = sub if isinstance(sub, list) else [sub]
        ssize = int(el.get("sub_size", 34))
        sy = (326 if h >= 400 else h * 0.58)
        for ln in lines:
            d.text((w / 2, sy), str(ln), font=fonts.get("med", ssize),
                   fill=L.with_alpha((168, 182, 205), 255 * a), anchor="mm")
            sy += ssize * 1.53
    L.safe_composite(img, card, int(x), int(y))


def draw_photo_circle(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    if a <= 0:
        return
    key = f"photo:{el['path']}:{el.get('size', 160)}"
    if key not in ctx["state"]:
        p = resolve_from(el["path"], ctx["spec_dir"])
        if not p.is_file():
            die(f"photo_circle 图片不存在: {p}")
        ctx["state"][key] = L.photo_circle(p, int(el.get("size", 160)))
    ph = ctx["state"][key]
    if a < 1.0:
        ph = ph.copy()
        ph.putalpha(ph.getchannel("A").point(lambda v: int(v * a)))
    size = ph.width
    x, y = float(el["x"]), float(el["y"]) + dy
    L.safe_composite(img, ph, int(x - size / 2), int(y - size / 2))
    ring = el.get("ring")
    if ring:
        d = ImageDraw.Draw(img)
        d.ellipse([x - size / 2 - 6, y - size / 2 - 6,
                   x + size / 2 + 6, y + size / 2 + 6],
                  outline=L.with_alpha(L.parse_color(ring), 255 * a),
                  width=int(el.get("ring_width", 4)))


def draw_glow(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    if a <= 0:
        return
    alpha = float(el.get("alpha", 60)) * a
    osc = pulse_mod(el, t)
    if osc and (el.get("pulse") or {}).get("on", "glow") in ("glow", "alpha"):
        alpha *= 1 + pulse_amount(el) * osc
    L.paste_glow(img, (float(el["x"]), float(el["y"]) + dy), int(el.get("size", 600)),
                 L.parse_color(el.get("color", "GREEN")), int(alpha))


def draw_band(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    if a <= 0:
        return
    key = f"band:{el['image']}"
    if key not in ctx["state"]:
        p = resolve_from(el["image"], ctx["spec_dir"])
        if not p.is_file():
            die(f"band 图片不存在: {p}")
        band = Image.open(p).convert("RGBA")
        if band.size != (ctx["w"], ctx["h"]):
            band = band.resize((ctx["w"], ctx["h"]), Image.LANCZOS)
        ctx["state"][key] = band
    band = ctx["state"][key]
    if a < 1.0:
        band = band.copy()
        band.putalpha(band.getchannel("A").point(lambda v: int(v * a)))
    L.safe_composite(img, band, int(el.get("x", 0)), int(el.get("y", 0) + dy))


def draw_highlight_zone(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    """静态单窗圈选（复用 rec_highlight 模板绘制逻辑，zones=[box]；enter 只控出现/消失）。"""
    if "box" not in el:
        die("highlight_zone 缺 box 字段（load_spec 应已拦截）")
    if a <= 0:
        return
    key = f"_hz:{id(el)}"
    if key not in ctx["state"]:
        params = {
            "zones": [el["box"]], "label": el.get("label", ""),
            "zone_color": el.get("zone_color", "CYAN"),
            "corner_color": el.get("corner_color", "GREEN"),
            "dim": el.get("dim", 110), "radius": el.get("radius", 26),
        }
        ctx["state"][key] = T.prepare_rec_highlight(params, ctx)
    T.draw_rec_highlight(img, t, ctx["state"][key], ctx)


def draw_progress_bar(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    if a <= 0:
        return
    d = ImageDraw.Draw(img)
    x, y, w = float(el["x"]), float(el["y"]) + dy, int(el["w"])
    h = int(el.get("h", 12))
    frm = float(el.get("from", 0.0))
    to = float(el.get("to", ctx["dur"] - 0.4))
    color = L.parse_color(el.get("color", "GREEN"))
    track = L.parse_color(el.get("track", [40, 52, 74]))
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2,
                        fill=L.with_alpha(track, 255 * a))
    prog = L.seg(t, frm, to)
    if prog > 0:
        d.rounded_rectangle([x, y, x + int(w * prog), y + h], radius=h // 2,
                            fill=L.with_alpha(color, 255 * a))


def draw_custom(img: Image.Image, el: dict, t: float, ctx: dict, a: float, dy: float, sc: float) -> None:
    key = f"plugin:{el['plugin']}"
    if key not in ctx["state"]:
        ctx["state"][key] = load_plugin(el, ctx["spec_dir"])
    pctx = {**ctx, "params": el.get("params") or {}, "alpha": a}
    ctx["state"][key].draw(img, t, pctx)


ELEMENT_DRAWERS = {
    "text": draw_text,
    "card": draw_card,
    "photo_circle": draw_photo_circle,
    "glow": draw_glow,
    "band": draw_band,
    "highlight_zone": draw_highlight_zone,
    "progress_bar": draw_progress_bar,
    "custom": draw_custom,
}


# ============================================================ 背景
def build_background_frame(spec: dict, ctx: dict) -> Image.Image:
    """非 video 底的每帧底图（RGBA）。"""
    bg = spec.get("background") or {"type": "dark_grid"}
    w, h = ctx["w"], ctx["h"]
    btype = bg["type"]
    if btype == "dark_grid":
        return L.dark_bg(w, h, grid=bool(bg.get("grid", True)))
    if btype == "gradient":
        top = L.parse_color(bg.get("top", [9, 15, 28]))
        bottom = L.parse_color(bg.get("bottom", [16, 27, 48]))
        img = L.vgrad(w, h, top, bottom).convert("RGBA")
        if bg.get("grid"):
            d = ImageDraw.Draw(img)
            step = max(48, w // 20)
            for x in range(0, w, step):
                d.line([(x, 0), (x, h)], fill=(255, 255, 255, 7))
            for y in range(0, h, step):
                d.line([(0, y), (w, y)], fill=(255, 255, 255, 7))
        return img
    if btype == "image":
        key = "_bg_image"
        if key not in ctx["state"]:
            p = resolve_from(bg["path"], ctx["spec_dir"])
            if not p.is_file():
                die(f"background 图片不存在: {p}")
            ctx["state"][key] = L.load_base_image(
                p, w, h, fit=bg.get("fit", "fill"),
                dim=float(bg.get("dim", 0)), blur=float(bg.get("blur", 0)))
        return ctx["state"][key].copy().convert("RGBA")
    raise L.MgError(f"build_background_frame 不该收到 background.type={btype}")


def prepare_base_video(spec: dict, ctx: dict, work_dir: Path, enc: dict) -> Path:
    """video 底预处理：裁到 (start, duration)，fit=blur_pad 时归一到目标画幅。产物即 checkpoint。"""
    bg = spec["background"]
    src = resolve_from(bg["path"], ctx["spec_dir"])
    if not src.is_file():
        die(f"background 视频不存在: {src}")
    prepped = work_dir / "base_prepped.mp4"
    if prepped.is_file() and prepped.stat().st_size > 0:
        print(f"[checkpoint] 底视频已处理：{prepped}")
        return prepped
    start = float(bg.get("start", 0))
    fit = bg.get("fit", "blur_pad")
    if fit == "blur_pad":
        L.fit_video_blur_pad(src, prepped, ctx["w"], ctx["h"], ctx["fps"],
                             enc["crf"], enc["preset"], enc["threads"], enc["nice"],
                             start=start, duration=ctx["dur"])
    elif fit == "none":
        cmd = (["nice", "-n", enc["nice"]] if enc.get("nice") else []) + \
            ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(src),
             "-t", f"{ctx['dur']:.3f}", "-an",
             "-c:v", "libx264", "-crf", enc["crf"], "-preset", enc["preset"],
             "-threads", enc["threads"], str(prepped)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            die(f"底视频裁剪失败: {p.stderr[:500]}")
    else:
        die(f"未知 background.fit: {fit}（video 底可选 blur_pad/none）")
    print(f"[prep] 底视频就绪：{prepped}")
    return prepped


# ============================================================ 主流程
def render(spec: dict, ctx: dict, out: Path, enc: dict, force: bool) -> None:
    work_dir = out.parent
    fdir = work_dir / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    if force:
        shutil.rmtree(fdir, ignore_errors=True)
        fdir.mkdir(parents=True, exist_ok=True)
        work_dir.joinpath("base_prepped.mp4").unlink(missing_ok=True)

    w, h, fps, dur = ctx["w"], ctx["h"], ctx["fps"], ctx["dur"]
    n = L.nframes(dur, fps)
    bg_type = (spec.get("background") or {"type": "dark_grid"})["type"]
    overlay_mode = bg_type == "video"

    base_video = None
    if overlay_mode:
        base_video = prepare_base_video(spec, ctx, work_dir, enc)

    # 模板 prepare（校验 + 补默认值；frame 模板配 video 底已在 load_spec 拒绝）
    tpl_draw = None
    tpl_params = None
    if "template" in spec:
        prepare, tpl_draw, mode = T.TEMPLATES[spec["template"]]
        if mode == "overlay" and not overlay_mode:
            die(f"模板 {spec['template']} 需要 video 底")
        tpl_params = prepare(spec.get("params") or {}, ctx)

    skipped = 0
    for i in range(n):
        if L.frame_exists(fdir, i):
            skipped += 1
            continue
        t = i / fps
        if overlay_mode:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        else:
            img = build_background_frame(spec, ctx)
        if tpl_draw is not None:
            tpl_draw(img, t, tpl_params, ctx)
        for el in spec.get("elements") or []:
            a, dy, sc = element_anim(el, t)
            if a <= 0.004:
                continue
            ELEMENT_DRAWERS[el["type"]](img, el, t, ctx, a, dy, sc)
        if overlay_mode:
            L.save_frame_png(img, fdir, i)
        else:
            L.save_frame_jpg(img, fdir, i)
    if skipped:
        print(f"[checkpoint] 复用已渲帧 {skipped}/{n}")

    print(f"[encode] {n} 帧 → {out}（{w}x{h}@{fps}，crf {enc['crf']}/{enc['preset']}/threads {enc['threads']}）")
    L.encode_frames(fdir, out, fps, enc["crf"], enc["preset"], enc["threads"],
                    enc["nice"], base_video=base_video)

    # 规格断言：时长 ± 容差、帧率一致、分辨率一致
    # （overlay 模式输出尺寸跟底视频走：fit=none 且底视频非目标画幅时圈选坐标会全错位）
    actual = L.probe_duration(out)
    if abs(actual - dur) > L.DUR_TOLERANCE:
        die(f"成片时长校验失败：实测 {actual:.3f}s vs 计划 {dur:.3f}s（容差 ±{L.DUR_TOLERANCE}s）")
    size = L.probe_size(out)
    if size != (w, h):
        die(f"成片分辨率校验失败：实测 {size[0]}x{size[1]} vs spec {w}x{h}"
            f"（video 底 fit=none 时底视频须已是目标画幅，否则用 blur_pad）")
    if float(fps).is_integer():
        afr = L.probe_frame_rate(out)
        want = f"{int(fps)}/1"
        if afr != want:
            die(f"成片帧率校验失败：avg_frame_rate={afr}，期望 {want}")
    print(f"[done] {out}（{actual:.3f}s {w}x{h}@{fps}，校验通过）")


def element_anim(el: dict, t: float) -> tuple[float, float, float]:
    """(alpha, dy, scale)——enter/exit 求值，pulse 由各 drawer 自取。"""
    alpha, dy, scale = 1.0, 0.0, 1.0
    enter = el.get("enter") or {}
    ex = el.get("exit") or {}
    at, adur = float(enter.get("at", 0.0)), float(enter.get("dur", 0.0))
    anim = enter.get("anim", "none")
    if anim != "none":
        ease = L.get_ease(enter.get("ease", "out_back" if anim == "rise_back" else "out_cubic"))
        p = ease(L.seg(t, at, at + adur)) if adur > 0 else (1.0 if t >= at else 0.0)
        alpha *= p
        if anim in ("rise", "rise_back"):
            dy += (1 - p) * float(enter.get("dy", 130))
        elif anim == "scale_in":
            scale = L.lerp(float(enter.get("scale_from", 0.85)), 1.0, p)
    elif "at" in enter:
        alpha *= 1.0 if t >= at else 0.0
    if ex:
        xat, xdur = float(ex.get("at", 0.0)), float(ex.get("dur", 0.5))
        p2 = L.get_ease(ex.get("ease", "out_cubic"))(L.seg(t, xat, xat + xdur))
        alpha *= (1 - p2)
        if ex.get("anim") == "sink":
            dy += p2 * float(ex.get("dy", 50))
    return L.clamp(alpha, 0.0, 1.0), dy, scale


def main() -> None:
    parser = argparse.ArgumentParser(description="motion-graphics 程序化逐帧动态图形渲染")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--spec", required=True, help="声明式 spec JSON（相对 project_dir 或绝对路径）")
    parser.add_argument("--out", default=None,
                        help="输出 clip 路径（默认 render/mg/<spec-stem>/clip.mp4，相对 project_dir 或绝对）")
    parser.add_argument("--duration", type=float, default=None, help="覆盖 spec.duration（秒）")
    parser.add_argument("--force", action="store_true", help="清帧全量重渲（改 spec 后必须）")
    parser.add_argument("--crf", default="18", help="x264 crf（默认 18，低载验证值）")
    parser.add_argument("--preset", default="veryfast", help="x264 preset（默认 veryfast）")
    parser.add_argument("--threads", default="2", help="编码线程（默认 2，共享机器低载）")
    parser.add_argument("--nice", default="19", help="nice 优先级（默认 19；传 0 关闭）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if not project.is_dir():
        die(f"项目目录不存在: {project}")
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            die(f"缺 {binary}（motion-graphics 依赖 ffmpeg 全套）", code=2)
    spec_path = resolve_from(args.spec, project).resolve()
    spec_dir = spec_path.parent

    try:
        spec = load_spec(spec_path, args.duration)
        w = int(spec.get("width", L.DEFAULT_W))
        h = int(spec.get("height", L.DEFAULT_H))
        fps = float(spec.get("fps", L.DEFAULT_FPS))
        dur = float(spec["duration"])
        fonts = L.FontBank(spec.get("font_dir"))
        ctx = {"w": w, "h": h, "fps": fps, "dur": dur,
               "fonts": fonts, "lib": L, "state": {}, "spec_dir": spec_dir}

        if args.out:
            out = resolve_from(args.out, project)
        else:
            out = project / "render" / "mg" / spec_path.stem / "clip.mp4"
        out = out.resolve()
        if out.suffix.lower() != ".mp4":
            die(f"--out 必须是 .mp4: {out}")

        if out.is_file() and out.stat().st_size > 0 and not args.force:
            print(f"[checkpoint] clip 已存在：{out}（改了 spec 要 --force 重渲）")
            return

        enc = {"crf": args.crf, "preset": args.preset, "threads": args.threads,
               "nice": args.nice if args.nice not in ("0", "None", "") else None}
        out.parent.mkdir(parents=True, exist_ok=True)
        render(spec, ctx, out, enc, args.force)
    except L.MgError as e:
        die(str(e), code=e.code)

    print(f"[next] 片段作为段进拼接清单：assemble --manifest（显式段清单）；"
          f"响度/字幕/混音归各自子命令，不在本工具内联")


if __name__ == "__main__":
    main()
