#!/usr/bin/env python3
"""fetch_engagement.py — 微信公众号 engagement 数据抓取（Phase 4.6 方案 A）

通过 camoufox-cli + 创作者中心爬虫拿 wx_mp 文章的阅读数 / 点赞数 / 评论数 /
分享数 / 收藏数，写入 published-track 的 pub_wx_mp 表。

CLI 形态：
    fetch   --row-id <id> | --source-folder <folder>
    fetch-all --days <N>

依赖：
- camoufox-cli（npm 全局）
- login-manager skill（同 crew 私有）
- published-track skill（同 crew 私有）
- python3 stdlib（json / sqlite3 / subprocess / pathlib / urllib）

⚠️ 本骨架不做真机 spike 验证（无公众号账号环境）。spike checklist 见
docs/wechat-mp-engagement-design.md §七。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── 常量 ─────────────────────────────────────────────────────────────────────

PLATFORM = "wx_mp"                              # published-track 表名 pub_ 后的部分
LOGIN_MANAGER_PLATFORM = "wx-mp"                # login-manager 中央存储 key
CREATOR_CENTER_URL = "https://mp.weixin.qq.com/"  # 后台入口（spike 验证）

# login-manager 与 published-track 路径（按 crew-skill 部署约定）
LOGIN_MANAGER_BIN = os.environ.get(
    "LOGIN_MANAGER_BIN",
    "~/.openclaw/workspace-main/skills/login-manager/scripts/login-manager.sh",
)
PUBLISHED_TRACK_ROOT = Path(
    os.environ.get("PUBLISHED_TRACK_ROOT", "./db")
).expanduser()
PUBLISHED_TRACK_DB = PUBLISHED_TRACK_ROOT / "published_track.db"
PUBLISHED_TRACK_SCRIPTS = Path(
    os.environ.get(
        "PUBLISHED_TRACK_SCRIPTS",
        "~/.openclaw/workspace-main/skills/published-track/scripts",
    )
).expanduser()
UPDATE_METRICS_SH = PUBLISHED_TRACK_SCRIPTS / "update-metrics.sh"

CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
FETCH_TIMEOUT_S = 30
SESSION_CLEANUP_ON_EXIT = True


# ── 平台行查询 / 更新 ───────────────────────────────────────────────────────

def lookup_published_row(row_id: int) -> dict | None:
    """查 pub_wx_mp 表单行（按 id）"""
    if not PUBLISHED_TRACK_DB.exists():
        return None
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"SELECT id, title, publish_url, publish_date, source_folder "
            f"FROM pub_{PLATFORM} WHERE id = ?",
            (row_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_pending_wx_mp_rows(days: int) -> list[int]:
    """列最近 days 天内已发布但 engagement 未更新（reads=0）的 row id 列表"""
    if not PUBLISHED_TRACK_DB.exists():
        return []
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    try:
        cur = conn.execute(
            f"SELECT id FROM pub_{PLATFORM} "
            f"WHERE publish_date >= ? AND reads = 0 "
            f"ORDER BY publish_date DESC",
            (threshold,),
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def update_metrics_row(row_id: int, metrics: dict) -> dict:
    """调 update-metrics.sh 写 pub_wx_mp（与 published-track 集成）"""
    if not UPDATE_METRICS_SH.exists():
        return {"ok": False, "error": f"update-metrics.sh not found at {UPDATE_METRICS_SH}"}
    cmd = [
        str(UPDATE_METRICS_SH),
        "--platform", PLATFORM,
        "--id", str(row_id),
        "--reads", str(metrics.get("reads", 0)),
        "--likes", str(metrics.get("likes", 0)),
        "--comments", str(metrics.get("comments", 0)),
        "--shares", str(metrics.get("shares", 0)),
        "--favorites", str(metrics.get("favorites", 0)),
    ]
    if metrics.get("top_comment"):
        cmd += ["--top-comment", metrics["top_comment"]]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip(), "stdout": result.stdout.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": result.stdout.strip()}


# ── login-manager 集成 ──────────────────────────────────────────────────────

def login_manager_check() -> bool:
    """探活 login-manager 中央 cookie。返回 True = 有效。"""
    result = subprocess.run(
        [LOGIN_MANAGER_BIN, "check", LOGIN_MANAGER_PLATFORM],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode == 0


def login_manager_cookie_import(session: str) -> None:
    """把中央 cookie 注到 camoufox session"""
    subprocess.run(
        [LOGIN_MANAGER_BIN, "cookie-import", LOGIN_MANAGER_PLATFORM, session],
        capture_output=True, text=True, timeout=15, check=True,
    )


def login_manager_session_cleanup(session: str) -> None:
    """关闭 camoufox session"""
    subprocess.run(
        [LOGIN_MANAGER_BIN, "session-cleanup", LOGIN_MANAGER_PLATFORM, session],
        capture_output=True, text=True, timeout=10, check=False,
    )


# ── camoufox-cli 集成 ───────────────────────────────────────────────────────

def session_name() -> str:
    """新 session 名（D18 + 4.5.5 并发约束：每任务一 session）"""
    return f"wx-mp-engagement-{secrets.token_hex(4)}"


def camoufox_open_session(session: str) -> None:
    """启 headless + persistent 会话 + 打开创作者中心"""
    cmd = [
        CAMOUFOX_BIN, "--session", session,
        "--persistent", "--headless", "--json",
        "open", CREATOR_CENTER_URL,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=FETCH_TIMEOUT_S, check=False)


def camoufox_fetch_dom(session: str, url: str) -> str:
    """在 session 内打开 url + 抓 document.documentElement.outerHTML"""
    open_cmd = [CAMOUFOX_BIN, "--session", session, "--persistent", "--headless",
                "--json", "open", url]
    subprocess.run(open_cmd, capture_output=True, text=True, timeout=FETCH_TIMEOUT_S, check=False)
    eval_cmd = [CAMOUFOX_BIN, "--session", session, "--json",
                "eval", "document.documentElement.outerHTML"]
    result = subprocess.run(eval_cmd, capture_output=True, text=True, timeout=FETCH_TIMEOUT_S,
                            check=False)
    if result.returncode != 0:
        return ""
    try:
        env = json.loads(result.stdout)
        data = env.get("data", "")
        if isinstance(data, str):
            return data
        return json.dumps(data)
    except json.JSONDecodeError:
        return ""


# ── DOM 解析 ────────────────────────────────────────────────────────────────

_NUMBER_RE = re.compile(r"[\d,]+")

def _first_int(s: str) -> int:
    """从字符串中提取第一个整数（容忍 '1,234' / '1.2w' / '56 次'）"""
    m = _NUMBER_RE.search(s)
    return int(m.group(0).replace(",", "")) if m else 0


def parse_dom_metrics(html: str) -> dict:
    """创作者中心单篇分析页 DOM → 标准 metrics dict

    ⚠️ selector 是基于公开信息推测，spike 验证后调整。
    """
    metrics = {"reads": 0, "likes": 0, "comments": 0, "shares": 0, "favorites": 0}

    patterns = [
        (r'class="[^"]*read-count[^"]*"[^>]*>([^<]+)<', "reads"),
        (r'class="[^"]*like-count[^"]*"[^>]*>([^<]+)<', "likes"),
        (r'class="[^"]*comment-count[^"]*"[^>]*>([^<]+)<', "comments"),
        (r'class="[^"]*share-count[^"]*"[^>]*>([^<]+)<', "shares"),
        (r'class="[^"]*favorite-count[^"]*"[^>]*>([^<]+)<', "favorites"),
    ]
    for pat, key in patterns:
        m = re.search(pat, html)
        if m:
            metrics[key] = _first_int(m.group(1))
    return metrics


# ── payload 构造 ────────────────────────────────────────────────────────────

def build_metrics_payload(raw: dict) -> dict:
    """把 camoufox 抓到的 raw dict → update-metrics.sh 期望的标准 metrics"""
    top = raw.get("top_comment") or {}
    if isinstance(top, dict):
        top_str = f"{top.get('user', '')}: {top.get('text', '')}" if top else ""
    else:
        top_str = str(top)
    return {
        "reads": raw.get("read_count", raw.get("reads", 0)),
        "likes": raw.get("like_count", raw.get("likes", 0)),
        "comments": raw.get("comment_count", raw.get("comments", 0)),
        "shares": raw.get("share_count", raw.get("shares", 0)),
        "favorites": raw.get("favorite_count", raw.get("favorites", 0)),
        "top_comment": top_str,
    }


# ── CLI 子命令 ──────────────────────────────────────────────────────────────

def cmd_fetch(*, args) -> None:
    """抓取单篇公众号文章 engagement"""
    if not args.row_id and not args.source_folder:
        sys.stderr.write("error: must pass --row-id or --source-folder\n")
        sys.exit(1)
    if not login_manager_check():
        sys.stderr.write(
            "error: wx-mp cookie 失效，请先走 login-manager qr-headless + qr-confirm 流程\n"
        )
        sys.exit(2)

    if args.row_id:
        row = lookup_published_row(args.row_id)
    else:
        # source_folder 路径：先查 row 再抓（spike 验证后实现）
        sys.stderr.write("error: --source-folder 模式待 spike 验证后实现\n")
        sys.exit(1)
    if row is None:
        sys.stderr.write(f"error: pub_wx_mp id={args.row_id} not found\n")
        sys.exit(1)

    session = session_name()
    try:
        login_manager_cookie_import(session)
        camoufox_open_session(session)
        url = row["publish_url"] or CREATOR_CENTER_URL
        html = camoufox_fetch_dom(session, url)
        raw = parse_dom_metrics(html)
        metrics = build_metrics_payload(raw)
        update_result = update_metrics_row(row["id"], metrics)
        result = {
            "ok": True,
            "row_id": row["id"],
            "title": row["title"],
            "publish_url": url,
            "session": session,
            "metrics": metrics,
            "update": update_result,
        }
    finally:
        if SESSION_CLEANUP_ON_EXIT:
            login_manager_session_cleanup(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_fetch_all(*, days: int) -> None:
    """批量抓取最近 days 天内未更新的所有 wx_mp 记录"""
    if days <= 0:
        sys.stderr.write("error: --days must be > 0\n")
        sys.exit(1)
    row_ids = list_pending_wx_mp_rows(days)
    results = []
    for rid in row_ids:
        try:
            cmd_fetch(args=mock_namespace(rid))  # type: ignore[name-defined]
            results.append({"row_id": rid, "ok": True})
        except SystemExit as e:
            results.append({"row_id": rid, "ok": False, "exit_code": e.code})
        except Exception as e:  # noqa: BLE001
            results.append({"row_id": rid, "ok": False, "error": str(e)})
    sys.stdout.write(json.dumps({
        "total": len(row_ids),
        "days": days,
        "results": results,
    }, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def mock_namespace(row_id: int):
    """最小 argparse.Namespace（fetch-all 调用 fetch 时复用）"""
    from argparse import Namespace
    return Namespace(row_id=row_id, source_folder=None)


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetch_engagement",
        description="WeChat Official Account engagement data fetcher (Phase 4.6)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_fetch = sub.add_parser("fetch", help="Fetch engagement for one row")
    g = p_fetch.add_mutually_exclusive_group(required=True)
    g.add_argument("--row-id", type=int)
    g.add_argument("--source-folder", type=str)
    p_fetch.set_defaults(func=lambda a: cmd_fetch(args=a))

    p_all = sub.add_parser("fetch-all", help="Fetch engagement for all pending rows in N days")
    p_all.add_argument("--days", type=int, default=7)
    p_all.set_defaults(func=lambda a: cmd_fetch_all(days=a.days))

    return p


def main(argv: list[str] | None = None) -> int:
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
