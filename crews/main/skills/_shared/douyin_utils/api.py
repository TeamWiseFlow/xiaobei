"""Business endpoint client for Douyin. No dynamic computation lives here."""

from __future__ import annotations
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from .http import DouyinRequestError, _send, request, session, serialized

ENDPOINTS = json.loads(Path(__file__).with_name("endpoints.json").read_text())


def item_id(value):
    if re.fullmatch(r"\d{15,22}", str(value)):
        return str(value)
    p = urlsplit(str(value))
    if p.scheme != "https" or p.hostname not in ("www.douyin.com", "v.douyin.com"):
        raise ValueError("INVALID_ITEM_URL")
    m = re.search(r"/(?:video|note|slides)/(\d{15,22})(?:/|$)", p.path)
    if m:
        return m.group(1)
    m = re.search(r"(?:^|&)modal_id=(\d{15,22})(?:&|$)", p.query)
    if not m:
        raise ValueError("ITEM_ID_REQUIRED")
    return m.group(1)


def common(profile, state):
    device = state.state.get("device", {})
    if profile == "creator":
        return {
            "cookie_enabled": "true",
            "screen_width": device.get("screen_width", 1920),
            "screen_height": device.get("screen_height", 1080),
            "browser_language": "zh-CN",
            "browser_platform": device.get("browser_platform", "Win32"),
            "browser_name": "Mozilla",
            "browser_version": state.ua.removeprefix("Mozilla/"),
            "browser_online": "true",
            "timezone_name": "Asia/Shanghai",
            "aid": "1128",
            "support_h265": "1",
        }
    version = re.search(r"Chrome/([\d.]+)", state.ua)
    if profile == "live":
        return {
            "aid": "6383",
            "app_name": "douyin_web",
            "live_id": "1",
            "device_platform": "web",
            "language": "zh-CN",
            "enter_from": "link_share",
            "cookie_enabled": "true",
            "screen_width": device.get("screen_width", 1920),
            "screen_height": device.get("screen_height", 1080),
            "browser_language": "zh-CN",
            "browser_platform": device.get("browser_platform", "Win32"),
            "browser_name": "Chrome",
            "browser_version": version.group(1) if version else "",
            "os_name": device.get("os_name", "Windows"),
            "os_version": device.get("os_version", "10"),
        }
    return {
        "device_platform": "webapp",
        "aid": "6383",
        "channel": "channel_pc_web",
        "update_version_code": "170400",
        "pc_client_type": "1",
        "pc_libra_divert": device.get("os_name", "Windows"),
        "support_h265": "1",
        "support_dash": "1",
        "cpu_core_num": device.get("cpu_core_num", 8),
        "version_code": "170400",
        "version_name": "17.4.0",
        "cookie_enabled": "true",
        "screen_width": device.get("screen_width", 1920),
        "screen_height": device.get("screen_height", 1080),
        "browser_language": "zh-CN",
        "browser_platform": device.get("browser_platform", "Win32"),
        "browser_name": "Chrome",
        "browser_version": version.group(1) if version else "",
        "browser_online": "true",
        "engine_name": "Blink",
        "engine_version": version.group(1) if version else "",
        "os_name": device.get("os_name", "Windows"),
        "os_version": device.get("os_version", "10"),
        "device_memory": device.get("device_memory", 8),
        "platform": "PC",
        "downlink": "10",
        "effective_type": "4g",
        "round_trip_time": "0",
    }


@serialized
def csrf(host):
    if host not in ("creator.douyin.com", "live.douyin.com", "www.douyin.com"):
        raise ValueError("INVALID_CSRF_HOST")
    state = session()
    if state.security(host).get("csrf_token"):
        return
    path = (
        "/web/api/media/anchor/search"
        if host == "creator.douyin.com"
        else "/webcast/room/chat/"
        if host == "live.douyin.com"
        else "/aweme/v1/web/commit/item/digg/"
    )
    url = "https://" + host + path
    response = _send(
        "HEAD",
        url,
        headers={
            "User-Agent": state.ua,
            "Cookie": state.cookies(url),
            "Referer": "https://" + host + "/",
            "x-secsdk-csrf-request": "1",
            "x-secsdk-csrf-version": "1.2.22",
        },
        data=None,
        timeout=30,
    )
    state.harvest(response, url)
    token = response.headers.get("X-Ware-Csrf-Token", "").split(",")
    if len(token) < 2 or not token[1].strip():
        raise DouyinRequestError("CSRF_HANDSHAKE_FAILED")
    state.state.setdefault("csrf", {})[host] = {
        "token": token[1].strip(),
        "expires_at": time.time() + 600,
    }
    state.save()


def call(name, params=None, *, body=None, confirm=False, expected_uid=None):
    if name not in ENDPOINTS:
        raise ValueError("UNKNOWN_METHOD")
    e = ENDPOINTS[name]
    if params is not None and not isinstance(params, dict):
        raise ValueError("PARAMS_OBJECT_REQUIRED")
    values = {**e["defaults"], **(params or {})}
    if name == "followers" and str(values.get("max_time", "0")) == "0":
        values.update(max_time=str(int(time.time())), source_type="1")
    if name == "following":
        values["source_type"] = "2" if str(values.get("max_time", "0")) == "0" else "1"
    if any(
        not isinstance(k, str) or not isinstance(v, (str, int, float, bool))
        for k, v in values.items()
    ):
        raise ValueError("SCALAR_PARAMS_REQUIRED")
    for k in e["required"]:
        if not str(values.get(k, "")):
            raise ValueError("PARAM_REQUIRED_" + k.upper())
    if e.get("write") and not confirm:
        return {"preview": True, "method": name, "params": values, "body": body}
    host = e.get("host", "www.douyin.com")
    if e.get("write") and host in (
        "www.douyin.com",
        "creator.douyin.com",
        "live.douyin.com",
    ):
        csrf(host)
    state = session()
    query = common(e["profile"], state)
    if e.get("version"):
        query.update(zip(("version_code", "version_name"), e["version"]))
    if e.get("body_fields"):
        body = values
    else:
        query.update(values)
    # Device tokens are issued by the platform or supplied by this API lifecycle.
    tokens = state.state.get("tokens", {})
    for k in ("webid", "msToken") if e["profile"] == "web" else ("msToken",):
        if tokens.get(k):
            query[k] = tokens[k]
    if e["profile"] == "web":
        cookie_values = {
            c["name"]: c["value"]
            for c in state.state["cookies"]
            if c.get("name") and c.get("value")
        }
        if cookie_values.get("UIFID"):
            query["uifid"] = cookie_values["UIFID"]
        if cookie_values.get("s_v_web_id"):
            query.update(
                verifyFp=cookie_values["s_v_web_id"], fp=cookie_values["s_v_web_id"]
            )
    if name == "self" and not any(
        c.get("name") in ("sessionid", "sessionid_ss") and c.get("value")
        for c in state.state["cookies"]
    ):
        raise DouyinRequestError("API_SESSION_EXPIRED")
    if name == "comment":
        query.update(
            app_name="aweme", enter_from="video_detail", previous_page="video_detail"
        )
    if name == "products":
        from urllib.parse import quote

        scene = query.pop("ecom_scene_id", "1001")
        query.pop("offset", None)
        query["entrance_info"] = quote(
            json.dumps(
                {
                    "room_id": values["room_id"],
                    "anchor_id": values["author_id"],
                    "carrier_type": "live_popup_card",
                    "ecom_scene_id": scene,
                },
                separators=(",", ":"),
            ),
            safe="",
        )
    if name == "product_detail":
        body = {
            k: values[k] for k in ("is_h5", "bff_type", "origin_type", "promotion_id")
        }
        query.pop("promotion_id", None)
        query.pop("bff_type", None)
    if name == "live_fetch":
        query.update(
            browser_name="Mozilla",
            browser_version=state.ua.removeprefix("Mozilla/"),
            tz_name="Asia/Shanghai",
        )
    result = request(
        e["profile"],
        "request",
        e["method"],
        "https://" + host + e["path"],
        params=query,
        body=body,
        body_encoding="form" if e.get("form") else "json",
        verify_identity=name == "self",
        expected_uid=expected_uid,
        binary_response=e.get("binary", False),
        empty_result=e.get("empty_result"),
        content_type=e.get("content_type"),
        static_headers={"referer": "https://" + host + "/", "origin": "https://" + host}
        if e["method"] == "POST"
        else {"referer": "https://" + host + "/"},
    )
    if name == "live_fetch":
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import DecodeError
        from .proto import Live_pb2

        try:
            return {
                "data": MessageToDict(
                    Live_pb2.LiveResponse.FromString(result),
                    preserving_proto_field_name=True,
                )
            }
        except DecodeError as exc:
            raise DouyinRequestError("LIVE_RESPONSE_INVALID") from exc
    return result


def collect(name, params, count=20, pages=10):
    e = ENDPOINTS[name]
    if not e.get("list") or e.get("write"):
        raise ValueError("METHOD_NOT_PAGEABLE")
    if not 1 <= count <= 100 or not 1 <= pages <= 10:
        raise ValueError("INVALID_COLLECTION_LIMIT")
    values = dict(params)
    result = []
    seen = set()
    seen_pages = {str(values.get(e["cursor"], e["defaults"].get(e["cursor"], "0")))}
    for page in range(pages):
        values["count"] = str(min(count - len(result), int(values.get("count", 20))))
        response = call(name, values)
        batch = response.get(e["list"])
        if not isinstance(batch, list):
            raise DouyinRequestError("PLATFORM_LIST_MISSING")
        for item in batch:
            key = str(
                item.get("aweme_id")
                or item.get("cid")
                or item.get("uid")
                or json.dumps(item, sort_keys=True)
            )
            if key not in seen:
                result.append(item)
                seen.add(key)
        if len(result) >= count or not response.get("has_more"):
            break
        cursor = response.get(e.get("response_cursor", e["cursor"]))
        if cursor is None or str(cursor) in seen_pages:
            raise DouyinRequestError("PLATFORM_CURSOR_INVALID")
        seen_pages.add(str(cursor))
        values[e["cursor"]] = str(cursor)
        if name.startswith("search_"):
            values["offset"] = str(cursor)
            values["search_id"] = str((response.get("log_pb") or {}).get("impr_id", ""))
            values["need_filter_settings"] = "0"
        if name == "user_posts":
            values["need_time_list"] = "0"
        if name == "notices" and response.get("min_time") is not None:
            values["min_time"] = str(response["min_time"])
    return {
        "ok": True,
        "items": result[:count],
        "count": min(count, len(result)),
        "pages": page + 1,
        "cursor": values.get(e["cursor"], "0"),
    }
