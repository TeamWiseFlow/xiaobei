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


# 抖音登录态关键 cookie（与 _shared/check-session.ts Tier1 一致：sessionid+sid_tt+uid_tt 必须全在）。
# httpOnly，document.cookie 读不到，必须走 cookies export。
DOUYIN_LOGIN_COOKIES = ("sessionid", "sid_tt", "uid_tt")


def _check_logged_in(session: str) -> None:
    """open 完上传页后立即验登录态，未登录直接 exit 2（SESSION_EXPIRED）。

    双重信号，任中即判未登录：
      1. URL 跳到登录页（含 /login 或 passport，或已不在 creator-micro/content/upload 上）
      2. cookies 缺 sessionid/sid_tt/uid_tt 任一（兜住「页面渲染但无真 session」的假登录态）

    SKILL.md 约定 exit 2 = session 失效 → 调用方走 login-manager 有头重登。本 skill 不自管重登。
    之前没这层守卫，未登录也一路点下去误报「发布成功」（2026-07-17 xiaobei 事故）。
    """
    # 信号 1：URL 跳登录页
    cur_url = camoufox_eval(session, "window.location.href") or ""
    on_login_page = ("/login" in cur_url) or ("passport" in cur_url)
    left_upload = "/creator-micro/content/upload" not in cur_url
    # 信号 2：导出 cookies 查关键字段
    tmp = f"/tmp/dy-logincheck-{session}.json"
    missing: list[str] = []
    try:
        subprocess.run(
            [CAMOUFOX_BIN, "--session", session, "--persistent", "--json", "cookies", "export", tmp],
            capture_output=True, text=True, timeout=30, check=False,
        )
        raw = json.loads(Path(tmp).read_text("utf-8"))
        arr = raw if isinstance(raw, list) else (raw.get("cookies") if isinstance(raw, dict) else [])
        names = {c.get("name") for c in arr if isinstance(c, dict)}
        missing = [k for k in DOUYIN_LOGIN_COOKIES if k not in names]
    except Exception as e:
        # 导出/解析失败本身是异常，但先不直接 crash——若 URL 已判登录页就够下结论；
        # 否则把导出失败当未登录处理（宁可误报重登，不可误报成功）。
        sys.stderr.write(f"[douyin-publish] warn: 登录态 cookie 导出异常: {e}\n")
        missing = list(DOUYIN_LOGIN_COOKIES)

    if on_login_page or (left_upload and not cur_url.startswith("about:")):
        sys.stderr.write(
            f"error: 未登录或登录态已失效（URL={cur_url}，已跳离上传页/到登录页）——"
            f"请走 login-manager --platform douyin 有头重登后重试\n"
        )
        sys.exit(2)
    if missing:
        sys.stderr.write(
            f"error: 未登录或登录态已失效（cookies 缺 {','.join(missing)}）——"
            f"请走 login-manager --platform douyin 有头重登后重试\n"
        )
        sys.exit(2)


def _dismiss_draft_dialog(session: str) -> None:
    """上传页可能弹「你还有上次未发布的视频，是否继续编辑？」草稿恢复框。

    点「放弃」清掉旧草稿，给新发布一个干净的上传页。无弹窗则 no-op。
    旧草稿在场时新视频上传/发布会被带偏（2026-07-17 xiaobei 事故根因之一：
    上次失败发布留了草稿，新发布被旧草稿带偏，页面跳管理页但实际没发出去）。
    """
    has_dialog = camoufox_eval(
        session,
        "(document.body.innerText||'').indexOf('你还有上次未发布的视频')>=0?'yes':'no'",
    ) == "yes"
    if not has_dialog:
        return
    sys.stderr.write("[douyin-publish] 检测到上次未发布草稿，点「放弃」清掉后重新上传...\n")
    if not camoufox_click_leaf_by_text(session, "放弃"):
        sys.stderr.write("warn: 草稿弹窗「放弃」按钮未点到，继续上传（可能受弹窗干扰）\n")
        return
    time.sleep(2)  # 等弹窗关闭、上传页重渲染
    # 放弃后可能弹二次确认（「确定放弃？」），有就点确定
    if camoufox_eval(session, "(document.body.innerText||'').indexOf('确定放弃')>=0?'yes':'no'") == "yes":
        camoufox_click_button_by_text(session, "确定")
        time.sleep(1)


def camoufox_eval(session: str, js: str, timeout: int = 30) -> Optional[str]:
    """在 session 内 eval JS,返回 data 字段(None 表示失败)。

    必须带 --persistent:ensureDaemon 按 session+mode 复用 daemon(不查 persistent-ness),
    若 eval 不带 --persistent 又恰好是首个触发 daemon spawn 的调用,会起一个非持久 daemon
    (临时 profile /tmp/playwright_firefoxdev_profile-XXX,无 auth cookie),后续
    camoufox_open --persistent 进来也复用这个非持久 daemon → 全程临时 profile → 登录页 +
    work_list sc=8(2026-07-18 xiaobei get-link 事故根因)。所有 camoufox-cli 调用必须
    一致带 --persistent,保证 daemon 首次 spawn 即持久。
    """
    cmd = [CAMOUFOX_BIN, "--session", session, "--persistent", "--json", "eval", js]
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
    # 登录态守卫：open 完立即验，未登录 exit 2，不往下走 fill/publish 误报成功。
    _check_logged_in(session)
    # 清掉上次失败发布留下的草稿弹窗，给新发布一个干净上传页。
    _dismiss_draft_dialog(session)
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
    发布前注入 fetch/XHR 拦截器捕获发布 API 响应中的 aweme_id,写入 localStorage(跨同源导航存活)。
    aweme_id 捕获不到 → exit 3（发布可能未真正成功，不再误报 ok）。"""
    # 拦截器：捕获所有 fetch/XHR 响应，深度搜索 aweme_id/item_id，全量记 debug 日志。
    # 旧版只匹配 url 含 'publish' 的请求 + 固定提取路径，对不上抖音真实发布接口，
    # aweme_id 一直 null（2026-07-17 xiaobei 事故）。现改为全量捕获 + 深度提取 + debug 落盘，
    # 下次跑能把真实发布 API 的 URL/响应 shape 反馈回来精准收窄。
    # aweme_id + debug 都写 localStorage：发布后页面跳管理页，window 变量随旧 document 销毁，
    # localStorage 在 creator.douyin.com 同源下跨导航存活，管理页能读回。
    js_intercept = """
    (function() {
        window.__capturedAwemeId = null;
        window.__publishDebug = [];
        try { localStorage.removeItem('douyin_last_aweme_id'); } catch(e) {}
        try { localStorage.removeItem('douyin_publish_debug'); } catch(e) {}
        function stash(id) {
            if (!id) return;
            id = String(id);
            if (window.__capturedAwemeId) return;
            window.__capturedAwemeId = id;
            try { localStorage.setItem('douyin_last_aweme_id', id); } catch(e) {}
        }
        function extract(data) {
            try {
                var found = null;
                (function walk(o, depth) {
                    if (found || depth > 10 || !o || typeof o !== 'object') return;
                    for (var k in o) {
                        if (!Object.prototype.hasOwnProperty.call(o, k)) continue;
                        var v = o[k];
                        if ((k === 'aweme_id' || k === 'item_id' || k === 'awemeId' || k === 'itemId' || k === 'video_id')
                            && v != null && v !== '' && typeof v !== 'object') { found = String(v); return; }
                        if (typeof v === 'object') walk(v, depth + 1);
                    }
                })(data, 0);
                return found;
            } catch(e) { return null; }
        }
        function logReq(url, method, status, body) {
            try {
                window.__publishDebug.push({
                    url: String(url).slice(0, 300), method: method || 'GET',
                    status: status, body: body ? String(body).slice(0, 1000) : null
                });
                if (window.__publishDebug.length > 300) window.__publishDebug.shift();
                try { localStorage.setItem('douyin_publish_debug', JSON.stringify(window.__publishDebug)); } catch(e) {}
            } catch(e) {}
        }
        var origFetch = window.fetch;
        window.fetch = function() {
            var url = arguments[0];
            var method = (arguments[1] && arguments[1].method) || 'GET';
            return origFetch.apply(this, arguments).then(function(resp) {
                try {
                    resp.clone().text().then(function(txt) {
                        logReq(url, method, resp.status, txt);
                        var id = null; try { id = extract(JSON.parse(txt)); } catch(e) {}
                        if (id) stash(id);
                    }).catch(function(){});
                } catch(e) {}
                return resp;
            });
        };
        var origOpen = XMLHttpRequest.prototype.open;
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url) {
            this.__url = url; this.__method = method;
            return origOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function() {
            var self = this;
            this.addEventListener('load', function() {
                try {
                    logReq(self.__url, self.__method, self.status, self.responseText);
                    var id = null; try { id = extract(JSON.parse(self.responseText)); } catch(e) {}
                    if (id) stash(id);
                } catch(e) {}
            });
            return origSend.apply(this, arguments);
        };
        return 'intercepted';
    })()
    """
    camoufox_eval(session, js_intercept)
    # 记发布前时间,用于 work_list 按 create_time 锁定本次作品(发布走 form/导航,
    # 拦截器抓不到 aweme_id 时回退打 work_list API 取 create_time>=此时刻的最新作品)。
    publish_start = int(time.time())
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
    # 拦截器 miss(发布走 form/导航非 fetch)→ 直接打 work_list API 拿最新作品。
    # 列表不按 create_time 排序,按 create_time>=publish_start-120 筛后取最新,锁定本次发布。
    if not aweme_id:
        aweme_id, title = _fetch_newest_aweme_id(session, since_ts=publish_start - 120)
        if aweme_id:
            sys.stderr.write(
                f"[douyin-publish] work_list API 取到最新作品 aweme_id={aweme_id} title={title!r}\n"
            )
            # 落 localStorage 供 get-link 复用(跨导航存活)
            camoufox_eval(
                session,
                f"try{{localStorage.setItem('douyin_last_aweme_id',{json.dumps(aweme_id)});}}catch(e){{}}",
            )
    # debug 日志落盘供排查（aweme_id 命中与否都写，方便 xiaobei 回传真实发布 API shape）
    debug_path = f"/tmp/dy-publish-debug-{int(time.time())}.json"
    debug_entries = _read_publish_debug(session)
    try:
        Path(debug_path).write_text(json.dumps(debug_entries, ensure_ascii=False, indent=2), "utf-8")
        sys.stderr.write(f"[douyin-publish] debug 日志已写 {debug_path}（{len(debug_entries)} 条请求，请回传给研发）\n")
    except Exception as e:
        sys.stderr.write(f"warn: debug 日志写盘失败: {e}\n")
    # aweme_id 没捕获到 → 发布可能未真正成功（拦截器没命中真实发布 API，或发布被服务端拒了）。
    # 不再误报 ok——宁可误判失败让人工核实管理页，不可误报成功。（2026-07-17 xiaobei 事故根因之二）
    if not aweme_id:
        sys.stderr.write(
            "error: 发布流程走完但未捕获到 aweme_id——发布可能未真正成功（发布 API 未命中拦截器或被服务端拒绝）。\n"
            f"       请人工到管理页核实是否真有新作品；debug 日志在 {debug_path}\n"
        )
        sys.exit(3)
    sys.stdout.write(json.dumps({"ok": True, "session": session, "aweme_id": aweme_id}, ensure_ascii=False))
    sys.stdout.write("\n")


WORK_LIST_URL = (
    "https://creator.douyin.com/janus/douyin/creator/pc/work_list"
    "?status=0&count=20&max_cursor=0&scene=star_atlas&device_platform=android&aid=1128"
)


def _fetch_newest_aweme_id(session: str, since_ts: Optional[int] = None) -> tuple[Optional[str], Optional[str]]:
    """直接打作品管理 list API 拿最新作品的 aweme_id。

    发布走 form/导航(非 fetch/XHR),发布页拦截器抓不到 aweme_id(2026-07-17 xiaobei 事故)。
    但发布成功后作品进管理页 list,同源 fetch work_list 带 cookie 即可拿到 aweme_list。
    列表**不按 create_time 排序**,必须自己排序取最新。

    Args:
        since_ts: 若给定,只考虑 create_time >= since_ts 的作品(发布前记的时间 - buffer,
                  用来锁定「本次发布」的作品,避免误中上一次的旧作品)。None 则不筛(取全局最新)。

    Returns:
        (aweme_id, title) 或 (None, None)。

    headless session 登录态间歇性不稳(2026-07-17 xiaobei 事故:同 URL 同 session
    有时 status_code=0 有时 =8,连发 15 次全 0 但偶发 8,无法稳定复现)。
    status_code!=0 时纯重试(同页连发就稳,不需 reload),最多 3 次;
    3 次全 sc!=0 → exit 2(SESSION_EXPIRED)让调用方走 login-manager 重登。
    """
    since = int(since_ts) if since_ts else 0
    js = f"""
    (async function() {{
        try {{
            var r = await fetch({json.dumps(WORK_LIST_URL)}, {{credentials: 'include'}});
            var j = await r.json();
            var sc = (typeof j.status_code === 'number') ? j.status_code : 0;
            var list = j.aweme_list || [];
            var items = list.map(function(it) {{
                var id = it.aweme_id || it.item_id;
                var ct = it.create_time || 0;
                var title = '';
                try {{ title = (it.aweme_desc && it.aweme_desc.text) || it.desc || it.title || ''; }} catch(e) {{}}
                return {{id: String(id), ct: Number(ct), title: String(title).slice(0, 60)}};
            }}).filter(function(x) {{ return x.id && x.id.length > 5; }});
            if ({since} > 0) items = items.filter(function(x) {{ return x.ct >= {since}; }});
            items.sort(function(a, b) {{ return b.ct - a.ct; }});
            var top = items[0];
            if (!top) return JSON.stringify({{sc: sc, id: null}});
            return JSON.stringify({{sc: sc, id: top.id, ct: top.ct, title: top.title, count: items.length}});
        }} catch(e) {{ return JSON.stringify({{sc: -1, id: null, err: String(e)}}); }}
    }})()
    """
    last_sc = None
    for attempt in range(3):
        out = camoufox_eval(session, js, timeout=40)
        data = None
        if out and out != "null":
            try:
                data = json.loads(out)
            except Exception:
                data = None
        if not data:
            # eval 失败(页面没开 / daemon 挂)→ 开管理页重试
            camoufox_open(session, "https://creator.douyin.com/creator-micro/content/manage")
            time.sleep(5)
            continue
        sc = data.get("sc", 0)
        aid = data.get("id")
        if sc == 0 and aid:
            return str(aid), data.get("title")
        if sc == 0 and not aid:
            # API 正常但没匹配作品(since_ts 筛掉所有)→ 不重试
            return None, None
        # sc != 0 → 鉴权间歇失败,短等重试
        last_sc = sc
        sys.stderr.write(
            f"[douyin-publish] work_list status_code={sc}(attempt {attempt + 1}/3),间歇鉴权失败,重试...\n"
        )
        time.sleep(2)
    # 3 次都 sc!=0 → session 失效,交调用方重登
    sys.stderr.write(
        f"error: work_list API 鉴权持续失败(3 次 status_code={last_sc})——登录态已失效,"
        "请走 login-manager --platform douyin 有头重登后重试\n"
    )
    sys.exit(2)


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


def _read_publish_debug(session: str) -> list:
    """从 localStorage 读发布期间拦截器记录的所有 fetch/XHR 请求（跨导航存活）。"""
    js = """
    (function() {
        try { var d = localStorage.getItem('douyin_publish_debug'); if (d) return d; } catch(e) {}
        return JSON.stringify(window.__publishDebug || []);
    })()
    """
    out = camoufox_eval(session, js)
    if not out or out == "null":
        return []
    try:
        return json.loads(out) if isinstance(json.loads(out), list) else []
    except Exception:
        return []


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
    # 策略2: 直接打 work_list API 取最新作品(发布走 form/导航,拦截器抓不到 aweme_id 时靠这路)。
    # 无 since_ts(不知发布时刻),取全局最新——run 流程下 get-link 紧跟 publish,localStorage 通常已命中,
    # 走到这里说明 localStorage 被清,取最新作品兜底。
    aweme_id, title = _fetch_newest_aweme_id(session)
    if aweme_id:
        url = "https://www.douyin.com/video/" + aweme_id
        sys.stderr.write(f"[douyin-publish] get-link 走 work_list 兜底:aweme_id={aweme_id} title={title!r}\n")
        sys.stdout.write(json.dumps({"ok": True, "url": url, "aweme_id": aweme_id}, ensure_ascii=False))
        sys.stdout.write("\n")
        return
    # 策略3: 管理页 DOM(旧方案,可能因改版失效)。当前页可能已是 manage,先看 URL 再决定是否 open。
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
    sys.stderr.write("warn: 视频链接提取失败(localStorage/work_list/DOM 均未命中),但发布已成功\n")
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
