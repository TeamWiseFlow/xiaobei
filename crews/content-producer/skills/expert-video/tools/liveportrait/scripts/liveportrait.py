#!/usr/bin/env python3
"""LivePortrait: validate, detect, submit, checkpoint, poll, and download."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[7] / 'skills' / '_shared'))
from bailian_media import APIError, download, fingerprint, media_info, request, save_json, upload, workspace

DETECT = '/services/aigc/image2video/face-detect'
SYNTHESIS = '/services/aigc/image2video/video-synthesis'


def local_source(value, folder, kind):
    if value.startswith(('http://', 'https://')):
        suffix = Path(urlsplit(value).path).suffix.lower() or ('.png' if kind == 'image' else '.wav')
        return download(value, folder / (kind + suffix), max_bytes=(10 if kind == 'image' else 15)*1024*1024)
    path = Path(value).resolve()
    if not path.is_file():
        raise ValueError(f'{kind} 文件不存在：{path}')
    return path


def validate_media(image, audio):
    if image.stat().st_size >= 10 * 1024 * 1024:
        raise ValueError('图片须小于 10MB')
    with Image.open(image) as pic:
        w, h = pic.size
        if pic.format not in ('JPEG', 'PNG', 'BMP', 'WEBP') or max(w, h) > 4096 or w / h > 2:
            raise ValueError('图片须为 JPEG/PNG/BMP/WebP，最大边 ≤4096，宽高比 ≤2')
        pic.verify()
    if audio.suffix.lower() not in ('.wav', '.mp3') or audio.stat().st_size >= 15 * 1024 * 1024:
        raise ValueError('音频须为 WAV/MP3 且小于 15MB')
    seconds, streams = media_info(audio)
    if not 1 < seconds < 180 or not any(s['codec_type'] == 'audio' for s in streams):
        raise ValueError('LivePortrait 音频时长须大于 1 秒、小于 180 秒')
    return seconds


def detect(base, key, image):
    image_url = upload(base, key, image, 'liveportrait-detect')
    data = request(base, key, DETECT, {'model': 'liveportrait-detect', 'input': {'image_url': image_url}})
    if (data.get('output') or {}).get('pass') is not True:
        raise ValueError('LivePortrait 人像检测未通过，请检查正脸、遮挡及人物大小')
    return data.get('request_id')


def finish(job_path, *, timeout=900, interval=5):
    job = json.loads(job_path.read_text())
    base, key = workspace()
    if job.get('base_url') != base:
        raise ValueError('任务不属于当前百炼业务空间')
    if not job.get('task_id'):
        raise ValueError('任务无 task_id，提交结果不确定；先查百炼控制台，不要重复提交')
    if fingerprint(job['audio_file']) != job['audio_sha256']:
        raise ValueError('驱动音频已改变，不能与该数字人任务混用')
    output_path = Path(job['video_file'])
    if job.get('timing_pass') is True and output_path.is_file():
        if job.get('video_sha256'):
            if fingerprint(output_path) != job['video_sha256']:
                raise ValueError('已完成的数字人视频被替换')
        elif job.get('video_duration'):
            # Older checkpoints saved the successful download before recording its hash.
            seconds, streams = media_info(output_path)
            if not any(s['codec_type'] == 'video' for s in streams) or abs(seconds - job['video_duration']) > .01:
                raise ValueError('既有数字人视频与任务记录不一致')
            job['video_sha256'] = fingerprint(output_path)
            job['status'] = 'SUCCEEDED'
            job.pop('error_code', None)
            save_json(job_path, job)
        if job.get('status') == 'SUCCEEDED' and job.get('video_sha256'):
            print(json.dumps({'video': str(output_path), 'audio': job['audio_file'], 'job': str(job_path)}, ensure_ascii=False))
            return
    deadline = time.monotonic() + timeout
    while True:
        data = request(base, key, '/tasks/' + job['task_id'])
        output = data.get('output') or {}
        status = output.get('task_status', 'UNKNOWN')
        job['status'] = status
        save_json(job_path, job)
        print(f'[info] LivePortrait status={status}', flush=True)
        if status == 'SUCCEEDED':
            video_url = (output.get('results') or {}).get('video_url') or output.get('video_url')
            if not video_url:
                raise ValueError('成功响应缺少 video_url')
            download(video_url, output_path, max_bytes=512*1024*1024)
            seconds, streams = media_info(output_path)
            if not any(s['codec_type'] == 'video' for s in streams):
                raise ValueError('下载结果没有视频轨')
            job['video_sha256'] = fingerprint(output_path)
            job['video_duration'] = seconds
            job['duration_delta'] = round(seconds - job['audio_duration'], 4)
            job['timing_pass'] = abs(job['duration_delta']) <= .12
            save_json(job_path, job)
            if not job['timing_pass']:
                raise ValueError('数字人与驱动音频时长偏差超过 0.12 秒；保留产物，需核验后再合成')
            print(json.dumps({'video': str(output_path), 'audio': job['audio_file'], 'job': str(job_path)}, ensure_ascii=False))
            return
        if status in ('FAILED', 'CANCELED', 'CANCELLED', 'UNKNOWN'):
            job['error_code'] = output.get('code', status)
            save_json(job_path, job)
            raise APIError(f'LivePortrait {status} code={job["error_code"]}')
        if time.monotonic() >= deadline:
            raise TimeoutError(f'任务仍在运行；用 liveportrait resume --job {job_path} 继续查询')
        time.sleep(min(interval, max(0, deadline - time.monotonic())))


def generate(args):
    base, key = workspace()
    target = args.output.resolve()
    job_path = target.with_suffix('.liveportrait.json')
    if target.suffix.lower() != '.mp4':
        raise ValueError('输出须为 .mp4')
    if target.exists() or job_path.exists():
        raise ValueError(f'输出或任务记录已存在；用 liveportrait resume --job {job_path}，不要重复生成')
    folder = target.parent / ('.' + target.stem + '-inputs')
    folder.mkdir(parents=True, exist_ok=True)
    image = local_source(args.image, folder, 'image')
    audio = local_source(args.audio, folder, 'audio')
    if target in (image, audio):
        raise ValueError('输出不得覆盖源文件')
    seconds = validate_media(image, audio)
    detect_id = detect(base, key, image)
    # Upload again for liveportrait: temporary URLs are bound to their model.
    body = {'model': 'liveportrait', 'input': {
        'image_url': upload(base, key, image, 'liveportrait'),
        'audio_url': upload(base, key, audio, 'liveportrait'),
    }, 'parameters': {'template_id': args.template, 'video_fps': args.fps, 'paste_back': True,
                       'head_move_strength': args.head_move, 'mouth_move_strength': 1, 'eye_move_freq': .5}}
    job = {'schema_version': 1, 'base_url': base, 'model': 'liveportrait',
           'status': 'SUBMITTING', 'image_file': str(image), 'audio_file': str(audio),
           'image_sha256': fingerprint(image), 'audio_sha256': fingerprint(audio),
           'audio_duration': seconds, 'video_file': str(target), 'detect_request_id': detect_id,
           'parameters': body['parameters']}
    save_json(job_path, job)
    result = request(base, key, SYNTHESIS, body, async_task=True)
    task_id = (result.get('output') or {}).get('task_id')
    if not task_id:
        raise ValueError('提交响应缺少 task_id，请先检查控制台任务')
    job.update(task_id=task_id, status='PENDING')
    save_json(job_path, job)
    finish(job_path, timeout=args.timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    gen = subs.add_parser('generate')
    gen.add_argument('--image', required=True, help='本人/已授权肖像，文件或 HTTP(S) URL')
    gen.add_argument('--audio', required=True, help='唯一驱动音轨，文件或 HTTP(S) URL')
    gen.add_argument('--output', required=True, type=Path)
    gen.add_argument('--template', choices=['calm', 'normal', 'active'], default='calm')
    gen.add_argument('--fps', type=int, choices=range(15, 31), default=30)
    gen.add_argument('--head-move', type=float, default=.3)
    gen.add_argument('--timeout', type=int, default=900)
    resume = subs.add_parser('resume')
    resume.add_argument('--job', required=True, type=Path)
    resume.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 3600:
        parser.error('--timeout 范围 1–3600 秒')
    if args.command == 'generate':
        if not 0 <= args.head_move <= 1:
            parser.error('--head-move 范围 0–1')
        generate(args)
    else:
        finish(args.job.resolve(), timeout=args.timeout)


if __name__ == '__main__':
    try:
        main()
    except (APIError, ValueError, OSError, TimeoutError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
