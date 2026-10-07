#!/usr/bin/env python3
"""Read own play counts and public interactions without filling missing metrics."""

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import call, item_id
from douyin_utils.http import DouyinRequestError

PUBLIC_FIELDS = {
    "digg_count": "likes",
    "comment_count": "comments",
    "share_count": "shares",
    "collect_count": "favorites",
}
CREATOR_PAGE_SIZE = 50
CREATOR_MAX_PAGES = 10


def numeric_id(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return ""
    value = str(value)
    return value if value.isascii() and value.isdecimal() else ""


def count_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if number.is_finite() and number >= 0 and number == number.to_integral_value():
        return int(number)
    return None


def account_uid():
    user = call("self").get("user")
    uid = (
        numeric_id(user.get("uid") or user.get("uid_str"))
        if isinstance(user, dict) else ""
    )
    if not uid:
        raise DouyinRequestError("SELF_PROFILE_MISSING")
    return uid


def creator_page(uid, cursor="0", count=CREATOR_PAGE_SIZE):
    page = call(
        "preview_videos",
        {"count": str(count), "max_cursor": cursor},
        expected_uid=uid,
    )
    works = page.get("aweme_list")
    if not isinstance(works, list):
        raise DouyinRequestError("CREATOR_WORKS_INVALID")
    for work in works:
        if not isinstance(work, dict) or not numeric_id(work.get("aweme_id")):
            raise DouyinRequestError("CREATOR_WORKS_INVALID")
        author = work.get("author")
        owner = (
            numeric_id(author.get("uid") or author.get("uid_str"))
            if isinstance(author, dict) else ""
        )
        if owner != uid:
            raise DouyinRequestError("CREATOR_ACCOUNT_MISMATCH")
    return page


def creator_plays(identifiers):
    """Read the creator list once per batch, preserving exact IDs and missingness."""
    pending = set(identifiers)
    result = {"uid": None, "plays": {}, "unavailable_reasons": {}}
    if not pending:
        return result
    reason = "CREATOR_PAGE_LIMIT"
    try:
        result["uid"] = account_uid()
        cursor = "0"
        seen_cursors = {cursor}
        for _ in range(CREATOR_MAX_PAGES):
            page = creator_page(result["uid"], cursor)
            for work in page["aweme_list"]:
                ident = numeric_id(work["aweme_id"])
                if ident not in pending:
                    continue
                pending.remove(ident)
                stats = work.get("statistics")
                plays = (
                    count_value(stats.get("play_count"))
                    if isinstance(stats, dict) else None
                )
                if plays is None:
                    result["unavailable_reasons"][ident] = "CREATOR_PLAY_COUNT_MISSING"
                else:
                    result["plays"][ident] = plays
            if not pending:
                break
            more = page.get("has_more")
            if more in (False, 0, "0"):
                reason = "CREATOR_ITEM_NOT_FOUND"
                break
            if more not in (True, 1, "1"):
                raise DouyinRequestError("CREATOR_PAGINATION_INVALID")
            cursor = numeric_id(page.get("max_cursor"))
            if not cursor or cursor in seen_cursors:
                raise DouyinRequestError("CREATOR_CURSOR_INVALID")
            seen_cursors.add(cursor)
    except (DouyinRequestError, ValueError) as e:
        reason = e.code if isinstance(e, DouyinRequestError) else str(e)
        if reason in ("API_ACCOUNT_MISMATCH", "CREATOR_ACCOUNT_MISMATCH"):
            # Discard the batch if account identity changes between pages.
            pending = set(identifiers)
            result["plays"].clear()
            result["unavailable_reasons"].clear()
    result["unavailable_reasons"].update({ident: reason for ident in pending})
    return result


def track(*args):
    r = subprocess.run(
        ["published-track", *map(str, args)], capture_output=True, text=True, timeout=30
    )
    if r.returncode:
        raise ValueError("PUBLISHED_TRACK_FAILED")
    return json.loads(r.stdout)


def metrics(ident, creator=None):
    basic = {}
    reasons = {}
    if creator is not None and ident in creator["plays"]:
        basic["plays"] = creator["plays"][ident]
    else:
        reasons["plays"] = (
            creator["unavailable_reasons"].get(ident, "CREATOR_ITEM_NOT_FOUND")
            if creator is not None else "CREATOR_DATA_NOT_REQUESTED"
        )
    try:
        kwargs = {"expected_uid": creator["uid"]} if creator and creator["uid"] else {}
        detail = call("detail", {"aweme_id": ident}, **kwargs).get("aweme_detail")
        if not isinstance(detail, dict) or numeric_id(detail.get("aweme_id")) != ident:
            raise DouyinRequestError("ITEM_DETAIL_MISMATCH")
        stats = detail.get("statistics")
        if not isinstance(stats, dict):
            raise DouyinRequestError("PUBLIC_STATS_MISSING")
        for src, dst in PUBLIC_FIELDS.items():
            number = count_value(stats.get(src))
            if number is None:
                reasons[dst] = "PUBLIC_METRIC_MISSING"
            else:
                basic[dst] = number
    except DouyinRequestError as e:
        if creator is None or e.code == "API_ACCOUNT_MISMATCH":
            raise
        reasons.update({field: e.code for field in PUBLIC_FIELDS.values()})
    sources = {
        field: "douyin:creator_work_list" if field == "plays" else "douyin:public_detail"
        for field in basic
    }
    return {
        "metrics": basic,
        "source": "+".join(sorted(set(sources.values()))) or "douyin:public_detail",
        "field_sources": sources,
        "unavailable": sorted(reasons),
        "unavailable_reasons": reasons,
        "complete": not reasons,
    }


def update(row, result):
    args = ["update-metrics", "--platform", "douyin", "--id", str(row["id"])]
    for k, v in result["metrics"].items():
        args.extend(["--" + k, str(v)])
    if not result["metrics"]:
        raise ValueError("METRICS_UNAVAILABLE")
    if not track(*args).get("ok"):
        raise ValueError("METRICS_UPDATE_FAILED")


def main():
    p = argparse.ArgumentParser(prog="douyin-engagement")
    p.add_argument("command", choices=("check", "list", "fetch", "daily"))
    p.add_argument("--row-id", type=int)
    a = p.parse_args()
    if a.command == "check":
        uid = account_uid()
        creator_page(uid, count=1)
        return {
            "ok": True, "web": True, "creator": True,
            "scope": "own_plays_and_public_interactions",
        }
    if a.command == "fetch" and a.row_id is None:
        raise ValueError("ROW_ID_REQUIRED")
    rows = track(
        "query",
        "--platform",
        "douyin",
        *(["--limit", "30"] if a.command != "fetch" else []),
    )
    if not isinstance(rows, list):
        raise ValueError("PUBLISHED_TRACK_BAD_RESPONSE")
    if a.command == "list":
        return {"ok": True, "rows": rows}
    if a.command == "fetch":
        rows = [r for r in rows if r["id"] == a.row_id]
        if not rows:
            raise ValueError("ROW_NOT_FOUND")
    selected = []
    out = []
    for row in rows:
        try:
            selected.append((row, item_id(row.get("publish_url", ""))))
        except ValueError:
            out.append({"row_id": row["id"], "ok": False, "error": "ITEM_ID_REQUIRED"})
    creator = creator_plays([ident for _, ident in selected])
    for row, ident in selected:
        try:
            result = metrics(ident, creator)
            if not result["metrics"]:
                out.append({
                    "row_id": row["id"], "aweme_id": ident, "ok": False,
                    "error": "METRICS_UNAVAILABLE", **result,
                })
                continue
            update(row, result)
            out.append({"row_id": row["id"], "aweme_id": ident, "ok": True, **result})
        except (DouyinRequestError, ValueError) as e:
            out.append({"row_id": row["id"], "ok": False, "error": str(e)})
    return {
        "ok": all(x["ok"] for x in out),
        "complete": all(x.get("complete", False) for x in out),
        "scanned": len(out),
        "outcomes": out,
    }


if __name__ == "__main__":
    try:
        r = main()
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r["ok"] else 1)
    except (DouyinRequestError, ValueError, OSError, subprocess.SubprocessError) as e:
        code = (
            e.code
            if isinstance(e, DouyinRequestError)
            else str(e)
            if isinstance(e, ValueError) and str(e).isupper()
            else "ENGAGEMENT_FAILED"
        )
        print(json.dumps({"ok": False, "error": code}))
        sys.exit(
            2
            if code
            in (
                "API_SESSION_MISSING",
                "API_SESSION_EXPIRED",
                "PLATFORM_AUTH_REJECTED",
                "PLATFORM_LOGIN_REJECTED",
            )
            else 1
        )
