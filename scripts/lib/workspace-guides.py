#!/usr/bin/env python3
"""Regenerate owned AGENTS.md sections while preserving surrounding user content."""

from pathlib import Path
import re
import sys


HEADING = "## 多行内容与真实换行"
GUIDE = r"""## 多行内容与真实换行

有些模型会把本应是**真实换行**的地方写成字面量 `\n`（反斜杠和 n 两个字符）。这会让普通文档、字幕、配置、消息正文和代码都挤成一行；问题不限于 Python。

- 写多行内容时，直接用文件写入工具传入实际分行的正文；用 shell 写文件时，heredoc 的正文也要实际分行。不要把多行内容先拼成带字面量 `\n` 的一行再原样写入。
- 写完后读回文件，核对预期的行数和段落。若本应多行的内容挤在一行，并出现本该用于断行的字面量 `\n`，先修正文件，再继续后续步骤；不要只凭“写入成功”判断。
- ✅ 目标文件实际内容：
  ```text
  第一行
  第二行
  ```
  ❌ 错误的单行内容：`第一行\n第二行`
- 多行 Python 也遵守同一规则：先写有真实换行的 `.py` 文件，再运行 `python3 /path/to/script.py`；不要用带字面量 `\n` 的 `python3 -c` 拼脚本。
- **保留有意的转义**：JSON 字符串、代码字符串、正则表达式等场景中，`\n` 可能是合法的转义写法；工具调用日志也可能转义展示换行。以最终文件或接收端的实际内容为准，不要对整份文件盲目全局替换。"""


def markdown_headings(content: str):
    """Find section boundaries without treating fenced examples as headings."""
    offset = 0
    fence = None
    for line in content.splitlines(keepends=True):
        delimiter = re.match(r" {0,3}(`{3,}|~{3,})([^\r\n]*)", line)
        if fence:
            if (delimiter and delimiter[1][0] == fence[0]
                    and len(delimiter[1]) >= len(fence) and not delimiter[2].strip()):
                fence = None
        elif delimiter:
            fence = delimiter[1]
        else:
            heading = re.match(r" {0,3}(#{1,6})[ \t]+([^\r\n]+)", line)
            if heading:
                yield offset, offset + len(line), len(heading[1]), heading[2].rstrip('# \t')
        offset += len(line)


def remove_sections(content: str, sections: set[tuple[int, str]]) -> str:
    """Delete each owned heading and its body through the next peer or parent heading."""
    headings = list(markdown_headings(content))
    for index in range(len(headings) - 1, -1, -1):
        start, _, level, title = headings[index]
        if (level, title) in sections:
            end = next((pos for pos, _, depth, _ in headings[index + 1:] if depth <= level), len(content))
            content = content[:start] + content[end:]
    return content


def replace_section(content: str, block: str) -> str:
    """Remove the old section, then append the current version."""
    newline = "\r\n" if "\r\n" in content else "\n"
    block = block.strip('\r\n').replace('\r\n', '\n').replace('\n', newline)
    heading = next(markdown_headings(block))
    content = remove_sections(content, {(heading[2], heading[3])}).rstrip('\r\n')
    return content + (newline * 2 if content else '') + block + newline


def updated_text(content: str) -> str:
    return replace_section(content, GUIDE)


def python_runtime_text(content: str, runtime: str) -> str:
    """Rebuild the owned Python section under Tools, including unmarked legacy copies."""
    newline = "\r\n" if "\r\n" in content else "\n"
    block = f"""### Python 环境

- `python` / `python3` 默认使用：`{runtime}`；临时脚本直接用 `python3 /绝对路径/script.py`，无需激活环境。
- 优先使用该环境已有依赖；不要自行下载另一套 Python 或向共享 venv 临时安装、升级依赖。
- 确需独立依赖的临时任务 spawn IT Engineer 使用同一自管解释器准备任务环境；Python 子进程使用 `sys.executable`。"""
    block = block.replace("\n", newline)
    pattern = (r"^<!-- xiaobei-python-runtime:start -->[ \t]*\r?\n.*?"
               r"^<!-- xiaobei-python-runtime:end -->[ \t]*(?:\r?\n){0,2}")
    content = re.sub(pattern, '', content, flags=re.M | re.S)
    content = remove_sections(content, {(3, 'Python 环境'), (3, '小贝 Python 环境')})
    headings = list(markdown_headings(content))
    for index, (_, _, level, title) in enumerate(headings):
        if level == 2 and title == 'Tools':
            end = next((pos for pos, _, depth, _ in headings[index + 1:] if depth <= level), len(content))
            before = content[:end].rstrip('\r\n')
            after = content[end:]
            suffix = newline * 2 + after if after else newline
            return before + newline * 2 + block + suffix
    return content.rstrip('\r\n') + newline * 2 + '## Tools' + newline * 2 + block + newline


def main() -> None:
    action, filename, *args = sys.argv[1:]
    path = Path(filename)
    original = path.read_bytes()
    content = original.decode("utf-8")
    if action == "newline" and not args:
        revised = updated_text(content)
    elif action == "python-runtime" and len(args) == 1:
        revised = python_runtime_text(content, args[0])
    elif action == "replace" and len(args) == 1:
        # Render only the new block. Literal @@WS@@ in user notes must stay untouched.
        block = sys.stdin.buffer.read().decode("utf-8").replace("@@WS@@", args[0])
        revised = replace_section(content, block)
    else:
        raise SystemExit("Usage: workspace-guides.py newline FILE | replace FILE WORKSPACE | python-runtime FILE VENV")
    if path.read_bytes() != original:
        raise SystemExit("Workspace file changed while preparing guidance; retry")
    path.write_bytes(revised.encode("utf-8"))


if __name__ == "__main__":
    main()
