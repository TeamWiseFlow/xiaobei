#!/usr/bin/env python3
"""Check narration gaps, scene audio review, repeated sources and a signed preview."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import os


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def number(value, label, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f'{label} 必须为有限数')
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f'{label} 必须为不小于 {minimum} 的有限数')
    return value


def run(command):
    proc = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=600)
    if proc.returncode:
        raise ValueError(proc.stderr[-1500:] or '媒体探测失败')
    return proc


def media(path):
    data = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                           '-of', 'json', path]).stdout)
    return data, number(data['format']['duration'], f'{path} duration', .001)


def silence_gaps(path, duration, noise_db, min_gap):
    result = run(['ffmpeg', '-nostdin', '-hide_banner', '-i', path, '-map', '0:a:0',
                  '-af', f'silencedetect=noise={noise_db}dB:d={min_gap}', '-f', 'null', '-'])
    gaps, start = [], None
    for kind, raw in re.findall(r'silence_(start|end):\s*([-+\d.eE]+)', result.stderr):
        timestamp = max(0, min(duration, float(raw)))
        if kind == 'start':
            start = timestamp
        elif start is not None:
            gaps.append((start, timestamp))
            start = None
    if start is not None:
        gaps.append((start, duration))
    return gaps


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        try:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def audit(project, plan_path, preview, review_path, decision=None):
    plan_hash = sha256(plan_path)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    preview_hash = sha256(preview)
    preview_info, duration = media(preview)
    if not any(s['codec_type'] == 'video' for s in preview_info['streams']):
        raise ValueError('preview 必须是实际可播放的视频')
    inputs = {}

    def source(raw):
        path = Path(raw)
        path = (project / path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_file():
            raise ValueError(f'素材不存在: {path}')
        key = str(path)
        if key not in inputs:
            content_hash = sha256(path)
            info, seconds = media(path)
            inputs[key] = {'sha256': content_hash, 'duration': seconds,
                           'has_video': any(s['codec_type'] == 'video' for s in info['streams']),
                           'has_audio': any(s['codec_type'] == 'audio' for s in info['streams'])}
        return path, inputs[key]

    findings = []
    policy = plan.get('sound_policy')
    gaps = []
    gap_check = 'not-applicable'
    if policy == 'narration':
        gap_check = 'dry-narration-silencedetect'
        if plan.get('voice_kind') != 'dry-narration':
            raise ValueError('必须提供最终时间轴上的旁白干声，voice_kind=dry-narration；不得用 BGM 混音测停顿')
        voice, info = source(plan['voice'])
        if not info['has_audio'] or abs(info['duration'] - duration) > .12:
            raise ValueError('旁白干声须含音轨并对齐 preview 全时间轴（时长差不超过0.12秒）')
        maximum = number(plan['max_gap_seconds'], 'max_gap_seconds', .01)
        noise = float(plan.get('silence_noise_db', -38))
        if not math.isfinite(noise) or not -90 <= noise <= -10:
            raise ValueError('silence_noise_db 范围 -90–-10')
        gaps = silence_gaps(voice, info['duration'], noise, maximum)
        for start, end in gaps:
            if end - start + .001 >= maximum:
                findings.append({'key': f'gap:{start:.3f}:{end:.3f}', 'kind': 'narration_gap',
                                 'start': start, 'end': end, 'seconds': end-start})
    elif policy == 'audio-scene':
        # Qwen Audio returns one complete mix, not an isolated narration stem.
        # BGM masks pauses; require actual listening through the existing manual gate.
        scene, info = source(plan['scene_audio'])
        if (not info['has_audio'] or abs(info['duration'] - duration) > .12
                or not any(s['codec_type'] == 'audio' for s in preview_info['streams'])):
            raise ValueError('audio-scene 须提供对齐完整成片时间轴的场景音轨，preview 须含音轨')
        gap_check = 'manual-scene-listening'
    elif policy not in ('silent', 'music-only'):
        raise ValueError('sound_policy 须为 narration / audio-scene / silent / music-only')
    if policy == 'silent' and any(s['codec_type'] == 'audio' for s in preview_info['streams']):
        raise ValueError('silent 计划的 preview 含音轨，先核对声音方案')

    segments = plan.get('segments', [])
    if not segments:
        raise ValueError('缺少有序 segments（必须覆盖完整 preview 时间轴）')
    inspected, ids, cursor = [], set(), 0.0
    for segment in segments:
        ident = str(segment['id']).strip()
        if not ident or ident in ids:
            raise ValueError('segment id 不可为空或重复')
        ids.add(ident)
        start = number(segment['start'], ident+' start')
        end = number(segment['end'], ident+' end')
        first = number(segment['source_start'], ident+' source_start')
        last = number(segment['source_end'], ident+' source_end')
        if end <= start or last <= first or abs(start-cursor) > .05:
            raise ValueError(f'{ident}: 时间轴需按序无缝覆盖，且源窗口/成片窗口时长须为正')
        cursor = end
        action = str(segment.get('action', '')).strip()
        if not action:
            raise ValueError(f'{ident}: 缺少实际画面动作 action（不能只写素材编号）')
        path, info = source(segment['source'])
        if not info['has_video'] or last > info['duration'] + .05:
            raise ValueError(f'{ident}: 源视频/源时间窗无效')
        current = {'id': ident, 'source': str(path), 'source_sha256': info['sha256'],
                   'start': start, 'end': end, 'source_start': first, 'source_end': last, 'action': action}
        for previous in inspected:
            overlap = min(last, previous['source_end']) - max(first, previous['source_start'])
            pair = f"{previous['id']}:{ident}"
            if info['sha256'] == previous['source_sha256'] and overlap > .05:
                findings.append({'key': 'reuse:'+pair, 'kind': 'source_window_reuse',
                                 'segments': [previous['id'], ident], 'overlap_seconds': overlap})
            if re.sub(r'\s+', '', action).casefold() == re.sub(r'\s+', '', previous['action']).casefold():
                findings.append({'key': 'action:'+pair, 'kind': 'repeated_action_label',
                                 'segments': [previous['id'], ident], 'action': action})
        inspected.append(current)
    if abs(cursor-duration) > .12:
        raise ValueError(f'segments 总时长 {cursor} 与 preview {duration} 不符')

    if review_path.resolve() in {plan_path.resolve(), preview.resolve(), *(Path(p) for p in inputs)}:
        raise ValueError('人工审片报告不得覆盖输入')
    binding = {'plan_sha256': plan_hash, 'preview': str(preview.resolve()),
               'preview_sha256': preview_hash, 'inputs': inputs}
    fingerprint = canonical_hash(binding)
    manual = None
    if decision:
        if decision.get('verdict') not in ('pass', 'fail') or not decision.get('reviewer', '').strip() or not decision.get('notes', '').strip():
            raise ValueError('审片登记须有 reviewer、verdict、具体 notes；不得只根据自动统计填 pass')
        manual = {**decision, 'fingerprint': fingerprint}
    elif review_path.is_file():
        old = json.loads(review_path.read_text(encoding='utf-8'))
        if (old.get('fingerprint') == fingerprint and old.get('verdict') in ('pass', 'fail')
                and str(old.get('reviewer', '')).strip() and str(old.get('notes', '')).strip()):
            manual = old
    exceptions = plan.get('exceptions', [])
    if not isinstance(exceptions, list) or any(not x.get('key') or not str(x.get('reason', '')).strip() for x in exceptions):
        raise ValueError('每个 exceptions 条目须有 finding key 和具体 reason')
    valid_keys = {f['key'] for f in findings}
    if any(x['key'] not in valid_keys for x in exceptions):
        raise ValueError('exception key 不属于当前检查结果；变更计划后先重新检查')
    resolved = {x['key'] for x in exceptions} if manual and manual['verdict'] == 'pass' else set()
    for finding in findings:
        finding['accepted'] = finding['key'] in resolved
    documented = {x['key'] for x in exceptions}
    status = ('fail' if any(x['key'] not in documented for x in findings) or manual and manual['verdict'] == 'fail'
              else 'pass' if manual else 'needs_review')
    # Bind signoff to stable media, including assets read before the silence scan.
    for raw, info in inputs.items():
        if sha256(Path(raw)) != info['sha256']:
            raise ValueError(f'检查时素材发生变化，重新运行: {raw}')
    if sha256(preview) != preview_hash or sha256(plan_path) != binding['plan_sha256']:
        raise ValueError('检查时计划或 preview 发生变化，重新运行')
    if decision:
        write_json(review_path, manual)
    return {'status': status, 'fingerprint': fingerprint, **binding,
            'segments': inspected, 'narration_gaps': gaps, 'findings': findings,
            'narration_gap_check': gap_check,
            'exceptions': exceptions, 'manual_review': manual,
            'review_scope': '听完整节奏、源动作是否重复、文案/画面对应、字形/安全区；不同 action 标签不证明画面不同'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_dir', type=Path)
    parser.add_argument('--plan', type=Path, default=Path('render/editing-plan.json'))
    parser.add_argument('--preview', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('review/edit-audit.json'))
    parser.add_argument('--verdict', choices=['pass', 'fail'])
    parser.add_argument('--reviewer')
    parser.add_argument('--notes')
    args = parser.parse_args()
    project = args.project_dir.resolve()
    def local(path):
        return (project/path).resolve()
    plan, preview, output = map(local, (args.plan, args.preview, args.output))
    if args.verdict is None and (args.reviewer or args.notes):
        raise ValueError('reviewer/notes 需与 verdict 一起使用')
    if output in (plan, preview):
        raise ValueError('报告不得覆盖输入')
    decision = {'verdict': args.verdict, 'reviewer': args.reviewer or '', 'notes': args.notes or ''} if args.verdict else None
    review_path = output.with_name(output.stem+'.manual.json')
    result = audit(project, plan, preview, review_path, decision)
    if output in map(Path, result['inputs']) or review_path in map(Path, result['inputs']):
        raise ValueError('报告不得覆盖素材输入')
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'pass' else 1 if result['status'] == 'fail' else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        sys.exit(3)
