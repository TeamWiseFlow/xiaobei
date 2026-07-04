#!/usr/bin/env python3
"""douyin-publish — 抖音内容发布（Phase 3.2 浏览器模拟方案）

替代原 open platform H5 Schema 路径。改走浏览器模拟（camoufox-cli 主推）：
- 不再依赖开放平台 H5 Schema / scope / 签名 / 中转页
- 登录 https://creator.douyin.com/creator-micro/content/upload?enter_from=dou_web
- 在创作者中心页面填表 + 上传视频 + 发布
- 走 login-manager 中央 cookie（D18）

子命令：
  login                   login-manager 中央 cookie 探活
  upload --video <path>   上传视频
  fill --title X --caption Y  填标题/描述/话题
  publish                 点"发布"按钮
  get-link                取已发布视频的公开链接
  run                     一键跑全流程（login + upload + fill + publish + get-link）
  cleanup <session>       关闭 camoufox session

依赖：
- camoufox-cli（npm 全局）
- login-manager skill（同 crew 私有，cookie 中央存储）
- login-manager 平台 key: `douyin`

参考：
- 形态仿 crews/main/skills/wechat-channels-publish（视频号浏览器模拟）
- 用户上下文：抖音开放平台发布能力被驳回（主体资质不满足）→ 走浏览器模拟绕过
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
LOGIN_MANAGER_BIN = os.environ.get(
    "LOGIN_MANAGER_BIN",
    "~/.openclaw/workspace-main/skills/login-manager/scripts/login-manager.sh",
)
CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
LOGIN_MANAGER_PLATFORM = "douyin"

UPLOAD_TIMEOUT_S = 600        # 大视频上传可能慢
TRANSCODE_POLL_S = 3
TRANSCODE_MAX_WAIT_S = 600    # 转码最多 10 分钟
POST_PUBLISH_POLL_S = 5
POST_PUBLISH_MAX_WAIT_S = 60  # 发布后跳转最多 1 分钟
QR_SCAN_TIMEOUT_S = 180       # 扫码登录 3 分钟


# ── 平台工具 ────────────────────────────────────────────────────────────────

def login_manager_check() -> bool:
    """探活 login-manager 中央 cookie。"""
    result = subprocess.run(
        [LOGIN_MANAGER_BIN, "check", LOGIN_MANAGER_PLATFORM],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode == 0


def session_name(purpose: str = "publish") -> str:
    """生成 camoufox session 名（D18 + 4.5.5 并发约束：每任务一 session）。"""
    return f"douyin-{purpose}-{secrets.token_hex(4)}"


def camoufox_open(session: str, url: str) -> None:
    """启 headless + persistent 会话 + 打开 URL。"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--persistent", "--headless", "--json", "open", url]
    subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)


def camoufox_eval(session: str, js: str, timeout: int = 30) -> Optional[str]:
    """在 session 内 eval JS，返回 data 字段（None 表示失败）。"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--json", "eval", js]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        env = json.loads(result.stdout)
        data = env.get("data")
        return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        return result.stdout


def camoufox_click(session: str, selector: str) -> bool:
    """click selector；返回是否成功。"""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return false;
        el.click();
        return true;
    }})()
    """
    out = camoufox_eval(session, js)
    return out == "true"


def camoufox_type(session: str, selector: str, text: str) -> bool:
    """在 input/textarea 填值；触发 input 事件。"""
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return false;
        var proto = Object.getPrototypeOf(el);
        var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, {json.dumps(text)});
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true;
    }})()
    """
    out = camoufox_eval(session, js)
    return out == "true"


def camoufox_set_file(session: str, selector: str, file_path: Path) -> bool:
    """通过 DataTransfer 注入 file 到 input[type=file]（绕过 CDP setFileInput 限制）。"""
    import base64
    b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    js = f"""
    (function() {{
        var el = document.querySelector({json.dumps(selector)});
        if (!el) return false;
        var bin = atob({json.dumps(b64)});
        var arr = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        var file = new File([arr], {json.dumps(file_path.name)}, {{ type: 'video/mp4' }});
        var dt = new DataTransfer();
        dt.items.add(file);
        el.files = dt.files;
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true;
    }})()
    """
    out = camoufox_eval(session, js, timeout=120)
    return out == "true"


def camoufox_wait_for_text(session: str, text: str, timeout: int = TRANSCODE_MAX_WAIT_S) -> bool:
    """轮询页面，等待出现特定文本（转码完成 / 上传成功）。"""
    js = f"document.body && document.body.innerText && document.body.innerText.indexOf({json.dumps(text)}) >= 0"
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = camoufox_eval(session, js)
        if out == "true":
            return True
        time.sleep(TRANSCODE_POLL_S)
    return False


def camoufox_close(session: str) -> None:
    """关闭 camoufox session。"""
    subprocess.run(
        [LOGIN_MANAGER_BIN, "session-cleanup", LOGIN_MANAGER_PLATFORM, session],
        capture_output=True, text=True, timeout=10, check=False,
    )


# ── 子命令实现 ──────────────────────────────────────────────────────────────

def cmd_login() -> None:
    """login-manager 中央 cookie 探活。"""
    if login_manager_check():
        sys.stdout.write(json.dumps({"ok": True, "platform": LOGIN_MANAGER_PLATFORM}, ensure_ascii=False))
        sys.stdout.write("\n")
        sys.exit(0)
    sys.stderr.write(
        f"error: {LOGIN_MANAGER_PLATFORM} cookie 失效；"
        f"请先走 login-manager qr-headless + qr-confirm 流程\n"
    )
    sys.exit(2)


def cmd_upload(*, video: str, session: Optional[str] = None) -> None:
    """上传视频到创作者中心。"""
    if not session:
        session = session_name("upload")
    video_path = Path(video).resolve()
    if not video_path.is_file():
        sys.stderr.write(f"error: video not found: {video_path}\n")
        sys.exit(1)

    camoufox_open(session, UPLOAD_URL)
    # 抖音创作者中心上传选择器（待真机 spike 验证；以下为公开推测）
    # 视频文件 input 通常在创作中心上传组件内：
    file_input_selector = 'input[type="file"][accept*="video"]'
    if not camoufox_set_file(session, file_input_selector, video_path):
        sys.stderr.write("error: 上传 input 未找到或注入失败（DOM 改版？）\n")
        sys.exit(1)

    sys.stderr.write("[douyin-publish] 视频已注入，等待上传/转码...\n")
    if not camoufox_wait_for_text(session, "上传成功", TRANSCODE_MAX_WAIT_S):
        sys.stderr.write("error: 视频上传/转码超时\n")
        sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "session": session, "video": str(video_path)}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_fill(*, session: str, title: str = "", caption: str = "") -> None:
    """填标题 / 描述 / 话题。"""
    if title:
        # 抖音创作者中心标题 input（待 spike 验证）
        if not camoufox_type(session, 'input[placeholder*="标题"]', title):
            sys.stderr.write("error: 标题 input 未找到\n")
            sys.exit(1)
    if caption:
        # 抖音创作者中心描述 contenteditable（待 spike 验证）
        if not camoufox_type(session, 'div[contenteditable][data-placeholder*="描述"]', caption):
            sys.stderr.write("error: 描述 input 未找到\n")
            sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "title": title, "caption": caption}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_publish(*, session: str) -> None:
    """点"发布"按钮。"""
    if not camoufox_click(session, 'button:has-text("发布")'):
        sys.stderr.write("error: 发布按钮未找到（DOM 改版？）\n")
        sys.exit(1)
    sys.stderr.write("[douyin-publish] 已点发布，等待跳转...\n")
    if not camoufox_wait_for_text(session, "发布成功", POST_PUBLISH_MAX_WAIT_S):
        sys.stderr.write("error: 发布后未检测到成功提示\n")
        sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "session": session}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_get_link(*, session: str) -> None:
    """取已发布视频的公开链接（从视频管理页获取）。"""
    # 抖音创作者中心视频管理页
    mgmt_url = "https://creator.douyin.com/creator-micro/content/manage"
    camoufox_open(session, mgmt_url)
    # 等待列表加载
    time.sleep(3)
    # 从列表第一条拿"分享"按钮复制链接
    # 抖音视频链接格式: https://www.douyin.com/video/<aweme_id>
    js = """
    (function() {
        // 找第一个视频的链接（从分享按钮或 data-id 提取 aweme_id）
        var row = document.querySelector('[class*="content-item"]:first-child, .video-item:first-child, tr:first-child');
        if (!row) return null;
        // 尝试从 a 标签拿 href
        var a = row.querySelector('a[href*="/video/"]');
        if (a) return a.href;
        // 尝试从 data 属性拿 aweme_id
        var id = row.dataset.awemeId || row.dataset.id;
        if (id) return 'https://www.douyin.com/video/' + id;
        return null;
    })()
    """
    out = camoufox_eval(session, js)
    if not out or out == "null":
        sys.stderr.write("error: 视频链接提取失败（DOM 改版？）\n")
        sys.exit(1)
    sys.stdout.write(json.dumps({"ok": True, "url": out}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_run(*, video: str, title: str, caption: str = "") -> None:
    """一键跑全流程：login → upload → fill → publish → get-link。"""
    if not login_manager_check():
        sys.stderr.write(
            f"error: {LOGIN_MANAGER_PLATFORM} cookie 失效；"
            f"请先走 login-manager qr-headless + qr-confirm 流程\n"
        )
        sys.exit(2)

    session = session_name("run")
    try:
        cmd_upload(video=video, session=session)
        cmd_fill(session=session, title=title, caption=caption)
        cmd_publish(session=session)
        cmd_get_link(session=session)
    finally:
        camoufox_close(session)


def cmd_cleanup(*, session: str) -> None:
    camoufox_close(session)
    sys.stdout.write(json.dumps({"ok": True, "session": session}, ensure_ascii=False))
    sys.stdout.write("\n")


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="publish_douyin",
        description="抖音内容发布（Phase 3.2 浏览器模拟方案，camoufox-cli 主推）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="login-manager 中央 cookie 探活")
    p_login.set_defaults(func=lambda a: cmd_login())

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

    p_clean = sub.add_parser("cleanup", help="关闭 camoufox session")
    p_clean.add_argument("--session", required=True)
    p_clean.set_defaults(func=lambda a: cmd_cleanup(session=a.session))

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
