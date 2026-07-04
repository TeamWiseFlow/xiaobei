#!/usr/bin/env python3
"""login_manager.py — 平台登录态管理（Phase 4.5.2 camoufox-cli 路径）

替代 Phase 4.5 前的 CDP WebSocket 抽 cookie 流程。保留中央存储
`~/.openclaw/logins/{platform}.json` 不变；改用 camoufox-cli 做
QR 截图 / cookies 导入导出 / 探活。

CLI 形态（与 Phase 4.5 前兼容 + 新增 camoufox 子命令）：
    check <platform>                     探活 (0/2)
    read  <platform>                     读中央 JSON
    write <platform>                     从 stdin 写中央 JSON
    status-all                           批量探活
    qr-headless <platform> [url]         启 headless + 截 QR
    qr-confirm <platform> [session]      轮询扫码 + cookies export
    cookie-export <platform> <session>   从 camoufox session 落中央 JSON
    cookie-import <platform> <session>   从中央 JSON 注 camoufox session
    session-cleanup <platform> [session] 关 camoufox session

依赖：camoufox-cli（npm 全局，Dockerfile 阶段 1 安装）；其余仅 Python stdlib。
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 常量 ─────────────────────────────────────────────────────────────────────

LOGINS_DIR = Path(os.environ.get("OPENCLAW_LOGINS_DIR", "~/.openclaw/logins")).expanduser()
CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
QR_SCAN_TIMEOUT_S = 180
QR_SCAN_POLL_INTERVAL_S = 3
PROBE_TIMEOUT_S = 8

VALID_PLATFORMS = (
    "douyin", "bilibili", "kuaishou",
    "xhs-publish", "xhs-browse",
    "weibo", "zhihu", "wechat-channels",
    "wx-mp",  # Phase 4.6 公众号创作者中心（engagement 抓取用）
)

# 平台 → camoufox 登录页 URL + 探活 URL
PLATFORM_LOGIN_URL = {
    "douyin":           "https://www.douyin.com/",
    "bilibili":         "https://www.bilibili.com/",
    "kuaishou":         "https://www.kuaishou.com/",
    "xhs-publish":      "https://creator.xiaohongshu.com/publish/publish?source=official",
    "xhs-browse":       "https://www.xiaohongshu.com/",
    "weibo":            "https://weibo.com/",
    "zhihu":            "https://www.zhihu.com/",
    "wechat-channels":  "https://channels.weixin.qq.com/",
    "wx-mp":            "https://mp.weixin.qq.com/",
}

# 平台 → 探活 URL（带 cookie GET 一次判 200）
PLATFORM_PROBE_URL = {
    "douyin":           "https://www.douyin.com/aweme/v1/web/aweme/post/",
    "bilibili":         "https://api.bilibili.com/x/web-interface/nav",
    "kuaishou":         "https://www.kuaishou.com/",
    "xhs-publish":      "https://creator.xiaohongshu.com/publish/publish?source=official",
    "xhs-browse":       "https://www.xiaohongshu.com/",
    "weibo":            "https://weibo.com/ajax/profile/info",
    "zhihu":            "https://www.zhihu.com/api/v4/me",
    "wechat-channels":  "https://channels.weixin.qq.com/",
    # Phase 4.6 wx-mp 探活：创作者中心首页（spike 后可换更精确的 API）
    "wx-mp":            "https://mp.weixin.qq.com/",
}


# ── 平台校验 ─────────────────────────────────────────────────────────────────

def validate_platform(platform: str) -> str:
    if platform not in VALID_PLATFORMS:
        sys.stderr.write(
            f"error: unknown platform {platform!r}\n"
            f"valid: {', '.join(VALID_PLATFORMS)}\n"
        )
        sys.exit(1)
    return platform


# ── 中央存储 IO ──────────────────────────────────────────────────────────────

def storage_path(platform: str) -> Path:
    return LOGINS_DIR / f"{platform}.json"


def read_storage(platform: str) -> dict | None:
    path = storage_path(platform)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def write_storage(platform: str, payload: dict) -> None:
    LOGINS_DIR.mkdir(parents=True, exist_ok=True)
    target = storage_path(platform)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, target)


# ── camoufox-cli 调用 ────────────────────────────────────────────────────────

def session_name(platform: str, purpose: str = "login") -> str:
    """生成 camoufox session 名：{platform}-{purpose}-{nonce}

    约束（D18 + 4.5.5）：每 agent / 每登录流程一 session，独立 profile dir。
    """
    nonce = secrets.token_hex(4)
    return f"{platform}-{purpose}-{nonce}"


def camoufox_open(
    session: str,
    url: str,
    *,
    headless: bool = True,
    persistent: bool = True,
    timeout: int = 30,
) -> str:
    """启 camoufox session 打开 URL；返回 JSON 信封字符串（stdout）"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--json"]
    if persistent:
        cmd.append("--persistent")
    if headless:
        cmd.append("--headless")
    cmd += ["open", url]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"camoufox-cli open failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def snapshot_qr_to_file(session: str, png_path: str) -> str:
    """用 camoufox-cli snapshot 取 QR PNG。返回 PNG 路径。"""
    png_path = os.path.abspath(png_path)
    cmd = [
        CAMOUFOX_BIN, "--session", session, "--json",
        "snapshot", png_path, "--qr-only",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"camoufox-cli snapshot failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return png_path


def poll_login_success(session: str, *, timeout: int, interval: int = QR_SCAN_POLL_INTERVAL_S) -> bool:
    """轮询 camoufox session 是否已登录成功（URL 变化 / QR 元素消失）。

    通过 camoufox-cli eval 取 window.location.href + 检查 QR 元素存在。
    """
    deadline = time.time() + timeout
    probe_js = (
        "JSON.stringify({"
        "  href: window.location.href,"
        "  hasQr: !!document.querySelector('img[src*=\"qrcode\"], canvas[class*=\"qr\"]')"
        "})"
    )
    while time.time() < deadline:
        try:
            result = subprocess.run(
                [CAMOUFOX_BIN, "--session", session, "--json",
                 "eval", probe_js],
                capture_output=True, text=True, timeout=8, check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                payload = json.loads(_unwrap_envelope(result.stdout))
                href = payload.get("href", "")
                has_qr = payload.get("hasQr", False)
                # 登录成功 = URL 不再是 login 页 + QR 元素消失
                if not has_qr and "/login" not in href and href:
                    return True
        except (subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError):
            pass
        time.sleep(interval)
    return False


def camoufox_export_cookies(platform: str, session: str) -> None:
    """从 camoufox session export cookies → 中央 JSON 存储"""
    validate_platform(platform)
    out_file = storage_path(platform).with_suffix(".cookies.json.tmp")
    cmd = [CAMOUFOX_BIN, "--session", session, "cookies", "export", str(out_file)]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"camoufox-cli cookies export failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    cookies = json.loads(out_file.read_text())
    out_file.unlink()
    payload = {
        "platform": platform,
        "cookies": cookies,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    write_storage(platform, payload)


def camoufox_import_cookies(platform: str, session: str) -> None:
    """从中央 JSON 存储 import cookies → camoufox session"""
    validate_platform(platform)
    payload = read_storage(platform)
    if payload is None or not payload.get("cookies"):
        raise RuntimeError(f"no cookies stored for platform {platform!r}")
    tmp = storage_path(platform).with_suffix(".import.json.tmp")
    tmp.write_text(json.dumps(payload["cookies"]))
    cmd = [CAMOUFOX_BIN, "--session", session, "cookies", "import", str(tmp)]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=15, check=False
    )
    tmp.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"camoufox-cli cookies import failed (rc={result.returncode}): {result.stderr.strip()}"
        )


def camoufox_close(session: str) -> None:
    """关闭 camoufox session（释放 daemon + 进程）"""
    subprocess.run(
        [CAMOUFOX_BIN, "close", "--session", session],
        capture_output=True, text=True, timeout=10, check=False,
    )


# ── 探活 ─────────────────────────────────────────────────────────────────────

def _cookie_header_from_payload(payload: dict, target_domain: str) -> str:
    """把中央 JSON cookies 转 raw HTTP Cookie header（薄适配）

    支持两种 cookies 字段格式：
    - 新格式（Phase 4.5+ camoufox-cli 原生）：list of dict，含 domain/path/name/value
    - 旧格式（Phase 4.5 前的 CDP 路径）："k=v; k=v" 字符串，return-as-is
    """
    cookies = payload.get("cookies", "")
    if isinstance(cookies, str):
        # 旧格式：raw cookie header 字符串，直接返回
        return cookies
    if not isinstance(cookies, list):
        return ""
    parts = []
    for c in cookies:
        if not isinstance(c, dict):
            continue
        domain = c.get("domain", "")
        if target_domain in domain or domain.lstrip(".") == target_domain.lstrip("."):
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts)


def probe_platform(platform: str, payload: dict | None = None) -> bool:
    """对平台做一次鉴权探活。返回 True 表示 session 有效。"""
    if payload is None:
        payload = read_storage(platform)
    if not payload or not payload.get("cookies"):
        return False
    target_url = PLATFORM_PROBE_URL.get(platform)
    if not target_url:
        return False
    target_domain = urllib.parse.urlparse(target_url).hostname or ""
    cookie_header = _cookie_header_from_payload(payload, target_domain)
    if not cookie_header:
        return False
    req = urllib.request.Request(
        target_url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:150.0) Gecko/20100101 Firefox/150.0",
            "Cookie": cookie_header,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


# ── envelope 解包 ────────────────────────────────────────────────────────────

def _unwrap_envelope(s: str) -> str:
    """camoufox-cli --json 输出形如 {success, data}，取 .data 的字符串。"""
    try:
        env = json.loads(s)
        if isinstance(env, dict) and "data" in env:
            data = env["data"]
            return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        pass
    return s


# ── CLI 子命令实现 ───────────────────────────────────────────────────────────

def cmd_check(platform: str) -> None:
    validate_platform(platform)
    payload = read_storage(platform)
    if payload is None:
        sys.exit(2)
    if not probe_platform(platform, payload):
        sys.exit(2)
    sys.stdout.write(json.dumps({
        "ok": True,
        "platform": platform,
        "updated_at": payload.get("updated_at"),
        "cookie_count": len(payload.get("cookies", [])),
    }, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_read(platform: str) -> None:
    validate_platform(platform)
    payload = read_storage(platform)
    if payload is None:
        sys.exit(2)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_write(platform: str) -> None:
    validate_platform(platform)
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"error: invalid JSON from stdin: {e}\n")
        sys.exit(1)
    if "platform" not in payload:
        payload["platform"] = platform
    if "updated_at" not in payload:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_storage(platform, payload)


def cmd_status_all() -> None:
    summary = {"platforms": [], "total": 0, "valid": 0, "expired": 0}
    for platform in VALID_PLATFORMS:
        payload = read_storage(platform)
        if payload is None:
            continue
        ok = probe_platform(platform, payload)
        summary["platforms"].append({
            "platform": platform,
            "ok": ok,
            "updated_at": payload.get("updated_at"),
            "cookie_count": len(payload.get("cookies", [])),
        })
        summary["total"] += 1
        summary["valid" if ok else "expired"] += 1
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_qr_headless(platform: str, url: str | None) -> None:
    validate_platform(platform)
    login_url = url or PLATFORM_LOGIN_URL[platform]
    session = session_name(platform, "login")
    camoufox_open(session, login_url, headless=True, persistent=True)
    qr_png = snapshot_qr_to_file(session, f"/tmp/qr-{platform}-{int(time.time())}.png")
    sys.stdout.write(json.dumps({
        "ok": True,
        "session": session,
        "platform": platform,
        "qr_path": qr_png,
        "login_url": login_url,
    }, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_qr_confirm(platform: str, *, session: str | None = None, timeout: int = QR_SCAN_TIMEOUT_S) -> None:
    validate_platform(platform)
    if session is None:
        # 默认选最近创建的 {platform}-login-* session
        # 简化：调一个子命令列出 sessions；这里直接报"必须显式传 session"
        sys.stderr.write("error: must pass --session explicitly to qr-confirm\n")
        sys.exit(1)
    if not poll_login_success(session, timeout=timeout):
        sys.exit(2)
    camoufox_export_cookies(platform, session)
    sys.stdout.write(json.dumps({"ok": True, "platform": platform, "session": session}, ensure_ascii=False))
    sys.stdout.write("\n")


def cmd_cookie_export(platform: str, session: str) -> None:
    camoufox_export_cookies(platform, session)


def cmd_cookie_import(platform: str, session: str) -> None:
    camoufox_import_cookies(platform, session)


def cmd_session_cleanup(platform: str, session: str) -> None:
    camoufox_close(session)


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="login_manager",
        description="Platform login state management via camoufox-cli (Phase 4.5.2)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Probe session validity (exit 0/2)")
    p_check.add_argument("platform")
    p_check.set_defaults(func=lambda a: cmd_check(a.platform))

    p_read = sub.add_parser("read", help="Print stored session JSON")
    p_read.add_argument("platform")
    p_read.set_defaults(func=lambda a: cmd_read(a.platform))

    p_write = sub.add_parser("write", help="Save session from stdin JSON")
    p_write.add_argument("platform")
    p_write.set_defaults(func=lambda a: cmd_write(a.platform))

    p_sa = sub.add_parser("status-all", help="Probe all stored sessions")
    p_sa.set_defaults(func=lambda a: cmd_status_all())

    p_qrh = sub.add_parser("qr-headless", help="Launch headless session + snapshot QR")
    p_qrh.add_argument("platform")
    p_qrh.add_argument("url", nargs="?", default=None)
    p_qrh.set_defaults(func=lambda a: cmd_qr_headless(a.platform, a.url))

    p_qrc = sub.add_parser("qr-confirm", help="Poll QR scan success + export cookies")
    p_qrc.add_argument("platform")
    p_qrc.add_argument("--session", required=True)
    p_qrc.add_argument("--timeout", type=int, default=QR_SCAN_TIMEOUT_S)
    p_qrc.set_defaults(func=lambda a: cmd_qr_confirm(a.platform, session=a.session, timeout=a.timeout))

    p_ce = sub.add_parser("cookie-export", help="Export camoufox session cookies to central JSON")
    p_ce.add_argument("platform")
    p_ce.add_argument("session")
    p_ce.set_defaults(func=lambda a: cmd_cookie_export(a.platform, a.session))

    p_ci = sub.add_parser("cookie-import", help="Import central JSON cookies into camoufox session")
    p_ci.add_argument("platform")
    p_ci.add_argument("session")
    p_ci.set_defaults(func=lambda a: cmd_cookie_import(a.platform, a.session))

    p_sc = sub.add_parser("session-cleanup", help="Close a camoufox session")
    p_sc.add_argument("platform")
    p_sc.add_argument("session")
    p_sc.set_defaults(func=lambda a: cmd_session_cleanup(a.platform, a.session))

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
