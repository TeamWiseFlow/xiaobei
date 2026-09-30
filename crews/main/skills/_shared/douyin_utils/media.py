"""Local media transfer using short-lived platform credentials and Relay metadata."""

from __future__ import annotations
import datetime
import json
from pathlib import Path
import secrets
import time
import zlib
from urllib.parse import quote
from .api import call
from .http import DouyinRequestError, request

PART_SIZE = 8 * 1024 * 1024


def credentials(sts):
    def get(*names):
        return next((sts[k] for k in names if sts.get(k)), None)

    expiry = get("expires_at", "expire_at", "ExpiredTime", "Expiration")
    if isinstance(expiry, str) and not expiry.isdigit():
        expiry = int(
            datetime.datetime.fromisoformat(expiry.replace("Z", "+00:00")).timestamp()
            * 1000
        )
    if expiry is not None:
        expiry = int(expiry)
        if expiry < 10**11:
            expiry *= 1000
    if not expiry or expiry <= time.time() * 1000:
        raise DouyinRequestError("UPLOAD_CREDENTIALS_EXPIRED")
    expiry = min(expiry, int(time.time() * 1000) + 23 * 3600 * 1000)
    value = {
        "access_key": get("AccessKeyID", "AccessKeyId", "access_key_id"),
        "secret_key": get("SecretAccessKey", "secret_access_key"),
        "session_token": get("SessionToken", "session_token"),
        "expires_at": expiry,
    }
    if any(not v for v in value.values()):
        raise DouyinRequestError("UPLOAD_CREDENTIALS_MISSING")
    return value


def gateway(method, query, sts, body=None):
    host = (
        "imagex.bytedanceapi.com"
        if query["Action"].endswith("ImageUpload")
        else "vod.bytedanceapi.com"
    )
    result = request(
        "media",
        "gateway-request",
        method,
        "https://" + host + "/",
        params=query,
        body=body,
        fields={"credentials": credentials(sts)},
        content_type="text/plain;charset=UTF-8"
        if body is not None and host.startswith("vod")
        else None,
        timeout=60,
    )
    if result.get("ResponseMetadata", {}).get("Error"):
        raise DouyinRequestError("UPLOAD_GATEWAY_REJECTED")
    if not isinstance(result.get("Result"), dict):
        raise DouyinRequestError("UPLOAD_GATEWAY_RESULT_MISSING")
    return result["Result"]


def transfer(node, expiry, query="", data=None, user_id="", finish=False):
    fields = {
        "credentials": {
            "upload_host": node["upload_host"],
            "store_uri": node["store_uri"],
            "upload_auth": node["auth"],
            "expires_at": expiry,
        },
    }
    if user_id:
        fields["user_id"] = str(user_id)
    if data is not None and not finish:
        fields.update(
            content_length=len(data),
            content_crc32=f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        )
    if finish:
        result = request_text_finish(node, fields, query, data)
    else:
        result = request(
            "media",
            "transfer-request",
            "POST",
            "https://"
            + node["upload_host"]
            + "/upload/v1/"
            + node["store_uri"]
            + query,
            fields=fields,
            payload=data,
            timeout=300,
            content_type="application/octet-stream",
        )
    if result.get("code") not in (2000, 0):
        raise DouyinRequestError("UPLOAD_TRANSFER_REJECTED")
    return result


def request_text_finish(node, fields, query, data):
    # A checksum list is small UTF-8 metadata; file chunks never enter Relay.
    return request(
        "media",
        "transfer-request",
        "POST",
        "https://" + node["upload_host"] + "/upload/v1/" + node["store_uri"] + query,
        body_text=data.decode(),
        fields=fields,
        content_type="text/plain",
        timeout=60,
    )


def upload_bytes(path, node, expiry, user_id=""):
    size = path.stat().st_size
    if size <= PART_SIZE:
        return transfer(node, expiry, data=path.read_bytes(), user_id=user_id)
    upload_id = node.get("upload_id")
    if not upload_id:
        upload_id = (
            transfer(node, expiry, "?uploadmode=part&phase=init", user_id=user_id).get(
                "data"
            )
            or {}
        ).get("uploadid")
    if not upload_id:
        raise DouyinRequestError("UPLOAD_ID_MISSING")
    checks = []
    offset = 0
    with path.open("rb") as stream:
        while chunk := stream.read(PART_SIZE):
            index = len(checks) + 1
            crc = f"{zlib.crc32(chunk) & 0xFFFFFFFF:08x}"
            transfer(
                node,
                expiry,
                f"?uploadid={quote(str(upload_id))}&part_number={index}&phase=transfer&part_offset={offset}",
                chunk,
                user_id,
            )
            checks.append(crc)
            offset += len(chunk)
    return transfer(
        node,
        expiry,
        f"?uploadmode=part&phase=finish&uploadid={quote(str(upload_id))}",
        ",".join(f"{i}:{c}" for i, c in enumerate(checks, 1)).encode(),
        user_id,
        finish=True,
    )


def upload(path, kind, *, user_id="", sts=None, space=None, functions=None, gcm=False):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("MEDIA_FILE_MISSING")
    if kind not in ("image", "video", "audio", "object"):
        raise ValueError("INVALID_MEDIA_KIND")
    if sts is None:
        response = call("upload_auth")
        raw = response.get("auth")
        sts = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(sts, dict):
            raise DouyinRequestError("UPLOAD_CREDENTIALS_MISSING")
    creds = credentials(sts)
    imagex = kind == "image" and not space
    common = (
        {
            "Version": "2018-08-01",
            "ServiceId": "jm8ajry58r",
            "app_id": "2906",
            "user_id": str(user_id),
        }
        if imagex
        else {
            "Version": "2020-11-19",
            "SpaceName": space or "aweme",
            **({} if space else {"app_id": "2906", "user_id": str(user_id)}),
        }
    )
    query = {"Action": "ApplyImageUpload" if imagex else "ApplyUploadInner", **common}
    if imagex:
        query["s"] = str(secrets.randbelow(10**12))
    else:
        query.update(FileType=kind, IsInner="1", FileSize=path.stat().st_size)
        if space:
            query["NeedFallback"] = "true"
        else:
            query["s"] = str(secrets.randbelow(10**12))
        if gcm:
            query["OpenGcmEnc"] = "true"
    result = gateway("GET", query, sts)
    addr = (
        result.get("UploadAddress")
        if imagex
        else next(
            iter((result.get("InnerUploadAddress") or {}).get("UploadNodes", [])), None
        )
    )
    if not addr or not addr.get("StoreInfos"):
        raise DouyinRequestError("UPLOAD_ADDRESS_MISSING")
    store = addr["StoreInfos"][0]
    node = {
        "store_uri": store["StoreUri"],
        "auth": store["Auth"],
        "upload_host": addr["UploadHosts"][0] if imagex else addr["UploadHost"],
        "session_key": addr["SessionKey"],
        "upload_id": store.get("UploadID", ""),
    }
    upload_bytes(path, node, creds["expires_at"], user_id)
    query = {"Action": "CommitImageUpload" if imagex else "CommitUploadInner", **common}
    body = {"SessionKey": node["session_key"]}
    if not imagex:
        body["Functions"] = (
            functions
            if functions is not None
            else [
                {"name": "GetMeta"},
                {"name": "Snapshot", "input": {"SnapshotTime": 0}},
            ]
        )
    # Refresh creator video credentials for commit; IM keeps its selected space.
    if kind == "video" and not space:
        refreshed = call("upload_auth").get("auth")
        sts = json.loads(refreshed) if isinstance(refreshed, str) else refreshed
    result = gateway("POST", query, sts, body)
    items = result.get("PluginResult") if imagex else result.get("Results")
    if not isinstance(items, list) or not items:
        raise DouyinRequestError("UPLOAD_COMMIT_RESULT_MISSING")
    info = items[0]
    if space:
        return info
    if imagex:
        return {
            "uri": info["ImageUri"],
            "width": int(info.get("ImageWidth", 0)),
            "height": int(info.get("ImageHeight", 0)),
        }
    meta = info.get("SourceInfo") or info.get("VideoMeta") or {}
    if not info.get("Vid"):
        raise DouyinRequestError("VIDEO_ID_MISSING")
    return {
        "vid": info["Vid"],
        "poster_uri": info.get("PosterUri", ""),
        "width": int(meta.get("Width", 0)),
        "height": int(meta.get("Height", 0)),
        "duration": float(meta.get("Duration", 0)),
        "size": int(meta.get("Size", 0)),
    }
