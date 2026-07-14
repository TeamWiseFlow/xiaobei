#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path


def state_path() -> Path:
    return Path.home() / ".openclaw" / "workspace-main" / "pending-followup.json"


def atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    path = state_path()
    if not path.exists():
        print(json.dumps({"status": "none"}, ensure_ascii=False, indent=2))
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "completed"
    payload["completedAt"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(path, payload)
    print(json.dumps({"status": "completed", "message": payload.get("message")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
