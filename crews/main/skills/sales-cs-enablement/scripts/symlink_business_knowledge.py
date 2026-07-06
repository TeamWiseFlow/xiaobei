#!/usr/bin/env python3
"""symlink_business_knowledge.py — 把 main agent 的 business_knowledge/ 软链到 sales-cs workspace

用法：
    python3 symlink_business_knowledge.py

行为：
- 源：main agent workspace 下的 business_knowledge/（本仓 crews/main/business_knowledge/，
  运行时为 ~/.openclaw/workspace-main/business_knowledge/）
- 目标：sales-cs workspace 下的 business_knowledge/（~/.openclaw/workspace-sales-cs/business_knowledge/）
- 源不存在 → 创建空目录（首次启用）
- 目标已存在且是软链 → 覆盖；已存在且是真实目录 → 报错（避免误删数据）

退出码：
  0  软链创建成功
  1  目标已存在为非软链 / 其他错误
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

MAIN_WORKSPACE = Path(
    os.environ.get("MAIN_WORKSPACE", str(Path.home() / ".openclaw" / "workspace-main"))
)
SALES_WORKSPACE = Path(
    os.environ.get("SALES_CS_WORKSPACE", str(Path.home() / ".openclaw" / "workspace-sales-cs"))
)
REPO_MAIN_BUSINESS_KNOWLEDGE = Path(
    os.environ.get(
        "REPO_MAIN_BUSINESS_KNOWLEDGE",
        str(Path(__file__).resolve().parents[4] / "crews" / "main" / "business_knowledge"),
    )
)


def resolve_source() -> Path:
    ws_bk = MAIN_WORKSPACE / "business_knowledge"
    if ws_bk.exists():
        return ws_bk
    if REPO_MAIN_BUSINESS_KNOWLEDGE.exists():
        return REPO_MAIN_BUSINESS_KNOWLEDGE
    # 首次启用：创建仓库内的空目录作为源
    REPO_MAIN_BUSINESS_KNOWLEDGE.mkdir(parents=True, exist_ok=True)
    return REPO_MAIN_BUSINESS_KNOWLEDGE


def main() -> int:
    try:
        src = resolve_source().resolve()
        SALES_WORKSPACE.mkdir(parents=True, exist_ok=True)
        dst = SALES_WORKSPACE / "business_knowledge"
        if dst.is_symlink():
            dst.unlink()
        elif dst.exists():
            sys.stderr.write(
                f"error: {dst} 已存在且不是软链，拒绝覆盖。请人工确认后处理。\n"
            )
            return 1
        dst.symlink_to(src, target_is_directory=True)
        sys.stdout.write(f"ok: {dst} -> {src}\n")
        return 0
    except OSError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
