"""Volcengine v3 voice design/cloning; credentials follow the existing TTS routing."""
import base64
import os
from pathlib import Path
import time
import uuid

import requests

from bailian_media import APIError, download, fingerprint, save_json

BASE = 'https://openspeech.bytedance.com/api/v3'


def headers():
    result = {'Content-Type': 'application/json', 'X-Api-Request-Id': str(uuid.uuid4())}
    app_id, access = (os.environ.get(k, '').strip() for k in ('VOLC_TTS_APP_ID', 'VOLC_TTS_ACCESS_KEY'))
    api_key = os.environ.get('VOLC_TTS_APP_KEY', '').strip()
    if app_id and access:
        # Enrollment uses App-Key, whereas speech synthesis uses App-Id.
        result.update({'X-Api-App-Key': app_id, 'X-Api-Access-Key': access})
    elif api_key:
        result['X-Api-Key'] = api_key
    else:
        raise ValueError('缺少火山 VOLC_TTS_APP_ID + VOLC_TTS_ACCESS_KEY 或 VOLC_TTS_APP_KEY')
    return result


def call(path, body):
    try:
        response = requests.post(BASE + path, json=body, headers=headers(), timeout=180)
    except requests.RequestException as exc:
        raise APIError(f'火山请求结果不确定：{type(exc).__name__}；先查询音色状态，勿重复训练') from None
    try:
        data = response.json()
    except ValueError:
        raise APIError(f'火山 HTTP {response.status_code}，非 JSON 响应') from None
    if response.status_code >= 400 or data.get('code', 0) not in (0, 20000000):
        raise APIError(f'火山 HTTP {response.status_code} code={data.get("code")} logid={response.headers.get("X-Tt-Logid", "-")}')
    return data


def build_payload(args, source=None):
    speaker = args.speaker_id or os.environ.get('VOLC_TTS_SPEAKER_ID', '').strip()
    if not speaker or not speaker.startswith('S_'):
        raise ValueError('火山音色创建需 --speaker-id S_... 或 VOLC_TTS_SPEAKER_ID（已购空闲槽位）；不会自动购买')
    if args.target_model not in (None, 'seed-icl-2.0'):
        raise ValueError('火山自定义音色只绑定 seed-icl-2.0，不接受百炼 target-model')
    body = {'speaker_id': speaker, 'language': 0 if args.language == 'zh' else 1}
    if args.command == 'voice-design':
        if not 1 <= len(args.description.strip()) <= 200 or not 1 <= len(args.preview_text.strip()) <= 300:
            raise ValueError('火山描述须为 1–200 字，试听文本为 1–300 字')
        body.update(prompt={'text_prompt': args.description}, text=args.preview_text)
    else:
        if not source:
            raise ValueError('声音复刻需要样本')
        body['audio'] = {'data': base64.b64encode(Path(source).read_bytes()).decode(), 'format': Path(source).suffix[1:].lower()}
        if args.preview_text:
            if not 4 <= len(args.preview_text) <= 300:
                raise ValueError('复刻试听文本须为 4–300 字')
            body['extra_params'] = {'demo_text': args.preview_text}
    return body


def update(profile, data):
    status = data.get('status')
    profile['remote_status'] = status
    profile['status'] = 'OK' if status in (2, 4) else ('FAILED' if status in (0, 3) else 'PENDING')
    profile['voice_id'] = data.get('speaker_id') or profile['voice_id']
    profile['remaining_training_times'] = data.get('available_training_times')
    versions = data.get('speaker_status') or []
    match = next((item for item in versions if item.get('model_type') == 5), None)
    if match:
        profile['model_type'] = 5
    return data.get('demo_audio') or ((match or {}).get('demo_audio'))


def save_preview(profile_path, profile, url):
    if url:
        path = profile_path.parent / 'preview.mp3'
        download(url, path, max_bytes=20*1024*1024)
        profile['preview_file'] = str(path)
        save_json(profile_path, profile)


def refresh(profile_path, profile, wait=0):
    headers()  # credential check without calling API
    if profile.get('base_url') != BASE:
        raise ValueError('火山音色档案端点无效')
    bound_app = profile.get('app_id')
    if bound_app and bound_app != os.environ.get('VOLC_TTS_APP_ID', '').strip():
        raise ValueError('火山音色档案所属 APP 与当前配置不一致')
    deadline = time.monotonic() + wait
    while True:
        data = call('/tts/get_voice', {'speaker_id': profile['voice_id']})
        preview = update(profile, data)
        save_json(profile_path, profile)
        if profile['status'] in ('OK', 'FAILED') or time.monotonic() >= deadline:
            save_preview(profile_path, profile, preview)
            return profile
        time.sleep(min(3, max(0, deadline - time.monotonic())))


def create(args, source=None):
    body = build_payload(args, source)
    profile_path = args.out_dir.resolve() / 'voice.json'
    if profile_path.exists():
        raise ValueError('音色档案已存在，使用 voice-status 查询，不重复训练')
    profile = {'schema_version': 1, 'provider': 'volc', 'base_url': BASE,
               'kind': args.command.removeprefix('voice-'), 'target_model': 'seed-icl-2.0',
               'voice_id': body['speaker_id'], 'status': 'CREATING',
               'app_id': os.environ.get('VOLC_TTS_APP_ID', '').strip(),
               'model_type': None, 'sample_sha256': fingerprint(source) if source else None}
    save_json(profile_path, profile)
    try:
        data = call('/tts/voice_design' if args.command == 'voice-design' else '/tts/voice_clone', body)
    except APIError:
        profile['status'] = 'CREATE_UNCONFIRMED'
        save_json(profile_path, profile)
        raise
    preview = update(profile, data)
    save_json(profile_path, profile)
    save_preview(profile_path, profile, preview)
    if profile['status'] == 'PENDING':
        profile = refresh(profile_path, profile, args.wait)
    return profile_path, profile
