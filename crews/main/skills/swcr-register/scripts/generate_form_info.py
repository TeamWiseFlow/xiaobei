#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate form-filling information Markdown for software copyright registration.

Analyzes the codebase and README to produce a Markdown file containing all
information needed to fill the online registration form at
https://register.ccopyright.com.cn/registration.html#/registerSoft

The Markdown includes:
- Software name (full and short), version
- Development info (dates, method, authors, copyright holders)
- Software functions and technical features (extracted from README)
- Source code statistics (line count, page count)
- Upload file checklist
- Offline mailing material checklist

Usage:
    python generate_form_info.py \
        --title "智能数据分析平台软件" \
        --short-name "智数平台" \
        --version "V1.0" \
        --source-dir /path/to/code \
        --completion-date 2026-05-20 \
        --publish-date 2026-06-01 \
        --dev-method "独立开发" \
        --author "张三" \
        --copyright-holder "张三" \
        --output form_info.md
"""

import argparse
import logging
import os
import re
import sys
from os import scandir
from os.path import abspath
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_EXTS = [
    "c", "h", "py", "js", "ts", "java", "cpp", "hpp",
    "go", "rs", "rb", "php", "cs", "swift", "kt", "scala",
    "jsx", "tsx", "vue", "svelte",
]
DEFAULT_COMMENT_CHARS = ["/*", "* ", "*/", "//", "#"]
DEFAULT_EXCLUDES = [
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "dist", "build", ".next", ".nuxt", "target", "bin",
    "obj", ".idea", ".vscode", "coverage", ".cache",
]


def count_source_lines(
    source_dir: str,
    exts: List[str],
    excludes: List[str],
    comment_chars: List[str],
) -> dict:
    """Count total and effective source code lines."""
    total_lines = 0
    effective_lines = 0
    file_count = 0
    abs_excludes = [abspath(e) for e in excludes]

    def _should_exclude(path: str) -> bool:
        abs_path = abspath(path)
        return any(abs_path.startswith(ex) for ex in abs_excludes)

    def _scan(directory: str) -> None:
        nonlocal total_lines, effective_lines, file_count
        try:
            for entry in scandir(directory):
                if entry.name.startswith("."):
                    continue
                if _should_exclude(entry.path):
                    continue
                if entry.is_file():
                    if any(entry.name.endswith(f".{ext}") for ext in exts):
                        try:
                            with open(entry.path, "r", encoding="utf-8", errors="replace") as f:
                                for line in f:
                                    total_lines += 1
                                    stripped = line.strip()
                                    if stripped and not any(
                                        stripped.startswith(cc) for cc in comment_chars
                                    ):
                                        effective_lines += 1
                            file_count += 1
                        except Exception as exc:
                            logger.warning("Error reading file %s: %s", entry.path, exc)
                elif entry.is_dir():
                    _scan(entry.path)
        except PermissionError:
            logger.warning("Permission denied: %s", directory)

    _scan(source_dir)
    return {
        "total_lines": total_lines,
        "effective_lines": effective_lines,
        "file_count": file_count,
    }


def calculate_pages(effective_lines: int, lines_per_page: int = 50) -> dict:
    """Calculate source code document page count."""
    if effective_lines <= 0:
        return {"total_pages": 0, "front_pages": 0, "back_pages": 0}

    total_pages_needed = (effective_lines + lines_per_page - 1) // lines_per_page

    if total_pages_needed <= 60:
        return {
            "total_pages": total_pages_needed,
            "front_pages": total_pages_needed,
            "back_pages": 0,
        }

    front = 30
    back = 30
    total = front + 1 + back  # +1 for ellipsis page
    return {
        "total_pages": total,
        "front_pages": front,
        "back_pages": back,
    }


def detect_languages(source_dir: str, excludes: List[str]) -> List[str]:
    """Detect primary programming languages in the codebase."""
    lang_map = {
        "py": "Python", "js": "JavaScript", "ts": "TypeScript",
        "java": "Java", "c": "C", "h": "C", "cpp": "C++", "hpp": "C++",
        "go": "Go", "rs": "Rust", "rb": "Ruby", "php": "PHP",
        "cs": "C#", "swift": "Swift", "kt": "Kotlin", "scala": "Scala",
        "jsx": "React JSX", "tsx": "React TSX", "vue": "Vue", "svelte": "Svelte",
    }
    ext_counts: dict = {}
    abs_excludes = [abspath(e) for e in excludes]

    def _should_exclude(path: str) -> bool:
        abs_path = abspath(path)
        return any(abs_path.startswith(ex) for ex in abs_excludes)

    def _scan(directory: str) -> None:
        try:
            for entry in scandir(directory):
                if entry.name.startswith("."):
                    continue
                if _should_exclude(entry.path):
                    continue
                if entry.is_file():
                    ext = entry.name.rsplit(".", 1)[-1] if "." in entry.name else ""
                    if ext in lang_map:
                        ext_counts[ext] = ext_counts.get(ext, 0) + 1
                elif entry.is_dir():
                    _scan(entry.path)
        except PermissionError:
            logger.warning("Permission denied: %s", directory)

    _scan(source_dir)

    sorted_exts = sorted(ext_counts.keys(), key=lambda x: ext_counts[x], reverse=True)
    languages = [lang_map[ext] for ext in sorted_exts if ext in lang_map]
    return languages[:5]  # top 5 languages


def extract_functions_from_readme(readme_path: str) -> dict:
    """Extract software functions and features from README."""
    result = {
        "main_functions": "",
        "tech_features": "",
        "description": "",
    }

    if not readme_path or not os.path.isfile(readme_path):
        return result

    try:
        with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return result

    # Extract description (first paragraph after title)
    lines = content.split("\n")
    desc_parts: List[str] = []
    past_title = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            past_title = True
            continue
        if past_title and stripped and not stripped.startswith("#") and not stripped.startswith("!["):
            # Skip table of contents lines, horizontal rules, and short labels
            if re.match(r"^[\s\-=*]+$", stripped):
                continue
            if len(stripped) < 5 and not any(c in stripped for c in "，。、；"):
                continue
            desc_parts.append(stripped)
            if len(desc_parts) >= 3:
                break
        if past_title and not stripped and desc_parts:
            break

    result["description"] = " ".join(desc_parts)

    # Extract "功能" or "Features" section
    in_features = False
    feature_parts: List[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*(功能|特性|feature|function)", stripped, re.IGNORECASE):
            in_features = True
            continue
        if in_features:
            if stripped.startswith("#"):
                break
            if stripped and not stripped.startswith("```"):
                feature_parts.append(stripped)

    result["main_functions"] = " ".join(feature_parts[:10])

    # Extract "技术" or "Tech" section
    in_tech = False
    tech_parts: List[str] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*(技术|架构|tech|arch|stack)", stripped, re.IGNORECASE):
            in_tech = True
            continue
        if in_tech:
            if stripped.startswith("#"):
                break
            if stripped and not stripped.startswith("```"):
                tech_parts.append(stripped)

    result["tech_features"] = " ".join(tech_parts[:5])

    return result


def generate_form_markdown(
    title: str,
    short_name: str,
    version: str,
    source_dir: str,
    completion_date: str,
    publish_date: str,
    dev_method: str,
    author: str,
    copyright_holder: str,
    co_authors: List[str],
    co_holders: List[str],
    stats: dict,
    pages: dict,
    languages: List[str],
    readme_info: dict,
) -> str:
    """Generate the form-filling information Markdown."""
    is_coop = dev_method == "合作开发"
    all_authors = [author] + co_authors
    all_holders = [copyright_holder] + co_holders

    # Generate main functions text (ensure 100+ chars)
    main_functions = readme_info.get("main_functions", "")
    desc = readme_info.get("description", "")
    if len(main_functions) < 100 and desc:
        main_functions = f"{main_functions} {desc}".strip()
    if len(main_functions) < 100:
        lang_str = "、".join(languages) if languages else "多种编程语言"
        main_functions = (
            f"{main_functions} 本软件基于{lang_str}开发，"
            "提供完整的数据处理、分析和管理功能，"
            "支持多种数据源的接入和处理，"
            "具备良好的扩展性、稳定性和易用性，"
            "可满足不同场景下的业务需求。"
        ).strip()

    # Generate tech features text (ensure 50+ chars)
    tech_features = readme_info.get("tech_features", "")
    if len(tech_features) < 50:
        lang_str = "、".join(languages) if languages else "多种编程语言"
        tech_features = (
            f"{tech_features} 本软件基于{lang_str}开发，"
            "采用模块化架构设计，"
            "具有良好的可维护性和可扩展性，"
            "支持跨平台部署和运行。"
        ).strip()

    # Source code document page info
    effective = stats.get("effective_lines", 0)
    if effective > 3000:
        source_doc_pages = 61
        source_doc_note = "源程序量 > 3000 行，文档必须为 61 页"
    else:
        source_doc_pages = pages.get("total_pages", 0)
        source_doc_note = f"源程序量 ≤ 3000 行，文档 {source_doc_pages} 页"

    lines = [
        f"# 软件著作权登记 — 填报信息",
        "",
        f"## 软件基本信息",
        "",
        f"| 字段 | 值 |",
        f"|------|-----|",
        f"| 软件全称 | {title} |",
        f"| 软件简称 | {short_name} |",
        f"| 版本号 | {version} |",
        f"| 开发完成日期 | {completion_date} |",
        f"| 首次发表日期 | {publish_date} |",
        f"| 开发方式 | {dev_method} |",
        "",
        f"## 著作权人信息",
        "",
        f"| 字段 | 值 |",
        f"|------|-----|",
        f"| 著作权人 | {'、'.join(all_holders)} |",
        f"| 作者 | {'、'.join(all_authors)} |",
    ]

    if is_coop:
        lines += [
            f"| 合作开发 | 是 |",
            f"| 证书副本数量 | {len(co_holders)} |",
            "",
            "### 合作开发注意事项",
            "",
            "- 需上传**合作开发协议**",
            "- 其他著作权人必须在登记网站注册并完成实名认证",
            "- 证书副本数量 = 其他著作权人数量",
        ]
    else:
        lines += [
            f"| 合作开发 | 否 |",
            f"| 证书副本数量 | 0 |",
        ]

    lines += [
        "",
        f"## 软件功能与特点",
        "",
        f"### 主要功能（{len(main_functions)} 字）",
        "",
        main_functions,
        "",
        f"### 技术特点（{len(tech_features)} 字）",
        "",
        tech_features,
        "",
        f"## 源程序统计",
        "",
        f"| 项目 | 值 |",
        f"|------|-----|",
        f"| 源代码文件数 | {stats.get('file_count', 0)} |",
        f"| 总行数 | {stats.get('total_lines', 0)} |",
        f"| 有效行数（非空非注释） | {effective} |",
        f"| 源程序文档页数 | {source_doc_pages} |",
        f"| 说明 | {source_doc_note} |",
        "",
        f"## 上传文件清单",
        "",
        f"| 表单字段 | 文件 | 格式 |",
        f"|---------|------|------|",
        f"| 程序鉴别材料 | {short_name}_源程序.docx | DOCX |",
        f"| 文档鉴别材料 | {short_name}_操作手册.docx | DOCX |",
    ]

    if is_coop:
        lines += [
            f"| 合作开发协议 | 合作开发协议.pdf | PDF |",
        ]

    lines += [
        "",
        f"## 线下邮寄材料清单",
        "",
        "在线填报提交后，需**单面打印**以下材料邮寄：",
        "",
        "1. 软件著作权登记申请表（网站自动生成，下载打印）",
        "2. 申请人身份证明（身份证复印件，**一页即可**）",
        "3. 程序鉴别材料（源程序文档打印件）",
        "4. 文档鉴别材料（操作手册打印件）",
    ]

    if is_coop:
        lines += ["5. 合作开发协议"]

    lines += [
        "",
        "## 填报流程提示",
        "",
        "1. 打开 https://register.ccopyright.com.cn/registration.html#/registerSoft",
        "2. 选择 **R11** → **计算机软件著作权登记申请** → 点击 **立即登记**",
        "3. 登录账号（未注册需先注册 + 实名认证，认证需 1-3 天）",
        "4. 选择 **我是申请人**",
        "5. 填写软件信息（全称、简称、版本号）",
        "6. 填写开发信息（开发方式、完成日期、发表日期、作者、著作权人）",
        "7. 填写软件功能与特点（主要功能 100+ 字、技术特点 50+ 字）",
        "8. 上传程序鉴别材料和文档鉴别材料",
        "9. 信息确认页：填写身份证复印件页数（1 页），其他自动填充",
        "10. 选择邮寄 → 挂号信 → 填写收信地址 → 保存并提交申请",
        "",
        "### 关键提醒",
        "",
        "- 软件全称与简称**必须不同**",
        "- 主要功能**100 字以上**，技术特点**50 字以上**",
        "- 所有材料**单面打印**",
        "- 证书领取选择**挂号信**",
    ]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate form-filling info Markdown for software copyright registration."
    )
    parser.add_argument("--title", required=True, help="Software full name")
    parser.add_argument("--short-name", required=True, help="Software short name")
    parser.add_argument("--version", default="V1.0", help="Software version")
    parser.add_argument("--source-dir", required=True, help="Source code directory")
    parser.add_argument("--completion-date", required=True, help="Development completion date (YYYY-MM-DD)")
    parser.add_argument("--publish-date", required=True, help="First publication date (YYYY-MM-DD) or '未发表'")
    parser.add_argument("--dev-method", required=True, choices=["独立开发", "合作开发"], help="Development method")
    parser.add_argument("--author", required=True, help="Primary author name")
    parser.add_argument("--copyright-holder", required=True, help="Copyright holder name")
    parser.add_argument("--co-authors", nargs="*", default=[], help="Co-author names")
    parser.add_argument("--co-holders", nargs="*", default=[], help="Co-copyright holder names")
    parser.add_argument("--readme", default=None, help="Path to README.md for extracting features")
    parser.add_argument("--output", required=True, help="Output Markdown file path")
    parser.add_argument(
        "--excludes", nargs="+", default=DEFAULT_EXCLUDES,
        help="Directories to exclude from line count",
    )

    args = parser.parse_args()

    if args.title == args.short_name:
        print("Error: 软件全称和简称不能相同！")
        return 1

    source_dir = abspath(args.source_dir)

    print(f"Analyzing source code in: {source_dir}")

    stats = count_source_lines(source_dir, DEFAULT_EXTS, args.excludes, DEFAULT_COMMENT_CHARS)
    print(f"Files: {stats['file_count']}, Total lines: {stats['total_lines']}, Effective lines: {stats['effective_lines']}")

    pages = calculate_pages(stats["effective_lines"])
    print(f"Source doc pages: {pages['total_pages']}")

    languages = detect_languages(source_dir, args.excludes)
    print(f"Languages: {', '.join(languages)}")

    readme_info = extract_functions_from_readme(args.readme) if args.readme else {}

    markdown = generate_form_markdown(
        title=args.title,
        short_name=args.short_name,
        version=args.version,
        source_dir=source_dir,
        completion_date=args.completion_date,
        publish_date=args.publish_date,
        dev_method=args.dev_method,
        author=args.author,
        copyright_holder=args.copyright_holder,
        co_authors=args.co_authors,
        co_holders=args.co_holders,
        stats=stats,
        pages=pages,
        languages=languages,
        readme_info=readme_info,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"Form info Markdown created: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
