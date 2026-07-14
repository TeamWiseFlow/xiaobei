#!/usr/bin/env python3
"""apply-awada-config.py — 把 awada channel + customerDB hook 合并进运行中的 openclaw.json。

读同目录 ../openclaw-awada-sample.json 作模板，提示输入 relayBaseUrl/ofbKey/lane/platform，
合并进 ~/.openclaw/openclaw.json 的 channels.awada 与 plugins，原子写回（先备份）。
不重启 Gateway（由调用方人工确认后执行）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent / "openclaw-awada-sample.json"
TARGET = Path(os.path.expanduser("~/.openclaw/openclaw.json"))
WISEFLOW_ROOT = Path(os.path.expanduser(
    os.environ.get("WISEFLOW_PROJECT_ROOT", "~/wiseflow-pro")
)).resolve()


def deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def prompt(label: str, default: str) -> str:
    val = input(f"{label} [{default}]: ").strip()
    return val or default


def main() -> int:
    if not SAMPLE.exists():
        print(f"ERROR: sample not found: {SAMPLE}", file=sys.stderr)
        return 1
    if not TARGET.exists():
        print(f"ERROR: target not found: {TARGET}", file=sys.stderr)
        return 1

    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))

    relay_base_url = prompt("relayBaseUrl", "https://relay.wiseflow.example.com")
    ofb_key = prompt("ofbKey", "<OFB_KEY>")
    lane = prompt("lane", "user")
    platform = prompt("platform", "wecom")

    sample.setdefault("channels", {}).setdefault("awada", {})
    sample["channels"]["awada"]["relayBaseUrl"] = relay_base_url
    sample["channels"]["awada"]["ofbKey"] = ofb_key
    sample["channels"]["awada"]["lane"] = lane
    sample["channels"]["awada"]["platform"] = platform

    # 渲染占位符
    def render(obj):
        if isinstance(obj, str):
            return (obj
                    .replace("{WISEFLOW_PROJECT_ROOT}", str(WISEFLOW_ROOT))
                    .replace("{HOME}", os.path.expanduser("~")))
        if isinstance(obj, dict):
            return {k: render(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [render(x) for x in obj]
        return obj

    overlay = render(sample)

    # 备份
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = TARGET.with_suffix(f".json.bak-{ts}")
    shutil.copy2(TARGET, bak)
    print(f"backup: {bak}")

    cfg = json.loads(TARGET.read_text(encoding="utf-8"))
    cfg = deep_merge(cfg, overlay)

    # 原子写回
    tmp = TARGET.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, TARGET)
    print(f"updated: {TARGET}")
    print("next: 确认后执行 systemctl --user restart openclaw-gateway.service")
    return 0


if __name__ == "__main__":
    sys.exit(main())
