"""Platform defaults for Chinese text in expert-video outputs."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def is_windows(platform: str | None = None) -> bool:
    return (platform or sys.platform).startswith('win')


def font_family(platform: str | None = None) -> str:
    return 'Microsoft YaHei' if is_windows(platform) else 'Noto Sans CJK SC'


def font_faces(platform: str | None = None) -> tuple[tuple[int, str], ...]:
    if is_windows(platform):
        return ((300, 'Microsoft YaHei Light'), (400, 'Microsoft YaHei'),
                (500, 'Microsoft YaHei'), (700, 'Microsoft YaHei Bold'))
    family = font_family(platform)
    return ((300, family + ' Light'), (400, family),
            (500, family + ' Medium'), (700, family + ' Bold'))


def font_css(platform: str | None = None) -> str:
    family = font_family(platform)
    return '\n'.join(f'@font-face {{ font-family: "{family}"; src: local("{name}"); font-weight: {weight}; }}'
                     for weight, name in font_faces(platform))


def font_available(platform: str | None = None, windows_dir: Path | None = None) -> bool:
    platform = platform or sys.platform
    if is_windows(platform):
        root = Path(windows_dir) if windows_dir else Path(os.environ.get('WINDIR', 'C:/Windows'))
        return all((root / 'Fonts' / name).is_file()
                   for name in ('msyhl.ttc', 'msyh.ttc', 'msyhbd.ttc'))
    if shutil.which('fc-list'):
        result = subprocess.run(['fc-list', ':lang=zh', 'family'],
                                capture_output=True, text=True, timeout=15, check=False)
        if result.returncode == 0 and font_family(platform) in result.stdout:
            return True
    if platform == 'darwin':
        return any((root / 'NotoSansCJKsc-Regular.otf').is_file() for root in
                   (Path.home() / 'Library/Fonts', Path('/Library/Fonts')))
    return False
