#!/usr/bin/env python3
"""Compose a presenter over slides, or mux narration only. Never stretch speech."""
import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def run(cmd):
    result = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, timeout=1200)
    if result.returncode:
        raise ValueError(result.stderr[-4000:])
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))


def stream(info, kind):
    return next((x for x in info['streams'] if x['codec_type'] == kind), None)


def duration(info, track):
    value = float(track.get('duration', info.get('format', {}).get('duration', 0)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError('无法确认输入时长')
    return value


def geometry(w, h, args):
    for name in ('size', 'aspect', 'margin', 'subtitle_safe', 'radius', 'border'):
        if not math.isfinite(getattr(args, name)):
            raise ValueError(f'{name} 必须为有限数')
    if not .1 <= args.size <= .5 or not .25 <= args.aspect <= 4:
        raise ValueError('size 范围 .1–.5；aspect 范围 .25–4')
    if min(args.margin, args.subtitle_safe, args.radius, args.border) < 0:
        raise ValueError('边距、安全区、圆角、描边不能为负')
    pw = int(w * args.size) // 2 * 2
    ph = int(pw / args.aspect) // 2 * 2
    if 2*args.border >= min(pw, ph) or args.radius > min(pw, ph)/2:
        raise ValueError('圆角或描边超过小窗尺寸')
    x = args.margin if args.corner.endswith('left') else w-args.margin-pw
    y = args.margin if args.corner.startswith('top') else h-args.subtitle_safe-args.margin-ph
    if x < 0 or y < 0 or x+pw > w or y+ph > h-args.subtitle_safe:
        raise ValueError('小窗放不进画布或侵入底部字幕安全区')
    return {'x': x, 'y': y, 'width': pw, 'height': ph, 'radius': args.radius, 'border': args.border,
            'subtitle_safe': args.subtitle_safe}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--presenter', type=Path, help='省略时仅合入旁白')
    parser.add_argument('--audio', type=Path, help='唯一音轨；省略时仅保留底视频音轨')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--corner', choices=['top-left', 'top-right', 'bottom-left', 'bottom-right'], default='bottom-right')
    parser.add_argument('--size', type=float, default=.22, help='小窗宽 / 画布宽')
    parser.add_argument('--aspect', type=float, default=1, help='小窗宽高比；源视频居中裁切，不拉伸')
    parser.add_argument('--margin', type=int, default=32, help='像素')
    parser.add_argument('--subtitle-safe', type=int, default=160, help='底部禁入带，像素')
    parser.add_argument('--radius', type=int, default=24, help='像素')
    parser.add_argument('--border', type=int, default=4, help='像素')
    parser.add_argument('--border-color', default='#ffffff', help='#RRGGBB')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.threads <= 24 or not re.fullmatch(r'#[0-9a-fA-F]{6}', args.border_color):
        raise ValueError('threads 范围 1–24；border-color 必须是 #RRGGBB')
    for name in ('ffmpeg', 'ffprobe'):
        if not shutil.which(name):
            raise EnvironmentError(f'缺少 {name}，交 IT engineer')
    output = args.output.resolve()
    inputs = [p.resolve() for p in (args.base, args.presenter, args.audio) if p is not None]
    if output in inputs or any(output.exists() and p.exists() and output.samefile(p) for p in inputs):
        raise ValueError('输出不得覆盖输入素材')
    if output.suffix.lower() != '.mp4':
        raise ValueError('输出必须为 .mp4')
    if output.exists() and not args.force:
        raise ValueError('输出已存在；检查后用 --force 重做')
    base = probe(args.base)
    video = stream(base, 'video')
    if not video:
        raise ValueError('base 必须含视频')
    w, h = video['width'], video['height']
    fps = float(Fraction(video['r_frame_rate']))
    if w % 2 or h % 2 or not 1 <= fps <= 120:
        raise ValueError('底视频需偶数尺寸、1–120 fps')
    if video.get('sample_aspect_ratio', '1:1') not in ('1:1', 'N/A') or any(x.get('rotation', 0) for x in video.get('side_data_list', [])):
        raise ValueError('底视频需先归一化方形像素与旋转方向')
    if abs(float(video.get('start_time', 0))) > .12:
        raise ValueError('底视频时间轴需从 0 开始，先用 clip-trim 归一化')
    seconds = duration(base, video)
    audio_info = probe(args.audio) if args.audio else base
    audio = stream(audio_info, 'audio')
    if not audio:
        raise ValueError('请提供 --audio 或含音轨的 base；不会使用 presenter 自带音轨')
    audio_seconds = duration(audio_info, audio)
    if abs(audio_seconds - seconds) > .12:
        raise ValueError(f'唯一音轨与底视频时长不匹配：base={seconds:.3f}s，'
                         f'audio={audio_seconds:.3f}s，容差=0.120s；先对齐翻页/裁剪')
    box = None
    if args.presenter:
        presenter = probe(args.presenter)
        pv = stream(presenter, 'video')
        if not pv:
            raise ValueError('presenter 缺少视频轨')
        presenter_seconds = duration(presenter, pv)
        if presenter_seconds < seconds-.12:
            raise ValueError(f'presenter 视频短于底视频：base={seconds:.3f}s，'
                             f'audio={audio_seconds:.3f}s，presenter={presenter_seconds:.3f}s，'
                             '容差=0.120s；先核对数字人驱动音频，禁止静默定帧/循环/变速')
        if pv.get('sample_aspect_ratio', '1:1') not in ('1:1', 'N/A') or any(x.get('rotation', 0) for x in pv.get('side_data_list', [])):
            raise ValueError('presenter 需先归一化方形像素与旋转方向')
        box = geometry(w, h, args)
    plan = {'output': str(output), 'duration': seconds, 'width': w, 'height': h, 'fps': fps,
            'audio_source': str((args.audio or args.base).resolve()), 'presenter': str(args.presenter.resolve()) if args.presenter else None,
            'pip': box, 'dry_run': args.dry_run}
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pip-compose-', dir=output.parent) as tmp:
        temp = Path(tmp)
        dest = temp / 'composed.mp4'
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-filter_complex_threads', '1', '-i', args.base.resolve()]
        if args.presenter:
            cmd += ['-i', args.presenter.resolve()]
        audio_index = 2 if args.presenter else 1
        if args.audio:
            cmd += ['-i', args.audio.resolve()]
        else:
            audio_index = 0
        if box:
            from PIL import Image, ImageDraw
            b, r = args.border, args.radius
            pw, ph = box['width'], box['height']
            iw, ih = pw-2*b, ph-2*b
            mask = Image.new('L', (iw, ih), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, iw-1, ih-1), radius=max(0, r-b), fill=255)
            mask.save(temp / 'mask.png')
            border = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
            draw = ImageDraw.Draw(border)
            draw.rounded_rectangle((0, 0, pw-1, ph-1), radius=r, fill=args.border_color)
            draw.rounded_rectangle((b, b, pw-b-1, ph-b-1), radius=max(0, r-b), fill=(0, 0, 0, 0))
            border.save(temp / 'border.png')
            mask_index = 2 + bool(args.audio)
            cmd += ['-loop', '1', '-framerate', str(fps), '-i', temp / 'mask.png',
                    '-loop', '1', '-framerate', str(fps), '-i', temp / 'border.png']
            graph = (f'[0:v]setpts=PTS-STARTPTS,setsar=1[base];'
                     f'[1:v]setpts=PTS-STARTPTS,scale={iw}:{ih}:force_original_aspect_ratio=increase,crop={iw}:{ih},setsar=1,fps={fps},format=rgba[p];'
                     f'[p][{mask_index}:v]alphamerge[rounded];'
                     f'[base][rounded]overlay=x={box["x"]+b}:y={box["y"]+b}:eof_action=pass:repeatlast=0[inner];'
                     f'[inner][{mask_index+1}:v]overlay=x={box["x"]}:y={box["y"]}:format=auto,format=yuv420p[v]')
            cmd += ['-filter_complex', graph, '-map', '[v]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
                    '-threads', str(args.threads), '-r', str(fps)]
        else:
            cmd += ['-map', '0:v:0', '-c:v', 'copy']
        cmd += ['-map', f'{audio_index}:a:0', '-af', 'asetpts=PTS-STARTPTS', '-c:a', 'aac', '-b:a', '192k',
                '-t', str(seconds), '-movflags', '+faststart', dest]
        run(cmd)
        result = probe(dest)
        rv = stream(result, 'video')
        ra = stream(result, 'audio')
        if not rv or not ra or (rv['width'], rv['height']) != (w, h) or abs(float(Fraction(rv['r_frame_rate']))-fps) > .01 or abs(duration(result, rv)-seconds) > .12 or abs(duration(result, ra)-seconds) > .12:
            raise ValueError('输出音视频尺寸/帧率/时长校验失败')
        dest.replace(output)
    output.with_suffix('.pip.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(plan, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (EnvironmentError, ImportError) as exc:
        print(f'[setup error] {exc}', file=sys.stderr)
        sys.exit(2)
    except (ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        sys.exit(1)
