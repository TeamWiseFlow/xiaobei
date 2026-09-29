#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wx_mp_hunter.py — 微信公众号文章抓取 CLI。

两条独立工作流：

1. **单篇 fetch**：用微信客户端 UA（``MicroMessenger``）+ 完整浏览器 headers
   + ``httpx follow_redirects`` 直访 ``mp.weixin.qq.com`` 文章长链。腾讯风控对该
   UA 直接放行（302 → ``&nwr_flag=1#wechat_redirect`` → 正文），无需 cookie /
   captcha / 登录态。

2. **账号 posts-list**：从本机微信客户端容器的 biz 消息库（SQLCipher 加密 +
   Zstd 压缩）扫 49 号文章消息，支持过去 N 小时或最新 N 条，按账号白名单
   过滤、按 url 去重。
   仅能拿到容器客户端已登录微信账号**已关注**的公众号推送。

3. **专题页流程（mp/homepage）**：camoufox-cli 无头浏览器打开专题页，
   完整滚动 + 分类 tab 采集 ``mp.weixin.qq.com/s`` 文章链接，再逐篇走 fetch。
   仅此流程需要 ``wx_mp`` session 登录态（在 camoufox profile 里就位即可，
   失效时走 login + login-confirm 重登）。

环境变量（仅 posts-list 用到）：
    WX_BIZ_CONTAINER        微信客户端容器名（默认 ``mimicwx-linux``）
    WX_BIZ_USER_DIR         容器内微信用户数据根目录
    WX_BIZ_KEYS_FILE        容器内密钥文件路径
    WX_BIZ_DB_REL           biz 消息库在用户数据根目录下的相对路径
                            （默认 ``db_storage/message/biz_message_0.db``）
    WX_BIZ_DB_KEY_NAME      密钥文件里 biz 库对应的 key 名
                            （默认 ``message/biz_message_0.db``）

退出码：
    0  成功
    1  通用错误（参数错 / 找不到 row / 网络错）
    2  session 失效（仅 login/login-confirm/专题页流程可能返回）
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional

try:
    import httpx
except ImportError:
    sys.stderr.write(
        "error: httpx not installed. Run `pip install httpx zstandard sqlcipher3`\n"
    )
    sys.exit(1)


# ── 常量 ─────────────────────────────────────────────────────────────────────

MP_BASE = "https://mp.weixin.qq.com"

# camoufox-cli 二进制（homepage 专题页流程用临时 session，不绑持久化 profile）
CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
# homepage 流程用的临时 session 名（一次性，不持久化登录态）
HOMEPAGE_SESSION = "wx_mp_hunter_homepage"

# ── biz 消息库扫库常量 ───────────────────────────────────────────────────────
# 依赖本机微信客户端容器（MimicWX-Linux 镜像）。容器名可 override，
# 其余路径全部硬编码/自动探测（复刻 MimicWX-Linux 的 find_db_dir 逻辑）。
WX_BIZ_CONTAINER = os.environ.get("WX_BIZ_CONTAINER", "mimicwx-linux")

# 硬编码常量（由 MimicWX-Linux 镜像布局和微信客户端数据库约定决定，不让用户配置）
WX_BIZ_KEYS_FILE = "/home/wechat/.xwechat/wechat_keys.json"
WX_BIZ_KEYS_FILE_COMPAT = "/tmp/wechat_keys.json"
WX_BIZ_DB_REL = "db_storage/message/biz_message_0.db"
WX_BIZ_DB_KEY_NAME = "message/biz_message_0.db"

# MimicWX-Linux 用户数据目录的搜索根（由 Dockerfile 里 `useradd -m wechat` 决定）
WX_BIZ_XWECHAT_ROOT = "/home/wechat/Documents/xwechat_files"
# 旧路径兜底
WX_BIZ_OLD_DATA_ROOT = "/home/wechat/.local/share/weixin/data"

# ── 单篇 fetch：微信客户端 UA 直访 ──────────────────────────────────────────

# 微信安卓内置 webview UA（实测可绕过 captcha）
WX_MICROMESSENGER_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-G991B Build/TP1A.220624.014; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/120.0.6099.230 Mobile Safari/537.36 "
    "MMWEBID/1234 MicroMessenger/8.0.40.2420(0x2800283F) WeChat/arm64 Weixin"
)

# 全局并发信号量：限制同时对 mp.weixin.qq.com 发起的请求数
_WX_FETCH_SEMAPHORE = asyncio.Semaphore(12)
# 相邻两次请求的最小间隔（秒）
_WX_FETCH_INTERVAL = 1.0
_WX_FETCH_LAST_START = 0.0
_WX_FETCH_THROTTLE_LOCK = asyncio.Lock()


# ── 工具函数 ─────────────────────────────────────────────────────────────────

def print_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def err_exit(msg: str, code: int = 1) -> None:
    print_json({"ok": False, "error": msg})
    sys.exit(code)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("必须为正整数")
    return parsed


# ── biz 消息库扫库 ───────────────────────────────────────────────────────────

def _require_biz_container_env() -> str:
    """posts-list 才检查容器环境是否就位；普通 fetch 不检查。

    返回自动探测到的 user_dir（wxid 那层目录，即 db_storage 的父目录）。
    失败直接 err_exit 报清晰错误。

    探测逻辑复刻 MimicWX-Linux 的 ``find_db_dir``：
    - 主搜索根：``/home/wechat/Documents/xwechat_files/*``（遍历所有子目录，不限定 ``wxid_*``）
    - 旧路径兜底：``/home/wechat/.local/share/weixin/data/db_storage``
    - 多账号场景取 ``db_storage/message`` mtime 最新的那个（最近活跃账号）
    """
    # 1. 校验容器可达
    try:
        _docker_exec(["true"], timeout=10.0)
    except RuntimeError:
        err_exit(
            f"容器 {WX_BIZ_CONTAINER} 不可达：posts-list 依赖本机运行的微信客户端容器，"
            f"请确认容器已启动（docker ps | grep {WX_BIZ_CONTAINER}）"
        )

    # 2. 自动探测 user_dir（复刻 MimicWX-Linux find_db_dir）
    probe_script = (
        "import os, time\n"
        "candidates = []\n"
        f"root = {WX_BIZ_XWECHAT_ROOT!r}\n"
        "if os.path.isdir(root):\n"
        "    for entry in os.listdir(root):\n"
        "        db_storage = os.path.join(root, entry, 'db_storage')\n"
        "        if os.path.isdir(db_storage):\n"
        "            msg_dir = os.path.join(db_storage, 'message')\n"
        "            try:\n"
        "                mtime = os.path.getmtime(msg_dir)\n"
        "            except OSError:\n"
        "                mtime = 0\n"
        "            candidates.append((db_storage, mtime))\n"
        f"old = {WX_BIZ_OLD_DATA_ROOT!r}\n"
        "if os.path.isdir(old):\n"
        "    db_storage = os.path.join(old, 'db_storage')\n"
        "    if os.path.isdir(db_storage):\n"
        "        try:\n"
        "            mtime = os.path.getmtime(os.path.join(db_storage, 'message'))\n"
        "        except OSError:\n"
        "            mtime = 0\n"
        "        candidates.append((db_storage, mtime))\n"
        "if not candidates:\n"
        "    raise SystemExit('no db_storage found')\n"
        "candidates.sort(key=lambda x: x[1], reverse=True)\n"
        "print(os.path.dirname(candidates[0][0]))\n"
    )
    try:
        out = _docker_exec(["python3", "-c", probe_script], timeout=15.0)
        user_dir = out.decode("utf-8", errors="replace").strip()
        if not user_dir:
            raise RuntimeError("probe returned empty user_dir")
        return user_dir
    except RuntimeError as e:
        err_exit(
            f"自动探测用户数据目录失败：{e}\n"
            f"请确认容器 {WX_BIZ_CONTAINER} 内已登录微信账号、"
            f"且 {WX_BIZ_XWECHAT_ROOT} 下存在带 db_storage 的账号目录"
        )


def _docker_exec(args: list[str], timeout: float = 30.0) -> bytes:
    cmd = ["docker", "exec", WX_BIZ_CONTAINER] + args
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker exec failed (rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout


def _docker_cp(src: str, dst: str, timeout: float = 60.0) -> None:
    cmd = ["docker", "cp", f"{WX_BIZ_CONTAINER}:{src}", dst]
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker cp failed (rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )


def _read_biz_db_key() -> str:
    """从容器内硬编码密钥文件读取 biz 消息库的密钥（hex 字符串）。

    主路径 ``/home/wechat/.xwechat/wechat_keys.json``，失败再试
    ``/tmp/wechat_keys.json``。从 JSON 里取 ``message/biz_message_0.db``
    对应的密钥；若 key 不存在，fallback 扫所有 key 找 basename 匹配
    ``biz_message_0.db`` 的（复刻 MimicWX lookup_db_key 的 fallback 逻辑）。
    """
    for keys_path in (WX_BIZ_KEYS_FILE, WX_BIZ_KEYS_FILE_COMPAT):
        try:
            raw = _docker_exec(["cat", keys_path])
            keys = json.loads(raw)
            # 1. 精确匹配
            key = keys.get(WX_BIZ_DB_KEY_NAME)
            if key:
                return key
            # 2. basename fallback
            for k, v in keys.items():
                if k.endswith("biz_message_0.db"):
                    return v
        except RuntimeError:
            continue
    raise RuntimeError(
        f"无法从容器 {WX_BIZ_CONTAINER} 读取 biz 消息库密钥："
        f"主路径 {WX_BIZ_KEYS_FILE} 和兜底路径 {WX_BIZ_KEYS_FILE_COMPAT} 都失败。"
        f"请确认容器内微信已登录、extract_key.py 已产出密钥文件。"
    )


def _copy_biz_db(tmp_dir: Path, user_dir: str) -> Path:
    """从容器拷出 biz 消息库（含 -wal / -shm），返回拷贝后的 .db 路径。

    user_dir 由 ``_require_biz_container_env`` 自动探测得到（wxid 那层目录）。
    """
    container_db = os.path.join(user_dir, WX_BIZ_DB_REL)
    db_name = Path(WX_BIZ_DB_REL).name
    for suffix in ("", "-wal", "-shm"):
        src = f"{container_db}{suffix}"
        try:
            _docker_cp(src, str(tmp_dir))
        except RuntimeError:
            # -wal / -shm 可能不存在，忽略错误
            if suffix:
                continue
            raise
    return tmp_dir / db_name


def _open_sqlcipher(db_path: Path, key_hex: str) -> sqlite3.Connection:
    """用 sqlcipher3 打开加密的 biz 消息库。cipher_compatibility = 4。"""
    try:
        import sqlcipher3  # type: ignore
    except ImportError:
        err_exit(
            "sqlcipher3 未安装。请运行 `pip install sqlcipher3`，"
            "系统需有 libsqlcipher-dev"
        )

    conn = sqlcipher3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(f"PRAGMA key = \"x'{key_hex}'\";")
    cur.execute("PRAGMA cipher_compatibility = 4;")
    try:
        cur.execute("SELECT count(*) FROM sqlite_master;")
        cur.fetchone()
    except sqlcipher3.DatabaseError as e:
        conn.close()
        raise RuntimeError(f"sqlcipher open failed: {e}") from e
    return conn


def _zstd_decompress(data: bytes) -> bytes:
    """Zstd 解压（魔数 ``\\x28\\xb5\\x2f\\xfd``）。"""
    if not data:
        return b""
    try:
        import zstandard  # type: ignore
    except ImportError:
        err_exit("zstandard 未安装。请运行 `pip install zstandard`")
    dctx = zstandard.ZstdDecompressor()
    return dctx.decompress(data)


# 49 号文章消息 XML 字段提取正则
_RE_TITLE = re.compile(r"<title><!\[CDATA\[(.*?)\]\]></title>", re.DOTALL)
_RE_URL = re.compile(r"<url><!\[CDATA\[(.*?)\]\]></url>", re.DOTALL)
_RE_AUTHOR = re.compile(r"<name><!\[CDATA\[(.*?)\]\]></name>", re.DOTALL)
_RE_PUB_TIME = re.compile(r"<pub_time>(\d+)</pub_time>", re.DOTALL)
_RE_COVER = re.compile(r"<cover><!\[CDATA\[(.*?)\]\]></cover>", re.DOTALL)


def _parse_49_message(content_bytes: bytes) -> Optional[dict[str, Any]]:
    """解析 49 号文章消息的 message_content（Zstd 压缩的 appmsg XML）。

    返回 dict: ``{title, url, author, publish_time(YYYY-MM-DD), cover}`` 或 None。
    """
    if not content_bytes:
        return None
    if not content_bytes.startswith(b"\x28\xb5\x2f\xfd"):
        return None
    try:
        xml = _zstd_decompress(content_bytes).decode("utf-8", errors="replace")
    except Exception:
        return None

    title_m = _RE_TITLE.search(xml)
    url_m = _RE_URL.search(xml)
    if not title_m or not url_m:
        return None
    title = title_m.group(1).strip()
    url = url_m.group(1).strip()
    if not title or not url:
        return None

    author_m = _RE_AUTHOR.search(xml)
    author = author_m.group(1).strip() if author_m else ""

    pub_m = _RE_PUB_TIME.search(xml)
    publish_time = ""
    if pub_m:
        try:
            ts = int(pub_m.group(1))
            publish_time = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            publish_time = ""

    cover_m = _RE_COVER.search(xml)
    cover = cover_m.group(1).strip() if cover_m else ""

    return {
        "title": title,
        "url": url,
        "author": author,
        "publish_time": publish_time,
        "cover": cover,
    }


def _scan_biz_messages(
    limit_hours: Optional[int],
    account_whitelist: Optional[set[str]] = None,
    recent_limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """扫描 biz 消息库，返回时间窗口或最近 N 条 49 号文章消息。

    Args:
        limit_hours: 时间窗口（小时）；recent 模式传 None
        account_whitelist: 公众号白名单（公众号名，即 author）。
            若为 None 则返回全部；若非空则只保留 author 在白名单内的消息。
        recent_limit: recent 模式保留的最新消息条数；非 recent 模式传 None

    Returns:
        List[Dict]，每个 dict 含 title/url/author/publish_time/cover。
        按消息接收时间倒序，已按 url 去重。
    """
    cutoff_ts = 0 if limit_hours is None else time.time() - limit_hours * 3600
    results: list[dict[str, Any]] = []
    url_indexes: dict[str, int] = {}

    # 自动探测 user_dir（校验容器可达 + 复刻 MimicWX find_db_dir）
    user_dir = _require_biz_container_env()

    tmp_dir = Path(tempfile.mkdtemp(prefix="bizscan_"))
    try:
        key_hex = _read_biz_db_key()
        db_path = _copy_biz_db(tmp_dir, user_dir)
        conn = _open_sqlcipher(db_path, key_hex)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';"
            )
            table_names = [row[0] for row in cur.fetchall()]

            for tbl in table_names:
                sql = (
                    f'SELECT local_id, create_time, message_content FROM "{tbl}" '
                    f"WHERE (local_type & 0xFFFF) = 49 AND create_time > ? "
                    f"ORDER BY create_time DESC;"
                )
                try:
                    cur.execute(sql, (cutoff_ts,))
                except sqlite3.DatabaseError:
                    continue

                for _local_id, _create_time, content_bytes in cur.fetchall():
                    if not isinstance(content_bytes, (bytes, bytearray, memoryview)):
                        continue
                    msg = _parse_49_message(bytes(content_bytes))
                    if not msg:
                        continue
                    if account_whitelist and msg["author"] not in account_whitelist:
                        continue
                    msg["_message_time"] = int(_create_time)
                    existing_index = url_indexes.get(msg["url"])
                    if existing_index is None:
                        url_indexes[msg["url"]] = len(results)
                        results.append(msg)
                    elif msg["_message_time"] > results[existing_index]["_message_time"]:
                        results[existing_index] = msg
        finally:
            conn.close()
    except Exception as e:
        sys.stderr.write(f"warning: scan biz db failed: {e}\n")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return _sort_and_limit_recent_messages(results, recent_limit)


def _sort_and_limit_recent_messages(
    messages: list[dict[str, Any]],
    recent_limit: Optional[int],
) -> list[dict[str, Any]]:
    messages.sort(key=lambda msg: msg["_message_time"], reverse=True)
    if recent_limit is not None:
        messages = messages[:recent_limit]
    for msg in messages:
        msg.pop("_message_time", None)
    return messages


# ── 单篇 fetch：MicroMessenger UA 直访 ──────────────────────────────────────

async def fetch_wx_article_html(
    url: str,
    *,
    user_agent: Optional[str] = None,
    proxy: Optional[str] = None,
    timeout: float = 30.0,
) -> tuple[Optional[str], Optional[httpx.Response]]:
    """用微信客户端 UA 直访公众号文章，返回 (html, response)。

    UA 伪装为微信客户端内置 webview，腾讯风控对该 UA 直接放行（302 到
    ``&nwr_flag=1#wechat_redirect``，follow 后即正文），无需 cookie / captcha。

    注意：必须传完整浏览器 headers。实测只传 UA 时 httpx 仍带默认
    ``Accept``/``Accept-Encoding`` 指纹，被腾讯识别为非浏览器流量而风控；
    传完整 headers 后稳定命中（3 MB+ 正文，含 ``var msg_title`` / ``js_content``）。

    Args:
        url: mp.weixin.qq.com 文章 URL（长链或短链均可）
        user_agent: 自定义 UA；默认 :data:`WX_MICROMESSENGER_UA`
        proxy: httpx 代理字符串（可选）
        timeout: 请求超时秒数

    Returns:
        ``(html, response)``。成功时 ``html`` 为正文、``response`` 为最终响应；
        失败时 ``(None, response_or_None)``。
    """
    ua = user_agent or WX_MICROMESSENGER_UA
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    async with httpx.AsyncClient(
        proxy=proxy, follow_redirects=True, timeout=timeout, headers=headers
    ) as client:
        async with _WX_FETCH_SEMAPHORE:
            global _WX_FETCH_LAST_START
            async with _WX_FETCH_THROTTLE_LOCK:
                now = time.monotonic()
                wait = _WX_FETCH_INTERVAL - (now - _WX_FETCH_LAST_START)
                _WX_FETCH_LAST_START = now + (wait if wait > 0 else 0)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                resp = await client.get(url)
            except httpx.HTTPError as e:
                sys.stderr.write(f"warning: fetch failed {url[:80]}: {e}\n")
                return None, None

    final_url = str(resp.url)
    body_head = resp.text[:512] if resp.text else ""
    if (
        "wappoc_appmsgcaptcha" in final_url
        or "环境异常" in body_head
        or resp.status_code != 200
    ):
        sys.stderr.write(
            f"warning: UA 直访仍被风控 status={resp.status_code} final={final_url[:80]}\n"
        )
        return None, resp

    return resp.text, resp


# ── HTML → Markdown 转换 ────────────────────────────────────────────────────

# 简易 HTML → Markdown 转换，依赖 stdlib html.parser（无 cheerio / 无 npm 依赖）

import html as html_module


def _normalize_img_url(raw: str) -> str:
    """规范化图片 URL：// 开头补 https:，已是 http 开头保持，其他原样。"""
    if not raw:
        return ""
    return raw if raw.startswith("http") else (
        f"https:{raw}" if raw.startswith("//") else raw
    )


def _extract_images_from_html(html_fragment: str) -> list[str]:
    """从 HTML 片段提取所有图片 URL（data-src 优先于 src），去重。"""
    images: list[str] = []
    for img_m in re.finditer(r'<img[^>]*>', html_fragment):
        img_tag = img_m.group(0)
        ds = re.search(r'data-src="([^"]+)"', img_tag)
        src = re.search(r'src="([^"]+)"', img_tag)
        raw = (ds.group(1) if ds else "") or (src.group(1) if src else "")
        if not raw:
            continue
        url = _normalize_img_url(raw)
        if url and url not in images:
            images.append(url)
    return images


def _html_to_markdown(html_fragment: str) -> str:
    """简易 HTML → Markdown 转换（段落 / 图片 / 加粗 / 链接 / 列表）。

    用 stdlib re + html.unescape，不依赖 cheerio / BeautifulSoup / html2text。
    图片以内联 ``![](url)`` 放在原文位置，不做序号化。
    """
    md = html_fragment
    # 移除 script/style
    md = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", md)
    md = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", md)
    # 图片：data-src 优先 → src
    def _img_repl(m: re.Match) -> str:
        img_tag = m.group(0)
        ds = re.search(r'data-src="([^"]+)"', img_tag)
        src = re.search(r'src="([^"]+)"', img_tag)
        raw = (ds.group(1) if ds else "") or (src.group(1) if src else "")
        if not raw:
            return ""
        return f"\n\n![]({_normalize_img_url(raw)})\n\n"

    md = re.sub(r"<img[^>]*>", _img_repl, md)
    # 加粗
    md = re.sub(r"<(?:strong|b)>([\s\S]*?)</(?:strong|b)>", r"**\1**", md)
    # 链接
    md = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)</a>',
        r"[\2](\1)",
        md,
    )
    # 段落 / 换行
    md = re.sub(r"<br\s*/?>", "\n", md)
    md = re.sub(r"</p>", "\n\n", md)
    md = re.sub(r"</section>", "\n", md)
    # 列表
    md = re.sub(r"<li[^>]*>", "\n- ", md)
    # 去剩余标签
    md = re.sub(r"<[^>]+>", "", md)
    # 解码实体
    md = html_module.unescape(md)
    # 压缩多余空白
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md


def _html_to_text(html_fragment: str) -> str:
    """去 HTML 标签 + 解码实体，返回纯文本。"""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html_fragment)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_tags(html_fragment: str) -> str:
    """去所有 HTML 标签，保留纯文本（不解码实体，用于拿标签内 raw text）。"""
    return re.sub(r"<[^>]+>", "", html_fragment)


class _MetaTagParser(HTMLParser):
    """读取 meta property/name 与 content，兼容属性顺序和引号变化。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "meta":
            return
        values = dict(attrs)
        key = (values.get("property") or values.get("name") or "").lower()
        content = (values.get("content") or "").strip()
        if key and content and key not in self.values:
            self.values[key] = content


def _extract_meta_fields(html: str) -> dict[str, str]:
    parser = _MetaTagParser()
    parser.feed(html)
    return parser.values


def _extract_cover_url(html: str, meta: dict[str, str]) -> str:
    """提取文章分享封面 URL；og:image 通常是分享卡片封面。"""
    candidates = [meta.get("og:image", ""), meta.get("twitter:image", "")]
    msg_cdn_url = re.search(
        r'var\s+msg_cdn_url\s*=\s*["\']([^"\']+)["\']',
        html,
    )
    if msg_cdn_url:
        candidates.append(msg_cdn_url.group(1))
    for candidate in candidates:
        normalized = _normalize_img_url(html_module.unescape(candidate).strip())
        if normalized:
            return normalized
    return ""


def _extract_article_fields(html: str) -> dict[str, Any]:
    """从文章 HTML 提取 title / author / publish_time / content_text /
    content_markdown / images / error_msg。

    全盘采用多类型识别方案，应对所有公众号类型：
    - 正常图文页（<h1> + js_content）
    - 图片分享页（id="js_image_desc"）
    - 视频分享页（id="js_common_share_desc"）
    - metadata description 链接列表（兜底）
    - 分享源页（id="js_share_source" data-url）
    - 新类型文本页（id="js_text_desc"）
    - 已删除页

    转 Markdown 用 stdlib re + html.unescape（不依赖 html2text / BeautifulSoup）。
    图片以内联 ``![](url)`` 放在原文位置，不做序号化。

    Returns:
        dict 含 title / author / publish_time / content_text / content_markdown /
        images / error_msg。error_msg 非空时表示识别到异常类型，content 可能为空。
    """
    result: dict[str, Any] = {
        "title": "",
        "author": "",
        "publish_time": "",
        "content_text": "",
        "content_markdown": "",
        "images": [],
        "cover_url": "",
        "error_msg": "",
    }
    # 参考 linxiaozhu/2026 d854e5b：分享卡片元数据优先，DOM 仅在缺值时回填。
    meta = _extract_meta_fields(html)
    result["title"] = meta.get("og:title", "")
    # 微信公众号作者应该用公众号名称
    result["author"] = ""
    result["cover_url"] = _extract_cover_url(html, meta)

    # ── publish_time: 多路兜底（已在上一轮实现，保留）──────────────────────
    # 1. <em id="publish_time">xxxx年xx月xx日</em>（PC 端常见）
    m = re.search(r'<[^>]*id="publish_time"[^>]*>([\s\S]*?)</[^>]+>', html)
    if m:
        pt_text = _strip_tags(m.group(1)).strip()
        date_m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', pt_text)
        result["publish_time"] = date_m.group(1) if date_m else pt_text
    # 2. var ct / var publish_time（Unix 时间戳，10 位）
    if not result["publish_time"]:
        for var_pat in (r'var\s+ct\s*=\s*["\']?(\d{10})', r'var\s+publish_time\s*=\s*["\']?(\d{10})'):
            m_ct = re.search(var_pat, html)
            if m_ct:
                try:
                    result["publish_time"] = datetime.fromtimestamp(int(m_ct.group(1))).strftime("%Y-%m-%d")
                    break
                except (ValueError, OSError):
                    pass
    # 3. og:article:published_time / article:published_time meta
    if not result["publish_time"]:
        for meta_prop in ('og:article:published_time', 'article:published_time'):
            if meta.get(meta_prop):
                result["publish_time"] = meta[meta_prop][:10]
                break
    # 4. 正则扫第一个"xxxx年xx月xx日"
    if not result["publish_time"]:
        m_date = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', html)
        if m_date:
            result["publish_time"] = m_date.group(1)

    # ── 多类型识别：按 <h1> 是否存在分两大类 ──────────────────────────────

    h1_m = re.search(r'<h1[^>]*>([\s\S]*?)</h1>', html)
    if h1_m:
        # ── B1. 正常图文页（有 <h1>）──────────────────────────────────────
        if not result["title"]:
            result["title"] = _strip_tags(h1_m.group(1)).strip()

        # author 多路兜底
        # 1. <a id="js_name">公众号名</a>
        if not result["author"]:
            m = re.search(r'<a[^>]*id="js_name"[^>]*>([\s\S]*?)</a>', html)
            if m:
                result["author"] = _strip_tags(m.group(1)).strip()
        # 2. var nickname = "..."
        if not result["author"]:
            m = re.search(r'var\s+nickname\s*=\s*[\'"](.+?)[\'"]', html)
            if m:
                result["author"] = html_module.unescape(m.group(1)).strip()
        # 3. <a class="profile_nickname">...</a>
        if not result["author"]:
            m = re.search(r'<a[^>]*class="[^"]*profile_nickname[^"]*"[^>]*>([\s\S]*?)</a>', html)
            if m:
                result["author"] = _strip_tags(m.group(1)).strip()
        # 4. 找 h1 的父 div，第一个有内容的子 div 里的 <strong>（图文页 author 主路径）
        if not result["author"]:
            # h1 在某个 div 容器里，同 div 下第一个有内容的子 div 里的 <strong>
            # 用正则近似：拿 h1 所在的父 div 块，扫其子 div
            parent_m = re.search(
                r'(<div[^>]*>(?:(?!<div[^>]*>).)*?<h1[^>]*>[\s\S]*?</h1>[\s\S]*?</div>)',
                html,
            )
            if parent_m:
                parent_html = parent_m.group(1)
                # 找父 div 下所有直接子 div（不递归）
                sub_divs = re.findall(r'<div[^>]*>(?:(?!<div[^>]*>).)*?</div>', parent_html)
                for sub in sub_divs:
                    if len(sub) > 20:  # 有内容的子 div
                        strong_m = re.search(r'<strong[^>]*>([\s\S]*?)</strong>', sub)
                        if strong_m:
                            result["author"] = _strip_tags(strong_m.group(1)).strip()
                            break
        # 5. id="js_wx_follow_nickname" / class="wx_follow_nickname"（新版分享页兜底）
        if not result["author"]:
            m = re.search(r'<[^>]*id="js_wx_follow_nickname"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m:
                result["author"] = _strip_tags(m.group(1)).strip()
        if not result["author"]:
            m = re.search(r'<[^>]*class="[^"]*wx_follow_nickname[^"]*"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m:
                result["author"] = _strip_tags(m.group(1)).strip()

        # content 多路识别
        # 1. 图片分享页（id="js_image_desc"）—— content 直接拿 desc 文本
        m = re.search(r'<[^>]*id="js_image_desc"[^>]*>([\s\S]*?)</[^>]+>', html)
        if m:
            result["content_text"] = _strip_tags(m.group(1)).strip()
            result["content_markdown"] = result["content_text"]
            return result

        # 2. 视频分享页（id="js_common_share_desc"）—— content 直接拿 desc 文本
        m = re.search(r'<[^>]*id="js_common_share_desc"[^>]*>([\s\S]*?)</[^>]+>', html)
        if m:
            result["content_text"] = _strip_tags(m.group(1)).strip()
            result["content_markdown"] = result["content_text"]
            return result

        # 3. 正常图文页（id="js_content"）—— 转 Markdown
        m = re.search(
            r'<div[^>]*id="js_content"[^>]*>([\s\S]*?)</div>\s*(?:<div|<span|</)',
            html,
        )
        if not m:
            m = re.search(r'<div[^>]*id="js_content"[^>]*>([\s\S]*?)</div>', html)
        if m:
            content_html = m.group(1)
            result["images"] = _extract_images_from_html(content_html)
            result["content_text"] = _html_to_text(content_html)
            result["content_markdown"] = _html_to_markdown(content_html)
            return result

        # 4. metadata description 链接列表（兜底，无法识别页面类型时）
        #    正则扫 href + 描述对，输出 [description](url)
        #    微信 metadata description 里链接是转义形态 \x26quot;url\x26quot; ...\x26gt;desc\x26lt;/a
        des_m = re.search(r'name="description"\s+content="([^"]+)"', html)
        if des_m:
            des = html_module.unescape(des_m.group(1))
            pattern = r'href=\\x26quot;(.*?)\\x26quot;.*?\\x26gt;(.*?)\\x26lt;/a'
            matches = re.findall(pattern, des)
            if matches:
                md_links = ""
                for url, description in matches:
                    cleaned_url = _clean_weixin_url(url)
                    md_links += f'[{description.strip()}]({cleaned_url})\n'
                result["content_markdown"] = md_links
                result["content_text"] = _strip_tags(md_links).strip()
                return result

        # 5. 都没命中 —— 新类型，报错
        result["error_msg"] = "new_type_article, type 6 —— cannot identify content type with <h1>"
        return result

    # ── B2. 无 <h1>（已删除/分享页/新类型）──────────────────────────────
    # 1. js_share_source 分享源（<span id="js_share_source" data-url="...">）
    m = re.search(r'<span[^>]*id="js_share_source"[^>]*data-url="([^"]+)"[^>]*>', html)
    if m:
        data_url = m.group(1).replace("http://", "https://", 1)
        if not data_url or not data_url.startswith("https://mp.weixin.qq.com"):
            result["error_msg"] = "new_type_article, type 4"
            return result
        # 拿 js_content 里的描述文本
        m2 = re.search(r'<div[^>]*id="js_content"[^>]*>([\s\S]*?)</div>', html)
        if not m2:
            result["error_msg"] = "new_type_article, type 3"
            return result
        des = _strip_tags(m2.group(1)).strip()
        result["content_markdown"] = f'[{des}]({data_url})'
        result["content_text"] = des
        return result

    # 2. js_text_desc 新类型（<p id="js_text_desc">）—— author 多路兜底 + 转 Markdown
    m = re.search(r'<p[^>]*id="js_text_desc"[^>]*>([\s\S]*?)</p>', html)
    if m:
        # author: js_name / js_wx_follow_nickname / wx_follow_nickname
        if not result["author"]:
            m2 = re.search(r'<a[^>]*id="js_name"[^>]*>([\s\S]*?)</a>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()
        if not result["author"]:
            m2 = re.search(r'<[^>]*id="js_wx_follow_nickname"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()
        if not result["author"]:
            m2 = re.search(r'<[^>]*class="[^"]*wx_follow_nickname[^"]*"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()
        if not result["author"]:
            result["error_msg"] = "2025-09-26 found new type cannot find author info"
            return result
        content_html = m.group(1)
        result["images"] = _extract_images_from_html(content_html)
        result["content_text"] = _html_to_text(content_html)
        result["content_markdown"] = _html_to_markdown(content_html)
        return result

    # 3. og:* meta 提取路（新版分享页：无 h1、无 js_share_source、无 js_text_desc，
    #    author 在 JS getElementById('js_wx_follow_nickname_*') 引用的 DOM id 里，
    #    真实文本 JS 动态填；title / description 在 og:title / og:description meta 里）
    og_title = meta.get("og:title", "")
    og_desc = meta.get("og:description", "")
    if og_title or og_desc:
        # title: og:title meta
        if og_title:
            result["title"] = og_title
        # author: og:article:author meta（常为空）→ js_name DOM → wx_follow_nickname DOM
        if not result["author"]:
            m2 = re.search(r'<a[^>]*id="js_name"[^>]*>([\s\S]*?)</a>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()
        # js_wx_follow_nickname 的真实 DOM id 可能带后缀（_large_font / _small_font / _top）
        # 用更宽的正则扫所有 id 以 js_wx_follow_nickname 开头的元素
        if not result["author"]:
            m2 = re.search(r'<[^>]*id="js_wx_follow_nickname[^"]*"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()
        if not result["author"]:
            m2 = re.search(r'<[^>]*class="[^"]*wx_follow_nickname[^"]*"[^>]*>([\s\S]*?)</[^>]+>', html)
            if m2:
                result["author"] = _strip_tags(m2.group(1)).strip()

        # content: og:description meta（正文摘要，含 \x0a 转义换行）→ 解码后直接当 markdown
        if og_desc:
            desc = og_desc
            # og:description 里 \x0a 是换行转义，统一成 \n
            desc = desc.replace("\\x0a", "\n").replace("\\x0A", "\n")
            result["content_text"] = desc.strip()
            result["content_markdown"] = desc.strip()
            # og:description 里的图片 URL 不在正文里（是摘要），images 从 og:image meta 拿
            if meta.get("og:image"):
                img_url = _normalize_img_url(meta["og:image"])
                if img_url:
                    result["images"] = [img_url]
            return result
        # 有 og:title 但没 og:description —— 至少 title 拿到了，继续走兜底
        if og_title:
            return result

    # 4. 都没命中 —— 已删除页 或 无法识别的新类型
    # 先试拿 author（js_name / js_wx_follow_nickname / wx_follow_nickname）判断是不是删除页
    if not result["author"]:
        m = re.search(r'<a[^>]*id="js_name"[^>]*>([\s\S]*?)</a>', html)
        if m:
            result["author"] = _strip_tags(m.group(1)).strip()
    if not result["author"]:
        m = re.search(r'<[^>]*id="js_wx_follow_nickname"[^>]*>([\s\S]*?)</[^>]+>', html)
        if m:
            result["author"] = _strip_tags(m.group(1)).strip()
    if not result["author"]:
        m = re.search(r'<[^>]*class="[^"]*wx_follow_nickname[^"]*"[^>]*>([\s\S]*?)</[^>]+>', html)
        if m:
            result["author"] = _strip_tags(m.group(1)).strip()

    if result["author"]:
        # 有 author 但没 content —— 已删除页
        result["error_msg"] = "it's a deleted page"
    else:
        # 连 author 都没有 —— 完全无法识别
        result["error_msg"] = "new_type_article, type 5 —— cannot identify page type (no <h1>, no author, no content)"

    return result


def _clean_weixin_url(url: str) -> str:
    """清理微信 URL，将转义字符替换为正常字符（metadata description 里的链接是转义形态）。"""
    replacements = {
        '\\x26amp;amp;': '&',
        '\\x26amp;': '&',
        '\\x26quot': '',
        '\\x26': '&',
    }
    for old, new in replacements.items():
        url = url.replace(old, new)
    return url


# ── 图片本地化 ───────────────────────────────────────────────────────────────

async def _download_image(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    max_bytes: int = 5 * 1024 * 1024,
    destination_subdir: str = "images",
) -> Optional[Path]:
    """下载单张图片到 dest_dir/images/<hash>.<ext>，返回本地路径。"""
    try:
        resp = await client.get(url, timeout=20.0)
        if resp.status_code != 200:
            return None
        data = resp.content
        if len(data) > max_bytes:
            return None
        h = hashlib.sha256(data).hexdigest()[:12]
        # 从 URL 或 content-type 推断扩展名
        ext = "jpg"
        ct = resp.headers.get("content-type", "").lower()
        if "png" in ct:
            ext = "png"
        elif "gif" in ct:
            ext = "gif"
        elif "webp" in ct:
            ext = "webp"
        elif "jpeg" in ct or "jpg" in ct:
            ext = "jpg"
        else:
            url_lower = url.lower().split("?")[0]
            if url_lower.endswith(".png"):
                ext = "png"
            elif url_lower.endswith(".gif"):
                ext = "gif"
            elif url_lower.endswith(".webp"):
                ext = "webp"
        dest = dest_dir / destination_subdir / f"{h}.{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest
    except Exception:
        return None


async def _download_images(
    images: list[str],
    output_dir: Path,
    concurrency: int = 4,
    max_total: int = 100 * 1024 * 1024,
) -> dict[str, Path]:
    """并发下载图片，返回 url → 本地路径映射。"""
    if not images:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    url_to_path: dict[str, Path] = {}
    total_bytes = 0

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": WX_MICROMESSENGER_UA},
    ) as client:
        async def _one(url: str) -> None:
            nonlocal total_bytes
            async with sem:
                p = await _download_image(client, url, output_dir)
                if p:
                    sz = p.stat().st_size
                    if total_bytes + sz > max_total:
                        p.unlink(missing_ok=True)
                        return
                    total_bytes += sz
                    url_to_path[url] = p

        await asyncio.gather(*[_one(u) for u in images])

    return url_to_path


async def _download_cover_image(cover_url: str, output_dir: Path) -> Optional[Path]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": WX_MICROMESSENGER_UA},
    ) as client:
        return await _download_image(
            client,
            cover_url,
            output_dir,
            destination_subdir="covers",
        )


def _rewrite_md_images(
    markdown: str,
    url_to_path: dict[str, Path],
    output_dir: Path,
) -> str:
    """把 markdown 里的图片 URL 替换为相对 output_dir 的本地路径。"""
    for url, path in url_to_path.items():
        try:
            rel = path.relative_to(output_dir)
        except ValueError:
            rel = path
        markdown = markdown.replace(url, str(rel))
    return markdown


# ── camoufox 辅助（homepage 专题页流程，临时 session，无登录态）─────────────

def _camoufox(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """homepage 流程用临时 session（不绑持久化 profile，不需要登录态）。"""
    cmd = [CAMOUFOX_BIN, "--session", HOMEPAGE_SESSION, "--json"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def _camoufox_eval(expr: str, timeout: int = 60) -> Any:
    r = _camoufox(["eval", expr], timeout=timeout)
    if r.returncode != 0:
        return None
    try:
        env = json.loads(r.stdout)
        data = env.get("data", "")
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data
    except json.JSONDecodeError:
        return None


def _camoufox_url() -> str:
    r = _camoufox(["url"], timeout=15)
    if r.returncode != 0:
        return ""
    try:
        env = json.loads(r.stdout)
        return env.get("data", {}).get("url", "")
    except json.JSONDecodeError:
        return ""


# ── 命令实现 ─────────────────────────────────────────────────────────────────

async def cmd_fetch(args: argparse.Namespace) -> int:
    """单篇抓全文：用微信客户端 UA 直访 mp.weixin.qq.com 文章长链。

    无需登录态、无需 cookie、无需 camoufox。
    """
    url = args.url
    # http 升 https
    if url.startswith("http://mp.weixin.qq.com/"):
        url = "https://" + url[len("http://"):]

    if not (url.startswith("https://mp.weixin.qq.com/") or url.startswith("http://mp.weixin.qq.com/")):
        err_exit(f"not a mp.weixin.qq.com url: {url}")

    html, resp = await fetch_wx_article_html(url)
    if html is None:
        final = str(resp.url)[:100] if resp is not None else "no response"
        status = resp.status_code if resp is not None else "N/A"
        err_exit(
            f"UA 直访被风控，放弃抓取: {url[:80]}\n"
            f"  status={status} final={final}"
        )

    fields = _extract_article_fields(html)
    result: dict[str, Any] = {
        "ok": True,
        "url": url,
        "title": fields["title"],
        "author": fields["author"],
        "publish_time": fields["publish_time"],
        "content_text": fields["content_text"],
        "content_markdown": fields["content_markdown"],
        "images": fields["images"],
        "cover_url": fields["cover_url"],
    }

    # 透传多类型识别的 error_msg（new_type_article type ... / it's a deleted page 等）
    if fields.get("error_msg"):
        result["ok"] = False
        result["error"] = fields["error_msg"]
        print_json(result)
        return 1

    # 图片/封面本地化
    if args.download_images or args.download_cover:
        output_dir = Path(args.output_dir or ".").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    if args.download_images:
        url_to_path = await _download_images(fields["images"], output_dir)
        result["content_markdown"] = _rewrite_md_images(
            result["content_markdown"], url_to_path, output_dir
        )

    if args.download_cover:
        if fields["cover_url"]:
            cover_path = await _download_cover_image(fields["cover_url"], output_dir)
            result["cover_local_path"] = str(cover_path.resolve()) if cover_path else ""
            result["cover_download_ok"] = cover_path is not None
        else:
            result["cover_local_path"] = ""
            result["cover_download_ok"] = False
            result["cover_download_error"] = "cover url not found"

    # 返回原始 HTML（可选）
    if args.html:
        result["content_html"] = html

    print_json(result)
    return 0


def cmd_posts_list(args: argparse.Namespace) -> int:
    """扫 biz 消息库拿时间窗口或最近 N 条文章推送列表。

    仅能拿到容器客户端已登录微信账号**已关注**的公众号推送。扫不到某账号
    时提示用户可能是未关注 / 该账号在此时间窗口内未发布。
    """
    recent_mode = args.recent is not None
    limit_hours = None if recent_mode else args.hours
    accounts_arg = args.accounts

    whitelist: Optional[set[str]] = None
    if accounts_arg:
        whitelist = {a.strip() for a in accounts_arg.split(",") if a.strip()}

    posts = _scan_biz_messages(limit_hours, whitelist, args.recent)

    # 健康度诊断：用户指定但未命中的账号
    missing_accounts: list[str] = []
    if whitelist:
        hit_authors = {p["author"] for p in posts if p.get("author")}
        missing_accounts = sorted(whitelist - hit_authors)

    result: dict[str, Any] = {
        "ok": True,
        "mode": "recent" if recent_mode else "hours",
        "total": len(posts),
        "posts": posts,
    }
    if recent_mode:
        result["recent_limit"] = args.recent
    else:
        result["limit_hours"] = limit_hours
    if missing_accounts:
        result["missing_accounts"] = missing_accounts
        if recent_mode:
            result["hint"] = (
                f"以下账号未出现在最近 {args.recent} 条文章中（共 {len(missing_accounts)} 个）："
                f"{'、'.join(missing_accounts)}。"
                f"可能是本机微信客户端未关注该公众号、近期未收到推送，或其消息被更新推送挤出前 {args.recent} 条。"
            )
        else:
            result["hint"] = (
                f"以下账号过去 {limit_hours}h 未在消息库中扫到文章（共 {len(missing_accounts)} 个）："
                f"{'、'.join(missing_accounts)}。"
                f"可能是该公众号在此时间窗口内未发布，也可能是本机微信客户端未关注该公众号。"
                f"若需稳定接收该公众号推送，请确认本机微信客户端已关注该公众号。"
            )

    print_json(result)
    return 0


# ── 登录流程（camoufox，不导出 cookie/UA/token）─────────────────────────────
#
# 仅专题页流程需要 wx_mp session 登录态。登录就位后登录态在 camoufox profile
# 里就位即可，不再导出 cookie/UA/token 落中央存储。
# 与 wx-mp-engagement 共用同一 wx_mp 持久化 session（同名约定共享 profile）。

# ── 专题页流程（mp/homepage）────────────────────────────────────────────────
#
# 用 camoufox-cli 无头打开 mp/homepage 专题页，完整滚动 + 分类 tab 采集
# mp.weixin.qq.com/s 文章链接，再对单篇链接走 fetch 抓全文。
# 仅此流程需要 wx_mp session 登录态（失效走 login + login-confirm 重登）。

async def cmd_homepage(args: argparse.Namespace) -> int:
    """采集 mp/homepage 专题页的全部文章链接。

    流程：
    1. camoufox 打开专题页（headless session）
    2. 整页滚动到底，直到 scrollHeight 连续多次稳定
    3. 查找分类 tab（常见 class：.jsCate），对每个分类逐个点击 + 滚动 + 提取链接
    4. 合并顶部推荐与各分类结果，按 URL 去重

    输出 JSON：``{ok, total, links: [{title, url}], session: "wx_mp"}``。
    后续对每个链接走 ``fetch <url>`` 抓全文。
    """
    url = args.url
    if "mp/homepage" not in url:
        err_exit(f"not a mp/homepage url: {url}")

    # 打开专题页
    r = _camoufox(["open", url], timeout=60)
    if r.returncode != 0:
        err_exit(f"camoufox open failed: {r.stderr.strip()}")

    # 检查是否跳登录页（homepage 不需要登录态，跳登录页说明 URL 问题）
    current_url = _camoufox_url()
    if "login" in current_url or "scanloginqrcode" in current_url:
        err_exit(f"专题页跳登录页: {current_url[:100]}")

    # 整页滚动到底，直到 scrollHeight 连续多次稳定
    scroll_js = r"""
    (async () => {
      const sleep = (ms) => new Promise(r => setTimeout(r, ms));
      let lastH = 0, stable = 0;
      for (let i = 0; i < 50; i++) {
        window.scrollTo(0, document.documentElement.scrollHeight);
        await sleep(400);
        const h = document.documentElement.scrollHeight;
        if (h === lastH) { stable++; if (stable >= 3) break; }
        else { stable = 0; }
        lastH = h;
      }
      return document.documentElement.scrollHeight;
    })()
    """
    _camoufox_eval(scroll_js, timeout=60)

    # 提取所有 a[href*="mp.weixin.qq.com/s"] 的标题和链接
    extract_js = r"""
    (() => {
      const links = [];
      document.querySelectorAll('a[href*="mp.weixin.qq.com/s"], a[href*="/s/"]').forEach(a => {
        const href = a.href || a.getAttribute('href') || '';
        const title = (a.innerText || a.textContent || '').trim();
        if (href && title) links.push({title, url: href});
      });
      return JSON.stringify(links);
    })()
    """
    raw = _camoufox_eval(extract_js, timeout=30)
    links: list[dict[str, str]] = []
    if isinstance(raw, str):
        try:
            links = json.loads(raw)
        except json.JSONDecodeError:
            pass

    # 查找分类 tab（.jsCate），对每个分类逐个点击 + 滚动 + 提取链接
    categories_js = r"""
    (() => {
      const tabs = document.querySelectorAll('.jsCate');
      const cats = [];
      tabs.forEach(t => {
        const name = (t.innerText || t.textContent || '').trim();
        if (name) cats.push({name, index: Array.from(tabs).indexOf(t)});
      });
      return JSON.stringify(cats);
    })()
    """
    raw = _camoufox_eval(categories_js, timeout=15)
    categories: list[dict[str, Any]] = []
    if isinstance(raw, str):
        try:
            categories = json.loads(raw)
        except json.JSONDecodeError:
            pass

    # 对每个分类点击 + 滚动 + 提取
    for cat in categories:
        click_js = f"""
        (() => {{
          const tabs = document.querySelectorAll('.jsCate');
          if (tabs[{cat['index']}]) tabs[{cat['index']}].click();
          return true;
        }})()
        """
        _camoufox_eval(click_js, timeout=15)
        time.sleep(1.0)
        _camoufox_eval(scroll_js, timeout=60)

        raw = _camoufox_eval(extract_js, timeout=30)
        if isinstance(raw, str):
            try:
                cat_links = json.loads(raw)
                links.extend(cat_links)
            except json.JSONDecodeError:
                pass

    # 按 URL 去重
    seen_urls: set[str] = set()
    unique_links: list[dict[str, str]] = []
    for link in links:
        u = link.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_links.append(link)

    print_json({
        "ok": True,
        "total": len(unique_links),
        "categories": [c["name"] for c in categories],
        "links": unique_links,
        "session": HOMEPAGE_SESSION,
    })
    return 0


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wx-mp-hunter",
        description="WeChat Official Account article fetcher",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # fetch
    p_fetch = sub.add_parser("fetch", help="抓单篇文章全文（微信客户端 UA 直访）")
    p_fetch.add_argument("url", help="mp.weixin.qq.com 文章 URL")
    p_fetch.add_argument("--html", action="store_true", help="同时返回正文原始 HTML")
    p_fetch.add_argument(
        "--download-images", action="store_true",
        help="把正文图片下载到本地，content_markdown 中 URL 替换为本地相对路径",
    )
    p_fetch.add_argument(
        "--download-cover", action="store_true",
        help="下载文章分享封面到 covers/<hash>.<ext>",
    )
    p_fetch.add_argument(
        "--output-dir", default="",
        help="图片下载目标目录（配合 --download-images；默认当前目录）",
    )
    p_fetch.set_defaults(func=cmd_fetch)

    # posts-list
    p_pl = sub.add_parser("posts-list", help="扫消息库拿时间窗口或最近 N 条文章推送列表")
    mode_group = p_pl.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--hours", type=positive_int, default=24,
        help="时间窗口模式：取过去 N 小时（默认 24）",
    )
    mode_group.add_argument(
        "--recent", type=positive_int, metavar="N",
        help="最近发布模式：取消息库中最新 N 条",
    )
    p_pl.add_argument(
        "--accounts", default="",
        help="公众号名白名单，逗号分隔；不传则返回全部",
    )
    p_pl.set_defaults(func=cmd_posts_list)

    # homepage（专题页流程）
    p_hp = sub.add_parser("homepage", help="采集 mp/homepage 专题页文章链接")
    p_hp.add_argument("url", help="mp.weixin.qq.com/mp/homepage URL")
    p_hp.set_defaults(func=cmd_homepage)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    try:
        if asyncio.iscoroutinefunction(func):
            return asyncio.run(func(args))
        return func(args)
    except KeyboardInterrupt:
        return 130
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
