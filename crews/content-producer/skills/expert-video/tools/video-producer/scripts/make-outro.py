#!/usr/bin/env python3
"""Make an image-and-slogan outro with the shared HyperFrames visual renderer."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPTS = Path(__file__).resolve().parent
DECK_TOOL = SCRIPTS.parents[1] / 'deck-render'
sys.path.insert(0, str(DECK_TOOL / 'scripts'))
from font_policy import font_family


def run(command):
    result = subprocess.run([str(part) for part in command], check=False)
    if result.returncode:
        raise RuntimeError(f'{command[0]} 失败，退出码 {result.returncode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_dir', type=Path)
    parser.add_argument('--image', required=True)
    parser.add_argument('--slogan', required=True)
    parser.add_argument('--color', type=Path)
    parser.add_argument('--duration', type=float, default=5)
    parser.add_argument('--width', type=int, default=1080)
    parser.add_argument('--fps', type=int, default=30)
    parser.add_argument('--output', default='render/outro/outro.mp4')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    project = args.project_dir.resolve()
    source = Path(args.image)
    source = (source if source.is_absolute() else project / source).resolve()
    if not source.is_file() or source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        raise ValueError('需要存在的 PNG/JPEG/WebP 形象图')
    if not args.slogan.strip() or not math.isfinite(args.duration) or args.duration <= 0 or args.width < 360 or args.width % 2 or not 1 <= args.fps <= 60:
        raise ValueError('slogan 非空；时长 >0；宽度至少 360 且为偶数；fps 1–60')
    output = (project / args.output).resolve()
    if output.suffix.lower() != '.mp4' or output == source:
        raise ValueError('输出必须是独立的 .mp4 文件')
    if output.is_file() and not args.force:
        print(f'[checkpoint] 片尾已存在：{output}；修改后用 --force')
        return

    config = {'bg': '#000000', 'text': '#ffffff', 'font': font_family(), 'size': 48, 'fadein': .5}
    if args.color:
        color_file = args.color if args.color.is_absolute() else project / args.color
        config.update(json.loads(color_file.read_text(encoding='utf-8')))
    for key in ('bg', 'text'):
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}', str(config[key])):
            raise ValueError(f'color.{key} 须为 #RRGGBB')
    font_size, fade = int(config['size']), float(config['fadein'])
    if font_size < 1 or not math.isfinite(fade) or fade < 0 or fade > args.duration:
        raise ValueError('color.size 须为正数；fadein 须在片尾时长内')
    height = round(args.width * 9 / 16)
    if height % 2:
        height += 1

    composition = output.parent / f'{output.stem}.composition'
    assets = composition / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    gsap = DECK_TOOL / 'node_modules/gsap/dist/gsap.min.js'
    if not gsap.is_file():
        raise EnvironmentError('缺少锁定 GSAP 包，先运行 scripts/install-deck-render.sh')
    shutil.copy2(gsap, assets / 'gsap.min.js')
    asset_name = 'portrait' + source.suffix.lower()
    if source != (assets / asset_name).resolve():
        shutil.copy2(source, assets / asset_name)
    (composition / 'hyperframes.json').write_text(json.dumps({'paths': {'assets': 'assets'}, 'media': {'autoProxy': False}}, indent=2) + '\n')
    font_css = json.dumps(str(config['font']))
    (composition / 'index.html').write_text(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<script src="assets/gsap.min.js"></script><style>
@font-face {{ font-family:{font_css}; src:local({font_css}); }}
* {{ box-sizing:border-box; }} html,body {{ margin:0; width:{args.width}px; height:{height}px; overflow:hidden; background:{config['bg']}; }}
#stage {{ position:relative; width:{args.width}px; height:{height}px; background:{config['bg']}; }}
img {{ position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }}
#slogan {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font:{font_size}px {font_css}, sans-serif; color:{config['text']}; text-align:center; padding:40px; }}
</style></head><body><div id="stage" data-composition-id="main" data-start="0"
data-duration="{args.duration}" data-width="{args.width}" data-height="{height}" data-fps="{args.fps}">
<img src="assets/{asset_name}" alt="portrait"><div id="slogan">{html.escape(args.slogan)}</div></div>
<script>const tl=gsap.timeline({{paused:true}});
tl.fromTo('#slogan',{{opacity:0}},{{opacity:1,duration:{max(.05, fade)}}},0);
window.__timelines=window.__timelines||{{}};window.__timelines.main=tl;</script></body></html>''', encoding='utf-8')

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.outro-', dir=output.parent) as temp:
        silent_video = Path(temp) / 'video.mp4'
        candidate = Path(temp) / 'with-audio.mp4'
        run([sys.executable, SCRIPTS / 'visual-render.py', 'render', composition,
             '--output', silent_video, '--workers', 1, '--quality', 'looks'])
        run([sys.executable, SCRIPTS / 'add-silent-audio.py', '--input', silent_video,
             '--output', candidate, '--duration', args.duration])
        candidate.replace(output)
    print(json.dumps({'output': str(output), 'composition': str(composition),
                      'width': args.width, 'height': height, 'fps': args.fps,
                      'duration': args.duration, 'font': config['font']}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, EnvironmentError, subprocess.TimeoutExpired) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
