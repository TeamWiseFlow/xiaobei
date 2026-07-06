#!/usr/bin/env python3
"""write_identity.py — 把 sales-cs 对外称呼写入其 workspace 的 IDENTITY.md

用法：
    python3 write_identity.py --name "小明助手"

行为：
- 定位 sales-cs workspace 的 IDENTITY.md（优先 ~/.openclaw/workspace-sales-cs/IDENTITY.md，
  回退到本仓 crews/sales-cs/IDENTITY.md）
- 替换 ## Name 段下的称呼（保留模板其余部分）
- 幂等：重复调用覆盖旧称呼

退出码：
  0  写入成功
  1  参数错 / 文件找不到
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEFAULT_WORKSPACE = Path.home() / ".openclaw" / "workspace-sales-cs"
REPO_FALLBACK = Path(
    os.environ.get(
        "SALES_CS_REPO_IDENTITY",
        str(Path(__file__).resolve().parents[4] / "crews" / "sales-cs" / "IDENTITY.md"),
    )
)


def resolve_identity_path() -> Path:
    ws = Path(os.environ.get("SALES_CS_WORKSPACE", str(DEFAULT_WORKSPACE)))
    candidate = ws / "IDENTITY.md"
    if candidate.exists():
        return candidate
    if REPO_FALLBACK.exists():
        return REPO_FALLBACK
    raise FileNotFoundError(f"IDENTITY.md not found at {candidate} or {REPO_FALLBACK}")


NAME_SECTION_RE = re.compile(r"(## Name\s*\n)([^\n]*)(\n)", re.MULTILINE)


def write_name(identity_path: Path, name: str) -> None:
    text = identity_path.read_text(encoding="utf-8")
    if not NAME_SECTION_RE.search(text):
        raise ValueError(f"## Name section not found in {identity_path}")
    new_text = NAME_SECTION_RE.sub(rf"\g<1>**{name}**（对外称呼）\g<3>", text, count=1)
    identity_path.write_text(new_text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="sales-cs 对外自我称呼")
    args = ap.parse_args()
    if not args.name.strip():
        sys.stderr.write("error: --name 不能为空\n")
        return 1
    try:
        p = resolve_identity_path()
        write_name(p, args.name.strip())
    except (FileNotFoundError, ValueError) as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    sys.stdout.write(f"ok: wrote Name='{args.name}' to {p}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
