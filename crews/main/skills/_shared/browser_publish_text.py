"""Fill publication editors from UTF-8 files without shell text expansion."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from publish_text import PublishTextError, read_publish_text
from video_version import verify_upload


def browser(session, *args):
    result = subprocess.run(
        [os.environ.get('CAMOUFOX_CLI', 'camoufox-cli'), '--session', session,
         '--persistent', '--json', *args],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError('BROWSER_COMMAND_FAILED')
    envelope = json.loads(result.stdout)
    if envelope.get('ok') is False or envelope.get('success') is False:
        raise RuntimeError('BROWSER_COMMAND_FAILED')
    data = envelope.get('data', envelope)
    return data.get('result', data) if isinstance(data, dict) else data


def channels_script(body):
    return r'''(() => {
      const text = BODY;
      const editors = [];
      const walk = root => {
        if (root.nodeType === 1) {
          if (root.getAttribute('data-placeholder') === '添加描述' && root.getClientRects().length) editors.push(root);
          if (root.shadowRoot) walk(root.shadowRoot);
        }
        for (const child of root.children || []) walk(child);
      };
      walk(document);
      if (editors.length !== 1) return {ok:false, error:'DESCRIPTION_EDITOR_NOT_UNIQUE'};
      const editor = editors[0];
      if (!editor.isContentEditable) return {ok:false, error:'DESCRIPTION_EDITOR_NOT_EDITABLE'};
      const doc = editor.ownerDocument;
      editor.scrollIntoView({block:'center'}); editor.focus(); editor.click();
      if (editor.getRootNode().activeElement !== editor) return {ok:false, error:'DESCRIPTION_FOCUS_FAILED'};
      if (!doc.execCommand('selectAll') || !doc.execCommand('delete')) return {ok:false, error:'DESCRIPTION_CLEAR_FAILED'};
      const lines = text.split('\n');
      for (let i = 0; i < lines.length; i++) {
        if (i && !doc.execCommand('insertParagraph')) return {ok:false, error:'DESCRIPTION_WRITE_FAILED'};
        if (lines[i] && !doc.execCommand('insertText', false, lines[i])) return {ok:false, error:'DESCRIPTION_WRITE_FAILED'};
      }
      const actual = (editor.innerText || '').replace(/\r/g, '');
      const normalize = value => value.replace(/\u00a0/g, ' ').trimEnd();
      const ok = normalize(actual) === normalize(text);
      return {ok, ...(ok ? {} : {error:'DESCRIPTION_MISMATCH'}), length:actual.length,
        head:actual.slice(0,40), tail:actual.slice(-60)};
    })()'''.replace('BODY', json.dumps(body, ensure_ascii=False), 1)


def upload_channels_video(args):
    source = Path(args.video).resolve(strict=True)
    command = ['browser-guide', 'stage-upload', str(source)]
    if args.inbound_root:
        command.extend(['--inbound-root', args.inbound_root])
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    target = Path(json.loads(result.stdout)['files'][0]['path'])
    try:
        confirmation = verify_upload(target, args.video_approval)
    except (OSError, ValueError):
        target.unlink(missing_ok=True)
        raise
    evidence = {'video_confirmation': confirmation, 'upload_file': str(target), 'upload_attempted': True}
    try:
        browser('wechat-channel', 'upload', 'input[type=file]', str(target))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        return {'ok': False, 'error': str(exc), **evidence}
    return {'ok': True, **evidence}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=('wechat-channel',))
    commands = parser.add_subparsers(dest='command', required=True)
    fill = commands.add_parser('fill')
    fill.add_argument('--body', required=True, help='纯正文文字或 @UTF-8正文文件路径')
    upload = commands.add_parser('upload-video', help='暂存并上传用户已确认的母带')
    upload.add_argument('--video', required=True)
    upload.add_argument('--video-approval', required=True)
    upload.add_argument('--inbound-root')
    args = parser.parse_args(argv)
    try:
        if args.command == 'upload-video':
            result = upload_channels_video(args)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result['ok'] else 1
        body = read_publish_text(args.body)
        if not body.strip():
            raise ValueError('BODY_EMPTY')
        result = browser('wechat-channel', 'eval', channels_script(body))
        if not isinstance(result, dict):
            raise RuntimeError('INVALID_BROWSER_RESPONSE')
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok') else 1
    except PublishTextError as exc:
        print(json.dumps({'ok': False, 'error': 'CONTENT_FILE_INVALID', 'message': str(exc)}, ensure_ascii=False))
        return 1
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
