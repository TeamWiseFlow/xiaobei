#!/usr/bin/env python3
"""Persistent creator browser login and video/note publication dispatcher."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS / '_shared'))
from publish_browser import Browser, MANAGE_URL, SESSION, publish_lock


def main(argv=None):
    p = argparse.ArgumentParser(prog='douyin-publish')
    sub = p.add_subparsers(dest='command', required=True)
    login = sub.add_parser('login', help='打开持久化有头创作者页面，由用户完成登录')
    login.add_argument('--resume-video', action='store_true', help='验证页面已丢失或登录失效时恢复登录，保留原视频提交记录')
    check = sub.add_parser('check', help='复用持久 profile 登录态，通过 HTTP 验证创作者接口')
    check.add_argument('--kind', choices=('video', 'note'), default='video')
    for kind in ('video', 'note'):
        cmd = sub.add_parser(kind)
        cmd.add_argument('--video', required=True) if kind == 'video' else cmd.add_argument('--images', nargs='+', required=True)
        cmd.add_argument('--title', required=True)
        cmd.add_argument('--caption', default='')
        cmd.add_argument('--declaration', choices=('aigc', 'ai', 'none'), default='aigc')
        if kind == 'video':
            cmd.add_argument('--cover-vertical', help='竖封面；脚本等比补底到 3:4')
            cmd.add_argument('--cover-horizontal', help='横封面；脚本等比补底到 4:3')
        if kind == 'note':
            cmd.add_argument('--original-sound', action='store_true', help='明确使用原声；配乐请使用分步工具')
        cmd.add_argument('--confirm', action='store_true')
    a = p.parse_args(argv)
    if a.command == 'check':
        return subprocess.call([sys.executable, str(TOOLS / 'douyin-engagement/scripts/douyin_engagement.py'), 'check'])
    if a.command == 'login':
        lock = publish_lock(allow_pending_video=True) if a.resume_video else publish_lock()
        with lock:
            current = Browser()
            state = current.command('info')
            if isinstance(state, dict) and state.get('running'):
                if a.resume_video and current.eval("/接收短信验证码|请输入当前手机号收到的短信验证码/.test(document.body.innerText)"):
                    raise ValueError('SMS_VERIFICATION_PENDING_USE_VIDEO_RESUME')
                current.headed = bool(state.get('headed'))
                current.close()
            Browser(headed=True).command('open', MANAGE_URL)
            print(json.dumps({'ok': True, 'state': 'awaiting_user_login', 'session': SESSION,
                              'hint': '在有头窗口完成登录后执行 douyin-publish check；登录态保存在持久化 profile'}, ensure_ascii=False))
        return 0
    paths = [a.video] if a.command == 'video' else a.images
    media = [Path(path).expanduser() for path in paths]
    if any(not path.is_file() or path.stat().st_size == 0 for path in media):
        raise ValueError('MEDIA_FILE_MISSING')
    if not a.title.strip() or len(a.title) > (20 if a.command == 'note' else 30) or len(a.caption) > 1000:
        raise ValueError('CONTENT_LENGTH_OUT_OF_RANGE')
    if a.command == 'note' and (not 1 <= len(media) <= 35 or any(
        path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif'}
        or path.stat().st_size > 50 * 1024 * 1024 for path in media
    )):
        raise ValueError('IMAGE_INPUT_INVALID')
    if not a.confirm:
        print(json.dumps({'ok': True, 'preview': True, 'kind': a.command,
                          'title': a.title, 'files': paths, 'declaration': a.declaration,
                          **({'cover_vertical': a.cover_vertical, 'cover_horizontal': a.cover_horizontal,
                              'ready': bool(a.cover_vertical and a.cover_horizontal)} if a.command == 'video' else {})}, ensure_ascii=False))
        return 0
    if a.command == 'note' and not a.original_sound:
        raise ValueError('ORIGINAL_SOUND_REQUIRED_USE_STEPS_FOR_MUSIC')
    if a.command == 'video' and a.declaration == 'none':
        raise ValueError('VIDEO_BROWSER_PUBLISH_REQUIRES_AIGC_DECLARATION')
    if a.command == 'video' and (not a.cover_vertical or not a.cover_horizontal):
        raise ValueError('DUAL_COVER_MISSING: 需要 --cover-vertical 和 --cover-horizontal')
    name, script = ('douyin-video-publish', 'publish_douyin.py') if a.command == 'video' else ('douyin-note-publish', 'publish_douyin_note.py')
    args = [sys.executable, str(TOOLS / name / 'scripts' / script), 'run', '--title', a.title, '--caption', a.caption]
    if a.command == 'video':
        args += ['--video', str(Path(a.video).expanduser().resolve()),
                 '--cover-vertical', str(Path(a.cover_vertical).expanduser().resolve()),
                 '--cover-horizontal', str(Path(a.cover_horizontal).expanduser().resolve())]
    else:
        args += ['--declaration', 'none' if a.declaration == 'none' else 'ai', '--original-sound', '--images',
                 *[str(Path(path).expanduser().resolve()) for path in a.images]]
    return subprocess.call(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
