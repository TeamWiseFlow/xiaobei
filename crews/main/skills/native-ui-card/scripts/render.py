#!/usr/bin/env python3
"""Render a self-contained group-chat card or a three-page Q&A discussion."""

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SIZE = (2160, 2880)


def required(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"缺少非空字段: {key}")
    return value.strip()


def esc(value):
    return html.escape(str(value), quote=True)


def emphasized(value, highlight=""):
    value = str(value)
    if not highlight:
        return esc(value)
    if highlight not in value:
        raise ValueError(f"金句不在正文中: {highlight}")
    before, after = value.split(highlight, 1)
    return f'{esc(before)}<span class="hl">{esc(highlight)}</span>{esc(after)}'


class Avatars:
    def __init__(self, spec_path, output, sources):
        self.spec_path = spec_path
        self.output = output
        self.sources = sources
        self.saved = {}
        self.manifest = []

    def add(self, value):
        value = value or "avatar-01.jpg"
        if value in self.saved:
            return self.saved[value]
        if re.fullmatch(r"avatar-\d{2}\.jpg", value):
            source = ASSETS / "avatars" / "square" / value
        else:
            source = Path(value)
            if not source.is_absolute():
                source = self.spec_path.parent / source
        source = source.resolve()
        if not source.is_file():
            raise ValueError(f"头像不存在: {source}")
        with Image.open(source) as image:
            if min(image.size) < 80:
                raise ValueError(f"头像尺寸太小（至少 80×80）: {source}")
            normalized = ImageOps.fit(image.convert("RGB"), (320, 320), method=Image.Resampling.LANCZOS)
            name = hashlib.sha256(str(source).encode()).hexdigest()[:12] + ".jpg"
            dest = self.output / "assets" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            normalized.save(dest, quality=92)
        rel = f"assets/{name}"
        self.saved[value] = rel
        self.manifest.append({"input": value, "source": str(source), "origin": self.sources.get(value, "bundled" if source.is_relative_to(ASSETS) else "unspecified"), "output": rel})
        return rel


def head(title, css):
    return f'<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{esc(title)}</title><style>{css}</style></head><body>'


CHECK = """<script>
window.addEventListener('load', () => setTimeout(() => {
 const flow = document.querySelector('[data-flow]');
 const result = {body: document.body.scrollHeight, flow: flow.scrollHeight,
   available: flow.clientHeight, images: [...document.images].every(i => i.complete && i.naturalWidth > 0)};
 const node = document.createElement('div'); node.id = 'card-check';
 node.style.display = 'none'; node.textContent = JSON.stringify(result);
 document.body.appendChild(node);
}, 300));
</script></body></html>"""


def group_html(spec, avatars):
    data = spec["group"]
    before, after = data.get("before"), data.get("after")
    if not isinstance(before, list) or len(before) < 2 or not isinstance(after, list) or len(after) < 3:
        raise ValueError("群聊需要至少 2 条日常铺垫和 3 条围观回复")
    css = (ASSETS / "group.css").read_text()
    out = head(spec["title"], css)
    out += f'<div class="chat-nav"><div class="back">‹</div><div class="group-info"><div class="group-name">{esc(required(data,"name"))}</div><div class="group-sub">{esc(required(data,"members"))}人</div></div><div class="more">⋯</div></div><div class="stream" data-flow>'

    def message(item, me=False):
        nick = required(item, "nick")
        body = emphasized(required(item, "text"), item.get("highlight", ""))
        avatar = avatars.add(item.get("avatar", "avatar-29.jpg" if me else None))
        return f'<div class="msg{" me" if me else ""}"><img class="avatar" src="{esc(avatar)}"><div class="body"><div class="nick">{esc(nick)}</div><div class="bubble">{body}</div></div></div>'

    out += f'<div class="time">{esc(data.get("time_before", "昨天 21:40"))}</div>'
    out += "".join(message(item) for item in before)
    out += f'<div class="time">{esc(data.get("time_point", "今天 09:58"))}</div>'
    out += message({"nick": data.get("self_name", "我"), "text": required(data, "point"), "highlight": required(data, "highlight"), "avatar": data.get("self_avatar", "avatar-29.jpg")}, True)
    out += message({"nick": data.get("self_name", "我"), "text": required(data, "apology"), "avatar": data.get("self_avatar", "avatar-29.jpg")}, True)
    out += f'<div class="time">{esc(data.get("time_after", "刚刚"))}</div>'
    out += "".join(message(item) for item in after)
    return out + '</div><div class="input-bar"><div class="input-ph">发消息</div><div class="mic">🎤</div></div>' + CHECK


def comment(item, avatars):
    avatar = avatars.add(item.get("avatar"))
    body = emphasized(required(item, "text"), item.get("highlight", ""))
    out = f'<div class="c"><img class="avatar" src="{esc(avatar)}"><div class="body"><div class="nick-row"><span class="nick">{esc(required(item,"nick"))}</span></div><div class="text">{body}</div>'
    if item.get("meta"):
        out += f'<div class="meta">{esc(item["meta"])}</div>'
    reply = item.get("reply")
    if reply:
        out += f'<div class="sub-reply"><div class="nick">{esc(required(reply,"nick"))} 回复 {esc(item["nick"])}</div><div class="text">{emphasized(required(reply,"text"), reply.get("highlight", ""))}</div></div>'
    return out + '</div></div>'


def qa_html(spec, avatars, page):
    data = spec["qa"]
    css = (ASSETS / "qa.css").read_text()
    out = head(f'{spec["title"]} · {page}/3', css)
    search = required(data, "search")
    out += f'<div class="top-nav"><div class="nav-row"><div class="nav-tabs"><span class="tab">关注</span><span class="tab active">推荐</span></div><div>⋯</div></div><div class="search-bar">🔍 大家都在搜：{esc(search)}</div></div>'
    if page == 1:
        question = required(data, "question")
        if search == question:
            raise ValueError("搜索框须使用与主问题不同的相关搜索词")
        out += f'<div class="question"><div class="q-title">{esc(question)}</div>'
        tags = data.get("tags", [])
        out += '<div class="q-tags">' + ''.join(f'<span class="q-tag">#{esc(str(tag).lstrip("#"))}</span>' for tag in tags) + '</div>'
        stats = data.get("stats", {})
        if stats:
            out += '<div class="q-meta">' + ''.join(f'<span>{esc(label)} <b>{esc(stats[label])}</b></span>' for label in ("关注", "回答", "浏览") if label in stats) + '</div>'
        out += '</div>'
        answerer = data["answerer"]
        out += f'<div class="answerer"><img class="a-avatar" src="{esc(avatars.add(answerer.get("avatar","avatar-29.jpg")))}"><div class="a-info"><div class="a-name">{esc(required(answerer,"nick"))} <span class="a-badge">主回答</span></div></div><div class="a-follow">+ 关注</div></div>'
        out += f'<div class="comments" data-flow><div class="c answer-only"><div class="body"><div class="text">{emphasized(required(data,"answer"),required(data,"answer_highlight"))}</div></div></div></div>'
    else:
        pages = data.get("pages", [])
        if len(pages) != 2 or any(not isinstance(p, list) or len(p) < 2 for p in pages):
            raise ValueError("问答式需要两页连续跟帖，每页至少 2 条")
        if not any(item.get("reply") for item in pages[0]):
            raise ValueError("问答图 2 至少需要一条楼中楼回复")
        if not pages[1][-1].get("highlight"):
            raise ValueError("问答图 3 的最后一条跟帖需要高亮收束金句")
        out += '<div class="comment-title">主回答下的讨论</div><div class="comments" data-flow>'
        out += ''.join(comment(item, avatars) for item in pages[page - 2])
        out += '</div>'
    footer = data.get("footer", {})
    caption = footer.get("caption", data.get("question", ""))
    author = footer.get("author", required(data["answerer"], "nick"))
    avatar = avatars.add(footer.get("avatar", data["answerer"].get("avatar", "avatar-29.jpg")))
    out += f'<div class="bottom-bar"><div class="video-cap">{esc(caption)}</div><div class="action-row"><div class="author"><img class="a-avatar" src="{esc(avatar)}"><span class="a-name">{esc(author)}</span><span class="follow">+关注</span></div></div></div>'
    return out + CHECK


def inspect(chrome, html_file):
    result = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=1500", "--window-size=1080,1440", "--dump-dom", html_file.as_uri()], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError(f"Chrome DOM 检查失败: {result.stderr[-600:]}")
    match = re.search(r'<div id="card-check"[^>]*>(.*?)</div>', result.stdout)
    if not match:
        raise RuntimeError("Chrome 未返回版面检查结果")
    check = json.loads(html.unescape(match.group(1)))
    validate_layout(check)


def validate_layout(check):
    problems = []
    if check["body"] > 1442:
        problems.append(f"整页高度 {check['body']}px 超过上限 1442px（通常是一屏放不下，需要精简整体内容或减少群聊消息条数）")
    if check["flow"] > check["available"] + 2:
        problems.append(f"讨论流高度 {check['flow']}px 超过可视区 {check['available']}px（群聊/问答消息条数过多或单条太长，请删减或缩短文案）")
    if not check["images"]:
        problems.append("头像加载失败（头像文件缺失、路径错误或图片损坏，请检查 card.json 中所有 avatar 字段）")
    if problems:
        raise ValueError("版面溢出：" + "；".join(problems))


def screenshot(chrome, html_file, png):
    result = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files", "--virtual-time-budget=1500", "--window-size=1080,1440", "--force-device-scale-factor=2", f"--screenshot={png}", html_file.as_uri()], capture_output=True, text=True, timeout=40)
    if result.returncode or not png.is_file():
        raise RuntimeError(f"Chrome 截图失败: {result.stderr[-600:]}")
    finish_png(png)


def finish_png(png):
    with Image.open(png) as image:
        if image.width < SIZE[0] or image.height < SIZE[1]:
            raise ValueError(f"截图尺寸不足: {image.size}")
        image.convert("RGB").crop((0, 0, *SIZE)).save(png)


def camoufox_call(session, *command):
    proc = subprocess.run(["camoufox-cli", "--session", session, "--json", *command], capture_output=True, text=True, timeout=40)
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"camoufox-cli 无有效响应: {proc.stderr[-600:]}") from exc
    if proc.returncode or not result.get("success"):
        raise RuntimeError(f"camoufox-cli 失败: {result.get('error', result)}")
    return result.get("data", {})


def camoufox_render(session, html_file, png):
    camoufox_call(session, "open", html_file.as_uri())
    check = camoufox_call(session, "eval", "({body:document.body.scrollHeight,flow:document.querySelector('[data-flow]').scrollHeight,available:document.querySelector('[data-flow]').clientHeight,images:[...document.images].every(i=>i.complete&&i.naturalWidth>0)})")["result"]
    validate_layout(check)
    dimensions = camoufox_call(session, "eval", "(document.body.style.zoom='2',({width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight}))")["result"]
    if dimensions["width"] < SIZE[0] or dimensions["height"] < SIZE[1]:
        raise RuntimeError(f"camoufox-cli 无法生成 2x 截图: {dimensions}")
    camoufox_call(session, "screenshot", "--full", str(png))
    finish_png(png)


def find_chrome(allow_camoufox=True):
    system = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if system:
        return system
    if allow_camoufox and shutil.which("camoufox-cli"):
        return None
    raise RuntimeError("缺少 Chrome/Chromium；请安装用于本地卡片渲染的 Chromium")


def main():
    parser = argparse.ArgumentParser(description="把群聊误发式或问答式连续讨论流文案渲染为 3:4 PNG")
    parser.add_argument("--input", required=True, type=Path, help="内容 JSON")
    parser.add_argument("--output", required=True, type=Path, help="作品目录")
    parser.add_argument("--force", action="store_true", help="覆盖同名生成文件")
    args = parser.parse_args()
    spec_path = args.input.resolve()
    spec = json.loads(spec_path.read_text())
    if not isinstance(spec, dict):
        raise ValueError("内容 JSON 顶层必须是对象")
    form = spec.get("form")
    platform = spec.get("platform")
    if form not in ("group", "qa") or platform not in ("xhs", "douyin"):
        raise ValueError("form 必须为 group/qa，platform 必须为 xhs/douyin")
    title = required(spec, "title")
    body = required(spec, "body")
    tags = spec.get("topics", [])
    if not isinstance(tags, list) or len(tags) > 10 or any(not isinstance(t, str) or not t.strip() for t in tags):
        raise ValueError("topics 必须为最多 10 个非空话题")
    if len(title) > 20 or len(body) + sum(len(t) + 2 for t in tags) > 1000:
        raise ValueError("标题超过 20 字，或正文加话题超过 1000 字")
    if not isinstance(spec.get("avatar_sources", {}), dict):
        raise ValueError("avatar_sources 必须是路径到来源的对象")
    output = args.output.resolve()
    names = ["page-01"] if form == "group" else ["page-01", "page-02", "page-03"]
    targets = [output / f"{n}.{ext}" for n in names for ext in ("html", "png")]
    targets += [output / n for n in ("note.md", "dna-meta.json", "assets-manifest.json")]
    # card.json 是输入文件（workflow 要求先写入作品目录），不参与「已有同名作品」判断；
    # 只有真正由本工具生成的产物存在时才需要 --force 覆盖。
    if not args.force and any(p.exists() for p in targets):
        raise ValueError("输出目录已有本工具生成的产物（page-*.png/html、note.md、dna-meta.json 或 assets-manifest.json）；修订时显式加 --force")
    chrome = find_chrome(allow_camoufox=platform != "douyin")
    session = f"native-ui-card-{os.getpid()}-{uuid.uuid4().hex[:8]}" if chrome is None else None
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=f".{output.name}-card-", dir=output.parent) as temporary:
            stage = Path(temporary)
            avatars = Avatars(spec_path, stage, spec.get("avatar_sources", {}))
            for index, name in enumerate(names, 1):
                content = group_html(spec, avatars) if form == "group" else qa_html(spec, avatars, index)
                path = stage / f"{name}.html"
                path.write_text(content)
                if chrome:
                    inspect(chrome, path)
                    screenshot(chrome, path, stage / f"{name}.png")
                else:
                    camoufox_render(session, path, stage / f"{name}.png")
            note = f'# {title}\n\n{body}\n'
            if tags:
                # body 已内联话题时不重复追加；只补 body 里缺失的话题（避免 note.md 标签重复两遍）
                body_has = set(re.findall(r"#([^\s#]+)", body))
                missing = [t for t in tags if t.lstrip('#') not in body_has]
                if missing:
                    note += '\n' + ' '.join('#' + t.lstrip('#') for t in missing) + '\n'
            (stage / "note.md").write_text(note)
            (stage / "dna-meta.json").write_text(json.dumps({"platform": platform, "dna_id": required(spec, "dna_id"), "content_type": "post", "form": f"native-ui-{form}"}, ensure_ascii=False, indent=2) + "\n")
            shutil.copyfile(spec_path, stage / "card.json")
            (stage / "assets-manifest.json").write_text(json.dumps(avatars.manifest, ensure_ascii=False, indent=2) + "\n")
            output.mkdir(parents=True, exist_ok=True)
            if args.force:
                for page in ("page-01", "page-02", "page-03"):
                    if page not in names:
                        for ext in ("html", "png"):
                            (output / f"{page}.{ext}").unlink(missing_ok=True)
            shutil.copytree(stage / "assets", output / "assets", dirs_exist_ok=True)
            for item in stage.iterdir():
                if item.is_file():
                    item.replace(output / item.name)
    finally:
        if session:
            subprocess.run(["camoufox-cli", "--session", session, "--json", "close"], capture_output=True, timeout=15)
    print(json.dumps({"ok": True, "form": form, "platform": platform, "images": [str(output / f"{n}.png") for n in names], "note": str(output / "note.md")}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"native-ui-card: {exc}", file=sys.stderr)
        sys.exit(1)
