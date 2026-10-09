#!/usr/bin/env python3
"""Suggest and verify deck page turns from TTS word timestamps."""
import argparse
import json
import math
from pathlib import Path
import sys

PUNCTUATION = frozenset('。！？；，、.!?;,')


def candidates(subtitle):
    found = []
    for item in subtitle.get('segments', []):
        text = str(item.get('text') or '').rstrip()
        if text and text[-1] in PUNCTUATION:
            moment = float(item['end'])
            if math.isfinite(moment) and moment >= 0:
                found.append({'time': round(moment, 3), 'punctuation': text[-1], 'sentence': None})
    for number, sentence in enumerate(subtitle.get('sentences', []), 1):
        words = sentence.get('words') or []
        for item in words:
            word = str(item.get('word', ''))
            if not word or word[-1] not in PUNCTUATION:
                continue
            moment = float(item['endTime'])
            if math.isfinite(moment) and moment >= 0:
                found.append({'time': round(moment, 3), 'punctuation': word[-1], 'sentence': number})
        text = str(sentence.get('text') or '')
        if words and text.rstrip().endswith(tuple(PUNCTUATION)):
            moment = float(words[-1]['endTime'])
            if math.isfinite(moment) and moment >= 0:
                found.append({'time': round(moment, 3), 'punctuation': text.rstrip()[-1], 'sentence': number})
    # Punctuation may be present in both the word stream and sentence text.
    return list({item['time']: item for item in found}.values())


def assess(spec, marks, tolerance):
    elapsed, turns = 0.0, []
    for index, scene in enumerate(spec['scenes'][:-1], 1):
        elapsed += float(scene['duration'])
        nearest = min(marks, key=lambda item: abs(item['time'] - elapsed))
        turns.append({'after_page': index, 'planned': round(elapsed, 3),
                      'nearest': nearest, 'delta': round(elapsed - nearest['time'], 3),
                      'aligned': abs(elapsed - nearest['time']) <= tolerance})
    return turns


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subtitle', required=True, type=Path, help='awk-tts 字级 .subtitle.json 或 ASR word segments JSON')
    parser.add_argument('--spec', type=Path, help='待核对的 deck-spec.json')
    parser.add_argument('--output', required=True, type=Path, help='边界诊断 JSON；不可覆盖输入')
    parser.add_argument('--tolerance', type=float, default=.12)
    args = parser.parse_args()
    if not 0 <= args.tolerance <= 1 or not math.isfinite(args.tolerance):
        parser.error('--tolerance 必须在 0–1 秒内')
    if args.output.resolve() in {p.resolve() for p in (args.subtitle, args.spec) if p}:
        parser.error('--output 不可覆盖输入')
    marks = candidates(json.loads(args.subtitle.read_text(encoding='utf-8')))
    if not marks:
        raise ValueError('字级时间戳中没有标点边界；需用稿件与音频人工逐句对齐')
    marks.sort(key=lambda item: item['time'])
    turns = assess(json.loads(args.spec.read_text(encoding='utf-8')), marks, args.tolerance) if args.spec else []
    report = {'source': str(args.subtitle.resolve()), 'candidates': marks,
              'tolerance': args.tolerance, 'page_turns': turns,
              'verdict': 'pass' if all(t['aligned'] for t in turns) else 'fail'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output.resolve()), 'verdict': report['verdict'],
                      'turns': len(turns), 'candidates': len(marks)}, ensure_ascii=False))
    if report['verdict'] == 'fail':
        raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError, OSError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
