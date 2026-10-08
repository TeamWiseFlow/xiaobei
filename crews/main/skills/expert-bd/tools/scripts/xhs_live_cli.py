#!/usr/bin/env python3
"""Bounded CLI for XHS PC live-room and private-message primitives."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
from pathlib import Path
import sys
import time

from xhs_utils.pc_session import SessionMissing, load_auth, save_auth, session_lock


LIVE_METHODS = frozenset({
    'list_categories', 'square_feed', 'current_room_info', 'join_room',
    'viewer_heart', 'join_business_base_info', 'user_card',
    'join_comment_info', 'aggregate_business_info', 'resource_by_id',
    'gift_panel', 'charge_panel', 'user_violation', 'send_comment',
    'mic_relation',
})
IM_METHODS = frozenset({
    'get_chats', 'get_group_chats', 'get_chat_info', 'get_message_history',
    'get_following', 'get_unread', 'get_unread_count', 'get_web_config',
    'get_system_config', 'get_user_me', 'get_recent_chats', 'get_emoji_config',
    'get_redmoji_version', 'get_message_config', 'voice_convert',
    'get_all_offline_messages', 'report_offline_message_ack',
    'get_group_message_history', 'revoke_message', 'revoke_group_all_message',
    'report_total_unread', 'get_message_location_list',
    'report_message_location_read', 'add_personal_emoji',
    'delete_personal_emoji', 'get_smile_file_id', 'get_stick_top_messages',
    'delete_message', 'send_captured_short_link_message',
    'send_short_link_message', 'get_celestial_lt', 'detect_message_policy',
    'mark_messages_read',
})
WRITE_METHODS = frozenset({
    'send_comment', 'revoke_message', 'revoke_group_all_message',
    'report_total_unread', 'report_message_location_read', 'mark_messages_read',
    'report_offline_message_ack', 'add_personal_emoji', 'delete_personal_emoji',
    'delete_message', 'send_captured_short_link_message', 'send_short_link_message',
})


def im_operation(command: str, conversation: str, *, limit: int = 30,
                 cursor: str = '0', message: str = '') -> dict:
    """Resolve chat state and perform one bounded operation with a single auth lease."""
    from xhs_bd_api.live import XHSLiveAPI

    with session_lock():
        auth = load_auth()
        try:
            api = XHSLiveAPI(auth)
            if command == 'list':
                result = api.get_chats(limit=limit, page=int(cursor))
            elif command == 'groups':
                result = api.get_group_chats(limit=limit, page=int(cursor))
            elif command == 'unread':
                result = api.get_unread()
            elif command == 'history':
                if conversation.startswith('group:'):
                    result = api.get_group_message_history({'group_id': conversation[6:],
                                                           'last_id': int(cursor), 'limit': limit})
                else:
                    result = api.get_message_history(conversation, last_id=int(cursor), limit=limit)
            elif command == 'revoke':
                result = api.revoke_message({'chat_user_id': conversation, 'message_id': message})
            elif command == 'delete':
                result = api.delete_message({'chat_user_id': conversation})
            else:
                chat = None
                for page in range(20):
                    response = api.get_chats(limit=100, page=page)
                    if not response_ok(response):
                        return {'ok': False, 'command': command, 'data': response}
                    data = response.get('data') or {}
                    entries = data.get('chat_list', data.get('chats', []))
                    if not isinstance(entries, list):
                        raise ValueError('CHAT_LIST_INVALID')
                    chat = next((item for item in entries if str(item.get('chat_user_id') or
                                (item.get('info') or {}).get('user_id') or item.get('chat_id')) == conversation), None)
                    if chat is not None or not data.get('has_more') or not entries:
                        break
                if chat is None:
                    raise ValueError('CONVERSATION_NOT_FOUND')
                store_id = chat.get('last_store_id', chat.get('store_id'))
                unread = chat.get('unread_count')
                if store_id is None or unread is None or not str(store_id).isdigit() or not str(unread).isdigit():
                    raise ValueError('READ_STATE_MISSING')
                result = api.mark_messages_read([{'chat_id': conversation, 'read_store_id': int(store_id),
                                                 'unread_count': int(unread), 'type': 1, 'need_rm_offline': True}])
            return {'ok': response_ok(result), 'command': command, 'data': result}
        finally:
            try:
                save_auth(auth)
            finally:
                auth.close()


def response_ok(result) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get('success') is False:
        return False
    if result.get('code') is not None:
        return result['code'] in (0, '0', 200, '200')
    return result.get('success') is True or 'data' in result or 'result' in result


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str), flush=True)


def available_methods(domain: str) -> dict:
    from xhs_bd_api.live import XHSLiveAPI

    names = LIVE_METHODS if domain == 'live' else IM_METHODS
    return {name: str(inspect.signature(getattr(XHSLiveAPI, name))) for name in sorted(names)}


def call_http(domain: str, method: str, positional: list, named: dict) -> dict:
    names = LIVE_METHODS if domain == 'live' else IM_METHODS
    if method not in names:
        raise ValueError(f'{domain} 不支持 {method}；运行 methods 查看接口')
    from xhs_bd_api.live import XHSLiveAPI

    with session_lock():
        auth = load_auth()
        try:
            result = getattr(XHSLiveAPI(auth), method)(*positional, **named)
        finally:
            try:
                save_auth(auth)
            finally:
                auth.close()
    if isinstance(result, dict):
        return {'ok': response_ok(result), 'method': method, 'data': result}
    return {'ok': True, 'method': method, 'data': result}


async def _listen(domain: str, room_id: str | None, seconds: int, max_events: int) -> dict:
    from xhs_bd_api.live import XHSLiveAPI

    with session_lock():
        auth = load_auth()
        websocket = None
        count = 0
        try:
            api = XHSLiveAPI(auth)
            websocket = await api.connect_push_from_storage(room_id=room_id)
            save_auth(auth)
        except BaseException:
            try:
                if websocket is not None:
                    await websocket.close()
            finally:
                auth.close()
            raise
    try:
        emit({'ok': True, 'state': 'connected', 'domain': domain,
              'room_id': room_id})
        deadline = time.monotonic() + seconds
        events = websocket.events()
        while count < max_events:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                event = await asyncio.wait_for(events.__anext__(), timeout=remaining)
            except (asyncio.TimeoutError, StopAsyncIteration):
                break
            decoded = event.get('decoded') or {}
            if domain == 'live' and decoded.get('im') and not decoded.get('room'):
                continue
            if domain == 'im' and decoded.get('room') and not decoded.get('im'):
                continue
            emit({'ok': True, 'event': event})
            count += 1
        return {'ok': True, 'state': 'stopped', 'events': count}
    finally:
        try:
            await websocket.close()
        finally:
            auth.close()


async def _send_websocket(kind: str, *, receiver: str = '', content: str = '',
                          room_id: str = '', payload: dict | None = None,
                          frame: str = '') -> dict:
    from xhs_bd_api.live import XHSLiveAPI

    with session_lock():
        auth = load_auth()
        websocket = None
        try:
            api = XHSLiveAPI(auth)
            websocket = await api.connect_push_from_storage(room_id=room_id or None)
            if kind == 'private':
                result = await websocket.send_private_message(receiver, content)
                return {'ok': True, 'state': 'submitted', 'mid': result['mid']}
            if kind == 'room-text':
                args = dict(payload or {})
                args['room_id'] = room_id
                await websocket.send_room_text(**args)
                return {'ok': True, 'state': 'submitted', 'room_id': room_id}
            if kind == 'captured-im':
                await websocket.send_captured_im_frame(frame)
                return {'ok': True, 'state': 'submitted', 'kind': kind}
            if kind == 'captured-room':
                await websocket.send_captured_room_frame(frame)
                return {'ok': True, 'state': 'submitted', 'kind': kind}
            raise ValueError(f'unknown websocket kind: {kind}')
        finally:
            try:
                if websocket is not None:
                    await websocket.close()
                save_auth(auth)
            finally:
                auth.close()


def _json_arg(text: str, expected: type, option: str):
    value = json.loads(text)
    if not isinstance(value, expected):
        raise ValueError(f'{option} 需要 JSON {expected.__name__}')
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description='小红书直播与私信 PC HTTP/WebSocket')
    parser.add_argument('domain', choices=('live', 'im'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('methods')
    call = sub.add_parser('call')
    call.add_argument('method')
    call.add_argument('--args', default='[]')
    call.add_argument('--kwargs', default='{}')
    call.add_argument('--confirm', action='store_true')
    for name in ('list', 'groups', 'history', 'unread', 'read', 'revoke', 'delete'):
        part = sub.add_parser(name)
        if name in ('history', 'read', 'revoke', 'delete'):
            part.add_argument('--conversation', required=True)
        if name in ('list', 'groups', 'history'):
            part.add_argument('--limit', type=int, default=30)
            part.add_argument('--cursor', default='0')
        if name == 'revoke':
            part.add_argument('--message', required=True)
        if name in ('read', 'revoke', 'delete'):
            part.add_argument('--confirm', action='store_true')
    listen = sub.add_parser('listen')
    listen.add_argument('--room-id', default='')
    listen.add_argument('--seconds', type=int, default=60)
    listen.add_argument('--max-events', type=int, default=100)
    send = sub.add_parser('send')
    send.add_argument('target')
    send.add_argument('content')
    send.add_argument('--host-id', default='')
    send.add_argument('--confirm', action='store_true')
    room_text = sub.add_parser('room-text')
    room_text.add_argument('room_id')
    room_text.add_argument('--payload', required=True,
                           help='room_type, command, nickname, avatar, user_id, content, priority, role 的 JSON 对象')
    room_text.add_argument('--confirm', action='store_true')
    captured = sub.add_parser('send-captured-frame')
    captured.add_argument('kind', choices=('im', 'room'))
    captured.add_argument('frame_file')
    captured.add_argument('--room-id', default='')
    captured.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'send' and args.domain == 'im' and args.target.startswith('group:'):
            raise ValueError('GROUP_OPERATION_UNSUPPORTED')
        if args.command == 'send' and not args.content.strip():
            raise ValueError('消息正文不能为空')
        if args.command in ('list', 'groups', 'history', 'unread', 'read', 'revoke', 'delete'):
            if args.domain != 'im':
                raise ValueError('命令仅适用于 xhs-im')
            conversation = getattr(args, 'conversation', '')
            if args.command in ('read', 'revoke', 'delete') and conversation.startswith('group:'):
                raise ValueError('GROUP_OPERATION_UNSUPPORTED')
            if hasattr(args, 'limit') and not 1 <= args.limit <= 100:
                raise ValueError('LIMIT_OUT_OF_RANGE')
            if hasattr(args, 'cursor') and (not args.cursor.isascii() or not args.cursor.isdigit()):
                raise ValueError('CURSOR_INVALID')
            if args.command in ('read', 'revoke', 'delete') and not args.confirm:
                result = {'ok': True, 'preview': True, 'command': args.command,
                          'conversation': conversation, 'message': getattr(args, 'message', None)}
            else:
                result = im_operation(args.command, conversation, limit=getattr(args, 'limit', 30),
                                      cursor=getattr(args, 'cursor', '0'), message=getattr(args, 'message', ''))
            emit(result)
            return 0 if result.get('ok') else 1
        write = args.command in ('send', 'room-text', 'send-captured-frame') or (
            args.command == 'call' and args.method in WRITE_METHODS)
        if write and not args.confirm:
            emit({'ok': True, 'preview': True, 'domain': args.domain, 'command': args.command,
                  'method': getattr(args, 'method', None), 'target': getattr(args, 'target', None),
                  'content': getattr(args, 'content', None)})
            return 0
        if args.command == 'methods':
            result = {'ok': True, 'methods': available_methods(args.domain)}
        elif args.command == 'call':
            result = call_http(args.domain, args.method,
                               _json_arg(args.args, list, '--args'),
                               _json_arg(args.kwargs, dict, '--kwargs'))
        elif args.command == 'listen':
            if args.domain == 'live' and not args.room_id:
                raise ValueError('直播监听需要 --room-id')
            if not 1 <= args.seconds <= 3600 or not 1 <= args.max_events <= 1000:
                raise ValueError('--seconds 需为 1..3600，--max-events 需为 1..1000')
            result = asyncio.run(_listen(args.domain, args.room_id or None,
                                         args.seconds, args.max_events))
        elif args.command == 'send':
            if not args.content.strip():
                raise ValueError('消息正文不能为空')
            if args.domain == 'live':
                if not args.host_id:
                    raise ValueError('直播评论需要 --host-id')
                result = call_http('live', 'send_comment', [args.target, args.content],
                                   {'host_id': args.host_id})
            else:
                result = asyncio.run(_send_websocket('private', receiver=args.target,
                                                      content=args.content))
        elif args.command == 'room-text':
            if args.domain != 'live':
                raise ValueError('room-text 仅用于直播')
            result = asyncio.run(_send_websocket(
                'room-text', room_id=args.room_id,
                payload=_json_arg(args.payload, dict, '--payload')))
        else:
            if (args.domain == 'live' and args.kind != 'room') or (
                args.domain == 'im' and args.kind != 'im'
            ):
                raise ValueError('捕获帧类型须与工具领域一致')
            frame = Path(args.frame_file).expanduser().read_text(encoding='utf-8').strip()
            result = asyncio.run(_send_websocket('captured-' + args.kind,
                                                 room_id=args.room_id, frame=frame))
        emit(result)
        return 0 if result.get('ok') else 1
    except SessionMissing as exc:
        emit({'ok': False, 'error': 'SESSION_MISSING', 'message': str(exc)})
        return 2
    except Exception as exc:
        emit({'ok': False, 'error': type(exc).__name__, 'message': str(exc)[:250]})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
