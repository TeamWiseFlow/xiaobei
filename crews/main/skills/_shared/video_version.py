"""Local records for preview confirmation and byte-for-byte upload verification."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


def sha256(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def read_record(path):
    raw = Path(path).read_bytes()
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError('记录必须是 JSON 对象')
    return record, hashlib.sha256(raw).hexdigest()


def write_new(path, record):
    """Publish a complete record and refuse to replace evidence from another run."""
    path = Path(path)
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        temp = Path(directory) / 'record.json'
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.link(temp, path)


def master_for_review(source, report_path):
    report_path = Path(report_path).resolve(strict=True)
    report, digest = read_record(report_path)
    source_hash = sha256(source)
    if report.get('source_sha256') != source_hash or report.get('verdict') not in ('pass', 'warn'):
        raise ValueError('VIDEO_REVIEW_MISMATCH: 使用当前母带的有效 video-review 报告')
    return {'path': str(source.resolve()), 'sha256': source_hash}, {
        'path': str(report_path), 'sha256': digest, 'review_id': report.get('review_id'),
        'verdict': report['verdict'],
    }


def confirm_preview(manifest, confirmation_ref):
    manifest = Path(manifest).resolve(strict=True)
    record, digest = read_record(manifest)
    if record.get('version') != 1 or record.get('kind') != 'video_preview' or not confirmation_ref.strip():
        raise ValueError('VIDEO_UNCONFIRMED: 需要预览记录和明确的用户确认引用')
    for key in ('master', 'preview', 'review'):
        material = record[key]
        if sha256(material['path']) != material['sha256']:
            raise ValueError(f'VIDEO_VERSION_MISMATCH: {key} 已变更，请重新预览和确认')
    approval = manifest.with_suffix('.approval.json')
    write_new(approval, {**record, 'kind': 'video_approval', 'confirmation_ref': confirmation_ref.strip(),
                         'preview_record_sha256': digest})
    return {'ok': True, 'approval': str(approval), 'master_sha256': record['master']['sha256']}


def verify_upload(source, approval, copy_to=None):
    """Validate the file being uploaded, optionally pinning it in a private copy."""
    try:
        record, approval_hash = read_record(approval)
        expected = record['master']['sha256']
        confirmation = record['confirmation_ref']
        review = record['review']
        preview = record['preview']
        if (record.get('version') != 1 or record.get('kind') != 'video_approval'
                or not isinstance(confirmation, str) or not confirmation.strip()
                or any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)
                       for value in (expected, preview['sha256'], review['sha256'], record['preview_record_sha256']))):
            raise ValueError('无效的预览确认记录')
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise ValueError('VIDEO_UNCONFIRMED: 需要有效的 video-edit confirm-preview 记录') from exc

    path = Path(source)
    if copy_to is not None:
        with path.open('rb') as original, Path(copy_to).open('xb') as target:
            shutil.copyfileobj(original, target)
        path = Path(copy_to)
    if sha256(path) != expected:
        if copy_to is not None:
            path.unlink()
        raise ValueError('VIDEO_VERSION_MISMATCH: 上传文件与用户确认的母带不同')
    return {'status': 'matched', 'master_sha256': expected, 'preview_sha256': preview['sha256'],
            'review_sha256': review['sha256'], 'review_id': review.get('review_id'),
            'approval_sha256': approval_hash, 'confirmation_ref': confirmation}


@contextmanager
def verified_video(source, approval):
    if approval is None:
        yield source, None
        return
    with tempfile.TemporaryDirectory(prefix='xiaobei-video-', ignore_cleanup_errors=True) as directory:
        target = Path(directory) / Path(source).name
        evidence = verify_upload(source, approval, copy_to=target)
        yield str(target), evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    confirm = commands.add_parser('confirm-preview')
    confirm.add_argument('manifest')
    confirm.add_argument('--confirmation-ref', required=True)
    verify = commands.add_parser('verify-upload')
    verify.add_argument('source')
    verify.add_argument('--video-approval', required=True)
    verify.add_argument('--copy-to')
    args = parser.parse_args()
    try:
        result = (confirm_preview(args.manifest, args.confirmation_ref) if args.command == 'confirm-preview'
                  else verify_upload(args.source, args.video_approval, args.copy_to))
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
