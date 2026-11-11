"""Private conversation state and durable, account-scoped send receipts."""
import hashlib
import base64
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid
from .im_client import participants
from .session import write_private

STATE_DIR = Path.home() / ".openclaw" / "douyin-im"


def read(path, *, lines=False):
    path = Path(path).expanduser()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError("IM_STATE_UNSAFE")
        if st.st_size > 16 * 1024**2:
            raise ValueError("IM_STATE_TOO_LARGE")
        try:
            raw = stream.read(16 * 1024**2 + 1)
            value = [json.loads(line) for line in raw.splitlines() if line.strip()] if lines else json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("IM_STATE_INVALID") from exc
    if not lines and not isinstance(value, dict):
        raise ValueError("IM_STATE_INVALID")
    return value


def conversation_path(my_id, to_id):
    return STATE_DIR / f"{my_id}-{to_id}.json"


def load_conversation(path):
    value = read(path)
    participants(value)
    return value


def save_conversation(my_id, to_id, conversation, fingerprint):
    value = {**conversation, "my_user_id": str(my_id), "to_user_id": str(to_id),
             "binding": fingerprint, "updated_at": int(time.time())}
    participants(value)
    path = conversation_path(my_id, to_id)
    write_private(path, value)
    return path, value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def receipt_path(uid, request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id):
        raise ValueError("REQUEST_ID_REQUIRED")
    return STATE_DIR / "receipts" / (digest([str(uid), request_id]) + ".json")


def start(uid, target, request_id, input_hash, fingerprint):
    path = receipt_path(uid, request_id)
    if path.exists() or path.is_symlink():
        value = read(path)
        if (value.get("input_hash") != input_hash or value.get("my_user_id") != str(uid)
                or value.get("to_user_id") != str(target)):
            raise ValueError("REQUEST_ID_CONFLICT")
        if value.get("status") in {"submitting", "unknown", "accepted", "rejected"}:
            if value["status"] == "submitting":
                update(path, value, "unknown", error="PREVIOUS_SEND_INTERRUPTED")
            return path, value, False
        if value.get("binding") != fingerprint:
            raise ValueError("IM_SESSION_CHANGED")
        return path, value, True
    value = {"version": 1, "request_id": request_id, "my_user_id": str(uid),
             "to_user_id": str(target), "input_hash": input_hash, "binding": fingerprint,
             "client_message_id": str(uuid.uuid4()), "status": "preparing"}
    update(path, value, "preparing")
    return path, value, True


def update(path, value, status, **extra):
    if status == "accepted" or "error" in extra:
        for key in ("error", "stage", "relay_info", "http_status", "request_info", "response_info"):
            if key in {"http_status", "response_info"} and value.get("response_file"):
                continue
            value.pop(key, None)
    value.update(status=status, updated_at=int(time.time()), **extra)
    write_private(path, value)


def capture_response(path, value, response):
    """Archive bounded response bytes before parsing or cookie harvesting."""
    from .http import response_info
    from .im_wire import MAX_WIRE_BYTES
    body = response.content
    captured = body[:MAX_WIRE_BYTES]
    info = response_info(response)
    target = Path(path).parent / "responses" / Path(path).name
    write_private(target, {"format_version": 1,
        **{key: value[key] for key in ("request_id", "my_user_id", "to_user_id", "client_message_id", "conversation_id")},
        "captured_at": int(time.time()), "response_info": info,
        "body_complete": len(captured) == len(body), "body_sha256": hashlib.sha256(captured).hexdigest(),
        "body_base64": base64.b64encode(captured).decode()})
    value.update(response_file=str(target), response_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                 response_info=info, http_status=response.status_code)
    write_private(path, value)


def public(value, path):
    return {"ok": value["status"] == "accepted", "status": value["status"],
            "request_id": value["request_id"], "receipt_file": str(path),
            **{k: value[k] for k in ("my_user_id", "to_user_id", "client_message_id",
                "server_message_id", "evidence", "error", "kind", "conversation_id", "stage",
                "relay_info", "http_status", "request_info", "response_info", "response_file") if k in value},
            "accepted": value["status"] == "accepted"}
