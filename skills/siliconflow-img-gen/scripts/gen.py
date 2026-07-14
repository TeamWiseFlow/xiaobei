#!/usr/bin/env python3
"""火山方舟 Seedream 图像生成（Phase 5 — D13 决策：img-gen Key 用户自带）

替代原 SiliconFlow (Qwen) 生图路径。改调火山方舟 Ark 平台
`/api/v3/images/generations` 端点（不是 `/api/coding/v3`，后者是 LLM 编码
路径；图像生成走标准推理 `/v3`）。

API key 走用户自带 `AWK_API_KEY` 环境变量（纯客户端，不入 server）。

支持模型：
  - doubao-seedream-4.5（默认，主力）
  - doubao-seedream-5.0-lite（fallback：主力不可用时自动切换）
  - doubao-seedream-3-0-t2i-250415（3.0 旧版，纯文生图，需 --model 显式指定）

参考：https://www.volcengine.com/docs/82379/1541523
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ── 常量 ─────────────────────────────────────────────────────────────────────

API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"

# 火山方舟支持的 model 列表
# 主力 doubao-seedream-4.5；fallback doubao-seedream-5.0-lite（主力不可用时自动切换）
DEFAULT_GEN_MODEL = "doubao-seedream-4.5"
DEFAULT_EDIT_MODEL = "doubao-seedream-4.5"  # 4.5 支持 image edit
FALLBACK_MODEL = "doubao-seedream-5.0-lite"
# 触发 fallback 的 HTTP 状态码（模型未开通 / 未找到 / 配额不足等模型层错误）
MODEL_UNAVAILABLE_CODES = {400, 403, 404}
DEFAULT_SIZE = "2048x2048"  # 火山默认 1:1

# 火山 size 校验（方式 2：宽x高）
# - 总像素范围 [2560x1440=3686400, 4096x4096=16777216]
# - 宽高比范围 [1/16, 16]
MIN_TOTAL_PIXELS = 2560 * 1440  # 3686400
MAX_TOTAL_PIXELS = 4096 * 4096  # 16777216
MIN_ASPECT_RATIO = 1 / 16
MAX_ASPECT_RATIO = 16

# 火山方式 1：固定 2K/3K/4K
SIZE_PRESETS_QUALITY = {"2K", "3K", "4K"}

# 推荐的 2K 分辨率（用户用得最多的）
SIZE_PRESETS_2K = {
    "2048x2048": "1:1",
    "2304x1728": "4:3",
    "1728x2304": "3:4",
    "2848x1600": "16:9",
    "1600x2848": "9:16",
    "2496x1664": "3:2",
    "1664x2496": "2:3",
    "3136x1344": "21:9",
}

RETRYABLE_STATUS_CODES = {403, 404, 429, 500, 503, 504}


# ── 校验 ─────────────────────────────────────────────────────────────────────

def _parse_size(size_str: str) -> tuple[int, int] | None:
    """解析 WxH 字符串。失败返回 None。"""
    m = re.match(r"^\s*(\d+)\s*[xX×]\s*(\d+)\s*$", size_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def validate_size(size_str: str) -> str:
    """校验火山 size 参数；无效报错退出。"""
    if size_str in SIZE_PRESETS_QUALITY:
        return size_str
    parsed = _parse_size(size_str)
    if parsed is None:
        _print_size_error(size_str, "格式必须是 'WxH' 或 '2K/3K/4K'")
        sys.exit(1)
    w, h = parsed
    total = w * h
    ratio = w / h if h != 0 else 0
    if total < MIN_TOTAL_PIXELS:
        _print_size_error(
            size_str,
            f"总像素 {total} 低于火山最小值 {MIN_TOTAL_PIXELS}（2560x1440）",
        )
        sys.exit(1)
    if total > MAX_TOTAL_PIXELS:
        _print_size_error(
            size_str,
            f"总像素 {total} 高于火山最大值 {MAX_TOTAL_PIXELS}（4096x4096）",
        )
        sys.exit(1)
    if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        _print_size_error(
            size_str,
            f"宽高比 {ratio:.4f} 超出火山范围 [{MIN_ASPECT_RATIO:.4f}, {MAX_ASPECT_RATIO}]",
        )
        sys.exit(1)
    return size_str


def _print_size_error(size_str: str, reason: str) -> None:
    print(f"[error] --image-size '{size_str}' 无效：{reason}", file=sys.stderr)
    print("[info] 合法选项：", file=sys.stderr)
    print("  方式 1（quality 预设）：2K / 3K / 4K", file=sys.stderr)
    print("  方式 2（2K 1:1 / 4:3 / 16:9 / 9:16 等）：", file=sys.stderr)
    for s, r in SIZE_PRESETS_2K.items():
        print(f"    {s} ({r})", file=sys.stderr)


# ── Payload 构造 ─────────────────────────────────────────────────────────────

def build_payload(args: argparse.Namespace, model: str) -> dict:
    """构造火山方舟 images/generations 请求体（model 由调用方传入，便于 fallback）。"""
    is_edit_mode = bool(args.image)
    payload: dict = {
        "model": model,
        "prompt": args.prompt,
    }

    # 图生图（image / image2 / image3）
    if is_edit_mode:
        # 火山支持单图或多图（URL / Base64 数组）
        images = [args.image]
        if args.image2:
            images.append(args.image2)
        if args.image3:
            images.append(args.image3)
        payload["image"] = images if len(images) > 1 else images[0]
    else:
        # 文生图：size 必填（火山默认 2048x2048）
        size = args.image_size or DEFAULT_SIZE
        payload["size"] = validate_size(size)

    # 可选参数
    if args.watermark is not None:
        payload["watermark"] = args.watermark
    if args.response_format:
        payload["response_format"] = args.response_format
    if args.seed is not None:
        payload["seed"] = args.seed

    return payload


# ── API 调用 ────────────────────────────────────────────────────────────────

class ImgGenHTTPError(Exception):
    """火山端 HTTP 错误（携带状态码与响应体，供 main 做 fallback 决策）。"""

    def __init__(self, code: int, body: str) -> None:
        super().__init__(f"HTTP {code}: {body}")
        self.code = code
        self.body = body


def api_request(payload: dict, api_key: str) -> dict:
    """调火山方舟 images/generations；返回解析后的 JSON。

    失败时抛 ImgGenHTTPError（由 main 决定是否 fallback 到备用模型）。
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"[error] HTTP {e.code}: {body}", file=sys.stderr)
        if e.code in RETRYABLE_STATUS_CODES:
            print(f"[hint] 火山端暂时不可用 (HTTP {e.code})，稍后重试", file=sys.stderr)
        raise ImgGenHTTPError(e.code, body)


# ── 图像下载 ────────────────────────────────────────────────────────────────

def download_image(url: str, dest_path: Path) -> None:
    """下载图片到本地。链接 24h 内有效（按火山文档）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "wiseflow-img-gen/2.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest_path.write_bytes(resp.read())


def _print_enable_guide(failed_model: str) -> None:
    """主力 + fallback 模型都不可用时，输出火山后台开通指引（供 Agent 转告用户）。"""
    print("", file=sys.stderr)
    print(f"[error] 图像生成模型 {failed_model} 不可用。已尝试主力 + fallback 均失败。", file=sys.stderr)
    print("[guide] 请到火山引擎后台开通视觉模型：", file=sys.stderr)
    print("  1. 打开 https://console.volcengine.com/ark/", file=sys.stderr)
    print("  2. 左侧「系统管理」→「开通管理」→「视觉模型」", file=sys.stderr)
    print("  3. 列表中找到 doubao-seedream-4.5 和 doubao-seedream-5.0-lite，点右侧「开通服务」", file=sys.stderr)
    print("[guide] 开通页面上方有 CodePlan 免费资源包活动：", file=sys.stderr)
    print("  doubao-seedream-4.5 送 200 张图，doubao-seedream-5.0-lite 送 50 张图。", file=sys.stderr)
    print("  ⚠️ 免费额度用光后，除非手动关闭服务，否则进入付费模式（额外付费）。", file=sys.stderr)
    print("  收费标准参见视觉模型页面。请提醒用户知悉。", file=sys.stderr)


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="火山方舟 Seedream 图像生成（text-to-image / image-edit）"
    )
    parser.add_argument("--prompt", required=True, help="图像描述（≤300 汉字 / 600 英文）")
    parser.add_argument(
        "--model", default=None,
        help="Model ID（默认 doubao-seedream-4.5，主力不可用时自动 fallback 到 doubao-seedream-5.0-lite；"
             "显式指定时不 fallback）",
    )
    parser.add_argument(
        "--image-size", default=None, dest="image_size",
        help="文生图尺寸。方式 1: 2K/3K/4K；方式 2: WxH（如 2048x2048）",
    )
    parser.add_argument("--seed", type=int, default=None, help="随机种子 (0-?)")
    parser.add_argument(
        "--watermark", choices=["true", "false"], default="false",
        help="是否加水印（火山默认 true；wiseflow 默认 false 避免后续 image 工具处理）",
    )
    parser.add_argument(
        "--response-format", default="url", dest="response_format",
        choices=["url", "b64_json"],
        help="返回格式：url（火山默认，链接 24h 有效）/ b64_json",
    )
    # image-edit inputs（火山 image 字段支持 URL 或 Base64）
    parser.add_argument("--image", default=None, help="源图 URL 或 Base64（启用图生图）")
    parser.add_argument("--image2", default=None, help="第二张参考图（image-edit）")
    parser.add_argument("--image3", default=None, help="第三张参考图（image-edit）")
    parser.add_argument("--out-dir", default=None, dest="out_dir", help="输出目录")
    args = parser.parse_args()

    api_key = os.environ.get("AWK_API_KEY")
    if not api_key:
        print("[error] AWK_API_KEY not set（火山方舟 API Key）", file=sys.stderr)
        sys.exit(1)

    # watermark 字段火山期望 bool（JSON），从字符串转
    args.watermark = args.watermark == "true"

    ts = int(time.time())
    out_dir = Path(args.out_dir) if args.out_dir else Path(f"./tmp/awk-img-{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 候选模型：用户显式 --model 时不 fallback；否则主力 → fallback
    is_edit_mode = bool(args.image)
    if args.model:
        candidates = [args.model]
    else:
        default_model = DEFAULT_EDIT_MODEL if is_edit_mode else DEFAULT_GEN_MODEL
        candidates = [default_model, FALLBACK_MODEL] if default_model != FALLBACK_MODEL else [default_model]

    mode = "image-edit" if is_edit_mode else "text-to-image"

    result: Optional[dict] = None
    last_code: Optional[int] = None
    for idx, cand_model in enumerate(candidates):
        payload = build_payload(args, cand_model)
        print(f"[info] Mode={mode} model={cand_model} size={payload.get('size', '-')}", file=sys.stderr)
        try:
            result = api_request(payload, api_key)
            break
        except ImgGenHTTPError as e:
            last_code = e.code
            is_last = idx == len(candidates) - 1
            if e.code in MODEL_UNAVAILABLE_CODES and not is_last:
                print(f"[warn] model {cand_model} 不可用 (HTTP {e.code})，切换 fallback...", file=sys.stderr)
                continue
            # 非模型层错误（5xx/429）或已是最后一个候选：直接失败
            if e.code in MODEL_UNAVAILABLE_CODES:
                _print_enable_guide(cand_model)
            sys.exit(1)

    if result is None:
        # 所有候选都失败（理论上上面 sys.exit 已退出，保险）
        _print_enable_guide(candidates[-1])
        sys.exit(1)

    # 火山响应：{ created, data: [{url, b64_json, size}], usage, ... }
    data = result.get("data", [])
    if not data:
        print(f"[error] No images in response: {result}", file=sys.stderr)
        sys.exit(1)

    # 检查每张图
    images: list[tuple[int, dict]] = []
    for i, item in enumerate(data):
        if "error" in item:
            print(f"[error] image[{i}] 生成失败: {item['error']}", file=sys.stderr)
            continue
        images.append((i, item))

    if not images:
        print("[error] 所有图片都生成失败，response 见上", file=sys.stderr)
        sys.exit(1)

    # 下载
    prompts_map: dict = {}
    for i, item in images:
        url = item.get("url", "")
        if not url:
            print(f"[error] image[{i}] 无 url 字段: {item}", file=sys.stderr)
            continue
        # 火山默认 jpeg；可通过 output_format 改 png
        ext = "jpg"
        dest = out_dir / f"{i:02d}.{ext}"
        print(f"[info] Downloading image {i} → {dest}", file=sys.stderr)
        download_image(url, dest)
        prompts_map[str(i)] = {"prompt": args.prompt, "url": url, "file": str(dest), "size": item.get("size", "")}

    (out_dir / "prompts.json").write_text(json.dumps(prompts_map, ensure_ascii=False, indent=2))

    # 简单 HTML gallery
    gallery_html = ["<!DOCTYPE html><html><body>"]
    for i, _ in images:
        gallery_html.append(f'<img src="{i:02d}.jpg" style="max-width:512px;margin:4px">')
    gallery_html.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(gallery_html))

    # 用量
    usage = result.get("usage", {})
    generated = usage.get("generated_images", len(images))
    print(f"[done] {len(images)} image(s) saved to {out_dir}/ (usage: generated={generated})", file=sys.stderr)
    for k, v in prompts_map.items():
        print(f"  [{k}] {v['file']} ({v['size']})", file=sys.stderr)


if __name__ == "__main__":
    main()
