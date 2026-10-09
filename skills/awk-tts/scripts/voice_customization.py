#!/usr/bin/env python3
"""Create and manage workspace-bound Qwen-Audio voice profiles."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from bailian_media import APIError, download, fingerprint, media_info, request, save_json, upload, workspace

MODELS = ['qwen-audio-3.0-tts-plus', 'qwen-audio-3.1-tts-flash', 'qwen-audio-3.0-tts-flash']
CUSTOMIZATION = '/services/audio/tts/customization'


def route(platform='auto'):
    import tts
    if platform == 'auto':
        return tts.resolve_tts_provider()
    if platform == 'volc':
        import volc_voice
        volc_voice.headers()
        return 'volc'
    if platform == 'workspace':
        base, key = workspace()
        return ('bailian', base, key, 'workspace')
    key = os.environ.get('AWK_API_KEY', '').strip()
    if not key:
        raise ValueError('Agent Plan 需要 AWK_API_KEY')
    return ('bailian', tts.BAILIAN_AGENT_PLAN_BASE, key, 'agent-plan')


def profile_route(profile):
    provider = profile.get('provider')
    if provider == 'volc':
        import volc_voice
        volc_voice.headers()
        if profile.get('base_url') != volc_voice.BASE:
            raise ValueError('火山音色档案端点无效')
        if profile.get('app_id') and profile['app_id'] != os.environ.get('VOLC_TTS_APP_ID', '').strip():
            raise ValueError('火山音色档案所属 APP 与当前配置不一致')
        return 'volc'
    if provider not in ('bailian-workspace', 'bailian-agent-plan'):
        raise ValueError('音色档案供应商无效')
    selected = route('workspace' if provider == 'bailian-workspace' else 'agent-plan')
    if selected[1] != profile.get('base_url'):
        raise ValueError('音色必须在创建时的业务空间 / Agent Plan 使用')
    return selected


def payload(args, audio_url=None):
    if not re.fullmatch(r'[A-Za-z0-9]{1,10}', args.name):
        raise ValueError('--name 仅允许 1–10 位英文字母/数字')
    inp = {'action': 'create_voice', 'target_model': args.target_model, 'prefix': args.name}
    body = {'model': 'voice-enrollment', 'input': inp}
    if args.command == 'voice-design':
        if not 1 <= len(args.description.strip()) <= 500:
            raise ValueError('声音描述须为 1–500 字符')
        if not 15 <= len(args.preview_text.strip()) <= 200:
            raise ValueError('试听文本须为 15–200 字符')
        inp.update(voice_prompt=args.description, preview_text=args.preview_text, language_hints=[args.language])
        body['parameters'] = {'sample_rate': 24000, 'response_format': 'wav'}
    else:
        if not audio_url:
            raise ValueError('声音复刻需要音频')
        inp['url'] = audio_url
    return body


def check_audio(path):
    if path.suffix.lower() not in ('.wav', '.mp3', '.m4a'):
        raise ValueError('复刻样本使用 WAV / MP3 / M4A')
    if path.stat().st_size >= 10 * 1024 * 1024:
        raise ValueError('复刻样本须小于 10MB')
    seconds, streams = media_info(path)
    if not 10 <= seconds <= 20 or not any(s['codec_type'] == 'audio' for s in streams):
        raise ValueError('请提供 10–20 秒清晰单人语音样本，无背景音乐')
    return seconds


def refresh(profile_path, *, wait=0):
    profile_path = Path(profile_path)
    profile = json.loads(profile_path.read_text())
    selected = profile_route(profile)
    if selected == 'volc':
        import volc_voice
        return volc_voice.refresh(profile_path, profile, wait)
    _, base, key, _ = selected
    if not profile.get('voice_id'):
        raise ValueError('音色档案不属于当前业务空间或缺少 voice_id')
    deadline = time.monotonic() + wait
    while True:
        data = request(base, key, CUSTOMIZATION,
                       {'model': 'voice-enrollment', 'input': {'action': 'query_voice', 'voice_id': profile['voice_id']}})
        output = data.get('output') or {}
        if output.get('target_model') and output['target_model'] != profile['target_model']:
            raise ValueError('远端音色绑定模型与本地档案不一致')
        profile['status'] = output.get('status', 'UNKNOWN')
        save_json(profile_path, profile)
        if profile['status'] in ('OK', 'UNDEPLOYED') or time.monotonic() >= deadline:
            return profile
        time.sleep(min(3, max(0, deadline - time.monotonic())))


def load_profile(path):
    profile = json.loads(Path(path).read_text())
    selected = profile_route(profile)
    supported = ['seed-icl-2.0'] if selected == 'volc' else MODELS
    if profile.get('status') != 'OK' or not profile.get('voice_id') or profile.get('target_model') not in supported:
        raise ValueError('音色尚未可用或模型不受支持；先运行 awk-tts voice-status --profile ...')
    return selected, profile


def create(args):
    selected = route(args.platform)
    folder = args.out_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    profile_path = folder / 'voice.json'
    if profile_path.exists():
        raise ValueError('voice.json 已存在；用 voice-status 恢复查询，或换输出目录创建另一音色')
    source_hash = None
    source = None
    if selected == 'volc':
        import volc_voice
        # Validate slot and provider/model options before any upload.
        if args.command == 'voice-design':
            volc_voice.build_payload(args)
    else:
        args.target_model = args.target_model or MODELS[0]
        if args.target_model not in MODELS:
            raise ValueError('百炼只支持 Qwen-Audio 语音合成模型')
        body = payload(args, 'placeholder' if args.command == 'voice-clone' else None)
    if args.command == 'voice-clone':
        if args.audio.startswith(('https://', 'http://')):
            # Validate the exact sample the service will receive, then upload those bytes.
            suffix = Path(args.audio.split('?', 1)[0]).suffix.lower() or '.wav'
            source = download(args.audio, folder / ('sample' + suffix), max_bytes=10*1024*1024)
        else:
            source = Path(args.audio).resolve()
        check_audio(source)
        source_hash = fingerprint(source)
    if selected == 'volc':
        profile_path, profile = volc_voice.create(args, source)
        print(json.dumps({'profile': str(profile_path), 'status': profile['status'], 'voice_id': profile['voice_id']}, ensure_ascii=False))
        return 0 if profile['status'] == 'OK' else 2
    _, base, key, mode = selected
    if source:
        body['input']['url'] = upload(base, key, source, 'voice-enrollment')
    profile = {'schema_version': 1, 'provider': 'bailian-' + mode, 'base_url': base,
               'kind': args.command.removeprefix('voice-'), 'target_model': args.target_model,
               'status': 'CREATING', 'sample_sha256': source_hash}
    save_json(profile_path, profile)
    try:
        data = request(base, key, CUSTOMIZATION, body, timeout=120)
    except APIError:
        profile['status'] = 'CREATE_UNCONFIRMED'
        save_json(profile_path, profile)
        raise
    output = data.get('output') or {}
    voice_id = output.get('voice_id') or output.get('voice')
    if not voice_id:
        raise ValueError('创建响应缺少 voice_id；先查询音色列表，不要重复创建')
    profile.update(voice_id=voice_id, status=output.get('status', 'PENDING'), request_id=data.get('request_id'))
    save_json(profile_path, profile)  # persist identity before preview decode / status polling
    preview = output.get('preview_audio') or {}
    if preview.get('data'):
        (folder / 'preview.wav').write_bytes(base64.b64decode(preview['data'], validate=True))
        profile['preview_file'] = str(folder / 'preview.wav')
        save_json(profile_path, profile)
    profile = refresh(profile_path, wait=args.wait)
    print(json.dumps({'profile': str(profile_path), 'voice_id': profile['voice_id'],
                      'target_model': profile['target_model'], 'status': profile['status'],
                      'preview_file': profile.get('preview_file')}, ensure_ascii=False))
    return 0 if profile['status'] == 'OK' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('voice-design', 'voice-clone'):
        sub = subs.add_parser(name)
        sub.add_argument('--name', default='voice')
        sub.add_argument('--platform', choices=['auto', 'volc', 'workspace', 'agent-plan'], default='auto')
        sub.add_argument('--speaker-id', help='火山已购音色槽位 S_...；不自动购买')
        sub.add_argument('--target-model', choices=MODELS + ['seed-icl-2.0'], default=None)
        sub.add_argument('--out-dir', required=True, type=Path)
        sub.add_argument('--wait', type=int, default=60)
        sub.add_argument('--language', choices=['zh', 'en'], default='zh')
        if name == 'voice-design':
            sub.add_argument('--description', required=True)
            sub.add_argument('--preview-text', required=True)
        else:
            sub.add_argument('--preview-text', default=None, help='火山复刻试听文本')
            sub.add_argument('--audio', required=True, help='本人/已授权的 10–20 秒样本，文件或 HTTP(S) URL')
    sub = subs.add_parser('voice-status')
    sub.add_argument('--profile', required=True, type=Path)
    sub.add_argument('--wait', type=int, default=0)
    sub = subs.add_parser('voice-list')
    sub.add_argument('--platform', choices=['auto', 'workspace', 'agent-plan'], default='auto')
    sub.add_argument('--prefix', default='')
    sub.add_argument('--page', type=int, default=0)
    args = parser.parse_args(argv)
    if hasattr(args, 'wait') and not 0 <= args.wait <= 600:
        parser.error('--wait 范围 0–600 秒')
    if args.command == 'voice-status':
        profile = refresh(args.profile, wait=args.wait)
        print(json.dumps(profile, ensure_ascii=False))
        return 0 if profile['status'] == 'OK' else 2
    if args.command == 'voice-list':
        selected = route(args.platform)
        if selected == 'volc':
            raise ValueError('火山使用 voice-status --profile 查询槽位；voice-list 仅用于百炼，请显式 --platform workspace/agent-plan')
        _, base, key, _ = selected
        data = request(base, key, CUSTOMIZATION, {'model': 'voice-enrollment', 'input': {
            'action': 'list_voice', 'prefix': args.prefix, 'page_index': args.page, 'page_size': 20}})
        voices = (data.get('output') or {}).get('voice_list', [])
        print(json.dumps([{k: item.get(k) for k in ('voice_id', 'status', 'target_model')} for item in voices], ensure_ascii=False))
        return 0
    return create(args)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, APIError) as exc:
        print(f'[error] {exc}', file=sys.stderr)
        raise SystemExit(1)
