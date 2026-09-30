#!/usr/bin/env python3
"""Read public interaction counts and update published-track without filling gaps."""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import call, item_id
from douyin_utils.http import DouyinRequestError


def track(*args):
    r = subprocess.run(
        ["published-track", *map(str, args)], capture_output=True, text=True, timeout=30
    )
    if r.returncode:
        raise ValueError("PUBLISHED_TRACK_FAILED")
    return json.loads(r.stdout)


def metrics(ident):
    basic = {}
    detail = call("detail", {"aweme_id": ident}).get("aweme_detail")
    if not isinstance(detail, dict) or str(detail.get("aweme_id", "")) != ident:
        raise DouyinRequestError("ITEM_DETAIL_MISMATCH")
    stats = detail.get("statistics")
    if not isinstance(stats, dict):
        raise DouyinRequestError("PUBLIC_STATS_MISSING")
    for src, dst in {
        "digg_count": "likes",
        "comment_count": "comments",
        "share_count": "shares",
        "collect_count": "favorites",
    }.items():
        value = stats.get(src)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if number >= 0 and math.isfinite(number) and number.is_integer():
            basic[dst] = int(value) if isinstance(value, int) else int(number)
    return {
        "metrics": basic,
        "source": "douyin:public_detail",
        "unavailable": sorted(
            {"plays", "likes", "comments", "shares", "favorites"} - basic.keys()
        ),
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
        call("self")
        return {"ok": True, "web": True, "scope": "public_interactions"}
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
    for row, ident in selected:
        try:
            result = metrics(ident)
            update(row, result)
            out.append({"row_id": row["id"], "aweme_id": ident, "ok": True, **result})
        except (DouyinRequestError, ValueError) as e:
            out.append({"row_id": row["id"], "ok": False, "error": str(e)})
    return {"ok": all(x["ok"] for x in out), "scanned": len(out), "outcomes": out}


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
