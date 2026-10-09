#!/usr/bin/env python3
"""Compose deck-talk footage / avatar / audio modes using one authoritative audio track."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[7] / 'skills' / '_shared'))
from bailian_media import fingerprint, save_json


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=1200)
    if result.returncode:
        raise ValueError(result.stderr[-2000:] or result.stdout[-2000:])
    return result.stdout


def media_duration(path):
    payload = json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', path]))
    return float(payload['format']['duration'])


def resolve_inputs(args):
    if args.mode == 'footage':
        if not args.presenter or args.audio or args.avatar_job:
            raise ValueError('footage 只接收 --presenter；唯一音轨从该视频提取，不接受另一条配音')
        if not args.presenter.is_file():
            raise ValueError('口播视频不存在')
        audio = args.output.with_suffix('.narration.wav').resolve()
        return args.presenter.resolve(), audio
    if args.mode == 'avatar':
        if not args.avatar_job or args.presenter or args.audio:
            raise ValueError('avatar 只接收 --avatar-job，自动使用任务对应的视频与同源音频')
        job = json.loads(args.avatar_job.read_text())
        if job.get('status') != 'SUCCEEDED' or job.get('timing_pass') is not True:
            raise ValueError('数字人任务未完成或时长核验未通过')
        presenter, audio = Path(job['video_file']), Path(job['audio_file'])
        if not presenter.is_file() or not audio.is_file():
            raise ValueError('数字人 job 溯源文件不存在：请核对 video_file/audio_file，勿手改 job')
        if fingerprint(audio) != job.get('audio_sha256') or fingerprint(presenter) != job.get('video_sha256'):
            raise ValueError('数字人 job 溯源不一致：video_file/audio_file 与记录的 SHA-256 不符；勿手改 job，需重新核验同源关系')
        if 'audio_duration' in job and abs(media_duration(audio) - float(job['audio_duration'])) > .12:
            raise ValueError('数字人 job 溯源不一致：当前驱动音频时长与任务记录 audio_duration 不符')
        if 'video_duration' in job and abs(media_duration(presenter) - float(job['video_duration'])) > .12:
            raise ValueError('数字人 job 溯源不一致：当前视频时长与任务记录 video_duration 不符')
        return presenter, audio
    if not args.audio or args.presenter or args.avatar_job:
        raise ValueError('audio 模式需要 --audio，不接受小窗视频或数字人任务')
    if not args.audio.is_file():
        raise ValueError('音频不存在')
    return None, args.audio.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=['footage', 'avatar', 'audio', 'none'])
    parser.add_argument('--base', required=True, type=Path, help='已按音频时长排好的幻灯 / B-roll / 混合画面')
    parser.add_argument('--presenter', type=Path, help='main 已剪好的口播视频，仅 footage')
    parser.add_argument('--avatar-job', type=Path, help='LivePortrait .liveportrait.json，仅 avatar')
    parser.add_argument('--audio', type=Path, help='用户/main 提供的音频，仅 audio')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--corner', choices=['top-left', 'top-right', 'bottom-left', 'bottom-right'], default='bottom-right')
    parser.add_argument('--subtitle-safe', type=int, default=160)
    parser.add_argument('--size', type=float, default=.22)
    args = parser.parse_args()
    if args.mode == 'none':
        args.mode = 'audio'
    args.output = args.output.resolve()
    metadata = args.output.with_suffix('.deck-talk.json')
    if args.output.suffix.lower() != '.mp4' or args.output.exists() or metadata.exists():
        raise ValueError('输出须为尚不存在的 .mp4，另存结果，不覆盖素材或既有交付')
    presenter, audio = resolve_inputs(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    extracted = args.mode == 'footage'
    if extracted and (audio.exists() or audio == args.base.resolve()):
        raise ValueError('提取音轨目标已存在或与输入冲突，请另选输出名')
    try:
        if extracted:
            run(['ffmpeg', '-v', 'error', '-nostdin', '-i', presenter, '-map', '0:a:0',
                 '-vn', '-c:a', 'pcm_s16le', audio])
        command = [sys.executable, Path(__file__).with_name('pip-compose.py'), '--base', args.base,
                   '--audio', audio, '--output', args.output, '--corner', args.corner,
                   '--subtitle-safe', args.subtitle_safe, '--size', args.size]
        if presenter:
            command += ['--presenter', presenter]
        run(command)
    except Exception:
        if extracted:
            audio.unlink(missing_ok=True)
        raise
    save_json(metadata, {'mode': args.mode, 'base': str(args.base.resolve()),
                         'presenter': str(presenter) if presenter else None,
                         'audio': str(audio), 'audio_sha256': fingerprint(audio),
                         'avatar_job': str(args.avatar_job.resolve()) if args.avatar_job else None,
                         'file': str(args.output)})
    print(json.dumps({'video': str(args.output), 'metadata': str(metadata)}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
