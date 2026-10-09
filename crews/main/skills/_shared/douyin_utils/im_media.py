"""IM attachment upload and business message content."""

import tempfile
import subprocess
from pathlib import Path
from .api import call
from .http import DouyinRequestError
from .media import upload
from .message import MessagePayload


def upload_attachment(path, kind, user_id, thumb=None):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("MEDIA_FILE_MISSING")
    if kind == "file" and path.stat().st_size > 10 * 1024**2:
        raise ValueError("IM_FILE_TOO_LARGE")
    if kind == "audio":
        raise ValueError("VOICE_CONTENT_REQUIRED")
    config = call("im_upload_config")
    sts = config.get("public_file_config" if kind == "file" else "public_image_config")
    if not isinstance(sts, dict) or not sts.get("space_name"):
        raise DouyinRequestError("IM_UPLOAD_CONFIG_MISSING")
    space = sts["space_name"]
    if kind == "image":
        gif = path.suffix.lower() == ".gif"
        functions = [
            {
                "name": "Encryption",
                "input": {"Config": {"copies": "cipher_v2"}},
                "PolicyParams": {
                    "policy-set": "still",
                    "still-width": "480",
                    "still-height": "480",
                }
                if gif
                else {"policy-set": "check,thumb,medium,large"},
            }
        ]
        info = upload(
            path, "image", user_id=user_id, sts=sts, space=space, functions=functions
        )
        return 27, MessagePayload._image_content(info, path.read_bytes(), gif=gif)
    if kind == "file":
        info = upload(
            path,
            "object",
            user_id=user_id,
            sts=sts,
            space=space,
            functions=[],
            gcm=True,
        )
        enc = info.get("Encryption") or info
        return 6, {
            "aweType": 15001,
            "name": path.name,
            "data_size": path.stat().st_size,
            "md5": enc.get("SourceMd5", ""),
            "skey": enc.get("SecretKey", ""),
            "uri": enc.get("Uri", ""),
            "format": path.suffix.lstrip(".").lower(),
        }
    with tempfile.TemporaryDirectory(prefix="douyin-im-cover-") as directory:
        cover = (
            Path(thumb).expanduser().resolve()
            if thumb
            else Path(directory) / "cover.jpg"
        )
        if not thumb:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    str(cover),
                ],
                capture_output=True,
                timeout=60,
            )
            if r.returncode or not cover.is_file():
                raise ValueError("IM_VIDEO_COVER_FAILED")
        inner = config.get("inner_image_config") or {}
        if not inner.get("space_name"):
            raise DouyinRequestError("IM_UPLOAD_CONFIG_MISSING")
        cover_info = upload(
            cover,
            "image",
            user_id=user_id,
            sts=sts,
            space=inner["space_name"],
            functions=[],
        )
        cover_uri = MessagePayload._plain_uri(cover_info)
    info = upload(
        path,
        "video",
        user_id=user_id,
        sts=sts,
        space=space,
        functions=[
            {
                "name": "Encryption",
                "input": {
                    "Config": {"copies": "cipher_v2", "aes_chunk_size": "524288"}
                },
                "PolicyParams": {"policy-set": "medium"},
            }
        ],
    )
    enc = info.get("Encryption") or {}
    extra = enc.get("Extra") or {}
    meta = info.get("VideoMeta") or info.get("SourceInfo") or {}
    return 30, {
        "video": {
            "tkey": enc.get("Uri") or info.get("Uri", ""),
            "md5": enc.get("SourceMd5", ""),
            "skey": enc.get("SecretKey", ""),
        },
        "poster": {
            "oid": extra.get("thumb_uri") or cover_uri,
            "md5": extra.get("thumb_md5", ""),
            "skey": extra.get("thumb_secret", ""),
        },
        "height": int(meta.get("Height", 0)),
        "width": int(meta.get("Width", 0)),
        "check_pics": [cover_uri] if cover_uri else [],
    }
