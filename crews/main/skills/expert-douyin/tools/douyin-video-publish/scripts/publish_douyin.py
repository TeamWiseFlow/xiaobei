#!/usr/bin/env python3
"""Persistent creator video publication with validated inputs and resumable SMS."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import unicodedata
from typing import Optional
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from publish_browser import Browser, MANAGE_URL, SESSION, UPLOAD_URL, publish_lock, video_publish_state_path

PERSISTENT_SESSION = SESSION
UPLOAD_TIMEOUT_S = 300
TRANSCODE_MAX_WAIT_S = 600
POST_PUBLISH_MAX_WAIT_S = 60
TITLE_SELECTOR = 'input[placeholder*="填写作品标题"]'
CAPTION_SELECTOR = '[contenteditable="true"][data-slate-editor="true"]'
WORK_LIST_URL = ('https://creator.douyin.com/janus/douyin/creator/pc/work_list'
                 '?status=0&count=20&max_cursor=0&scene=star_atlas&device_platform=android&aid=1128')
PENDING_STATES = {'submitted', 'awaiting_verification', 'unconfirmed'}
DRAFT_HINT = '保留当前页面；用 edit-draft 继续编辑并检查视频、标题与双封面；视频缺失时 upload --resume-draft --video 原成片路径'
RESULT_HINT = '用 resume/get-link 核查本次作品，勿重跑 run 或重复点发布；未确认成功时可检查原草稿'


class PublishError(RuntimeError):
    def __init__(self, code, hint='', exit_code=1):
        super().__init__(code)
        self.code, self.hint, self.exit_code = code, hint, exit_code


def browser(session):
    if session != SESSION:
        raise PublishError('SESSION_INVALID', '必须使用持久化 session douyin')
    return Browser()


def camoufox_eval(session, js, timeout=30):
    result = browser(session).command('eval', js, timeout=timeout)
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def evaluate(session, js):
    result = browser(session).eval(js)
    return result


def state_path():
    return video_publish_state_path()


def read_state():
    path = state_path()
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text('utf-8'))
        if not isinstance(state, dict) or state.get('session') != SESSION:
            raise ValueError('invalid state')
        return state
    except (OSError, ValueError) as exc:
        raise PublishError('PUBLISH_STATE_INVALID', '保留原状态文件并人工核查本次任务') from exc


def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state['session'] = SESSION
    fd, temporary = tempfile.mkstemp(prefix='.douyin-video-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(state, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_no_pending():
    if read_state().get('state') in PENDING_STATES:
        raise PublishError('PUBLISH_PENDING', RESULT_HINT, 3)


def _check_logged_in(session):
    url = evaluate(session, 'window.location.href') or ''
    if url.split('?', 1)[0].rstrip('/').endswith(('/login', '/creator-micro/login')):
        raise PublishError('SESSION_EXPIRED', '执行 douyin-publish login；提交过的作品先核实，勿重发', 2)


# Keyboard and pointer operations use fresh, scoped Playwright refs.
def control_ref(session, selector, *, button=False):
    marker = 'data-xiaobei-publish-target'
    setup = evaluate(session, f'''(() => {{
      const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
      const nodes = Array.from(document.querySelectorAll({json.dumps(selector)})).filter(visible);
      if (nodes.length !== 1 || nodes[0].disabled || nodes[0].readOnly || nodes[0].getAttribute('aria-disabled') === 'true') return false;
      document.querySelectorAll('[{marker}]').forEach(e => e.removeAttribute('{marker}'));
      const e = nodes[0]; e.setAttribute('{marker}', '1');
      e.setAttribute('data-xiaobei-old-label', e.getAttribute('aria-label') || '');
      e.setAttribute('aria-label', 'xiaobei publication target');
      if ({json.dumps(button)} && !e.matches('button,[role="button"],a,input')) {{
        e.setAttribute('data-xiaobei-old-role', e.getAttribute('role') || ''); e.setAttribute('role', 'button');
      }} else if (!{json.dumps(button)} && e.isContentEditable && e.getAttribute('role')!=='textbox') {{
        e.setAttribute('data-xiaobei-old-role', e.getAttribute('role') || ''); e.setAttribute('role', 'textbox');
      }}
      return true;
    }})()''')
    if setup is not True:
        raise PublishError('CONTROL_NOT_UNIQUE_OR_EDITABLE', selector)
    snapshot = browser(session).command('snapshot', '-s', f'[{marker}]')
    refs = re.findall(r'\[ref=(e\d+)\]', snapshot.get('snapshot', ''))
    if not refs:
        raise PublishError('CONTROL_REF_MISSING', selector)
    return refs[0]


def cleanup_control(session):
    evaluate(session, '''(() => {
      document.querySelectorAll('[data-xiaobei-old-role]').forEach(e => {
        const role=e.getAttribute('data-xiaobei-old-role');
        if (role) e.setAttribute('role',role); else e.removeAttribute('role');
        e.removeAttribute('data-xiaobei-old-role');
      });
      document.querySelectorAll('[data-xiaobei-old-label]').forEach(e => {
        const label=e.getAttribute('data-xiaobei-old-label');
        if (label) e.setAttribute('aria-label',label); else e.removeAttribute('aria-label');
        e.removeAttribute('data-xiaobei-old-label');
      });
      document.querySelectorAll('[data-xiaobei-publish-target]').forEach(e => e.removeAttribute('data-xiaobei-publish-target'));
    })()''')


def click_selector(session, selector):
    try:
        ref = control_ref(session, selector, button=True)
        browser(session).command('click', ref)
    finally:
        cleanup_control(session)


def click_text(session, text, *, scope='body', required=True):
    selected = evaluate(session, f'''(() => {{
      const root=document.querySelector({json.dumps(scope)}); if (!root) return false;
      const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
      const nodes=Array.from(root.querySelectorAll('button,[role="button"],div,span,li,option,a,label'))
        .filter(e=>visible(e) && (e.innerText||'').trim()==={json.dumps(text)});
      const buttons=nodes.filter(e=>e.matches('button,[role="button"]'));
      const leaves=nodes.filter(e=>!nodes.some(child=>child!==e && e.contains(child)));
      const targets=buttons.length ? buttons : leaves;
      if (targets.length!==1) return false;
      targets[0].setAttribute('data-xiaobei-text-target','1'); return true;
    }})()''')
    if not selected:
        if required:
            raise PublishError('CONTROL_NOT_FOUND', text)
        return False
    try:
        click_selector(session, '[data-xiaobei-text-target]')
    finally:
        evaluate(session, "document.querySelectorAll('[data-xiaobei-text-target]').forEach(e=>e.removeAttribute('data-xiaobei-text-target'))")
    return True


def editor_text_matches(actual, expected):
    # Slate topic nodes may add Unicode spaces/format characters. Compare the
    # whole logical text: a matching prefix cannot prove the rest was written.
    def normalized(text):
        return ''.join(c for c in unicodedata.normalize('NFKC', text)
                       if not c.isspace() and unicodedata.category(c) != 'Cf')
    return normalized(actual) == normalized(expected)


def camoufox_type(session, selector, text):
    try:
        ref = control_ref(session, selector)
        b = browser(session)
        b.command('click', ref)
        b.command('press', 'ControlOrMeta+A')
        b.command('press', 'Backspace')
        if text:
            b.command('type', ref, text)
        b.command('press', 'Tab')
        # Read after React renders, including controlled-value reversion. Inputs
        # (titles and OTPs) must match exactly, including short or empty values.
        result = evaluate(session, f'''(async () => {{
          await new Promise(r=>setTimeout(r,150));
          const e=document.querySelector({json.dumps(selector)});
          if (!e) return null;
          return 'value' in e ? {{value:e.value}} : {{editor:e.innerText||''}};
        }})()''')
        if not isinstance(result, dict):
            return False
        if 'value' in result:
            return result['value'] == text
        return editor_text_matches(result.get('editor', ''), text)
    finally:
        cleanup_control(session)


def page_status(session):
    _check_logged_in(session)
    result = evaluate(session, r'''(() => {
      const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
      const text=document.body.innerText||'';
      // The permanent "点击发布后…上传中…请勿关闭页面" footer is advice,
      // not upload progress. It can span lines in the rendered page.
      const busyText=text.replace(/点击发布后[\s\S]*?请勿关闭页面[^\n]*/g, '');
      const busy=/上传中|正在上传|转码中|正在转码|视频处理中/.test(busyText);
      const progress=Array.from(document.querySelectorAll('[role="progressbar"]')).some(e=>
        visible(e) && Number(e.getAttribute('aria-valuenow')) < Number(e.getAttribute('aria-valuemax')||100));
      const videos=Array.from(document.querySelectorAll('video'));
      const video=videos.some(v=>
        (v.currentSrc||v.getAttribute('src')) && v.readyState>=2 && Number.isFinite(v.duration) && v.duration>0);
      const title=document.querySelector('input[placeholder*="填写作品标题"]');
      const caption=document.querySelector('[contenteditable="true"][data-slate-editor="true"]');
      const declarationDialog=Array.from(document.querySelectorAll('[role="dialog"]')).some(e=>
        visible(e) && /对作品内容添加声明|内容由AI生成/.test(e.innerText||''));
      const coverControls=Array.from(document.querySelectorAll('[class*="coverControl"]')).filter(visible);
      const hasPreview=e=>Array.from(e.querySelectorAll('img')).some(i=>
        i.complete && i.naturalWidth>=120 && i.naturalHeight>=120 && !!i.getAttribute('src')) ||
        [e,...e.querySelectorAll('*')].some(n=>n.clientWidth>=60 && n.clientHeight>=60 && /^url\(/.test(getComputedStyle(n).backgroundImage));
      // Prefer the two observed cover slots; fallback to separately labelled slots.
      const labelledCover=label=>Array.from(document.querySelectorAll('div,section'))
        .some(e=>visible(e) && (e.innerText||'').trim().length<100 &&
          (e.innerText||'').includes(label) && hasPreview(e) &&
          !/选择封面|设置横封面|设置竖封面/.test(e.innerText||''));
      const covers=coverControls.length===2 ? coverControls.every(hasPreview) :
        labelledCover('竖封面') && labelledCover('横封面');
      const missing=/双封面缺失|横封面缺失|竖封面缺失/.test(text);
      const quality=/封面存在文字展示不全|封面不佳/.test(text);
      const sms=/接收短信验证码|请输入当前手机号收到的短信验证码/.test(text);
      const rejected=(text.match(/(?:发布失败|上传失败|转码失败|验证码错误|验证码不正确|验证码已过期)[^\n]{0,80}/)||[])[0]||'';
      return {url:location.href,video_ready:video && !busy && !progress,busy:busy||progress,
        video_sources:videos.map(v=>v.currentSrc||v.getAttribute('src')).filter(Boolean),
        video_duration:videos.find(v=>v.readyState>=2 && Number.isFinite(v.duration) && v.duration>0)?.duration||0,
        caption:caption ? caption.innerText||'' : null,
        title:title ? title.value : '',dual_cover_ready:covers && !missing,cover_missing:missing,
        cover_quality_error:quality,sms_required:sms,rejected:rejected,
        aigc:text.includes('内容由AI生成') && !text.includes('请选择自主声明') && !declarationDialog};
    })()''')
    if not isinstance(result, dict):
        raise PublishError('PAGE_STATUS_UNAVAILABLE', DRAFT_HINT)
    return result


def wait_for(session, check, timeout, code, hint=DRAFT_HINT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = page_status(session)
        if status['rejected']:
            raise PublishError('PLATFORM_REJECTED', status['rejected'])
        if check(status):
            return status
        time.sleep(2)
    raise PublishError(code, hint)


def validate_media(video):
    path = Path(video).expanduser().resolve()
    if path.suffix.lower() not in {'.mp4', '.mov'} or not path.is_file() or path.stat().st_size == 0:
        raise PublishError('VIDEO_INPUT_INVALID', '需要非空 mp4/mov 文件')
    return path


def validate_content(title, caption):
    if not title.strip():
        raise PublishError('TITLE_MISSING')
    if len(title) > 30 or len(caption) > 1000:
        raise PublishError('CONTENT_LENGTH_OUT_OF_RANGE')


def validate_cover(path):
    from PIL import Image
    file = Path(path).expanduser().resolve()
    try:
        with Image.open(file) as im:
            im.verify()
    except (OSError, ValueError) as exc:
        raise PublishError('COVER_INPUT_INVALID', str(file)) from exc
    return file


def prepare_cover(source, output, ratio):
    """Fit the entire image into the required ratio, padding instead of cropping."""
    from PIL import Image, ImageOps
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert('RGB')
        unit = math.ceil(max(image.width / ratio[0], image.height / ratio[1]))
        size = (ratio[0] * unit, ratio[1] * unit)
        # Cap large uploads without changing the ratio or cutting text.
        if max(size) > 2048:
            unit = 2048 // max(ratio)
            size = (ratio[0] * unit, ratio[1] * unit)
        fitted = ImageOps.contain(image, size, Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', size, (234, 234, 234))
        canvas.paste(fitted, ((size[0]-fitted.width)//2, (size[1]-fitted.height)//2))
        canvas.save(output, quality=95)


def cmd_open_page(*, session=SESSION):
    check_no_pending()
    browser(session).command('open', UPLOAD_URL)
    _check_logged_in(session)
    return {'ok': True, 'session': session, 'url': evaluate(session, 'window.location.href')}


def cmd_upload(*, video, session=SESSION, resume_draft=False):
    path = validate_media(video)
    check_no_pending()
    save_state({'state': 'draft', 'video': str(path)})
    if not resume_draft:
        cmd_open_page(session=session)
    else:
        _check_logged_in(session)
        if not is_draft_url(evaluate(session, 'window.location.href') or ''):
            raise PublishError('DRAFT_PAGE_REQUIRED', '先打开上传页并续编目标草稿')
    if evaluate(session, "document.body.innerText.includes('你还有上次未发布的视频')"):
        if resume_draft:
            click_text(session, '继续编辑')
        else:
            raise PublishError('DRAFT_PRESENT', '用 edit-draft 继续编辑已有草稿；核实后再决定是否放弃，不自动清除')
    previous_sources = evaluate(session, "Array.from(document.querySelectorAll('video')).map(v=>v.currentSrc||v.getAttribute('src')).filter(Boolean)") or []
    browser(session).command('upload', 'input[type="file"][accept*="video"]', str(path), timeout=UPLOAD_TIMEOUT_S)
    sys.stderr.write('[douyin-video-publish] 等待视频可播放且上传/转码结束…\n')
    # Require stable readiness; the title form can exist before any media is uploaded.
    ready = 0
    def stable(status):
        nonlocal ready
        changed = any(source not in previous_sources for source in status.get('video_sources', []))
        ready = ready + 1 if status['video_ready'] and changed else 0
        return ready >= 2
    wait_for(session, stable, TRANSCODE_MAX_WAIT_S, 'VIDEO_NOT_UPLOADED')
    return {'ok': True, 'state': 'video_ready', 'session': session, 'video': str(path)}


def cmd_edit_draft(*, session=SESSION, confirm_unpublished=False):
    state = read_state()
    if state.get('state') in PENDING_STATES:
        if not confirm_unpublished:
            raise PublishError('PUBLISH_PENDING', '先 resume 核查；仅人工确认未发布后用 edit-draft --confirm-unpublished 续编', 3)
        status = page_status(session)
        if status['sms_required']:
            raise PublishError('SMS_VERIFICATION_REQUIRED', '先完成当前短信验证，不清除验证任务', 4)
        item = matching_work(state, work_items(session))
        if item:
            state.update(state='published', aweme_id=item['id'])
            save_state(state)
            return published_result(state)
        state['state'] = 'draft'
        for field in ('submitted_at', 'baseline_ids', 'sms_requested', 'aweme_id'):
            state.pop(field, None)
        save_state(state)
        if '/content/manage' in status['url']:
            cmd_open_page(session=session)
    if evaluate(session, "document.body.innerText.includes('你还有上次未发布的视频')"):
        click_text(session, '继续编辑')
    status = page_status(session)
    if '/content/manage' in status['url']:
        raise PublishError('DRAFT_PAGE_REQUIRED', '先用 open-page 打开上传页')
    state['state'] = 'draft'
    save_state(state)
    return {'ok': True, 'state': 'draft', 'page': status, 'hint': DRAFT_HINT}


def _select_ai_declaration(session):
    if page_status(session)['aigc']:
        return True
    dialog_open = evaluate(session, '''Array.from(document.querySelectorAll('[role="dialog"]')).some(e=>
      e.getClientRects().length && /对作品内容添加声明|内容由AI生成/.test(e.innerText||''))''')
    if not dialog_open and not click_text(session, '请选择自主声明', required=False):
        return False
    # Semi's parent label intercepts pointer clicks on its nested span. Click
    # the unique label, then confirm its radio state before saving the dialog.
    selected = evaluate(session, r'''(async () => {
      const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
      const labels=Array.from(document.querySelectorAll('[role="dialog"] label.semi-radio'))
        .filter(e=>visible(e) && (e.innerText||'').trim()==='内容由AI生成');
      if (labels.length!==1) return false;
      labels[0].click();
      await new Promise(r=>setTimeout(r,150));
      const radio=labels[0].querySelector('input[type="radio"],[role="radio"]');
      return !!(radio && (radio.checked || radio.getAttribute('aria-checked')==='true')) ||
        labels[0].classList.contains('semi-radio-checked');
    })()''')
    if selected is not True:
        return False
    click_text(session, '确定')
    return wait_for(session, lambda s: s['aigc'], 10, 'AIGC_DECLARATION_MISSING')['aigc']


def cmd_fill(*, session, title='', caption=''):
    validate_content(title, caption)
    check_no_pending()
    _check_logged_in(session)
    if not camoufox_type(session, TITLE_SELECTOR, title):
        raise PublishError('TITLE_WRITE_FAILED', '真实键盘输入后标题读回不一致；保留草稿检查')
    if not camoufox_type(session, CAPTION_SELECTOR, caption):
        raise PublishError('CAPTION_WRITE_FAILED', DRAFT_HINT)
    if not _select_ai_declaration(session):
        raise PublishError('AIGC_DECLARATION_MISSING')
    if page_status(session)['title'] != title:
        raise PublishError('TITLE_WRITE_FAILED')
    state = read_state()
    state.update(state='draft', title=title, caption=caption)
    save_state(state)
    return {'ok': True, 'state': 'filled', 'title': title, 'caption': caption}


def cover_input(session, horizontal):
    # Guard the observed layout before using nth; never inject an arbitrary file input.
    inputs = evaluate(session, "Array.from(document.querySelectorAll('input[type=\"file\"]')).map(e=>e.accept)")
    if (not isinstance(inputs, list) or len(inputs) != 4 or 'video' not in inputs[1]
            or not all('image' in inputs[i] and 'video' not in inputs[i] for i in (0, 2, 3))):
        raise PublishError('COVER_INPUT_LAYOUT_CHANGED', '检查当前封面弹窗；不猜测 file input 序号')
    return f'input[type="file"] >> nth={3 if horizontal else 2}'


def watch_cover_preview(session):
    # Keep large data URLs inside this page. Reset per upload (never localStorage)
    # and observe load events so re-uploading the same image is also supported.
    started = evaluate(session, r'''(() => {
      const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
      const dialogs=Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible);
      if (dialogs.length!==1) return false;
      const dialog=dialogs[0], previous=window.__xiaobeiCoverUpload;
      if (previous) previous.dialog.removeEventListener('load',previous.onLoad,true);
      const watch={dialog,before:new Map(Array.from(dialog.querySelectorAll('img')).map(i=>[i,i.getAttribute('src')])),loaded:new WeakSet()};
      watch.onLoad=e=>{if(e.target.tagName==='IMG')watch.loaded.add(e.target)};
      dialog.addEventListener('load',watch.onLoad,true);
      window.__xiaobeiCoverUpload=watch;
      return true;
    })()''')
    if started is not True:
        raise PublishError('COVER_DIALOG_MISSING', DRAFT_HINT)


def cover_preview_ready(session):
    return evaluate(session, r'''(() => {
      const watch=window.__xiaobeiCoverUpload;
      if (!watch || !watch.dialog.isConnected) return false;
      const visible=e=>!!(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
      return Array.from(watch.dialog.querySelectorAll('img')).some(i=> {
        const src=i.getAttribute('src')||'';
        return visible(i) && i.complete && i.naturalWidth>0 && i.naturalHeight>0 &&
          /^(data:image|blob:)/.test(src) &&
          (watch.loaded.has(i) || !watch.before.has(i) || watch.before.get(i)!==src);
      }) && !/上传中|正在上传/.test(watch.dialog.innerText);
    })()''') is True


def clear_cover_watch(session):
    evaluate(session, '''(() => {
      const watch=window.__xiaobeiCoverUpload;
      if (watch) watch.dialog.removeEventListener('load',watch.onLoad,true);
      delete window.__xiaobeiCoverUpload;
    })()''')


def cmd_cover(*, session, cover_vertical, cover_horizontal):
    vertical, horizontal = validate_cover(cover_vertical), validate_cover(cover_horizontal)
    check_no_pending()
    initial = page_status(session)
    if not initial['video_ready']:
        raise PublishError('VIDEO_NOT_UPLOADED', DRAFT_HINT)
    browser(session).command('press', 'Escape')
    # Slate topic suggestions can remain after Tab and intercept cover clicks.
    evaluate(session, "Array.from(document.querySelectorAll('[class*=\"publish-mention-wrapper\"]')).forEach(w=>{w.style.display='none';w.style.visibility='hidden';})")
    with tempfile.TemporaryDirectory(prefix='douyin-covers-') as temporary:
        for is_horizontal, source, ratio in ((False, vertical, (3, 4)), (True, horizontal, (4, 3))):
            output = Path(temporary) / ('horizontal.jpg' if is_horizontal else 'vertical.jpg')
            prepare_cover(source, output, ratio)
            if is_horizontal:
                if not click_text(session, '设置横封面', required=False):
                    evaluate(session, "(() => {const e=document.querySelectorAll('[class*=\"coverControl\"]')[1]; if(e) e.setAttribute('data-xiaobei-cover-entry','1')})()")
                    try:
                        click_selector(session, '[data-xiaobei-cover-entry]')
                    finally:
                        evaluate(session, "document.querySelectorAll('[data-xiaobei-cover-entry]').forEach(e=>e.removeAttribute('data-xiaobei-cover-entry'))")
            else:
                # The first observed coverControl is the vertical slot.
                evaluate(session, "(() => {const e=document.querySelector('[class*=\"coverControl\"]'); if(e) e.setAttribute('data-xiaobei-cover-entry','1')})()")
                try:
                    click_selector(session, '[data-xiaobei-cover-entry]')
                finally:
                    evaluate(session, "document.querySelectorAll('[data-xiaobei-cover-entry]').forEach(e=>e.removeAttribute('data-xiaobei-cover-entry'))")
            selector = cover_input(session, is_horizontal)
            watch_cover_preview(session)
            try:
                browser(session).command('upload', selector, str(output), timeout=UPLOAD_TIMEOUT_S)
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if cover_preview_ready(session):
                        break
                    time.sleep(2)
                else:
                    raise PublishError('COVER_UPLOAD_TIMEOUT', DRAFT_HINT)
            finally:
                clear_cover_watch(session)
            click_text(session, '完成', scope='[role="dialog"]')
            time.sleep(1)
    def covers_ready(status):
        if status['cover_quality_error']:
            raise PublishError('COVER_TEXT_UNSAFE', '检查两张封面的文字安全区后重新设置')
        return status['dual_cover_ready']
    status = wait_for(session, covers_ready,
                      60, 'DUAL_COVER_MISSING', '核查两张封面保存结果及平台文字安全区检测；不要点发布')
    state = read_state()
    state.update(cover_vertical=str(vertical), cover_horizontal=str(horizontal))
    state['cover_recovery'] = {'url': status['url'], 'title': initial['title'],
                               'caption': initial.get('caption'),
                               'duration': initial.get('video_duration', 0), 'attempted': False}
    save_state(state)
    status = restore_cover_video(session, status)
    return {'ok': True, 'state': 'covers_ready', 'page': status}


def is_draft_url(url):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'creator.douyin.com'
            and parsed.path in {'/creator-micro/content/upload', '/creator-micro/content/post/video'})


def restore_cover_video(session, status):
    state = read_state()
    recovery = state.get('cover_recovery', {})
    # Only the observed cover-induced DOM removal warrants reopening a draft.
    # Never reload an uploading video, an SMS challenge, or a submitted task.
    if (status['video_ready'] or status.get('video_sources') or status['busy']
            or status['sms_required'] or state.get('state') != 'draft' or not recovery
            or recovery.get('attempted') or recovery.get('url') != status['url']
            or not is_draft_url(status['url']) or not status['dual_cover_ready']
            or status['cover_quality_error'] or status['rejected']):
        return status
    def same_form(current):
        return (current['title'] == recovery['title'] and current['dual_cover_ready']
                and current['aigc'] and not current['cover_quality_error']
                and (recovery.get('caption') is None or
                     (current.get('caption') is not None and
                      editor_text_matches(current['caption'], recovery['caption']))))
    if not same_form(status):
        raise PublishError('DRAFT_CHANGED_AFTER_COVER', DRAFT_HINT)
    recovery['attempted'] = True
    save_state(state)
    browser(session).command('open', status['url'])
    if evaluate(session, "document.body.innerText.includes('你还有上次未发布的视频')"):
        click_text(session, '继续编辑')
    ready = 0
    def restored(current):
        nonlocal ready
        ready = ready + 1 if current['video_ready'] else 0
        return ready >= 2
    current = wait_for(session, restored, 60, 'VIDEO_NOT_UPLOADED')
    if (not same_form(current) or
            (recovery.get('duration', 0) and
             abs(current.get('video_duration', 0)-recovery['duration']) > 0.5)):
        raise PublishError('DRAFT_CHANGED_AFTER_COVER', DRAFT_HINT)
    return current


def preflight(session):
    status = restore_cover_video(session, page_status(session))
    if not status['title'].strip():
        raise PublishError('TITLE_MISSING', DRAFT_HINT)
    validate_content(status['title'], read_state().get('caption', ''))
    if not status['video_ready']:
        raise PublishError('VIDEO_NOT_UPLOADED', DRAFT_HINT)
    if not status['dual_cover_ready']:
        raise PublishError('DUAL_COVER_MISSING', DRAFT_HINT)
    if status['cover_quality_error']:
        raise PublishError('COVER_TEXT_UNSAFE', '检查封面边缘文字，补底保留完整内容后重新设置')
    if not status['aigc']:
        raise PublishError('AIGC_DECLARATION_MISSING')
    if status['rejected']:
        raise PublishError('PLATFORM_REJECTED', status['rejected'])
    expected = read_state().get('title')
    if expected and expected != status['title']:
        raise PublishError('TITLE_MISMATCH', '当前草稿标题与本次填入标题不同')
    expected_caption = read_state().get('caption')
    if (expected_caption is not None and
            (status.get('caption') is None or not editor_text_matches(status['caption'], expected_caption))):
        raise PublishError('CAPTION_WRITE_FAILED', '当前草稿简介与本次填入内容不一致；'+DRAFT_HINT)
    return status


def work_items(session):
    # Quote integer IDs before parsing in JS, preserving all 19 digits.
    js = f'''(async () => {{
      const response=await fetch({json.dumps(WORK_LIST_URL)},{{credentials:'include'}});
      if (!response.ok) return {{error:'WORK_LIST_HTTP_ERROR'}};
      const raw=await response.text();
      const data=JSON.parse(raw.replace(/("(?:aweme_id|item_id)"\\s*:\\s*)(\\d+)(?=\\s*[,}}])/g,'$1"$2"'));
      if (data.status_code!==0) return {{error:data.status_code===8?'SESSION_EXPIRED':'WORK_LIST_REJECTED'}};
      if (!Array.isArray(data.aweme_list)) return {{error:'WORK_LIST_INVALID'}};
      return {{items:data.aweme_list.map(it=>({{
        id:String(it.aweme_id||it.item_id||''),ct:Number(it.create_time||0),
        title:String(it.title||it.aweme_title||(it.aweme_desc && (it.aweme_desc.title||it.aweme_desc.text))||it.desc||'')
      }})).filter(it=>/^\\d{{15,22}}$/.test(it.id))}};
    }})()'''
    # Retain the bounded same-page retry for intermittent creator authentication responses.
    for attempt in range(3):
        result = evaluate(session, js)
        if isinstance(result, dict) and result.get('error') == 'SESSION_EXPIRED' and attempt < 2:
            time.sleep(2)
            continue
        break
    if not isinstance(result, dict) or 'items' not in result:
        code = result.get('error', 'WORK_LIST_INVALID') if isinstance(result, dict) else 'WORK_LIST_INVALID'
        raise PublishError(code, RESULT_HINT, 2 if code == 'SESSION_EXPIRED' else 3)
    return result['items']


def matching_work(state, items):
    old = set(state['baseline_ids'])
    title = state['title']
    accepted = {title}
    if state.get('caption'):
        accepted.update({title+'\n'+state['caption'], title+' '+state['caption']})
    candidates = [it for it in items if it['id'] not in old and it['ct'] >= state['submitted_at']-5
                  and it['title'] in accepted]
    if len(candidates) > 1:
        raise PublishError('PUBLISH_RESULT_AMBIGUOUS', RESULT_HINT, 3)
    return candidates[0] if candidates else None


def published_result(state):
    return {'ok': True, 'state': 'published', 'session': SESSION, 'aweme_id': state['aweme_id'],
            'url': 'https://www.douyin.com/video/' + state['aweme_id']}


def cmd_resume(*, session=SESSION, timeout=POST_PUBLISH_MAX_WAIT_S):
    state = read_state()
    if state.get('state') == 'published':
        return published_result(state)
    if state.get('state') not in PENDING_STATES:
        raise PublishError('NO_PENDING_PUBLICATION', '尚无本次提交记录；不能用最新旧作品代替', 3)
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        status = page_status(session)
        if status['sms_required']:
            state['state'] = 'awaiting_verification'
            save_state(state)
            raise PublishError('SMS_VERIFICATION_REQUIRED', '页面已保留；verify-send 获取验证码，再用 verify-code --code-file 私有文件续接；也可在窗口完成验证后 resume', 4)
        if status['rejected']:
            state['state'] = 'unconfirmed'
            save_state(state)
            raise PublishError('PLATFORM_REJECTED', status['rejected']+'；'+RESULT_HINT, 3)
        if '/creator-micro/content/manage' in status['url']:
            item = matching_work(state, work_items(session))
            if item:
                state.update(state='published', aweme_id=item['id'])
                save_state(state)
                return published_result(state)
        # Surface validation blockers immediately instead of waiting for an unrelated navigation.
        elif time.monotonic()-started >= 6 and (not status['video_ready'] or not status['title'].strip() or not status['dual_cover_ready'] or status['cover_quality_error']):
            state['state'] = 'unconfirmed'
            save_state(state)
            raise PublishError('PUBLISH_BLOCKED', DRAFT_HINT+'；'+RESULT_HINT, 3)
        time.sleep(2)
    state['state'] = 'unconfirmed'
    save_state(state)
    raise PublishError('PUBLISH_UNCONFIRMED', RESULT_HINT+'；'+DRAFT_HINT, 3)


def cmd_publish(*, session):
    check_no_pending()
    status = preflight(session)
    baseline = work_items(session)
    # Recheck after the read-only request; do not click if the form changed meanwhile.
    current = preflight(session)
    if current['title'] != status['title']:
        raise PublishError('TITLE_MISMATCH')
    state = read_state()
    state.update(state='submitted', title=current['title'], submitted_at=int(time.time()),
                 baseline_ids=[it['id'] for it in baseline])
    state.pop('aweme_id', None)
    state.pop('sms_requested', None)
    save_state(state)  # Persist before clicking: a transport failure must never cause automatic resubmit.
    click_text(session, '发布')
    return cmd_resume(session=session)


def cmd_get_link(*, session):
    return cmd_resume(session=session)


def verification_state(session):
    state = read_state()
    if state.get('state') not in PENDING_STATES or not page_status(session)['sms_required']:
        raise PublishError('SMS_DIALOG_MISSING', '只续接已提交任务的当前短信验证弹窗')
    return state


def cmd_verify_send(*, session):
    state = verification_state(session)
    if state.get('sms_requested'):
        raise PublishError('SMS_ALREADY_REQUESTED', '等待当前验证码；不自动重发')
    state.update(state='awaiting_verification', sms_requested=True)
    save_state(state)
    # Persist the send intent before clicking, including ambiguous transport outcomes.
    click_text(session, '获取验证码')
    deadline = time.monotonic()+10
    while time.monotonic()<deadline:
        if evaluate(session, r"Array.from(document.querySelectorAll('[role=\"dialog\"]')).some(d=>/接收短信验证码|请输入当前手机号收到的短信验证码/.test(d.innerText) && /\d+\s*(?:s|秒)|重新获取/.test(d.innerText))"):
            return {'ok': False, 'state': 'awaiting_verification', 'sms_requested': True, 'session': session}
        time.sleep(1)
    raise PublishError('SMS_SEND_UNCONFIRMED', '点击结果未确认；检查页面倒计时，不自动重复发送', 4)


def read_code_file(file):
    path = Path(file).expanduser()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise PublishError('CODE_FILE_UNSAFE', '使用当前用户拥有、权限 0600 的普通文件，不接受软链接')
            code = stream.read(32).strip()
    except OSError as exc:
        raise PublishError('CODE_FILE_UNSAFE', '使用当前用户拥有、权限 0600 的普通文件，不接受软链接') from exc
    if not re.fullmatch(r'[0-9]{4,8}', code):
        raise PublishError('CODE_INVALID', '验证码文件仅含 4–8 位数字')
    return code


def cmd_verify_code(*, session, code_file):
    code = read_code_file(code_file)
    verification_state(session)
    selector = '[role="dialog"] input:not([type="hidden"]):not([type="file"]):not([type="button"]):not([type="submit"]):not([readonly]):not([disabled])'
    if not camoufox_type(session, selector, code):
        raise PublishError('CODE_WRITE_FAILED', '验证码未写入当前弹窗；勿重发作品', 4)
    click_text(session, '验证', scope='[role="dialog"]')
    # Give the validation response a chance to dismiss the SMS dialog.
    deadline = time.monotonic()+15
    while time.monotonic()<deadline:
        status = page_status(session)
        if status['rejected']:
            raise PublishError('SMS_CODE_REJECTED', status['rejected'], 4)
        if not status['sms_required']:
            break
        time.sleep(1)
    return cmd_resume(session=session)


def cmd_status(*, session):
    return {'ok': False, 'state': read_state().get('state', 'idle'), 'session': session,
            'page': page_status(session), 'hint': RESULT_HINT if read_state().get('state') in PENDING_STATES else DRAFT_HINT}


def cmd_run(*, video, title, caption='', cover_vertical, cover_horizontal):
    validate_media(video)
    validate_content(title, caption)
    validate_cover(cover_vertical)
    validate_cover(cover_horizontal)
    check_no_pending()
    try:
        cmd_upload(video=video)
        cmd_fill(session=SESSION, title=title, caption=caption)
        cmd_cover(session=SESSION, cover_vertical=cover_vertical, cover_horizontal=cover_horizontal)
        return cmd_publish(session=SESSION)
    finally:
        # Preserve an unfinished form or challenge for diagnosis and continuation.
        if read_state().get('state') == 'published':
            try:
                Browser().close()
            except Exception:
                pass


def build_parser():
    p = argparse.ArgumentParser(prog='douyin-video-publish', description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    for name, function in [('open-page', cmd_open_page),
                           ('publish', cmd_publish), ('get-link', cmd_get_link), ('resume', cmd_resume),
                           ('status', cmd_status), ('verify-send', cmd_verify_send)]:
        command = sub.add_parser(name)
        command.add_argument('--session', default=SESSION, choices=[SESSION])
        command.set_defaults(func=lambda a, f=function: f(session=a.session))
    draft = sub.add_parser('edit-draft')
    draft.add_argument('--session', default=SESSION, choices=[SESSION])
    draft.add_argument('--confirm-unpublished', action='store_true', help='仅人工确认原提交未发布后结案并续编草稿')
    draft.set_defaults(func=lambda a: cmd_edit_draft(session=a.session, confirm_unpublished=a.confirm_unpublished))
    upload = sub.add_parser('upload')
    upload.add_argument('--video', required=True)
    upload.add_argument('--session', default=SESSION, choices=[SESSION])
    upload.add_argument('--resume-draft', action='store_true', help='保留当前草稿页面并补传视频')
    upload.set_defaults(func=lambda a: cmd_upload(video=a.video, session=a.session, resume_draft=a.resume_draft))
    fill = sub.add_parser('fill')
    fill.add_argument('--session', default=SESSION, choices=[SESSION])
    fill.add_argument('--title', required=True)
    fill.add_argument('--caption', default='')
    fill.set_defaults(func=lambda a: cmd_fill(session=a.session, title=a.title, caption=a.caption))
    for name in ('cover', 'run'):
        command = sub.add_parser(name)
        command.add_argument('--cover-vertical', required=True)
        command.add_argument('--cover-horizontal', required=True)
        if name == 'cover':
            command.add_argument('--session', default=SESSION, choices=[SESSION])
            command.set_defaults(func=lambda a: cmd_cover(session=a.session, cover_vertical=a.cover_vertical, cover_horizontal=a.cover_horizontal))
        else:
            command.add_argument('--video', required=True)
            command.add_argument('--title', required=True)
            command.add_argument('--caption', default='')
            command.set_defaults(func=lambda a: cmd_run(video=a.video, title=a.title, caption=a.caption, cover_vertical=a.cover_vertical, cover_horizontal=a.cover_horizontal))
    verify = sub.add_parser('verify-code')
    verify.add_argument('--session', default=SESSION, choices=[SESSION])
    verify.add_argument('--code-file', required=True)
    verify.set_defaults(func=lambda a: cmd_verify_code(session=a.session, code_file=a.code_file))
    return p


def main(argv: Optional[list[str]] = None):
    args = build_parser().parse_args(argv)
    try:
        with publish_lock(allow_pending_video=True):
            result = args.func(args)
            if result.get('state') == 'published' and args.cmd != 'run':
                try:
                    browser(SESSION).close()
                except Exception:
                    pass
        print(json.dumps(result, ensure_ascii=False))
        return 4 if result.get('state') == 'awaiting_verification' else 0
    except PublishError as exc:
        state = safe_error_state()
        hint = exc.hint
        if exc.code == 'SESSION_EXPIRED' and state.get('state') in PENDING_STATES:
            hint = '本次提交结果未知；验证页面已丢失或登录失效时用 douyin-publish login --resume-video 恢复同一 profile，登录后 resume 核查原作品，勿重发'
        print(json.dumps({'ok': False, 'error': exc.code, 'state': state.get('state', 'idle'),
                          'publish_attempted': state.get('state') in PENDING_STATES | {'published'},
                          'hint': hint, 'session': SESSION}, ensure_ascii=False))
        return exc.exit_code
    except Exception:
        # Browser errors may contain code input or response data. Return only a safe error category.
        state = safe_error_state()
        pending = state.get('state') in PENDING_STATES
        print(json.dumps({'ok': False, 'error': 'BROWSER_OPERATION_FAILED', 'state': state.get('state', 'idle'),
                          'publish_attempted': pending, 'hint': RESULT_HINT if pending else DRAFT_HINT}, ensure_ascii=False))
        return 3 if pending else 1


def safe_error_state():
    try:
        return read_state()
    except PublishError:
        return {'state': 'unconfirmed'}


if __name__ == '__main__':
    sys.exit(main())
