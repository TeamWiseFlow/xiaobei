#!/usr/bin/env python3
"""HTTP creator login, video and image-note publication with durable receipts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPTS = Path(__file__).resolve().parent
TOOLS = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TOOLS / '_shared'))
from publish_browser import Browser, MANAGE_URL, SESSION, publish_lock
sys.path.insert(0, str(TOOLS.parent.parent / '_shared'))
from publish_text import PublishTextError, read_publish_text
import video_publish as video
import note_publish as note


def content_options(parser):
    parser.add_argument('--title', required=True)
    parser.add_argument('--caption', default='', help='正文文字或 @UTF-8正文文件路径')


def video_commands(parent):
    commands = parent.add_subparsers(dest='action', required=True)
    for name, function in (
        ('publish', video.cmd_publish),
        ('get-link', video.cmd_get_link), ('resume', video.cmd_resume),
        ('status', video.cmd_status), ('verify-send', video.cmd_verify_send),
    ):
        command = commands.add_parser(name)
        command.add_argument('--session', default=SESSION, choices=[SESSION])
        command.set_defaults(func=lambda a, f=function: f(session=a.session))
        if name == 'publish':
            command.add_argument('--confirm', action='store_true')
        if name == 'verify-send':
            command.add_argument('--method', choices=('mobile_sms_verify', 'mobile_up_sms_verify'), default='mobile_sms_verify')
            command.add_argument('--confirm', action='store_true')
    for name in ('verify-prepare', 'verify-qr', 'verify-poll', 'verify-confirm'):
        command = commands.add_parser(name)
        if name == 'verify-prepare':
            command.add_argument('--restart', action='store_true', help='仅重建已过期的只读验证准备，不发送验证码或重发作品')
        if name == 'verify-confirm':
            command.add_argument('--method', choices=('mobile_up_sms_verify',), default='mobile_up_sms_verify')
            command.add_argument('--confirm', action='store_true')
    close = commands.add_parser('close', help='按用户确认结案本地任务；不撤回或删除线上作品')
    close.add_argument('--outcome', required=True, choices=('published', 'cancelled'))
    close.add_argument('--url', help='已发布作品的官方分享链接或完整视频链接')
    close.add_argument('--confirmation', required=True, help='用户确认原文或 @UTF-8确认文件')
    close.add_argument('--confirm', action='store_true')
    close.set_defaults(func=lambda a: video.cmd_close(
        outcome=a.outcome, url=a.url, confirmation=a.confirmation, confirm=a.confirm))
    run = commands.add_parser('run', help='完整视频流程；默认预览，--confirm 后提交')
    content_options(run)
    run.add_argument('--video', required=True)
    run.add_argument('--cover-vertical', help='竖封面；等比补底到 3:4')
    run.add_argument('--cover-horizontal', help='横封面；等比补底到 4:3')
    run.add_argument('--declaration', choices=('aigc', 'ai', 'none'), default='aigc')
    run.add_argument('--confirm', action='store_true')
    run.add_argument('--prepare-only', action='store_true', help='只上传并准备本次请求，停止在提交前')
    run.add_argument('--visibility', choices=('public', 'private', 'friends'), default='public')
    run.set_defaults(func=lambda a: video.cmd_run(
        video=a.video, title=a.title, caption=a.caption,
        cover_vertical=a.cover_vertical, cover_horizontal=a.cover_horizontal))
    verify = commands.add_parser('verify-code')
    verify.add_argument('--session', default=SESSION, choices=[SESSION])
    verify.add_argument('--code-file', required=True)
    verify.set_defaults(func=lambda a: video.cmd_verify_code(
        session=a.session, code_file=a.code_file))


def note_commands(parent):
    commands = parent.add_subparsers(dest='action', required=True)
    close = commands.add_parser('close')
    close.add_argument('--outcome', choices=('published', 'cancelled'), required=True)
    close.add_argument('--url')
    close.add_argument('--confirmation', required=True)
    close.add_argument('--confirm', action='store_true')
    for name in ('verify-prepare', 'verify-qr', 'verify-poll', 'verify-send', 'verify-code', 'verify-confirm'):
        verify = commands.add_parser(name)
        if name == 'verify-prepare':
            verify.add_argument('--restart', action='store_true', help='仅重建已过期的只读验证准备，不发送验证码或重发作品')
        if name in ('verify-send', 'verify-confirm'):
            verify.add_argument('--method', choices=('mobile_sms_verify', 'mobile_up_sms_verify'), default='mobile_up_sms_verify' if name == 'verify-confirm' else 'mobile_sms_verify')
            verify.add_argument('--confirm', action='store_true')
        if name == 'verify-code':
            verify.add_argument('--code-file', required=True)
    for name in ('publish', 'get-link', 'run', 'status', 'resume'):
        command = commands.add_parser(name)
        if name == 'run':
            command.add_argument('--images', nargs='+', required=True)
        if name == 'run':
            content_options(command)
            command.add_argument('--declaration', choices=('aigc', 'ai', 'none'), default='ai')
        if name == 'get-link':
            command.add_argument('--title', help='兼容旧参数，HTTP 取链以保存的原任务为准')
        if name in ('publish', 'run'):
            command.add_argument('--original-sound', action='store_true',
                                 help='明确使用原声；当前 HTTP 图文入口不提供配乐选择')
            command.add_argument('--confirm', action='store_true')
        if name == 'run':
            command.add_argument('--prepare-only', action='store_true')
            command.add_argument('--visibility', choices=('public', 'private', 'friends'), default='public')


def build_parser():
    parser = argparse.ArgumentParser(prog='douyin-publish', description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    login = commands.add_parser('login', help='复用统一 API 登录流程，生成抖音扫码二维码')
    login.add_argument('--resume-video', action='store_true',
                       help='仅恢复原 API 账号，保留已有提交记录')
    check = commands.add_parser('check', help='验证统一 API 账号及创作者会话')
    check.add_argument('--kind', choices=('video', 'note'), default='video')
    video_commands(commands.add_parser('video', help='HTTP 视频发布、收据、验证续接与取链'))
    note_commands(commands.add_parser('note', help='HTTP 原声图文发布、收据、验证续接与取链'))
    return parser


def normalize_argv(argv):
    args = list(sys.argv[1:] if argv is None else argv)
    # Preserve the existing "video/note --media ..." one-step form.
    if len(args) > 1 and args[0] in ('video', 'note') and args[1].startswith('--') and args[1] != '--help':
        args.insert(1, 'run')
    return args


def preview_run(args):
    if args.command == 'video':
        media = [str(video.validate_media(args.video))]
        video.validate_content(args.title, args.caption)
    else:
        media = [str(Path(path).expanduser().resolve()) for path in args.images]
        note.validate(media, args.title, args.caption)
    result = {'ok': True, 'preview': True, 'kind': args.command, 'action': 'run',
              'title': args.title, 'caption': args.caption, 'files': media,
              'declaration': args.declaration, 'visibility': args.visibility,
              'prepare_only': args.prepare_only}
    if args.command == 'video':
        result.update(cover_vertical=args.cover_vertical, cover_horizontal=args.cover_horizontal,
                      ready=bool(args.cover_vertical and args.cover_horizontal))
    print(json.dumps(result, ensure_ascii=False))
    return 0


def main(argv=None):
    args = build_parser().parse_args(normalize_argv(argv))
    backend = os.environ.get('DOUYIN_PUBLISH_BACKEND', 'api')
    if backend not in {'browser', 'api'}:
        raise ValueError('INVALID_PUBLISH_BACKEND')
    if backend == 'browser' and not (
            args.command == 'video' and getattr(args, 'action', '') in {'status', 'resume', 'get-link', 'close'}
            or args.command in {'video', 'note'} and getattr(args, 'action', '') in {'run', 'publish'}
                and not getattr(args, 'confirm', False)):
        raise ValueError('LEGACY_BROWSER_READ_ONLY: 新登录、发布和取数使用统一 API 会话')
    if backend == 'browser' and (args.command == 'login' or getattr(args, 'action', '') in {'run', 'publish'} and getattr(args, 'confirm', False)):
        from douyin_utils.creator import pending
        if pending():
            raise ValueError('PUBLISH_PENDING_API: 先核查原 HTTP 发布任务')
    if backend == 'api' and args.command == 'login':
        from douyin_utils.creator import pending
        if pending() and not args.resume_video:
            raise ValueError('PUBLISH_PENDING: 保留原任务，仅恢复原账号时使用 login --resume-video')
        target = Path.home() / '.openclaw/douyin-api/creator-login.png'
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        login_cli = TOOLS.parent.parent / 'douyin-hunter/tools/douyin-login/scripts/douyin_login.py'
        with publish_lock(allow_pending_video=args.resume_video):
            return subprocess.call([sys.executable, str(login_cli), 'qr', '--output', str(target)])
    if args.command == 'check':
        if backend == 'api':
            from douyin_utils.creator import owner, ensure_session, items
            from douyin_utils.http import DouyinRequestError, public_error_info, session
            try:
                uid = owner()
                ensure_session(uid)
                items(uid)
            except DouyinRequestError as exc:
                context = {'session_source': 'api'}
                try:
                    current = session()
                    context.update(session_file=str(current.path), runtime_expired=current.runtime_expired,
                                   identity_cached=bool(current.state.get('uid')),
                                   pending_action=(current.state.get('login_flow') or {}).get('action'))
                except DouyinRequestError:
                    pass
                print(json.dumps({'ok': False, 'error': exc.code, **context, **public_error_info(exc),
                                  'hint': '先用 douyin-login status 核对同一 API 会话并按其状态续接，不自动重新扫码或切换账号'}, ensure_ascii=False))
                return 2 if exc.code in {'API_SESSION_MISSING', 'API_SESSION_EXPIRED', 'PLATFORM_AUTH_REJECTED', 'PLATFORM_LOGIN_REJECTED', 'RUNTIME_EXPIRED'} else 1
            print(json.dumps({'ok': True, 'uid': uid, 'transport': 'http', 'session_source': 'api'}))
            return 0
        return subprocess.call([sys.executable, str(TOOLS / 'douyin-engagement/scripts/douyin_engagement.py'), 'check'])
    if hasattr(args, 'caption'):
        args.caption = read_publish_text(args.caption)
        if args.command == 'video':
            video.validate_content(args.title, args.caption)
        else:
            note.validate(title=args.title, caption=args.caption)
    if hasattr(args, 'confirmation'):
        args.confirmation = read_publish_text(args.confirmation)
    if hasattr(args, 'images'):
        args.images = [str(Path(path).expanduser().resolve()) for path in args.images]
        note.validate(images=args.images, title=getattr(args, 'title', '上传'))
    if args.command == 'video' and args.action == 'run':
        args.video = str(video.validate_media(args.video))
    if args.command == 'note' and hasattr(args, 'declaration'):
        args.declaration = 'none' if args.declaration == 'none' else 'ai'
    if args.action in ('run', 'publish') and not args.confirm:
        if args.action == 'run':
            return preview_run(args)
        print(json.dumps({'ok': True, 'preview': True, 'kind': args.command, 'action': 'publish',
                          'message': '先核对当前草稿、账号、文案、媒体与声明；已有发布授权时加 --confirm'}, ensure_ascii=False))
        return 0
    if args.action == 'run':
        if args.command == 'note' and not args.original_sound:
            raise ValueError('HTTP_ORIGINAL_SOUND_REQUIRED')
        if args.command == 'video':
            if args.declaration == 'none':
                raise ValueError('VIDEO_PUBLISH_REQUIRES_AIGC_DECLARATION')
            if not args.cover_vertical or not args.cover_horizontal:
                raise ValueError('DUAL_COVER_MISSING: 需要 --cover-vertical 和 --cover-horizontal')
    if backend == 'api':
        from douyin_utils.creator import execute
        if hasattr(args, 'visibility'):
            args.visibility = {'public': 0, 'private': 1, 'friends': 2}[args.visibility]
        with publish_lock():
            result = execute(args, prepare_cover=video.prepare_cover)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('ok') else 4 if result.get('state') == 'awaiting_verification' else 3
    if (args.command == 'note' and args.action in {'close', 'status', 'resume', 'verify-send', 'verify-code'}
            or args.action in {'verify-prepare', 'verify-qr', 'verify-poll', 'verify-confirm'}):
        raise ValueError('API_PUBLISH_CONFIGURATION_REQUIRED')
    if getattr(args, 'prepare_only', False) or getattr(args, 'visibility', 'public') != 'public':
        raise ValueError('API_PUBLISH_CONFIGURATION_REQUIRED')
    return (video if args.command == 'video' else note).execute(args)


def cli(argv=None):
    from douyin_utils.http import DouyinRequestError, public_error_info
    try:
        return main(argv)
    except PublishTextError as exc:
        print(json.dumps({'ok': False, 'error': 'CONTENT_FILE_INVALID', 'message': str(exc),
                          'publish_attempted': False}, ensure_ascii=False))
        return 1
    except video.PublishError as exc:
        print(json.dumps({'ok': False, 'error': exc.code, 'hint': exc.hint,
                          'publish_attempted': False}, ensure_ascii=False))
        return exc.exit_code
    except DouyinRequestError as exc:
        print(json.dumps({'ok': False, 'error': exc.code, **public_error_info(exc)}, ensure_ascii=False))
        return 1
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(cli())
