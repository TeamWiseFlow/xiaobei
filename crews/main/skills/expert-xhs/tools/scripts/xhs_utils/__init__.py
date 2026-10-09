"""Resolve the XHS library shared by Hunter and Expert tools."""

from pathlib import Path

_skills = next(
    (parent for parent in Path(__file__).resolve().parents
     if (parent / '_shared' / 'xhs_utils').is_dir()),
    None,
)
if _skills is None:
    raise ImportError('XHS shared library is missing')
for _directory in (
    _skills / 'xhs-hunter' / 'scripts' / 'xhs_utils',
    _skills / 'expert-xhs' / 'tools' / 'scripts' / 'xhs_utils',
    _skills / '_shared' / 'xhs_utils',
):
    if _directory.is_dir() and str(_directory) not in __path__:
        __path__.append(str(_directory))
