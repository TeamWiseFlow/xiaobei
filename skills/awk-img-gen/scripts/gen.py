#!/usr/bin/env python3
"""百炼图像生成与编辑；支持业务空间和 Agent Plan，模型不可用时在当前模式内回退。"""
import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ── 端点与模型 ────────────────────────────────────────────────────────────────

WS_BASE_TEMPLATE = "https://{wsid}.cn-beijing.maas.aliyuncs.com/api/v1"
AGENT_PLAN_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1"
GEN_PATH = "/services/aigc/multimodal-generation/generation"

# 业务空间模型候选链（主力 → fallback，用户 --model 显式指定时关闭 fallback）
WS_MODEL_CHAIN = ["qwen-image-3.0-pro", "qwen-image-3.0", "qwen-image-2.0-pro-2026-06-22"]
# Agent Plan 默认 Qwen Image 3.0 Pro，模型不可用时回退万相
PLAN_MODEL_CHAIN = ["qwen-image-3.0-pro", "wan2.7-image-pro", "wan2.7-image"]

# 触发候选链 fallback 的 HTTP 状态码（模型未开通 / 未找到 / 无权限）
MODEL_UNAVAILABLE_CODES = {403, 404}
# 400 需结合 body 判断（可能是模型不存在，也可能是参数错——参数错不 fallback）
MODEL_ERROR_BODY_HINTS = ("modelnotfound", "model not found", "not exist", "unsupported model", "access denied")

REQUEST_TIMEOUT = 300

# ── size 校验（qwen-image 系文档：总像素 [512*512, 2048*2048]，宽高比 [1/8, 8]）──

DEFAULT_SIZE = "2048*2048"  # 1:1
MIN_TOTAL_PIXELS = 512 * 512        # 262144
MAX_TOTAL_PIXELS = 2048 * 2048      # 4194304
MIN_ASPECT_RATIO = 1 / 8
MAX_ASPECT_RATIO = 8

# 推荐尺寸（qwen-image 2.0/3.0 文档推荐值，DashScope 风格 * 分隔）
SIZE_PRESETS = {
    "2048*2048": "1:1 (默认)",
    "2688*1536": "16:9",
    "1536*2688": "9:16",
    "2368*1728": "4:3",
    "1728*2368": "3:4",
}

IMAGE_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".bmp": "image/bmp", ".tiff": "image/tiff", ".webp": "image/webp",
}


# ── 模式解析 ─────────────────────────────────────────────────────────────────

def resolve_mode(platform: str = "auto") -> tuple[str, str, list[str], str]:
    """返回 (base, key, chain, mode)。auto 优先业务空间；显式模式只读对应凭据。"""
    if platform in ("auto", "dashscope"):
        wsid = (os.environ.get("WORKSPACE_ID") or "").strip()
        key = (
            (os.environ.get("MODELSTUDIO_API_KEY") or "").strip()
            or (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
        )
        if wsid and key:
            return WS_BASE_TEMPLATE.format(wsid=wsid), key, WS_MODEL_CHAIN, "workspace"
        if platform == "dashscope":
            print("[error] --platform dashscope 需要 WORKSPACE_ID + MODELSTUDIO_API_KEY（或 DASHSCOPE_API_KEY），不会切换到 Agent Plan", file=sys.stderr)
            sys.exit(1)
        if wsid:
            print("[warn] WORKSPACE_ID 已配置但 MODELSTUDIO_API_KEY/DASHSCOPE_API_KEY 缺失，尝试 agent plan", file=sys.stderr)
    key = (os.environ.get("AWK_API_KEY") or "").strip()
    if key:
        return AGENT_PLAN_BASE, key, PLAN_MODEL_CHAIN, "agent-plan"
    if platform == "plan":
        print("[error] --platform plan 需要 AWK_API_KEY（百炼 Agent Plan key），不会切换到业务空间", file=sys.stderr)
        sys.exit(1)
    print("[error] 百炼生图凭据未配置：需要以下任一组凭据", file=sys.stderr)
    print("  - 业务空间：WORKSPACE_ID + MODELSTUDIO_API_KEY（或 DASHSCOPE_API_KEY）", file=sys.stderr)
    print("  - agent plan：AWK_API_KEY（token-plan 端点）", file=sys.stderr)
    sys.exit(1)


# ── size 处理 ────────────────────────────────────────────────────────────────

def _parse_size(size_str: str) -> tuple[int, int] | None:
    """解析 WxH / W*H / W×H 字符串。失败返回 None。"""
    m = re.match(r"^\s*(\d+)\s*[xX×*]\s*(\d+)\s*$", size_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def normalize_size(size_str: str) -> str:
    """校验并规范化 size 为 DashScope 风格 'W*H'；'auto' 原样放行；无效报错退出。"""
    if size_str.strip().lower() == "auto":
        return "auto"
    parsed = _parse_size(size_str)
    if parsed is None:
        _print_size_error(size_str, "格式必须是 'WxH'（或 W*H）或 'auto'")
        sys.exit(1)
    w, h = parsed
    total = w * h
    ratio = w / h if h != 0 else 0
    if total < MIN_TOTAL_PIXELS:
        _print_size_error(size_str, f"总像素 {total} 低于百炼最小值 {MIN_TOTAL_PIXELS}（512x512）")
        sys.exit(1)
    if total > MAX_TOTAL_PIXELS:
        _print_size_error(size_str, f"总像素 {total} 高于百炼最大值 {MAX_TOTAL_PIXELS}（2048x2048）")
        sys.exit(1)
    if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        _print_size_error(size_str, f"宽高比 {ratio:.4f} 超出百炼范围 [1/8, 8]")
        sys.exit(1)
    return f"{w}*{h}"


def _print_size_error(size_str: str, reason: str) -> None:
    print(f"[error] --image-size '{size_str}' 无效：{reason}", file=sys.stderr)
    print("[info] 推荐尺寸（总像素 512x512 ~ 2048x2048，宽高比 1:8 ~ 8:1）：", file=sys.stderr)
    for s, r in SIZE_PRESETS.items():
        print(f"    {s} ({r})", file=sys.stderr)


# ── 图像引用解析 ──────────────────────────────────────────────────────────────

def resolve_image_ref(value: str) -> str:
    """把 --image 入参解析为生成接口可接受的引用：URL / data URI 原样，本地文件转 data URI。"""
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value)
    if not path.is_file():
        print(f"[error] 参考图不存在: {value}", file=sys.stderr)
        sys.exit(1)
    mime = IMAGE_MIME_BY_EXT.get(path.suffix.lower()) or mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ── Payload 构造 ─────────────────────────────────────────────────────────────

def build_payload(args: argparse.Namespace, model: str) -> dict:
    """构造百炼 multimodal-generation 请求体（model 由调用方传入，便于候选链 fallback）。"""
    content: list[dict] = []

    # 编辑模式：1-3 张参考图在前，text 在后（qwen-image 3.0/2.0 与 wan2.7-image 同构）
    is_edit_mode = bool(args.image)
    if is_edit_mode:
        for ref in (args.image, args.image2, args.image3):
            if ref:
                content.append({"image": resolve_image_ref(ref)})

    content.append({"text": args.prompt})

    parameters: dict = {
        "watermark": bool(args.watermark),
        # 默认关 prompt 改写：封面/海报场景要精确渲染指定文字，扩写会破坏布局指令。
        # 需要模型自动扩写润色时显式 --prompt-extend。
        "prompt_extend": bool(args.prompt_extend),
    }
    if args.seed is not None:
        parameters["seed"] = args.seed
    if is_edit_mode:
        # 编辑模式默认不指定 size（跟随输入图）；显式传了才带上
        if args.image_size:
            parameters["size"] = normalize_size(args.image_size)
    else:
        parameters["size"] = normalize_size(args.image_size or DEFAULT_SIZE)

    return {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }


# ── API 调用 ────────────────────────────────────────────────────────────────

class ImgGenHTTPError(Exception):
    """生成接口 HTTP 错误（携带状态码与响应体，供 main 做候选链 fallback 决策）。"""

    def __init__(self, code: int, body: str) -> None:
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def is_model_unavailable(exc: ImgGenHTTPError) -> bool:
    """判断 HTTP 错误是否属于"模型层不可用"（可沿候选链 fallback）。

    403/404 直接算；400 需 body 命中模型类错误关键词（参数错的 400 不 fallback，
    换模型也一样错，快速失败暴露真实原因）。
    """
    if exc.code in MODEL_UNAVAILABLE_CODES:
        return True
    if exc.code == 400:
        lowered = exc.body.lower()
        return any(hint in lowered for hint in MODEL_ERROR_BODY_HINTS)
    return False


def api_request(url: str, payload: dict, api_key: str) -> dict:
    """调用生成接口；返回解析后的 JSON。失败抛 ImgGenHTTPError。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise ImgGenHTTPError(e.code, body)


def extract_image_urls(resp: dict) -> list[str]:
    """从响应提取图片 URL：output.choices[*].message.content[*].image。"""
    urls: list[str] = []
    output = resp.get("output") or {}
    for choice in output.get("choices") or []:
        message = choice.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("image"):
                    urls.append(item["image"])
        elif isinstance(content, str) and content.startswith("http"):
            urls.append(content)
    return urls


# ── 图像下载 ────────────────────────────────────────────────────────────────

def download_image(url: str, dest_path: Path) -> None:
    """下载图片到本地。链接 24h 内有效（按百炼文档）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "wiseflow-awk-img-gen/3.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest_path.write_bytes(data)


def _print_enable_guide(mode: str, failed_model: str) -> None:
    """候选链全部不可用时，输出开通指引（供 Agent 转告用户）。"""
    print("", file=sys.stderr)
    print(f"[error] 图像生成模型 {failed_model} 不可用（模式={mode}），候选链已全部尝试。", file=sys.stderr)
    if mode == "workspace":
        print("[guide] 请到阿里云百炼控制台检查业务空间模型授权：", file=sys.stderr)
        print("  1. 打开 https://bailian.console.aliyun.com/", file=sys.stderr)
        print(f"  2. 确认业务空间（WORKSPACE_ID）已授权模型：{'、'.join(WS_MODEL_CHAIN)}", file=sys.stderr)
        print("  3. 确认 MODELSTUDIO_API_KEY 属于该业务空间", file=sys.stderr)
    else:
        print("[guide] 请检查 Agent Plan（token-plan）订阅：", file=sys.stderr)
        print(f"  1. 确认订阅包含图像生成能力，模型：{'、'.join(PLAN_MODEL_CHAIN)}", file=sys.stderr)
        print("  2. 确认 AWK_API_KEY 为百炼 agent plan 的 key（sk-sp-* 形态）", file=sys.stderr)
    print("[hint] 免 key 实拍图片可退公共技能 pexels-footage / pixabay-footage（非 AI 生成）。", file=sys.stderr)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="百炼图像生成与编辑（DashScope 业务空间 / Agent Plan）"
    )
    parser.add_argument("--platform", choices=["auto", "dashscope", "plan"], default="auto", help="auto 优先百炼业务空间，再 Agent Plan；dashscope / plan 固定使用对应端点和凭据")
    parser.add_argument("--prompt", required=True, help="图像描述（要渲染的文字直接写完整句子）")
    parser.add_argument(
        "--model", default=None,
        help="Model ID（缺省按模式走候选链自动 fallback；显式指定时不 fallback）",
    )
    parser.add_argument(
        "--image-size", default=None, dest="image_size",
        help="尺寸 WxH 或 auto，文生图默认 2048x2048；编辑模式缺省跟随输入图",
    )
    parser.add_argument("--seed", type=int, default=None, help="随机种子 [0, 2147483647]")
    parser.add_argument(
        "--watermark", choices=["true", "false"], default="false",
        help="是否加水印（百炼默认 false；xiaobei 保持 false 避免后续 image 工具处理）",
    )
    parser.add_argument(
        "--prompt-extend", action="store_true", dest="prompt_extend",
        help="允许百炼自动扩写 prompt（API 默认开；本脚本默认关，保证封面文字/布局指令精确）",
    )
    # image-edit inputs（URL / data URI / 本地文件路径均可）
    parser.add_argument("--image", default=None, help="参考图 1：URL 或本地路径（启用编辑模式）")
    parser.add_argument("--image2", default=None, help="参考图 2（编辑模式，多图融合）")
    parser.add_argument("--image3", default=None, help="参考图 3（编辑模式，多图融合）")
    parser.add_argument("--out-dir", default=None, dest="out_dir", help="输出目录")
    args = parser.parse_args()

    if (args.image2 or args.image3) and not args.image:
        parser.error("--image2 / --image3 必须与 --image 一起使用")
    base, api_key, chain, mode = resolve_mode(args.platform)

    # watermark 字段百炼期望 bool（JSON），从字符串转
    args.watermark = args.watermark == "true"

    ts = int(time.time())
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"./tmp/awk-img-{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 候选模型：用户显式 --model 时不 fallback；否则按模式走候选链
    candidates = [args.model] if args.model else list(chain)
    is_edit_mode = bool(args.image)
    gen_mode = "image-edit" if is_edit_mode else "text-to-image"

    url = base + GEN_PATH
    result: dict | None = None
    for idx, cand_model in enumerate(candidates):
        payload = build_payload(args, cand_model)
        size = payload["parameters"].get("size", "-")
        print(f"[info] Mode={gen_mode} provider={mode} model={cand_model} size={size}", file=sys.stderr)
        try:
            result = api_request(url, payload, api_key)
            break
        except ImgGenHTTPError as e:
            print(f"[error] HTTP {e.code}: {e.body[:500]}", file=sys.stderr)
            is_last = idx == len(candidates) - 1
            if is_model_unavailable(e) and not is_last:
                print(f"[warn] model {cand_model} 不可用 (HTTP {e.code})，切换候选链下一个...", file=sys.stderr)
                continue
            if is_model_unavailable(e):
                _print_enable_guide(mode, cand_model)
            sys.exit(1)

    if result is None:
        _print_enable_guide(mode, candidates[-1])
        sys.exit(1)

    # 百炼响应：output.choices[0].message.content[*].image → URL（24h 有效）
    image_urls = extract_image_urls(result)
    if not image_urls:
        print(f"[error] 响应中无图片 URL: {json.dumps(result, ensure_ascii=False)[:800]}", file=sys.stderr)
        sys.exit(1)

    prompts_map: dict = {}
    for i, image_url in enumerate(image_urls):
        dest = out_dir / f"{i:02d}.png"
        print(f"[info] Downloading image {i} → {dest}", file=sys.stderr)
        download_image(image_url, dest)
        prompts_map[str(i)] = {
            "prompt": args.prompt,
            "model": result.get("model") or cand_model,
            "provider_mode": mode,
            "url": image_url,
            "file": str(dest),
        }

    (out_dir / "prompts.json").write_text(json.dumps(prompts_map, ensure_ascii=False, indent=2))

    # 简单 HTML gallery
    gallery_html = ["<!DOCTYPE html><html><body>"]
    for i in range(len(image_urls)):
        gallery_html.append(f'<img src="{i:02d}.png" style="max-width:512px;margin:4px">')
    gallery_html.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(gallery_html))

    usage = result.get("usage") or {}
    print(f"[done] {len(image_urls)} image(s) saved to {out_dir}/ (usage: {json.dumps(usage, ensure_ascii=False)})", file=sys.stderr)
    for k, v in prompts_map.items():
        print(f"  [{k}] {v['file']}", file=sys.stderr)


if __name__ == "__main__":
    main()
