#!/usr/bin/env python3
"""douyin-publish - 抖音内容发布(纯浏览器模拟方案,形态仿 wechat-channels-publish)

形态与 wechat-channels-publish 同构:纯浏览器操作,走 forked camoufox-cli 持久化 session
`douyin` + upload 命令,在创作者中心页面填表 + 上传视频 + 发布。

**与 login-manager 的边界**:
- 探活 / 有头手动登录 / 导出 cookie+UA 落中央存储 → **全交 login-manager**(不在本 skill 内做)
- 本 skill 只复用 login-manager 准备好的持久化 session `douyin` 做发布操作
- 本 skill **不吃 cookie**,浏览器操作严禁 `cookies import`

子命令:
  upload --video <path>   上传视频(forked cli upload 命令,底层 setInputFiles 穿透 shadow DOM)
  fill --title X --caption Y  填标题/描述/话题
  publish                 点"发布"按钮
  get-link                取已发布视频的公开链接
  run                     一键跑全流程(upload + fill + publish + get-link)

发布任务跑完即 close 持久化 session `douyin`--登录态在磁盘 profile,不留进程占内存,下次发布 `--session douyin --persistent` 重起无头即恢复;只在 session 卡死时由调用方手动 `camoufox-cli --session douyin --json close` teardown。本 skill 不提供 cleanup 子命令。

依赖:
- camoufox-cli(全局可用)
- login-manager skill(探活/有头登录/导出 cookie+UA 落中央存储供 viral-chaser/published-track 消费)
  --本 skill 不调用 login-manager,但前置假设它已把持久化 session `douyin` 登录态准备好

参考:
- 形态仿 crews/main/skills/wechat-channels-publish(视频号浏览器模拟,纯浏览器操作不导出 cookie)
- 用户上下文:抖音开放平台发布能力被驳回(主体资质不满足)→ 走浏览器模拟绕过
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── 常量 ─────────────────────────────────────────────────────────────────────

UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web"
CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
# 持久化 session 名 = 平台 key(一个且只有一个持久化 session)
# 由 login-manager 负责探活/有头登录/导出 cookie+UA 落中央存储;本 skill 只复用此 session 做发布操作
PERSISTENT_SESSION = "douyin"

UPLOAD_TIMEOUT_S = 300       # 上传最多 5 分钟(大文件)
TRANSCODE_POLL_S = 3
TRANSCODE_MAX_WAIT_S = 600    # 转码最多 10 分钟
POST_PUBLISH_POLL_S = 5
POST_PUBLISH_MAX_WAIT_S = 60  # 发布后跳转最多 1 分钟


# ── 平台工具 ────────────────────────────────────────────────────────────────


def session_name(purpose: str = "publish") -> str:
    """生成 camoufox session 名(D18 + 4.5.5 并发约束:每任务一 session)。"""
    return f"douyin-{purpose}-{secrets.token_hex(4)}"


def camoufox_open(session: str, url: str) -> None:
    """启 persistent 会话 + 打开 URL(camoufox-cli 默认 headless)。"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--persistent", "--json", "open", url]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)


def camoufox_eval(session: str, js: str, timeout: int = 30) -> Optional[str]:
    """在 session 内 eval JS,返回 data 字段(None 表示失败)。"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--json", "eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        env = json.loads(result.stdout)
        data = env.get("data")
        if isinstance(data, dict):
            # camoufox-cli eval 返回 {"data": {"result": "..."}}
            return data.get("result")
        return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        return result.stdout


def camoufox_click(session: str, selector: str) -> bool:
    """click selector;返回是否成功。"""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return 'false';
        el.click();
        return 'true';
    }})()
    """
    out = camoufox_eval(session, js)
    return out == "true"


def camoufox_type(session: str, selector: str, text: str) -> bool:
    """在 input/textarea 填值;触发 input 事件。"""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return 'false';
        var proto = Object.getPrototypeOf(el);
        var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, {json.dumps(text)});
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'true';
    }})()
    """
    out = camoufox_eval(session, js)
    return out == "true"


def camoufox_upload(session: str, selector: str, file_path: Path) -> bool:
    """用 forked cli 的 upload 命令注入文件到 input[type=file]。

    fork 加的 upload 命令底层走 Playwright locator.setInputFiles,穿透 shadow DOM,
    无需 DataTransfer base64 hack(绕过 CDP setFileInput 在某些 DOM 下的限制)。
    """
    result = subprocess.run(
        [CAMOUFOX_BIN, "--session", session, "--persistent", "--json", "upload", selector, str(file_path)],
        capture_output=True, text=True, timeout=UPLOAD_TIMEOUT_S, check=False,
    )
    return result.returncode == 0


def camoufox_wait_for_text(session: str, text: str, timeout: int = TRANSCODE_MAX_WAIT_S) -> bool:
    """轮询页面,等待出现特定文本(转码完成 / 上传成功)。"""
    js = f"document.body && document.body.innerText && document.body.innerText.indexOf({json.dumps(text)}) >= 0"
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = camoufox_eval(session, js)
        if out == "true":
            return True
        time.sleep(TRANSCODE_POLL_S)
    return False


def camoufox_wait_for_selector(session: str, selector: str, timeout: int = TRANSCODE_MAX_WAIT_S) -> bool:
    """轮询页面,等待 selector 命中(比文本匹配稳:抖音上传完成后表单 input 渲染出来才是真完成信号)。"""
    js = f"document.querySelector({json.dumps(selector)}) ? 'true' : 'false'"
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = camoufox_eval(session, js)
        if out == "true":
            return True
        time.sleep(TRANSCODE_POLL_S)
    return False


def camoufox_wait_for_url_contains(session: str, substr: str, timeout: int = POST_PUBLISH_MAX_WAIT_S) -> bool:
    """轮询直到当前 URL 含 substr(发布成功后跳转到 /content/manage 是权威成功信号)。"""
    js = f"window.location.href.indexOf({json.dumps(substr)}) >= 0 ? 'true' : 'false'"
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = camoufox_eval(session, js)
        if out == "true":
            return True
        time.sleep(POST_PUBLISH_POLL_S)
    return False


def camoufox_type_contenteditable(session: str, selector: str, text: str) -> bool:
    """往 contenteditable 富文本区填文本(抖音简介是 editor-kit contenteditable div,value setter 无效)。
    先 focus + execCommand insertText(富文本编辑器标准路径),读回若为空则回退 textContent + input 事件。"""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return 'no-element';
        el.focus();
        try {{
            var range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            var sel = window.getSelection();
            sel.removeAllRanges(); sel.addRange(range);
            document.execCommand('insertText', false, {json.dumps(text)});
        }} catch (e) {{}}
        if (!el.innerText || el.innerText.trim().length < 2) {{
            el.innerText = {json.dumps(text)};
            el.dispatchEvent(new InputEvent('input', {{bubbles: true, inputType: 'insertText', data: {json.dumps(text)}}}));
        }}
        return el.innerText.length > 0 ? 'true' : 'empty';
    }})()
    """
    return camoufox_eval(session, js) == "true"


def camoufox_click_button_by_text(session: str, text: str) -> bool:
    """按 innerText 精确匹配点 button/[role=button](:has-text 不是 CSS,querySelector 用不了)。"""
    js = f"""
    (function() {{
        var btns = Array.from(document.querySelectorAll('button,[role="button"]'));
        for (var b of btns) {{ if ((b.innerText || '').trim() === {json.dumps(text)}) {{ b.click(); return 'true'; }} }}
        return 'no-button';
    }})()
    """
    return camoufox_eval(session, js) == "true"


def camoufox_click_leaf_by_text(session: str, text: str) -> bool:
    """按 innerText 精确匹配点叶子节点(下拉选项、自定义 select 项等无语义标签场景)。"""
    js = f"""
    (function() {{
        var nodes = Array.from(document.querySelectorAll('div,span,li,option,a'));
        for (var n of nodes) {{
            if (n.children.length === 0 && (n.innerText || '').trim() === {json.dumps(text)}) {{ n.click(); return 'true'; }}
        }}
        return 'no-leaf';
    }})()
    """
    return camoufox_eval(session, js) == "true"


# ── 子命令实现 ──────────────────────────────────────────────────────────────


def cmd_upload(*, video: str, session: Optional[str] = None) -> None:
    """上传视频到创作者中心。session 默认走持久化 `douyin`(登录态在持久化 session 里)。
    同 session 已有命令在跑时,新命令 fail-first(同 session 已有命令在跑时新命令直接 fail)--agent 等当前操作完成再重试。"""
    if not session:
        session = PERSISTENT_SESSION
    video_path = Path(video).resolve()
    if not video_path.is_file():
        sys.stderr.write(f"error: video not found: {video_path}\n")
        sys.exit(1)

    camoufox_open(session, UPLOAD_URL)
    # 抖音创作者中心上传 file input(2026-07-17 真机 spike 确认:accept 含 video/*,.mp4 等,唯一一个)
    file_input_selector = 'input[type="file"][accept*="video"]'
    if not camoufox_upload(session, file_input_selector, video_path):
        sys.stderr.write("error: 上传 input 未找到或 upload 注入失败(DOM 改版?)\n")
        sys.exit(1)

    sys.stderr.write("[douyin-publish] 视频已注入,等待上传/转码...\n")
    # 上传+转码完成的真实信号是表单渲染出来(标题 input 出现),而非页面文本"上传成功"--
    # 抖音上传页根本没有"上传成功"这四个字,旧写法必超时。2026-07-17 真机 spike 确认。
    if not camoufox_wait_for_selector(session, 'input[placeholder*="填写作品标题"]', TRANSCODE_MAX_WAIT_S):
        sys.stderr.write("error: 视频上传/转码超时(标题表单未出现)\n")
        sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "session": session, "video": str(video_path)}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_fill(*, session: str, title: str = "", caption: str = "") -> None:
    """填标题 / 简介 / 话题 + 自主声明(内容由AI生成)。选择器 2026-07-17 真机 spike 确认。"""
    if title:
        # 主标题 input(placeholder="填写作品标题,为作品获得更多流量")。收窄到"填写作品标题"
        # 避免误中付费场景标题 input(placeholder="请输入付费场景下的视频标题")。
        if not camoufox_type(session, 'input[placeholder*="填写作品标题"]', title):
            sys.stderr.write("error: 标题 input 未找到\n")
            sys.exit(1)
    if caption:
        # 简介是 editor-kit contenteditable div(data-placeholder="添加作品简介"),value setter 无效。
        if not camoufox_type_contenteditable(session, 'div[contenteditable="true"][data-placeholder*="作品简介"]', caption):
            sys.stderr.write("error: 简介 contenteditable 未找到或填入失败\n")
            sys.exit(1)
    # 自主声明:Semi-UI 自定义下拉,默认"请选择自主声明"。点开再选"内容由AI生成"。
    if not _select_ai_declaration(session):
        sys.stderr.write("error: 自主声明「内容由AI生成」选择失败\n")
        sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "title": title, "caption": caption}, ensure_ascii=False))
    sys.stdout.write("\n")


def _select_ai_declaration(session: str) -> bool:
    """点开自主声明下拉,选「内容由AI生成」。下拉不存在(页面改版去掉声明区)时返回 True 不当错误。"""
    js_open = """
    (function() {
        var nodes = Array.from(document.querySelectorAll('div,span'));
        for (var n of nodes) {
            if ((n.innerText || '').trim() === '请选择自主声明') { n.click(); return 'clicked'; }
        }
        return 'no-select';
    })()
    """
    if camoufox_eval(session, js_open) != "clicked":
        # 没有自主声明区--不阻断（部分账号/页面无此选项）
        return True
    time.sleep(1)
    # 选「内容由AI生成」
    if not camoufox_click_leaf_by_text(session, "内容由AI生成"):
        return False
    time.sleep(1)
    # 点「确定」按钮让声明生效（2026-07-17 真机确认：选完声明后需点确定）
    return camoufox_click_button_by_text(session, "确定")


def cmd_publish(*, session: str) -> None:
    """点"发布"按钮(button[type=submit] 文本"发布",:has-text 非 CSS,按 innerText 点)。
    发布前注入 fetch 拦截器捕获发布 API 响应中的 aweme_id,写入 localStorage(跨同源导航存活)。"""
    # 注入 fetch/XHR 拦截器，捕获发布 API 响应中的 aweme_id。
    # 关键:把 id 写进 localStorage 而不是 window 变量——发布成功后页面跳转到管理页,
    # window.__capturedAwemeId 随旧 document 销毁,get-link 再就读不到。localStorage 在
    # creator.douyin.com 同源下跨导航存活,管理页能直接读回。(2026-07-17 事故根因)
    js_intercept = """
    (function() {
        window.__capturedAwemeId = null;
        try { localStorage.removeItem('douyin_last_aweme_id'); } catch(e) {}
        function stash(id) {
            if (!id) return;
            id = String(id);
            window.__capturedAwemeId = id;
            try { localStorage.setItem('douyin_last_aweme_id', id); } catch(e) {}
        }
        function extract(data) {
            try {
                return data.aweme && data.aweme.aweme_id || data.aweme_id || (data.item && data.item.id) || null;
            } catch(e) { return null; }
        }
        var origFetch = window.fetch;
        window.fetch = function() {
            var url = arguments[0];
            if (typeof url === 'string' && url.indexOf('publish') >= 0) {
                return origFetch.apply(this, arguments).then(function(resp) {
                    resp.clone().json().then(function(data) { stash(extract(data)); }).catch(function(){});
                    return resp;
                });
            }
            return origFetch.apply(this, arguments);
        };
        var origOpen = XMLHttpRequest.prototype.open;
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url) {
            this.__url = url;
            return origOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function() {
            var self = this;
            this.addEventListener('load', function() {
                if (self.__url && self.__url.indexOf('publish') >= 0) {
                    try { stash(extract(JSON.parse(self.responseText))); } catch(e) {}
                }
            });
            return origSend.apply(this, arguments);
        };
        return 'intercepted';
    })()
    """
    camoufox_eval(session, js_intercept)
    if not camoufox_click_button_by_text(session, "发布"):
        sys.stderr.write("error: 发布按钮未找到(DOM 改版?)\n")
        sys.exit(1)
    sys.stderr.write("[douyin-publish] 已点发布,等待跳转...\n")
    # 发布成功后页面跳转到作品管理页 /content/manage(中间会闪"正在发布"转圈 toast)。
    # 没有"发布成功"文本,旧 wait_for_text 必超时。2026-07-17 真机 spike 确认。
    if not camoufox_wait_for_url_contains(session, "/creator-micro/content/manage", POST_PUBLISH_MAX_WAIT_S):
        sys.stderr.write("error: 发布后未跳转到管理页\n")
        sys.exit(1)
    # 跳到管理页后立刻读 localStorage——趁登录态还在、同源 document 还在,把 id 落到本进程。
    aweme_id = _read_captured_aweme_id(session)
    sys.stdout.write(json.dumps({"ok": True, "session": session, "aweme_id": aweme_id}, ensure_ascii=False))
    sys.stdout.write("\n")


def _read_captured_aweme_id(session: str) -> Optional[str]:
    """从 localStorage(跨导航存活)读发布时捕获的 aweme_id,读不到再退回 window 变量。"""
    js = """
    (function() {
        try { var id = localStorage.getItem('douyin_last_aweme_id'); if (id) return id; } catch(e) {}
        return window.__capturedAwemeId || null;
    })()
    """
    out = camoufox_eval(session, js)
    if out and out != "null":
        return out
    return None


def cmd_get_link(*, session: str) -> None:
    """取已发布视频的公开链接。

    策略1(首选):读 publish 时写入 localStorage 的 aweme_id——localStorage 在
    creator.douyin.com 同源下跨发布→管理导航存活,无需重开页面,登录态还在。
    策略2(兜底):管理页 DOM 找刚发布作品卡片(改版后 selector 可能失效,仅兜底)。
    """
    # 策略1: localStorage(跨导航存活)+ window 变量双保险
    aweme_id = _read_captured_aweme_id(session)
    if aweme_id:
        url = "https://www.douyin.com/video/" + aweme_id
        sys.stdout.write(json.dumps({"ok": True, "url": url, "aweme_id": aweme_id}, ensure_ascii=False))
        sys.stdout.write("\n")
        return
    # 策略2: 管理页 DOM(旧方案,可能因改版失效)。当前页可能已是 manage,先看 URL 再决定是否 open。
    cur_url = camoufox_eval(session, "window.location.href")
    if not cur_url or "/creator-micro/content/manage" not in (cur_url or ""):
        camoufox_open(session, "https://creator.douyin.com/creator-micro/content/manage")
        time.sleep(3)
    js = """
    (function() {
        var a = document.querySelector('a[href*="/video/"]');
        if (a) return a.href;
        var el = document.querySelector('[data-aweme-id],[data-id],[data-e2e*="video"]');
        if (el) { var id = el.getAttribute('data-aweme-id') || el.getAttribute('data-id'); if (id) return 'https://www.douyin.com/video/' + id; }
        return null;
    })()
    """
    out = camoufox_eval(session, js)
    if out and out != "null":
        sys.stdout.write(json.dumps({"ok": True, "url": out}, ensure_ascii=False))
        sys.stdout.write("\n")
        return
    sys.stderr.write("warn: 视频链接提取失败(localStorage 和管理页 DOM 均未命中),但发布已成功\n")
    sys.stdout.write(json.dumps({"ok": True, "url": None, "note": "published but link extraction failed"}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_run(*, video: str, title: str, caption: str = "") -> None:
    """一键跑全流程:upload → fill → publish → get-link。

    探活/登录/导出 cookie+UA 交 login-manager(不在本 skill 内做)--本函数假设持久化 session
    `douyin` 已由 login-manager 登录态准备好,直接复用做发布操作。若 session 失效,camoufox-cli
    open 创作者中心页面会跳登录页,下游 snapshot/snapshot 失败会显式报错(由调用方转 login-manager 重登)。
    """
    session = PERSISTENT_SESSION
    try:
        cmd_upload(video=video, session=session)
        cmd_fill(session=session, title=title, caption=caption)
        cmd_publish(session=session)
        cmd_get_link(session=session)
    finally:
        # 用完即 close--登录态在磁盘 profile,不留进程占内存;下次发布按需重起无头 session
        try:
            subprocess.run([CAMOUFOX_BIN, "--session", session, "--json", "close"],
                           capture_output=True, text=True, timeout=10, check=False)
        except Exception:
            pass


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="publish_douyin",
        description="抖音内容发布(纯浏览器模拟方案,形态仿 wechat-channels-publish。探活/有头登录/导出 cookie+UA 交 login-manager)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_upload = sub.add_parser("upload", help="上传视频")
    p_upload.add_argument("--video", required=True)
    p_upload.add_argument("--session", default=None)
    p_upload.set_defaults(func=lambda a: cmd_upload(video=a.video, session=a.session))

    p_fill = sub.add_parser("fill", help="填标题/描述")
    p_fill.add_argument("--session", required=True)
    p_fill.add_argument("--title", default="")
    p_fill.add_argument("--caption", default="")
    p_fill.set_defaults(func=lambda a: cmd_fill(session=a.session, title=a.title, caption=a.caption))

    p_pub = sub.add_parser("publish", help="点发布按钮")
    p_pub.add_argument("--session", required=True)
    p_pub.set_defaults(func=lambda a: cmd_publish(session=a.session))

    p_link = sub.add_parser("get-link", help="取已发布视频链接")
    p_link.add_argument("--session", required=True)
    p_link.set_defaults(func=lambda a: cmd_get_link(session=a.session))

    p_run = sub.add_parser("run", help="一键跑全流程")
    p_run.add_argument("--video", required=True)
    p_run.add_argument("--title", required=True)
    p_run.add_argument("--caption", default="")
    p_run.set_defaults(func=lambda a: cmd_run(video=a.video, title=a.title, caption=a.caption))

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
