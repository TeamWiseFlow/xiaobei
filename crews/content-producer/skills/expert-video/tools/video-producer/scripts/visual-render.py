#!/usr/bin/env python3
"""Scaffold and render an HTML/GSAP visual clip with the pinned HyperFrames runtime."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

DECK_TOOL = Path(__file__).resolve().parents[2] / 'deck-render'
sys.path.insert(0, str(DECK_TOOL / 'scripts'))
from font_policy import font_css, font_family


def positive_int(raw):
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError('须为正整数')
    return value


def positive_seconds(raw):
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('时长须为有限正数')
    return value


def scaffold(project, width, height, fps, duration, background):
    if width < 360 or height < 360 or width % 2 or height % 2 or fps > 60:
        raise ValueError('宽高至少 360 且为偶数；fps 范围 1–60')
    if not background.startswith('#') or len(background) != 7 or any(c not in '0123456789abcdefABCDEF' for c in background[1:]):
        raise ValueError('background 须为 #RRGGBB')
    gsap = DECK_TOOL / 'node_modules/gsap/dist/gsap.min.js'
    if not gsap.is_file():
        raise EnvironmentError('缺少锁定 GSAP 包，先运行 scripts/install-deck-render.sh')
    if project.exists() and any(project.iterdir()):
        raise ValueError('目标目录非空；scaffold 不覆盖已有画面')
    (project / 'assets').mkdir(parents=True, exist_ok=True)
    shutil.copy2(gsap, project / 'assets/gsap.min.js')
    family = font_family()
    (project / 'index.html').write_text(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<script src="assets/gsap.min.js"></script><style>
{font_css()}
* {{ box-sizing:border-box; }} html,body {{ margin:0; width:{width}px; height:{height}px; overflow:hidden; background:{background}; font-family:'{family}',sans-serif; }}
#stage {{ position:relative; width:{width}px; height:{height}px; overflow:hidden; background:{background}; }}
/* 在 stage 内放独立素材层，用绝对坐标和 GSAP 时间轴定义逐件入场。 */
</style></head><body>
<div id="stage" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{width}" data-height="{height}" data-fps="{fps}">
<!-- 在此加入 img、SVG、文字或纸片元素；素材放 assets/，勿引用外部 URL。 -->
</div><script>
const tl = gsap.timeline({{paused:true}});
window.__timelines = window.__timelines || {{}};
window.__timelines.main = tl;
</script></body></html>''', encoding='utf-8')
    (project / 'hyperframes.json').write_text(json.dumps({'paths': {'assets': 'assets'}, 'media': {'autoProxy': False}}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sc = sub.add_parser('scaffold', help='建立空白 HTML/GSAP 视觉片段项目')
    sc.add_argument('project', type=Path)
    sc.add_argument('--width', type=positive_int, default=1920)
    sc.add_argument('--height', type=positive_int, default=1080)
    sc.add_argument('--fps', type=positive_int, default=25)
    sc.add_argument('--duration', type=positive_seconds, default=5)
    sc.add_argument('--background', default='#0a1120')
    for name in ('check', 'preview', 'render'):
        command = sub.add_parser(name)
        command.add_argument('project', type=Path)
        if name != 'check':
            command.add_argument('--output', required=True, type=Path)
        if name == 'preview':
            command.add_argument('--at', help='逗号分隔的截图时间点')
        if name == 'render':
            command.add_argument('--quality', choices=('draft', 'looks', 'delivery'), default='delivery')
            command.add_argument('--workers', type=int, default=2)
            command.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if args.command == 'scaffold':
        project = args.project.resolve()
        scaffold(project, args.width, args.height, args.fps, args.duration, args.background)
        print(json.dumps({'project': str(project), 'duration': args.duration, 'width': args.width,
                          'height': args.height, 'fps': args.fps, 'font': font_family()}))
        return
    if not (args.project / 'index.html').is_file():
        raise ValueError('缺少 composition/index.html')
    wrapper = str(DECK_TOOL / 'deck-render.sh')
    command = [wrapper, args.command, str(args.project.resolve())]
    if args.command != 'check':
        command += ['--output', str(args.output.resolve())]
    if args.command == 'preview' and args.at:
        command += ['--at', args.at]
    if args.command == 'render':
        command += ['--quality', args.quality, '--workers', str(args.workers)]
        if args.force:
            command.append('--force')
    raise SystemExit(subprocess.run(command, check=False).returncode)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, EnvironmentError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
