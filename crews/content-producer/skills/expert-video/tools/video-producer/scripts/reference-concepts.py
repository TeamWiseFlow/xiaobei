#!/usr/bin/env python3
"""reference-concepts（可选工具）— 吃甲方给的参考拆解报告出 2–3 差异化概念。

本工具只接报告原档当输入；参考视频由 main 调用对应 hunter 下载，再用 viral-chaser 转写与抽帧。
默认流程不含本阶段：仅当甲方（多为直接对话模式下的用户）提供了参考拆解报告时才用。

Usage:
  video-producer reference-concepts <project_dir> --report-file path

入：project_dir（CP 自建工作区 output_videos/<topic-en-slug>/）+ 参考拆解报告路径
出：project_dir/reference/concepts.md（2–3 差异化概念 + 成本 + 备选路径）

无报告则跳过（本脚本不报错退出），agent 直接按通用制作流程推进。
"""

import argparse
import sys
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description="reference-concepts（可选：据参考拆解报告出差异化概念）")
    parser.add_argument("project_dir", help="项目目录（CP 自建工作区 output_videos/<topic-en-slug>/）")
    parser.add_argument("--report-file", default=None, help="甲方给的参考拆解报告路径（如 main 的 viral-chaser 产物）")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    out_dir = project / "reference"
    out_dir.mkdir(parents=True, exist_ok=True)
    concepts_path = out_dir / "concepts.md"

    # checkpoint
    if concepts_path.is_file():
        print(f"[checkpoint] concepts.md 已存在，沿用：{concepts_path}")
        return

    if not args.report_file:
        print("[skip] 无参考拆解报告输入，跳过本工具")
        return

    report = Path(args.report_file)
    if not report.is_file():
        print(f"[warn] 报告文件不存在: {args.report_file}，跳过本工具")
        return

    # 复制报告原档到工作区（不做任何下载/转写/抽帧，只存档供后续阶段参考）
    import shutil
    archived = out_dir / "reference-report.md"
    if not archived.is_file():
        shutil.copy2(report, archived)

    # 提示 agent 据报告出 2–3 差异化概念写入 concepts.md
    stub = f"""# 据参考片出的差异化概念

## 参考片来源

{archived.name}（甲方给的参考拆解报告原档，本工具未做下载/转写/抽帧）。

## 概念候选（agent 据报告填）

> agent 读 archived 报告，出 2–3 个**差异化**概念（不抄原片，做差异化），每个概念含：
> - 名称与一句话定位
> - 与参考片的差异化点（节奏/钩子/结构/调性任一的差异化）
> - 预算估算（USD）
> - 备选路径（如该概念走不通的 fallback）

### 概念 1
（agent 填）

### 概念 2
（agent 填）

### 概念 3（可选）
（agent 填）

## 用户选定

> 呈交甲方（Brief owner）选定一个概念，写入 brief.md。未选定前不进基线生产（script-write）。
"""
    concepts_path.write_text(stub, encoding="utf-8")
    print(f"[done] 报告已存档：{archived}")
    print(f"[stub] concepts.md 模板已落：{concepts_path}")
    print(f"[next] agent 据报告填概念 → 呈交甲方选定 → 回通用制作流程（script-write）")


if __name__ == "__main__":
    main()
