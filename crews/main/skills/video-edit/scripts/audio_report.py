#!/usr/bin/env python3
"""Measure audio without modifying media or treating project targets as measurements."""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from video_version import sha256, write_new


def span(value):
    try:
        start, end = map(float, value.split(':'))
        if not math.isfinite(end) or not 0 <= start < end:
            raise ValueError
    except ValueError as exc:
        raise argparse.ArgumentTypeError('时间窗格式为 START:END，单位秒，0 ≤ START < END') from exc
    return start, end


def named_span(value):
    label, _, interval = value.partition(':')
    if not label.strip():
        raise argparse.ArgumentTypeError('时间窗需要名称')
    return label, span(interval)


def audio(path, filters, *output):
    return subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-v', 'info', '-xerror',
                           '-i', str(path), '-map', '0:a:0', '-af', filters, *output],
                          capture_output=True, timeout=120)


def number(value):
    parsed = float(value)
    return round(parsed, 3) if math.isfinite(parsed) else None


def trim(window):
    start, end = window
    return f'asetpts=PTS-STARTPTS,atrim=start={start}:end={end},asetpts=PTS-STARTPTS'


def loudness(path):
    result = audio(path, 'loudnorm=print_format=json', '-f', 'null', '-')
    log = result.stderr.decode(errors='replace')
    blocks = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', log)
    if result.returncode or not blocks:
        return {'status': 'unknown', 'reason': 'audio_unavailable'}
    measured = json.loads(blocks[-1])
    lufs = number(measured['input_i'])
    peak = number(measured['input_tp'])
    return {'status': 'measured' if lufs is not None and peak is not None else 'unknown',
            'integrated_lufs': lufs, 'true_peak_dbtp': peak}


def window_level(path, label, window):
    filters = trim(window) + ',astats=measure_perchannel=none:measure_overall=RMS_level+Peak_level+Number_of_samples'
    result = audio(path, filters, '-f', 'null', '-')
    log = result.stderr.decode(errors='replace')
    report = {'label': label, 'start_seconds': window[0], 'end_seconds': window[1]}
    values = dict(re.findall(r'\[Parsed_astats_\d+ @ [^\]]+\] (RMS level dB|Peak level dB|Number of samples): ([^\s]+)', log))
    rate = re.search(r'Audio: [^\n]*?\b(\d+) Hz', log)
    samples = int(values.get('Number of samples', 0))
    if result.returncode or not samples or not rate:
        return {**report, 'status': 'unknown', 'reason': 'window_has_no_decoded_audio'}
    seconds = samples / int(rate[1])
    rms = number(values['RMS level dB'])
    peak = number(values['Peak level dB'])
    status = 'partial' if seconds < window[1] - window[0] - 0.002 else 'silent' if peak is None else 'measured'
    return {**report, 'status': status, 'actual_duration_seconds': round(seconds, 6),
            'rms_dbfs': rms, 'sample_peak_dbfs': peak}


def estimate_tempo(samples, rate):
    import numpy as np

    size, hop = 512, 128
    frames = np.lib.stride_tricks.sliding_window_view(samples, size)[::hop]
    magnitudes = np.log1p(100 * np.abs(np.fft.rfft(frames * np.hanning(size))))
    flux = np.maximum(np.diff(magnitudes, axis=0), 0).mean(axis=1)
    onsets = np.flatnonzero((flux[1:-1] >= flux[:-2]) & (flux[1:-1] > flux[2:])
                           & (flux[1:-1] > max(0.01, 0.2 * flux.max())))
    if len(onsets) < 4:
        return {'status': 'unknown', 'reason': 'too_few_onsets'}
    flux -= flux.mean()
    curve = np.correlate(flux, flux, mode='full')[len(flux) - 1:]
    pulses = []
    first, last = math.ceil(rate * 60 / (hop * 220)), math.floor(rate * 60 / (hop * 45))
    for lag in range(first, last + 1):
        score = float(curve[lag] / curve[0])
        if score >= 0.25 and curve[lag] >= curve[lag - 1] and curve[lag] > curve[lag + 1]:
            pulses.append((lag, score))
    if not pulses:
        return {'status': 'unknown', 'reason': 'weak_periodicity'}
    strongest = max(score for _, score in pulses)
    candidates = [{'bpm': round(rate * 60 / (hop * lag), 1), 'periodicity': round(score, 3)}
                  for lag, score in sorted(pulses, key=lambda pulse: -pulse[1]) if score >= strongest * 0.8][:4]
    if len(candidates) != 1:
        return {'status': 'ambiguous', 'candidates': candidates}
    return {'status': 'estimated', **candidates[0]}


def bgm_tempo(path, window):
    import numpy as np

    rate = 11025
    result = audio(path, trim(window), '-ac', '1', '-ar', str(rate), '-c:a', 'pcm_f32le', '-f', 'f32le', '-')
    samples = np.frombuffer(result.stdout, dtype='<f4')
    seconds = len(samples) / rate
    interval = {'start_seconds': window[0], 'end_seconds': window[1], 'actual_duration_seconds': round(seconds, 6)}
    if result.returncode or not np.isfinite(samples).all():
        return {**interval, 'status': 'unknown', 'reason': 'audio_unavailable'}
    if seconds < 4:
        return {**interval, 'status': 'unknown', 'reason': 'window_too_short'}
    if seconds < window[1] - window[0] - 0.002:
        return {**interval, 'status': 'unknown', 'reason': 'window_incomplete'}
    return {**interval, **estimate_tempo(samples, rate)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--window', type=named_span, action='append', default=[], metavar='LABEL:START:END')
    parser.add_argument('--bgm', type=Path)
    parser.add_argument('--bgm-window', type=span, metavar='START:END')
    parser.add_argument('--output', type=Path, help='保存 JSON 报告到新文件')
    args = parser.parse_args()
    if (args.bgm is None) != (args.bgm_window is None):
        parser.error('--bgm 与 --bgm-window 需同时提供')
    if args.bgm_window and args.bgm_window[1] - args.bgm_window[0] > 120:
        parser.error('BGM 测量时间窗最多 120 秒，请使用实际选段')
    try:
        source = args.input.resolve(strict=True)
        bgm = args.bgm.resolve(strict=True) if args.bgm is not None else None
        paths = {path for path in (source, bgm) if path is not None}
        if any(not path.is_file() for path in paths):
            raise ValueError('音频测量需要本地媒体文件')
        sources = {path: sha256(path) for path in paths}
        version = subprocess.check_output(['ffmpeg', '-version'], text=True, timeout=10).splitlines()[0]
        report = {'version': 1, 'ffmpeg': version, 'source': str(source),
                  'source_sha256': sources[source], 'stream': '0:a:0',
                  'time_origin': 'first_audio_timestamp', 'loudness': loudness(source),
                  'windows': [window_level(source, label, window) for label, window in args.window]}
        if bgm is not None:
            report['bgm'] = {'source': str(bgm), 'source_sha256': sources[bgm],
                             'method': 'spectral_flux_autocorrelation_v1', **bgm_tempo(bgm, args.bgm_window)}
        if any(sha256(path) != digest for path, digest in sources.items()):
            raise ValueError('音频测量期间源文件已修改，请重跑')
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_new(args.output, report)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    except (OSError, ValueError, ImportError, subprocess.SubprocessError) as exc:
        parser.exit(1, f'audio-report: {exc}\n')


if __name__ == '__main__':
    main()
