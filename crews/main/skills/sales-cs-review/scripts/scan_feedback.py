#!/usr/bin/env python3
"""scan_feedback.py — 扫描 sales-cs workspace 的 feedback/ 目录，输出结构化摘要

用法：
    python3 scan_feedback.py
    python3 scan_feedback.py --since 2026-06-01

行为：
- 读 ~/.openclaw/workspace-sales-cs/feedback/*.md
- 统计反馈条目数、按日期分布、高频关键词
- 输出 JSON 到 stdout

退出码：
  0  成功（含无反馈）
  1  workspace 不存在
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SALES_WORKSPACE = Path(
    os.environ.get("SALES_CS_WORKSPACE", str(Path.home() / ".openclaw" / "workspace-sales-cs"))
)
FEEDBACK_DIR = SALES_WORKSPACE / "feedback"

ENTRY_RE = re.compile(r"^##\s+Feedback\s*:?\s*(.*)$", re.MULTILINE)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="只统计此日期之后（YYYY-MM-DD）")
    args = ap.parse_args()

    if not SALES_WORKSPACE.exists():
        sys.stderr.write(f"error: sales-cs workspace 不存在：{SALES_WORKSPACE}\n")
        return 1

    if not FEEDBACK_DIR.exists():
        sys.stdout.write(json.dumps({
            "workspace": str(SALES_WORKSPACE),
            "total": 0,
            "files": [],
            "note": "feedback 目录不存在，尚无客户反馈",
        }, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        return 0

    files = sorted(FEEDBACK_DIR.glob("*.md"))
    since = args.since
    entries = []
    keyword_counter: Counter[str] = Counter()

    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        # 文件名日期回退
        m_date = DATE_RE.search(f.name)
        file_date = m_date.group(1) if m_date else None
        if since and file_date and file_date < since:
            continue
        matches = ENTRY_RE.findall(text)
        for title in matches:
            entries.append({"file": f.name, "date": file_date, "title": title.strip()})
        # 粗关键词：投诉/退款/价格/试用/开票等
        for kw in ["投诉", "退款", "价格", "试用", "开票", "人工", "不满", "bug", "无法"]:
            if kw in text:
                keyword_counter[kw] += text.count(kw)

    summary = {
        "workspace": str(SALES_WORKSPACE),
        "total": len(entries),
        "files": [f.name for f in files],
        "keywords": dict(keyword_counter.most_common(10)),
        "entries": entries,
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
