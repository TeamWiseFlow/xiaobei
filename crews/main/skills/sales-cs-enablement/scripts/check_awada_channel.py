#!/usr/bin/env python3
"""check_awada_channel.py — 检查 openclaw.json 是否已配置 awada channel

退出码：
  0  已配置（channels.awada 存在且非空）
  1  未配置 / 配置文件不存在 / 解析失败
  2  openclaw.json 不存在

输出：JSON 状态到 stdout，供 main agent 判断分支。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OPENCLAW_JSON = Path(
    os.environ.get("OPENCLAW_JSON", str(Path.home() / ".openclaw" / "openclaw.json"))
)


def main() -> int:
    if not OPENCLAW_JSON.exists():
        sys.stdout.write(json.dumps({
            "configured": False,
            "reason": "openclaw.json not found",
            "path": str(OPENCLAW_JSON),
        }, ensure_ascii=False))
        sys.stdout.write("\n")
        return 2
    try:
        cfg = json.loads(OPENCLAW_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        sys.stdout.write(json.dumps({
            "configured": False,
            "reason": f"parse error: {e}",
            "path": str(OPENCLAW_JSON),
        }, ensure_ascii=False))
        sys.stdout.write("\n")
        return 1

    channels = cfg.get("channels", {}) or {}
    awada = channels.get("awada")
    configured = bool(awada) and isinstance(awada, dict) and awada.get("lane") or False
    # 更宽松：只要 awada 段存在且非空即视为已配置
    configured = bool(awada) and isinstance(awada, dict) and len(awada) > 0

    sys.stdout.write(json.dumps({
        "configured": configured,
        "awada": awada,
        "path": str(OPENCLAW_JSON),
    }, ensure_ascii=False))
    sys.stdout.write("\n")
    return 0 if configured else 1


if __name__ == "__main__":
    sys.exit(main())
