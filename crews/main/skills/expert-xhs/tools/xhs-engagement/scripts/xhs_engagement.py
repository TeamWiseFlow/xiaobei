#!/usr/bin/env python3
"""Read XHS Creator note metrics and update published-track."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from creator_session import (  # noqa: E402
    CreatorApiFailure, CreatorSessionMissing, claim_daily_run, creator_api,
    observe,
)

PLATFORM = "xhs"
PUBLISHED_TRACK_DB = Path(os.environ.get(
    "PUBLISHED_TRACK_DB", "~/.openclaw/workspace-main/db/published_track.db"
)).expanduser()
PUBLISHED_TRACK_SCRIPTS = Path(os.environ.get(
    "PUBLISHED_TRACK_SCRIPTS", "~/.openclaw/workspace-main/skills/published-track/scripts"
)).expanduser()
UPDATE_METRICS_SH = PUBLISHED_TRACK_SCRIPTS / "update-metrics.sh"

def lookup_published_row(row_id: int) -> dict | None:
    if not PUBLISHED_TRACK_DB.exists():
        return None
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, title, publish_url, publish_date, source_folder "
            "FROM pub_xhs WHERE id = ?",
            (row_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_all_xhs_rows() -> list[dict]:
    """取 pub_xhs 全部行（id/title/publish_url）。

    不按日期/指标过滤——后台列表首页本身就是天然窗口：页内有什么解析什么，
    匹配上的行写库，匹配不上的报 unmatched 跳过（老作品不在首页是常态，非错误）。
    """
    if not PUBLISHED_TRACK_DB.exists():
        return []
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT id, title, publish_url FROM pub_xhs ORDER BY id DESC"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def update_metrics_row(
    row_id: int, metrics: dict, deep: dict | None = None,
    portrait: dict | None = None,
) -> dict:
    """写库委托 published-track 的 update-metrics.sh。"""
    if not UPDATE_METRICS_SH.exists():
        return {"ok": False, "error": f"update-metrics.sh not found at {UPDATE_METRICS_SH}"}
    cmd = [
        str(UPDATE_METRICS_SH),
        "--platform", PLATFORM,
        "--id", str(row_id),
        "--views", str(metrics.get("views", 0)),
        "--comments", str(metrics.get("comments", 0)),
        "--likes", str(metrics.get("likes", 0)),
        "--favorites", str(metrics.get("collects", 0)),  # pub_xhs 收藏列叫 favorites
        "--shares", str(metrics.get("shares", 0)),
    ]
    temp_paths: list[Path] = []
    try:
        for payload, flag in ((deep, "--deep-file"), (portrait, "--fan-portrait-file")):
            if payload is None:
                continue
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as stream:
                temp_paths.append(Path(stream.name))
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            cmd += [flag, str(temp_paths[-1])]
            if flag == "--deep-file":
                cmd += ["--deep-source", "xhs:creator_datacenter"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip(), "stdout": result.stdout.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": result.stdout.strip()}


def normalize_title(s: str) -> str:
    """标题归一化：折叠空白（含全角空格）、去尾部省略号（后台 displayTitle 可能截断）"""
    return re.sub(r"[\s　]+", " ", s).strip().rstrip(".…").rstrip()


def print_json(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def err_exit(error: str, msg: str, code: int = 1) -> None:
    sys.stderr.write(f"error: {msg}\n")
    print_json({"ok": False, "platform": PLATFORM, "error": error, "msg": msg})
    sys.exit(code)


METRIC_ALIASES = {
    "views": ("view_count", "viewCount", "read_count", "readCount", "views", "read_num"),
    "comments": ("comments_count", "comment_count", "commentCount", "comments", "comment_num"),
    "likes": ("like_count", "likeCount", "liked_count", "likedCount", "likes"),
    "collects": ("collect_count", "collectCount", "collected_count", "favorite_count", "favorites"),
    "shares": ("shared_count", "share_count", "shareCount", "shares", "share_num"),
}
CONTAINERS = ("metrics", "statistics", "stat", "interact_info", "interactInfo", "note_info", "noteInfo", "data")
MAX_PAGES = 10
DAILY_PAGES = 3
PAGE_DELAY_SECONDS = 3
MAX_ANALYZE_PAGES = 10
MAX_DETAIL_REQUESTS = 5
MAX_PORTRAIT_REQUESTS = 3
PORTRAIT_MIN_VIEWS = 100
SUMMARY_FIELDS = (
    "imp_count", "read_count", "coverClickRate", "view_time_avg",
    "increase_fans_count", "danmaku_count",
)
DETAIL_FIELDS = (
    "impl_count", "view_count", "cover_click_rate", "view_time_avg",
    "finish5s_rate", "full_view_rate", "exit_view2s_rate",
    "play60s_count", "rise_fans_count",
)


def _number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(万|w|W|k|K)?", text)
    if not match:
        return None
    multiplier = {None: 1, "万": 10000, "w": 10000, "W": 10000, "k": 1000, "K": 1000}[match.group(2)]
    return int(float(match.group(1)) * multiplier)


def _maps(note: dict) -> list[dict]:
    result = [note]
    for key in CONTAINERS:
        nested = note.get(key)
        if isinstance(nested, dict):
            result.append(nested)
            for subkey in CONTAINERS:
                child = nested.get(subkey)
                if isinstance(child, dict):
                    result.append(child)
    return result


def parse_note(note: dict) -> dict:
    if not isinstance(note, dict):
        raise ValueError("Creator note is not an object")
    maps = _maps(note)
    identity = ""
    title = ""
    for source in maps:
        identity = identity or str(source.get("note_id") or source.get("noteId") or source.get("id") or "")
        title = title or str(source.get("title") or source.get("display_title") or source.get("displayTitle") or "")
    metrics: dict[str, int] = {}
    missing: list[str] = []
    for name, aliases in METRIC_ALIASES.items():
        value = None
        for source in maps:
            for alias in aliases:
                if alias in source:
                    value = _number(source[alias])
                    if value is not None:
                        break
            if value is not None:
                break
        if value is None:
            missing.append(name)
        else:
            metrics[name] = value
    return {"id": identity, "title": title, "metrics": metrics, "missing": missing}


def schema_keys(note: dict) -> dict:
    return {
        "top": sorted(note),
        "nested": {
            key: sorted(value)
            for key, value in note.items()
            if isinstance(value, dict)
        },
    }


def load_notes(*, max_pages: int = MAX_PAGES, allow_partial: bool = False) -> tuple[list[dict], dict]:
    """Follow Creator cursors; daily intentionally reads only the newest pages."""
    notes: list[dict] = []
    page = 0
    seen: set[int] = set()
    first_schema: dict = {}
    with creator_api() as api:
        for index in range(max_pages):
            if page in seen:
                raise CreatorApiFailure("Creator 作品列表返回重复分页游标")
            seen.add(page)
            success, message, response = api.get_posted_notes_page(page=page)
            if not success:
                code = response.get("code") if isinstance(response, dict) else None
                raise CreatorApiFailure(message, code=code)
            data = response.get("data") if isinstance(response, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("notes"), list):
                raise CreatorApiFailure("Creator 作品列表 data.notes 结构未知")
            batch = data["notes"]
            if batch and not first_schema:
                first_schema = schema_keys(batch[0])
            notes.extend(batch)
            try:
                next_page = int(data.get("page", -1))
            except (TypeError, ValueError) as exc:
                raise CreatorApiFailure("Creator 作品列表游标无效") from exc
            if next_page == -1:
                break
            if index + 1 >= max_pages:
                if not allow_partial:
                    raise CreatorApiFailure(f"Creator 作品列表超过 {max_pages} 页上限")
                break
            page = next_page
            time.sleep(PAGE_DELAY_SECONDS)
    observe("metrics-list", "ok", pages=len(seen), notes=len(notes))
    return [parse_note(note) for note in notes], first_schema


def _deep_fields(data: dict, fields: tuple[str, ...]) -> dict:
    """Keep the API's field names and units; omit missing or malformed values."""
    return {
        key: value for key in fields
        if (value := data.get(key)) is not None
        and not isinstance(value, bool)
        and isinstance(value, (int, float))
        and value >= 0
    }


def load_analytics(*, max_pages: int = MAX_ANALYZE_PAGES, allow_partial: bool = False) -> dict[str, dict]:
    """Bounded data-analysis list, indexed only by unambiguous note ID."""
    by_id: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    with creator_api() as api:
        for page in range(1, max_pages + 1):
            success, message, response = api.get_note_analyze_page(page_num=page)
            if not success:
                code = response.get("code") if isinstance(response, dict) else None
                raise CreatorApiFailure(message, code=code)
            data = response.get("data") if isinstance(response, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("note_infos"), list):
                raise CreatorApiFailure("Creator 数据分析 note_infos 结构未知")
            batch = data["note_infos"]
            for note in batch:
                if not isinstance(note, dict) or not note.get("id"):
                    continue
                note_id = str(note["id"])
                if note_id in by_id:
                    duplicate_ids.add(note_id)
                else:
                    by_id[note_id] = _deep_fields(note, SUMMARY_FIELDS)
            total = _number(data.get("total"))
            if len(batch) < 10 or (total is not None and page * 10 >= total):
                break
            if page >= max_pages:
                if not allow_partial:
                    raise CreatorApiFailure(f"Creator 数据分析列表超过 {max_pages} 页上限")
                break
            time.sleep(PAGE_DELAY_SECONDS)
    for note_id in duplicate_ids:
        by_id.pop(note_id, None)
    observe("analytics-list", "ok", notes=len(by_id), duplicates=len(duplicate_ids))
    return by_id


def load_note_detail(note_id: str) -> dict:
    with creator_api() as api:
        success, message, response = api.get_note_analytics_base(note_id)
    if not success:
        code = response.get("code") if isinstance(response, dict) else None
        raise CreatorApiFailure(message, code=code)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise CreatorApiFailure("Creator 单篇数据分析结构未知")
    return _deep_fields(data, DETAIL_FIELDS)


def load_note_portrait(note_id: str) -> dict | None:
    """Return the complete audience data object only when it contains a portrait."""
    with creator_api() as api:
        success, message, response = api.get_note_audience_portrait(note_id)
    if not success:
        code = response.get("code") if isinstance(response, dict) else None
        raise CreatorApiFailure(message, code=code)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise CreatorApiFailure("Creator 单篇受众画像结构未知")
    if data.get("no_data"):
        return None
    if not any(data.get(field) for field in ("gender", "age", "city", "interest")):
        return None
    return data


def portrait_eligible(entry: dict, summary: dict) -> bool:
    views = entry.get("metrics", {}).get("views", 0)
    reads = summary.get("read_count", 0)
    return max(views or 0, reads or 0) >= PORTRAIT_MIN_VIEWS


def previous_detail(row_id: int) -> tuple[dict, str | None]:
    """Retain the last verified detail when a bounded batch skips that note."""
    if not PUBLISHED_TRACK_DB.exists():
        return {}, None
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    try:
        raw = conn.execute("SELECT deep_metrics FROM pub_xhs WHERE id=?", (row_id,)).fetchone()
        stored = json.loads(raw[0]) if raw and raw[0] else {}
        if not isinstance(stored, dict):
            return {}, None
        detail = stored.get("detail")
        captured = stored.get("detail_captured_at")
        return (detail if isinstance(detail, dict) else {}, captured if isinstance(captured, str) else None)
    except (sqlite3.Error, ValueError):
        return {}, None
    finally:
        conn.close()


def _published_id(url: str) -> str:
    path = urlparse(url or "").path.rstrip("/")
    return path.rsplit("/", 1)[-1] if path else ""


def match(entries: list[dict], *, title: str, publish_url: str, normalize_title) -> dict | None:
    note_id = _published_id(publish_url)
    if note_id:
        by_id = [entry for entry in entries if entry["id"] == note_id]
        if len(by_id) == 1:
            return by_id[0]
        if len(by_id) > 1 or any(entry["id"] for entry in entries):
            return None
    target = normalize_title(title)
    by_title = [entry for entry in entries if target and normalize_title(entry["title"]) == target]
    return by_title[0] if len(by_title) == 1 else None


def dispatch(args) -> int:
    command = args.cmd
    daily = command == "daily"
    try:
        if daily and not claim_daily_run():
            print_json({
                "ok": True, "platform": "xhs",
                "skipped": "ALREADY_RUN_TODAY",
            })
            return 0
        if daily:
            command = "fetch-all"
        if command == "check":
            with creator_api() as api:
                success, message, response = api.get_user_info()
            if not success:
                code = response.get("code") if isinstance(response, dict) else None
                raise CreatorApiFailure(message, code=code)
            observe("metrics-check", "ok")
            print_json({"ok": True, "platform": "xhs"})
            return 0
        rows = []
        if command == "fetch" and args.row_id:
            row = lookup_published_row(args.row_id)
            if row is None:
                err_exit("ROW_NOT_FOUND", f"pub_xhs id={args.row_id} not found", 1)
            rows = [row]
        elif command == "fetch-all":
            rows = list_all_xhs_rows()
            if not rows:
                print_json({"ok": True, "platform": "xhs", "total": 0, "matched": 0, "unmatched": 0, "results": []})
                return 0

        entries, schema = load_notes(max_pages=DAILY_PAGES, allow_partial=True) if daily else load_notes()
        if daily:
            rows = [
                row for row in rows
                if match(entries, title=row.get("title") or "", publish_url=row.get("publish_url") or "", normalize_title=normalize_title)
            ]
            if not rows:
                print_json({"ok": True, "platform": "xhs", "total": 0, "matched": 0,
                            "unmatched": 0, "creator_notes_scanned": len(entries), "results": []})
                return 0
        analytics: dict[str, dict] = {}
        analytics_error = None
        try:
            analytics = load_analytics(max_pages=DAILY_PAGES, allow_partial=True) if daily else load_analytics()
        except CreatorApiFailure as exc:
            analytics_error = str(exc)[:160]
            observe("analytics-list", "unavailable", code=exc.code)
        if command == "probe":
            print_json({"ok": True, "notes_found": len(entries), "first_note_schema": schema, "first_note_missing_metrics": entries[0]["missing"] if entries else [], "analytics_found": len(analytics), "analytics_error": analytics_error})
            return 0
        if command == "list":
            print_json({"ok": True, "platform": "xhs", "total": len(entries), "notes": [{**entry, "deep_summary": analytics.get(entry["id"], {})} for entry in entries], "analytics_error": analytics_error})
            return 0
        if command == "fetch" and not rows:
            found = match(entries, title=args.title, publish_url="", normalize_title=normalize_title)
            if found is None:
                err_exit("NOTE_NOT_IN_CREATOR_BACKEND", "未匹配到唯一作品", 1)
            if found["missing"]:
                err_exit("METRICS_SCHEMA_UNVERIFIED", f"Creator API 缺指标字段: {', '.join(found['missing'])}", 1)
            detail = {}
            portrait = None
            portrait_error = None
            detail_error = None
            if analytics_error is None:
                try:
                    detail = load_note_detail(found["id"])
                except CreatorApiFailure as exc:
                    detail_error = str(exc)[:160]
            if analytics_error is None and portrait_eligible(found, analytics.get(found["id"], {})):
                time.sleep(PAGE_DELAY_SECONDS)
                try:
                    portrait = load_note_portrait(found["id"])
                except CreatorApiFailure as exc:
                    portrait_error = str(exc)[:160]
            print_json({"ok": True, "platform": "xhs", "title": args.title, "matched_title": found["title"], "metrics": found["metrics"], "deep_summary": analytics.get(found["id"], {}), "deep_detail": detail, "fan_portrait": portrait, "analytics_error": analytics_error or detail_error, "portrait_error": portrait_error})
            return 0

        results = []
        detail_attempts = 0
        detail_blocked = analytics_error is not None
        portrait_attempts = 0
        portrait_blocked = analytics_error is not None
        for row in rows:
            found = match(entries, title=row.get("title") or "", publish_url=row.get("publish_url") or "", normalize_title=normalize_title)
            if found is None:
                results.append({"row_id": row["id"], "ok": False, "error": "NOTE_NOT_FOUND"})
                continue
            if found["missing"]:
                results.append({"row_id": row["id"], "ok": False, "error": "METRICS_SCHEMA_UNVERIFIED", "missing": found["missing"]})
                continue
            summary = analytics.get(found["id"], {})
            detail = {}
            detail_captured_at = None
            detail_error = None
            if not detail_blocked and detail_attempts < MAX_DETAIL_REQUESTS:
                if detail_attempts:
                    time.sleep(PAGE_DELAY_SECONDS)
                detail_attempts += 1
                try:
                    detail = load_note_detail(found["id"])
                    if detail:
                        detail_captured_at = datetime.now(timezone.utc).isoformat()
                except CreatorApiFailure as exc:
                    detail_error = str(exc)[:160]
                    detail_blocked = True
                    observe("analytics-detail", "unavailable", code=exc.code)
            if not detail and summary:
                detail, detail_captured_at = previous_detail(row["id"])
            deep = None
            if summary or detail:
                deep = {"summary": summary, "detail": detail}
                if detail_captured_at:
                    deep["detail_captured_at"] = detail_captured_at
            portrait = None
            portrait_error = None
            if (
                not portrait_blocked
                and portrait_attempts < MAX_PORTRAIT_REQUESTS
                and portrait_eligible(found, summary)
            ):
                time.sleep(PAGE_DELAY_SECONDS)
                portrait_attempts += 1
                try:
                    portrait = load_note_portrait(found["id"])
                except CreatorApiFailure as exc:
                    portrait_error = str(exc)[:160]
                    portrait_blocked = True
                    observe("analytics-portrait", "unavailable", code=exc.code)
            update = update_metrics_row(row["id"], found["metrics"], deep, portrait)
            results.append({"row_id": row["id"], "ok": bool(update.get("ok")), "matched_title": found["title"], "metrics": found["metrics"], "deep_metrics": deep, "fan_portrait": portrait, "analytics_error": analytics_error or detail_error, "portrait_error": portrait_error, "update": update})
        if command == "fetch":
            result = results[0]
            print_json({"platform": "xhs", **result})
            return 0 if result["ok"] else 1
        matched = sum(bool(item["ok"]) for item in results)
        output = {"ok": matched > 0, "platform": "xhs", "total": len(rows), "matched": matched,
                  "unmatched": len(rows) - matched, "results": results}
        if daily:
            output["creator_notes_scanned"] = len(entries)
        print_json(output)
        return 0 if matched > 0 else 1
    except CreatorSessionMissing as exc:
        print_json({"ok": False, "error": "SESSION_MISSING", "msg": str(exc)})
        return 2
    except CreatorApiFailure as exc:
        observe("metrics-" + command, "rejected", code=exc.code)
        print_json({"ok": False, "error": "CREATOR_REJECTED", "code": exc.code, "msg": str(exc)})
        return 2 if exc.code in (401, 403, "401", "403") else 1
    except Exception as exc:
        observe("metrics-" + command, "error", error_type=type(exc).__name__)
        print_json({"ok": False, "error": "CREATOR_FAILED", "msg": str(exc)[:200]})
        return 1

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="小红书 Creator 指标采集")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "probe", "list", "fetch-all", "daily"):
        sub.add_parser(name)
    fetch = sub.add_parser("fetch")
    group = fetch.add_mutually_exclusive_group(required=True)
    group.add_argument("--row-id", type=int)
    group.add_argument("--title")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0


if __name__ == "__main__":
    sys.exit(main())
