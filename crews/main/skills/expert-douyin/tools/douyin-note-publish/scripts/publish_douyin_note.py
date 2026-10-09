#!/usr/bin/env python3
"""Publish image notes through the persistent douyin browser session."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from publish_browser import Browser, SESSION, UPLOAD_URL, MANAGE_URL, publish_lock

VISIBLE = 'e.getClientRects().length > 0'

class LoginRequired(RuntimeError):
    pass


class WaitTimeout(RuntimeError):
    pass


def check_login(b):
    url = b.eval('window.location.href') or ''
    if urlparse(url).path.rstrip('/') in ('/login', '/creator-micro/login'):
        raise LoginRequired('SESSION_EXPIRED: 创作者中心跳转登录页')



def wait_for(b, action, message, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_login(b)
        value = action()
        if value:
            return value
        time.sleep(1)
    raise WaitTimeout(message)


def click_text(b, text, selector='button,div,span,a,li,label'):
    return b.eval(f'''(() => {{const nodes=[...document.querySelectorAll({json.dumps(selector)})]
      .filter(e=>{VISIBLE} && (e.children.length===0 || e.tagName==='BUTTON') && e.textContent.trim()==={json.dumps(text)});
      if(nodes.length!==1) return false; (nodes[0].closest('button')||nodes[0]).click(); return true;}})()''')


def validate(images=None, title='', caption=''):
    if not title.strip() or len(title) > 20:
        raise ValueError('图文标题必须为 1–20 字')
    if len(caption) > 1000:
        raise ValueError('图文描述不能超过 1000 字')
    if images is not None:
        if not 1 <= len(images) <= 35:
            raise ValueError('图文需要 1–35 张图片')
        for name in images:
            path = Path(name)
            if not path.is_file() or path.suffix.lower() not in {'.jpg','.jpeg','.png','.webp','.bmp','.tif'}:
                raise ValueError(f'图片不存在或格式不支持: {name}')
            if not 0 < path.stat().st_size <= 50 * 1024 * 1024:
                raise ValueError(f'图片必须非空且不超过 50MB: {name}')


def upload(b, images):
    b.command('open', UPLOAD_URL)
    check_login(b)
    wait_for(b, lambda: click_text(b, '发布图文'), '找不到发布图文标签')
    b.command('upload', 'input[type=file][accept*="image"]',
              *[str(Path(p).resolve()) for p in images], timeout=300)
    wait_for(b, lambda: b.eval('!!document.querySelector(\'input[placeholder="添加作品标题"]\')'),
             '图片上传超时，标题表单未出现', timeout=300)
    wait_for(b, lambda: b.eval(f"document.body.innerText.includes('已添加{len(images)}张图片') && !document.body.innerText.includes('取消上传')"),
             '图片尚未全部上传成功，不能选择推荐音乐', timeout=300)


# Candidate tokens and DOM references live in the current page, so reloading invalidates them.
CARD_DATA = """const describe = e => ({
  name:e.querySelector('[class*=song-name]')?.textContent.trim(),
  author:e.querySelector('.song-author')?.textContent.trim(),
  duration:e.querySelector('.song-duration')?.textContent.trim()
});"""


def list_music(b):
    check_login(b)
    opened = b.eval('''(() => {
      if([...document.querySelectorAll('[class*=card-wrapper]')].some(e=>e.getClientRects().length)) return true;
      const actions=[...document.querySelectorAll('span[class*=action]')].filter(e=>
        e.getClientRects().length && ['选择音乐','修改音乐'].includes(e.textContent.trim()));
      if(actions.length!==1) return false; actions[0].click(); return true;
    })()''')
    if not opened:
        raise RuntimeError('找不到唯一音乐入口；先完成图片上传')
    js = '''(() => {''' + CARD_DATA + '''
      const cards=[...document.querySelectorAll('[class*=card-wrapper]')].filter(e=>e.getClientRects().length);
      if(!cards.length) return null;
      window.__noteMusicCandidates = new Map();
      return cards.map(e=>{
        const data=describe(e), choice=crypto.randomUUID();
        window.__noteMusicCandidates.set(choice,{element:e,data});
        return {choice,...data,usage:e.querySelector('[class*=user-count]')?.textContent.trim()};
      });
    })()'''
    return wait_for(b, lambda: b.eval(js), '未获取到音乐候选；检查页面，不猜测歌名')


def select_music(b, choice):
    check_login(b)
    key = json.dumps(choice)
    selected = b.eval('''(() => {''' + CARD_DATA + f'''
      const entry=window.__noteMusicCandidates?.get({key});
      if(!entry || !entry.element.isConnected || !entry.element.getClientRects().length ||
         JSON.stringify(describe(entry.element))!==JSON.stringify(entry.data)) return null;
      window.__noteSelectedMusic=null;
      if(!entry.element.closest('[class*=card-container-act]')) entry.element.click();
      return entry.data;
    }})()''')
    if not selected:
        raise RuntimeError('候选已失效或不存在；重新 music-list 后选择')
    use = '''(() => {''' + CARD_DATA + f'''
      const entry=window.__noteMusicCandidates?.get({key});
      if(!entry || !entry.element.isConnected || JSON.stringify(describe(entry.element))!==JSON.stringify(entry.data)) return false;
      const active=entry.element.closest('[class*=card-container-act]');
      if(!active || !active.getClientRects().length) return false;
      const buttons=[...active.querySelectorAll('button')].filter(e=>!e.disabled && e.textContent.trim()==='使用');
      if(buttons.length!==1) return false; buttons[0].click(); return true;
    }})()'''
    wait_for(b, lambda: b.eval(use), '目标歌曲激活卡片内未找到唯一使用按钮')
    wait_for(b, lambda: verify_music(b, selected['name']), '配乐断言失败，禁止发布')
    b.eval(f'window.__noteSelectedMusic={json.dumps(selected,ensure_ascii=False)}')
    return selected


def verify_music(b, name):
    return b.eval(f'''(() => {{
      if([...document.querySelectorAll('[class*=card-wrapper]')].some(e=>e.getClientRects().length)) return false;
      const labels=[...document.querySelectorAll('div,span')].filter(e=>
        e.getClientRects().length && !e.children.length && e.textContent.trim()==={json.dumps(name)});
      return labels.some(e=>{{let p=e; for(let i=0;i<5 && p && p!==document.body;i++,p=p.parentElement)
        {{if(p.innerText.includes('修改音乐')) return true;}} return false;}});
    }})()''')


def fill_input(b, selector, value):
    # camoufox-cli fill accepts snapshot refs only, not CSS selectors.
    result = b.eval(f'''(() => {{
      const inputs=[...document.querySelectorAll({json.dumps(selector)})].filter(e=>{VISIBLE});
      if(inputs.length!==1) throw new Error('输入框缺失或不唯一');
      const e=inputs[0];
      if(!(e instanceof HTMLInputElement) || e.disabled || e.readOnly)
        throw new Error('输入框不可编辑');
      e.focus();
      const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
      setter.call(e,{json.dumps(value)});
      e.dispatchEvent(new Event('input',{{bubbles:true}}));
      e.dispatchEvent(new Event('change',{{bubbles:true}}));
      return e.value==={json.dumps(value)};
    }})()''')
    if not result:
        raise RuntimeError('输入框读回不一致')
    # Read in a separate browser turn, after controlled-component updates.
    if not b.eval(f'''(() => {{
      const inputs=[...document.querySelectorAll({json.dumps(selector)})].filter(e=>{VISIBLE});
      if(inputs.length!==1 || inputs[0].value!=={json.dumps(value)}) return false;
      inputs[0].focus(); return true;
    }})()'''):
        raise RuntimeError('输入框更新后读回不一致')


def fill(b, title, caption, declaration='ai'):
    check_login(b)
    fill_input(b, 'input[placeholder="添加作品标题"]', title)
    js = f'''(() => {{const editors=[...document.querySelectorAll('div[contenteditable=true]')].filter(e=>{VISIBLE});
      if(editors.length!==1) return false; const e=editors[0]; e.focus();
      const r=document.createRange(); r.selectNodeContents(e); const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);
      document.execCommand('insertText',false,{json.dumps(caption)});
      return e.innerText.trim()==={json.dumps(caption.strip())};}})()'''
    if not b.eval(js):
        raise RuntimeError('描述框缺失、不唯一或读回不一致')
    if declaration == 'ai':
        opened = click_text(b, '请选择自主声明') or click_text(b, '自主声明')
        if opened:
            wait_for(b, lambda: click_text(b, '内容由AI生成'), 'AI 声明选项未找到')
            if not click_text(b, '确定', 'button'):
                raise RuntimeError('AI 声明确认失败')
        elif not b.eval("document.body.innerText.includes('内容由AI生成')"):
            raise RuntimeError('AI 声明不可用，停止发布')


def note_link_candidate(b, title, *, click=False):
    # 管理页的标题区域实际展示标题+正文；搜索结果也可能包含无关作品。
    # 前缀仅用于定位候选，最终必须在图文编辑页完整校验标题。
    return b.eval(f'''(() => {{
      const title={json.dumps(title)};
      const nodes=[...document.querySelectorAll('[class*="info-title-text-"]')]
        .filter(e=>{VISIBLE} && (e.textContent||'').trim().startsWith(title));
      const actions=new Set();
      for(const t of nodes) {{
        const card=t.closest('[class*="info-title-operation-"]');
        if(!card) continue;
        const edits=[...card.querySelectorAll('button,a,span,div')].filter(e=>
          {VISIBLE} && !e.children.length && e.textContent.trim()==='编辑作品');
        if(edits.length===1) actions.add(edits[0]);
      }}
      const result={{titles:nodes.length,actions:actions.size}};
      if(nodes.length===1 && actions.size===1) {{
        if({json.dumps(click)}) [...actions][0].click();
        result.status='unique';
      }} else result.status=nodes.length>1 || actions.size>1 ? 'ambiguous' : 'missing';
      return result;
    }})()''')


def wait_note_edit(b, title, timeout=30):
    diagnostic = {}
    def locate_and_click():
        nonlocal diagnostic
        # DOM 判定和点击在同一次 JS 执行内完成，列表刷新不能插入两者之间。
        diagnostic = note_link_candidate(b, title, click=True)
        if diagnostic['status'] == 'ambiguous':
            raise RuntimeError(f'多个标题前缀候选，需人工核实，不能重发: {diagnostic}')
        return diagnostic['status'] == 'unique'
    try:
        wait_for(b, locate_and_click, '作品列表尚未出现目标', timeout=timeout)
    except WaitTimeout as exc:
        raise WaitTimeout(f'作品列表等待超时: {diagnostic}') from exc


def get_note_link(b, title):
    if not title.strip():
        raise ValueError('取链需要完整非空标题')
    b.command('open', MANAGE_URL)
    attempts = 4
    for attempt in range(attempts):
        b.command('reload')
        check_login(b)
        wait_for(b, lambda: b.eval('!!document.querySelector(\'input[placeholder*="搜索作品"]\')'), '管理页搜索框未出现')
        fill_input(b, 'input[placeholder*="搜索作品"]', title)
        b.command('press', 'Enter')
        # 等待搜索后的列表替换，避免立即点击尚未刷新的旧列表。
        time.sleep(5)
        try:
            wait_note_edit(b, title)
        except WaitTimeout as exc:
            if attempt == attempts - 1:
                raise RuntimeError(f'重新搜索{attempts}次仍未找到唯一作品，不能重发: {exc}') from exc
            print(f'[retry] 取链搜索 {attempt + 1}/{attempts}: {exc}; 3秒后重新搜索', file=sys.stderr)
            time.sleep(3)
            continue
        break
    def read_id():
        url = b.eval('window.location.href') or ''
        parsed = urlparse(url)
        mid = parse_qs(parsed.query).get('mid', [''])[0]
        return mid if parsed.hostname == 'creator.douyin.com' and parsed.path.endswith('/content/post/image') and re.fullmatch(r'\d{19}', mid) else None
    mid = wait_for(b, read_id, '未捕获图文编辑页 mid')
    def read_title():
        return b.eval(f'''(() => {{
          const inputs=[...document.querySelectorAll('input[placeholder="添加作品标题"]')].filter(e=>{VISIBLE});
          return inputs.length===1 && inputs[0].value ? {{title:inputs[0].value}} : null;
        }})()''')
    actual = wait_for(b, read_title, '图文编辑页标题未加载，链接待核实')
    if actual['title'] != title:
        raise RuntimeError(f'图文编辑页标题不一致，链接待核实: {actual["title"]!r}')
    return {'ok': True, 'session': SESSION, 'content_id': mid, 'mid': mid,
            'url': f'https://www.douyin.com/note/{mid}'}


def publish(b, original_sound=False):
    check_login(b)
    if not original_sound:
        selected = b.eval('window.__noteSelectedMusic || null')
        if not selected or not verify_music(b, selected['name']):
            raise RuntimeError('尚未确认配乐；先 music-list / music-select，或明确选择 --original-sound')
    if not click_text(b, '发布', 'button'):
        raise RuntimeError('未找到唯一可见发布按钮')
    wait_for(b, lambda: '/content/manage' in (b.eval('window.location.href') or ''), '发布后未跳转管理页，请核实后再操作')


def build_parser():
    p = argparse.ArgumentParser(prog='douyin-note-publish')
    sub = p.add_subparsers(dest='cmd', required=True)
    for cmd in ('open-page','upload','music-list','music-select','fill','publish','get-note-link','run'):
        s = sub.add_parser(cmd)
        s.add_argument('--headed', action='store_true')
        if cmd in ('run','upload'):
            s.add_argument('--images', nargs='+', required=True)
        if cmd in ('run','fill','get-note-link'):
            s.add_argument('--title', required=True)
        if cmd in ('run','fill'):
            s.add_argument('--caption', default='')
            s.add_argument('--declaration', choices=('ai','none'), default='ai')
        if cmd == 'music-select':
            s.add_argument('--choice', required=True)
        if cmd in ('publish','run'):
            s.add_argument('--original-sound', action='store_true', required=cmd == 'run',
                           help='明确使用原声；有配乐时必须使用分步流程')
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    b = Browser(a.headed)
    publish_attempted = False
    try:
        if a.cmd in ('run','fill','upload'):
            validate(getattr(a,'images',None), getattr(a,'title','上传'), getattr(a,'caption',''))
        with publish_lock():
            try:
                if a.cmd == 'open-page':
                    b.command('open', UPLOAD_URL)
                    result = {'ok':True,'session':SESSION,'url':b.eval('window.location.href'),
                              'hint':'用页面元素判定登录态，未登录交 douyin-publish login'}
                else:
                    result = {'ok':True,'session':SESSION}
                    if a.cmd in ('upload','run'):
                        upload(b,a.images)
                    if a.cmd == 'music-list':
                        result['candidates'] = list_music(b)
                    if a.cmd == 'music-select':
                        result['music'] = select_music(b,a.choice)
                    if a.cmd in ('fill','run'):
                        fill(b,a.title,a.caption,a.declaration)
                    if a.cmd in ('publish','run'):
                        publish_attempted = True
                        publish(b,a.original_sound)
                    if a.cmd in ('get-note-link','run'):
                        try:
                            result = get_note_link(b,a.title)
                        except LoginRequired:
                            raise
                        except Exception as exc:
                            with tempfile.NamedTemporaryFile(mode='w',prefix='dy-note-debug-',suffix='.json',delete=False) as f:
                                json.dump({'error':str(exc),'title':a.title},f,ensure_ascii=False)
                            print(json.dumps({'ok':False,'error':'LINK_UNCONFIRMED','debug':f.name,'hint':'人工核实，禁止自动重发'},ensure_ascii=False))
                            return 3
                print(json.dumps(result,ensure_ascii=False))
            finally:
                if a.cmd in ('run','get-note-link'):
                    try:
                        b.close()
                    except Exception as exc:
                        print(f'close: {exc}',file=sys.stderr)
        return 0
    except LoginRequired as exc:
        print(json.dumps({'ok':False, 'error':'SESSION_EXPIRED', 'platform':SESSION,
                          'publish_attempted':publish_attempted,
                          'hint':'按共用登录流程恢复；若已点击发布，先核实管理页，不重发'},ensure_ascii=False))
        print(f'error: {exc}',file=sys.stderr)
        return 2
    except Exception as exc:
        print(f'error: {exc}',file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
