#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def state_path() -> Path:
    return Path.home() / ".openclaw" / "workspace-main" / "pending-followup.json"


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a pending Main Agent followup.")
    parser.add_argument("--reason", default="gateway-restart")
    parser.add_argument("--message", default="Gateway 已重启。请发送一条消息测试新的 channel binding 是否生效。")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    payload = {
        "version": 1,
        "type": "gateway-restart-followup",
        "status": "pending",
        "reason": args.reason,
        "createdAt": now.isoformat(),
        "expiresAt": (now + timedelta(days=1)).isoformat(),
        "message": args.message,
    }
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, payload)
    print(json.dumps({"pendingFollowup": str(path), "status": "pending"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
