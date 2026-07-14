#!/usr/bin/env python3
"""symlink_business_knowledge.py — 把 main agent 的 business_knowledge.md + business_knowledge/ 软链到 sales-cs workspace

用法：
    python3 symlink_business_knowledge.py

行为：
- 源（优先 workspace，回退仓库；首次启用从仓库模板复制 .md）：
    - business_knowledge.md   业务知识正文（单文件）
        workspace: ~/.openclaw/workspace-main/business_knowledge.md
        仓库模板:  crews/main/business_knowledge.md
    - business_knowledge/     支撑材料文件夹
        workspace: ~/.openclaw/workspace-main/business_knowledge/
        仓库:      crews/main/business_knowledge/
- 目标：sales-cs workspace 下的同名条目（~/.openclaw/workspace-sales-cs/）
- 源 .md 不存在 → 从仓库模板复制一份到 workspace-main
- 源文件夹不存在 → 创建仓库内空目录
- 目标已存在且是软链 → 覆盖；已存在且是真实文件/目录 → 报错（避免误删数据）

退出码：
  0  全部软链创建成功
  1  目标已存在为非软链 / 其他错误
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

MAIN_WORKSPACE = Path(
    os.environ.get("MAIN_WORKSPACE", str(Path.home() / ".openclaw" / "workspace-main"))
)
SALES_WORKSPACE = Path(
    os.environ.get("SALES_CS_WORKSPACE", str(Path.home() / ".openclaw" / "workspace-sales-cs"))
)
REPO_MAIN = Path(
    os.environ.get(
        "REPO_MAIN",
        str(Path(__file__).resolve().parents[4] / "crews" / "main"),
    )
)
REPO_BK_MD = REPO_MAIN / "business_knowledge.md"
REPO_BK_DIR = REPO_MAIN / "business_knowledge"


def resolve_md_source() -> Path:
    ws_md = MAIN_WORKSPACE / "business_knowledge.md"
    if ws_md.exists():
        return ws_md
    # 首次启用：从仓库模板复制到 workspace-main
    if REPO_BK_MD.exists():
        MAIN_WORKSPACE.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_BK_MD, ws_md)
        return ws_md
    # 仓库也没模板：建空文件兜底
    MAIN_WORKSPACE.mkdir(parents=True, exist_ok=True)
    ws_md.write_text("# 业务知识（business_knowledge）\n\n（待补充）\n", encoding="utf-8")
    return ws_md


def resolve_dir_source() -> Path:
    ws_dir = MAIN_WORKSPACE / "business_knowledge"
    if ws_dir.exists():
        return ws_dir
    if REPO_BK_DIR.exists():
        return REPO_BK_DIR
    REPO_BK_DIR.mkdir(parents=True, exist_ok=True)
    return REPO_BK_DIR


def link_one(src: Path, dst: Path) -> int:
    src = src.resolve()
    if dst.is_symlink():
        dst.unlink()
    elif dst.exists():
        sys.stderr.write(
            f"error: {dst} 已存在且不是软链，拒绝覆盖。请人工确认后处理。\n"
        )
        return 1
    dst.symlink_to(src, target_is_directory=src.is_dir())
    sys.stdout.write(f"ok: {dst} -> {src}\n")
    return 0


def main() -> int:
    try:
        SALES_WORKSPACE.mkdir(parents=True, exist_ok=True)
        md_src = resolve_md_source()
        dir_src = resolve_dir_source()
        rc = link_one(md_src, SALES_WORKSPACE / "business_knowledge.md")
        if rc != 0:
            return rc
        rc = link_one(dir_src, SALES_WORKSPACE / "business_knowledge")
        return rc
    except OSError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
