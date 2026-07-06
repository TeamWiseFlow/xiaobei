#!/usr/bin/env python3
"""fetch_engagement.py — 微信公众号 engagement 数据抓取（Phase 4.6 方案 A）

通过 camoufox-cli + 创作者中心爬虫拿 wx_mp 文章的阅读数 / 点赞数 / 评论数 /
分享数 / 收藏数，写入 published-track 的 pub_wx_mp 表。

方案 A = 浏览器直接拿（先试这个）。创作者中心后台的文章列表页本身就把每篇已发布
文章的 engagement 数字列出来了，所以走"列表页 → 按标题匹配 → 抓行内数字"，
不需要打开单篇分析页。

CLI 形态：
    probe                          打开创作者中心 + dump DOM/截图，供 spike 调 selector
    list                           列出后台所有文章 + 行内 metrics（spike + 日常自查）
    fetch   --row-id <id>          抓单篇（按 title 在列表页匹配）
    fetch-all --days <N>           批量抓最近 N 天未更新（reads=0）的 row

依赖：
- camoufox-cli（npm 全局）
- login-manager skill（同 crew 私有）
- published-track skill（同 crew 私有）
- python3 stdlib

⚠️ selector 集中在 SELECTORS 常量，spike 后改这里即可。
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

PLATFORM = "wx_mp"                              # published-track 表名前缀
LOGIN_MANAGER_PLATFORM = "wx-mp"                # login-manager 中央存储 key

# 创作者中心入口（spike 验证）。新版后台登录后落在 mp.weixin.qq.com 域。
CREATOR_CENTER_URL = os.environ.get(
    "WX_MP_CREATOR_CENTER_URL", "https://mp.weixin.qq.com/"
)
# 内容管理列表页（登录后跳转到这里，列表行内含阅读/点赞/评论/分享/收藏）。
# spike 后若实际路径不同，改这个常量或环境变量即可。
CREATOR_CENTER_LIST_URL = os.environ.get(
    "WX_MP_LIST_URL", "https://mp.weixin.qq.com/cgi-bin/appmsg?action=list"
)

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

# spike dump 输出目录
PROBE_OUT_DIR = Path(
    os.environ.get("PROBE_OUT_DIR", "./wx-mp-engagement-probe")
).expanduser()

# ── selector（spike 后改这里）──────────────────────────────────────────────
# 创作者中心列表页：每篇文章一行。下面是一组**候选** selector，按顺序试，第一个
# 命中的用。spike 后把命中的那条提到最前，删掉无效的。
LIST_ROW_SELECTORS = [
    "tr.appmsg_item",                 # 老版表格行
    "div.weui-desktop-card__card",    # 新版卡片
    "li.appmsg_item",
    "div.appmsg_item",
]
# 行内：标题 + 各指标。指标文本里直接含数字（如 "阅读 1,234"）。
TITLE_SELECTORS = [".appmsg_title", "a.title", ".weui-desktop-card__title", ".title"]
METRIC_LABEL_RE = re.compile(
    r"(阅读|阅读数|点赞|喜欢|评论|留言|分享|转发|收藏|在看)[^\d]*([\d,]+)",
)


# ── 平台行查询 / 更新 ───────────────────────────────────────────────────────

def lookup_published_row(row_id: int) -> dict | None:
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
        cmd += ["--top-comment", str(metrics["top_comment"])]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip(), "stdout": result.stdout.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": result.stdout.strip()}


# ── login-manager 集成 ──────────────────────────────────────────────────────

def login_manager_check() -> bool:
    result = subprocess.run(
        [LOGIN_MANAGER_BIN, "check", LOGIN_MANAGER_PLATFORM],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return result.returncode == 0


def login_manager_cookie_import(session: str) -> None:
    subprocess.run(
        [LOGIN_MANAGER_BIN, "cookie-import", LOGIN_MANAGER_PLATFORM, session],
        capture_output=True, text=True, timeout=15, check=True,
    )


def login_manager_session_cleanup(session: str) -> None:
    subprocess.run(
        [LOGIN_MANAGER_BIN, "session-cleanup", LOGIN_MANAGER_PLATFORM, session],
        capture_output=True, text=True, timeout=10, check=False,
    )


# ── camoufox-cli 集成 ───────────────────────────────────────────────────────

def session_name() -> str:
    return f"wx-mp-engagement-{secrets.token_hex(4)}"


def camoufox_run(args: list[str], *, timeout: int = FETCH_TIMEOUT_S) -> subprocess.CompletedProcess:
    cmd = [CAMOUFOX_BIN, "--json"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def camoufox_open(session: str, url: str, *, headless: bool = True) -> None:
    args = ["--session", session, "--persistent"]
    if headless:
        args.append("--headless")
    camoufox_run(args + ["open", url])


def camoufox_eval(session: str, expr: str) -> str:
    """在 session 内 eval JS，返回字符串结果"""
    result = camoufox_run(["--session", session, "eval", expr])
    if result.returncode != 0:
        return ""
    try:
        env = json.loads(result.stdout)
        data = env.get("data", "")
        return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        return result.stdout


def camoufox_screenshot(session: str, out_path: Path) -> bool:
    result = camoufox_run(
        ["--session", session, "screenshot", "--path", str(out_path)],
        timeout=FETCH_TIMEOUT_S,
    )
    return result.returncode == 0


# ── 列表页 DOM 解析 ─────────────────────────────────────────────────────────

# 抓列表页用的 JS：返回每行的标题 + 整段文本（指标从文本里正则提）
_LIST_JS_TEMPLATE = r"""
(() => {
  const rowSels = %s;
  const titleSels = %s;
  function pickText(root, sels) {
    for (const s of sels) {
      const el = root.querySelector(s);
      if (el && el.textContent.trim()) return el.textContent.trim();
    }
    return '';
  }
  let rows = [];
  for (const rs of rowSels) {
    const els = document.querySelectorAll(rs);
    if (els.length) {
      rows = Array.from(els);
      break;
    }
  }
  return JSON.stringify(rows.map(r => ({
    title: pickText(r, titleSels),
    text: r.textContent.replace(/\s+/g, ' ').trim(),
  })).filter(x => x.title || x.text));
})()
"""


def _js_array_literal(items: list[str]) -> str:
    return json.dumps(items)


def fetch_article_list(session: str) -> list[dict]:
    """打开列表页，eval JS 拿 [{title, text}, ...]"""
    camoufox_open(session, CREATOR_CENTER_LIST_URL)
    js = _LIST_JS_TEMPLATE % (
        _js_array_literal(LIST_ROW_SELECTORS),
        _js_array_literal(TITLE_SELECTORS),
    )
    raw = camoufox_eval(session, js)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def parse_metrics_from_text(text: str) -> dict:
    """从行文本里提指标。文本形如 '... 阅读 1,234 点赞 56 评论 7 分享 8 收藏 9 ...'"""
    metrics = {"reads": 0, "likes": 0, "comments": 0, "shares": 0, "favorites": 0}
    label_map = {
        "阅读": "reads", "阅读数": "reads",
        "点赞": "likes", "喜欢": "likes",
        "评论": "comments", "留言": "comments",
        "分享": "shares", "转发": "shares",
        "收藏": "favorites",
        "在看": "likes",  # 在看归到 likes（公众号无单独 likes 概念时）
    }
    for label, value in METRIC_LABEL_RE.findall(text):
        key = label_map.get(label)
        if key:
            # 不覆盖更大的值（防同名指标重复匹配取到 0）
            num = int(value.replace(",", ""))
            if num > metrics[key]:
                metrics[key] = num
    return metrics


def normalize_title(s: str) -> str:
    """标题归一化用于匹配：去空白 + 去常见前缀符号"""
    return re.sub(r"\s+", "", s).strip("·*- ").lower()


def match_article(rows: list[dict], target_title: str) -> dict | None:
    """按标题在列表里找最匹配的行，返回 {title, metrics}"""
    norm_target = normalize_title(target_title)
    if not norm_target:
        return None
    for row in rows:
        if normalize_title(row.get("title", "")) == norm_target:
            return {"title": row["title"], "metrics": parse_metrics_from_text(row.get("text", ""))}
    # 模糊包含
    for row in rows:
        nt = normalize_title(row.get("title", ""))
        if nt and (norm_target in nt or nt in norm_target):
            return {"title": row["title"], "metrics": parse_metrics_from_text(row.get("text", ""))}
    return None


# ── CLI 子命令 ──────────────────────────────────────────────────────────────

def _ensure_login() -> None:
    if not login_manager_check():
        sys.stderr.write(
            "error: wx-mp cookie 失效，请先走 login-manager qr-headless + qr-confirm 流程\n"
        )
        sys.exit(2)


def cmd_probe(args) -> None:
    """spike 用：打开创作者中心 + 列表页，dump DOM/截图/文章列表 JSON"""
    _ensure_login()
    PROBE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = session_name()
    try:
        login_manager_cookie_import(session)
        # 1. 入口页
        camoufox_open(session, CREATOR_CENTER_URL)
        camoufox_screenshot(session, PROBE_OUT_DIR / "01_center.png")
        # 2. 列表页
        camoufox_open(session, CREATOR_CENTER_LIST_URL)
        camoufox_screenshot(session, PROBE_OUT_DIR / "02_list.png")
        html = camoufox_eval(session, "document.documentElement.outerHTML")
        (PROBE_OUT_DIR / "02_list.html").write_text(html, encoding="utf-8")
        # 3. 解析列表
        rows = fetch_article_list(session)
        (PROBE_OUT_DIR / "03_articles.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = {
            "ok": True,
            "session": session,
            "out_dir": str(PROBE_OUT_DIR),
            "articles_found": len(rows),
            "first_3": rows[:3],
        }
    finally:
        if SESSION_CLEANUP_ON_EXIT:
            login_manager_session_cleanup(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_list(args) -> None:
    """列出后台所有文章 + 行内 metrics"""
    _ensure_login()
    session = session_name()
    try:
        login_manager_cookie_import(session)
        rows = fetch_article_list(session)
        articles = [
            {"title": r.get("title", ""), "metrics": parse_metrics_from_text(r.get("text", ""))}
            for r in rows
        ]
        result = {"ok": True, "session": session, "total": len(articles), "articles": articles}
    finally:
        if SESSION_CLEANUP_ON_EXIT:
            login_manager_session_cleanup(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_fetch(args) -> None:
    """抓单篇：按 row.title 在列表页匹配，拿行内 metrics 写库"""
    if not args.row_id and not args.source_folder:
        sys.stderr.write("error: must pass --row-id or --source-folder\n")
        sys.exit(1)
    _ensure_login()

    if args.row_id:
        row = lookup_published_row(args.row_id)
    else:
        sys.stderr.write("error: --source-folder 模式待 spike 验证后实现\n")
        sys.exit(1)
    if row is None:
        sys.stderr.write(f"error: pub_wx_mp id={args.row_id} not found\n")
        sys.exit(1)

    session = session_name()
    try:
        login_manager_cookie_import(session)
        rows = fetch_article_list(session)
        matched = match_article(rows, row["title"] or "")
        if matched is None:
            sys.stderr.write(
                f"error: 列表页未找到标题匹配的 row id={row['id']} title={row['title']!r}\n"
                f"hint: 跑 probe 子命令检查 selector / 列表是否加载\n"
            )
            sys.exit(1)
        metrics = matched["metrics"]
        update_result = update_metrics_row(row["id"], metrics)
        result = {
            "ok": True,
            "row_id": row["id"],
            "title": row["title"],
            "matched_title": matched["title"],
            "publish_url": row["publish_url"],
            "session": session,
            "metrics": metrics,
            "update": update_result,
        }
    finally:
        if SESSION_CLEANUP_ON_EXIT:
            login_manager_session_cleanup(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_fetch_all(args) -> None:
    """批量抓最近 days 天内未更新的所有 wx_mp 记录"""
    if args.days <= 0:
        sys.stderr.write("error: --days must be > 0\n")
        sys.exit(1)
    row_ids = list_pending_wx_mp_rows(args.days)
    if not row_ids:
        sys.stdout.write(json.dumps({"total": 0, "days": args.days, "results": []}, indent=2))
        sys.stdout.write("\n")
        return

    _ensure_login()
    session = session_name()
    results = []
    try:
        login_manager_cookie_import(session)
        rows = fetch_article_list(session)
        for rid in row_ids:
            row = lookup_published_row(rid)
            if row is None:
                results.append({"row_id": rid, "ok": False, "error": "row not found"})
                continue
            matched = match_article(rows, row["title"] or "")
            if matched is None:
                results.append({"row_id": rid, "ok": False, "error": "title not matched in list"})
                continue
            upd = update_metrics_row(rid, matched["metrics"])
            results.append({"row_id": rid, "ok": upd.get("ok", True), "metrics": matched["metrics"]})
    finally:
        if SESSION_CLEANUP_ON_EXIT:
            login_manager_session_cleanup(session)
    sys.stdout.write(json.dumps({
        "total": len(row_ids),
        "days": args.days,
        "results": results,
    }, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetch_engagement",
        description="WeChat Official Account engagement fetcher (Phase 4.6 方案 A)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", help="打开创作者中心 dump DOM/截图，spike 调 selector 用").set_defaults(
        func=cmd_probe
    )
    sub.add_parser("list", help="列出后台所有文章 + 行内 metrics").set_defaults(func=cmd_list)

    p_fetch = sub.add_parser("fetch", help="抓单篇 engagement（按 title 在列表页匹配）")
    g = p_fetch.add_mutually_exclusive_group(required=True)
    g.add_argument("--row-id", type=int)
    g.add_argument("--source-folder", type=str)
    p_fetch.set_defaults(func=cmd_fetch)

    p_all = sub.add_parser("fetch-all", help="批量抓最近 N 天未更新的 row")
    p_all.add_argument("--days", type=int, default=7)
    p_all.set_defaults(func=cmd_fetch_all)

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
