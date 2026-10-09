#!/usr/bin/env python3
"""Use the existing qualitative DNA engine with platform-local defaults."""
import importlib.util
import json
import sys
from pathlib import Path


def main():
    platform, *args = sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    settings = json.loads((root / 'platform-runtime/platforms.json').read_text())
    if platform not in ('x', 'tiktok', 'kuaishou'):
        raise SystemExit('Unsupported style-profile platform')
    engine = root / 'expert-xhs/tools/xhs-style-profiler/scripts/build_style_profile.py'
    spec = importlib.util.spec_from_file_location('qualitative_dna', engine)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PLATFORM = settings[platform]['workspace']
    module.PLATFORM_LABEL = {'x': 'X/Twitter', 'tiktok': 'TikTok', 'kuaishou': '快手'}[platform]
    module.PLATFORM_DESC = module.PLATFORM_LABEL + '内容'
    module.DEFAULT_KIND = 'note' if platform == 'x' else 'video'
    module.KIND_SUFFIX_HINT = '视频与图文/文字样本分别建 DNA，不混合统计'
    if platform == 'x':
        module.KIND_LABELS['note'] = '文字与图文帖子'
        module.REPORT_DIMENSION_PROMPTS['title-cover'] = '- 记录首句钩子、媒体首图与封面；纯文字样本不臆测图像。'
        module.REPORT_DIMENSION_PROMPTS['imageset-visual'] = '- 记录实际媒体构图、顺序与信息分工；纯文字作品标注不适用。'
    module.run(args)


if __name__ == '__main__':
    main()
