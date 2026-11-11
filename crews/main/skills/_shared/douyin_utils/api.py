"""Business endpoint client for Douyin. No dynamic computation lives here."""

from __future__ import annotations
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
from .http import DouyinRequestError, _send, request, session, serialized
from .search import user_filters, check_user_filters

ENDPOINTS = json.loads(Path(__file__).with_name("endpoints.json").read_text())
ITEM_HOSTS = {"www.douyin.com", "v.douyin.com", "www.iesdouyin.com", "iesdouyin.com"}
SHORT_URL_MAX_REDIRECTS = 5


def _item_url(value, error, *, base=None):
    try:
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == "\\" for c in value):
            raise ValueError(error)
        parsed = urlsplit(urljoin(base, value) if base else value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ITEM_HOSTS
            or parsed.port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(error)
        return parsed
    except ValueError:
        raise ValueError(error) from None


def _item_id(parsed):
    match = re.search(r"/(?:video|note|slides)/(\d{15,22})(?:/|$)", parsed.path)
    if not match:
        match = re.search(r"(?:^|&)modal_id=(\d{15,22})(?:&|$)", parsed.query)
    return match.group(1) if match else None


def _short_item_id(value):
    current, visited = value, set()
    # Use an anonymous client, independent of API cookies, Relay and netrc auth.
    with requests.Session() as client:
        client.trust_env = False
        for hop in range(SHORT_URL_MAX_REDIRECTS + 1):
            parsed = _item_url(current, "SHORT_URL_INVALID_REDIRECT")
            ident = _item_id(parsed)
            if ident:
                return ident
            if current in visited:
                raise ValueError("SHORT_URL_REDIRECT_LOOP")
            visited.add(current)
            try:
                with client.get(
                    current, timeout=(5, 10), allow_redirects=False, stream=True
                ) as response:
                    status = response.status_code
                    if status in (404, 410):
                        raise ValueError("SHORT_URL_EXPIRED")
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError("SHORT_URL_REDIRECT_MISSING")
                        target = _item_url(
                            location, "SHORT_URL_INVALID_REDIRECT", base=current
                        ).geturl()
                        if hop == SHORT_URL_MAX_REDIRECTS:
                            raise ValueError("SHORT_URL_TOO_MANY_REDIRECTS")
                        current = target
                    elif status >= 400:
                        raise ValueError("SHORT_URL_HTTP_ERROR")
                    else:
                        raise ValueError("SHORT_URL_ITEM_ID_MISSING")
            except requests.Timeout:
                raise ValueError("SHORT_URL_TIMEOUT") from None
            except requests.RequestException:
                raise ValueError("SHORT_URL_NETWORK_ERROR") from None


def item_id(value):
    value = str(value).strip()
    if re.fullmatch(r"\d{15,22}", value):
        return value
    parsed = _item_url(value, "INVALID_ITEM_URL")
    ident = _item_id(parsed)
    if ident:
        return ident
    if parsed.hostname == "v.douyin.com":
        return _short_item_id(value)
    raise ValueError("ITEM_ID_REQUIRED")


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


def ensure_webid():
    """Recover a platform-issued web identifier from the exact identity endpoint."""
    current = session()
    value = current.state.get("tokens", {}).get("webid")
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value):
        return value
    expected_uid = current.state.get("uid")
    call("self", expected_uid=expected_uid)
    refreshed = session().state
    if expected_uid and refreshed.get("uid") != expected_uid:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    value = refreshed.get("tokens", {}).get("webid")
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise DouyinRequestError("WEB_DEVICE_ID_UNAVAILABLE")
    return value


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


def call(name, params=None, *, body=None, confirm=False, expected_uid=None, _uifid_retry=False):
    if name not in ENDPOINTS:
        raise ValueError("UNKNOWN_METHOD")
    e = ENDPOINTS[name]
    if params is not None and not isinstance(params, dict):
        raise ValueError("PARAMS_OBJECT_REQUIRED")
    values = {**e["defaults"], **(params or {})}
    if name == "search_users":
        values = user_filters(values)
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
    query = {} if name == "fast_detect" else common(e["profile"], state)
    if e.get("version"):
        query.update(zip(("version_code", "version_name"), e["version"]))
    if e.get("body_fields"):
        body = values
    else:
        query.update(values)
    # Device tokens are issued by the platform or supplied by this API lifecycle.
    tokens = state.state.get("tokens", {})
    for k in ("webid", "msToken") if e["profile"] == "web" else ("msToken",) if e["profile"] != "creator" else ():
        if tokens.get(k):
            query[k] = tokens[k]
    if e["profile"] == "creator":
        if tokens.get("creator_msToken"):
            query["msToken"] = tokens["creator_msToken"]
        elif state.state.get("session_channels", {}).get("creator"):
            raise DouyinRequestError("CREATOR_TOKEN_UNAVAILABLE")
        elif tokens.get("msToken"):
            query["msToken"] = tokens["msToken"]
    if e["profile"] == "web":
        cookie_values = {
            c["name"]: c["value"]
            for c in state.state["cookies"]
            if c.get("name") and c.get("value")
        }
        if cookie_values.get("UIFID") and name != "replies":
            query["uifid"] = cookie_values["UIFID"]
        if cookie_values.get("s_v_web_id") and name != "replies":
            query.update(
                verifyFp=cookie_values["s_v_web_id"], fp=cookie_values["s_v_web_id"]
            )
    if name == "self" and not any(
        c.get("name") in ("sessionid", "sessionid_ss") and c.get("value")
        for c in state.state["cookies"]
    ):
        raise DouyinRequestError("API_SESSION_EXPIRED")
    if name == "replies":
        for key in ("uifid", "verifyFp", "fp"):
            query.pop(key, None)
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
    referer = "https://" + host + "/"
    if name == "search_users":
        from urllib.parse import quote
        referer += "search/" + quote(str(values["keyword"]), safe="") + "?type=user"
    if name == "create":
        media_type = (body or {}).get("item", {}).get("common", {}).get("media_type")
        referer += "creator-micro/content/post/" + ("image" if media_type == 2 else "video")
    headers = {"referer": referer}
    if name in {"comments", "replies"}:
        headers["referer"] = "https://www.douyin.com/video/" + str(values.get("aweme_id") or values["item_id"])
    if e["method"] == "POST":
        headers["origin"] = "https://" + host
    if name == "fast_detect":
        headers["agw-js-conv"] = "str"
    try:
        result = request(
            e["profile"], "request", e["method"], "https://" + host + e["path"],
            params=query, body=body,
            body_encoding="form" if e.get("form") else "json",
            verify_identity=name == "self", expected_uid=expected_uid,
            binary_response=e.get("binary", False), empty_result=e.get("empty_result"),
            capture_response=name == "create", content_type=e.get("content_type"),
            static_headers=headers,
            **({"query_tail": {"verifyFp": cookie_values["s_v_web_id"], "fp": cookie_values["s_v_web_id"]}}
               if name == "replies" and cookie_values.get("s_v_web_id") else {}),
        )
    except DouyinRequestError as exc:
        if (exc.code == "PLATFORM_UIFID_MISSING" and not e.get("write")
                and e["profile"] == "web" and name != "feed" and not _uifid_retry
                and not state.cookies("https://www.douyin.com/").count("UIFID=")):
            call("feed", _uifid_retry=True)
            if not session().cookies("https://www.douyin.com/").count("UIFID="):
                raise exc
            return call(name, params, body=body, confirm=confirm,
                        expected_uid=expected_uid, _uifid_retry=True)
        raise
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
    values = user_filters(params) if name == "search_users" else dict(params)
    feed = e.get("pagination") == "refresh-index"
    if feed:
        cursor = str(values.get(e["cursor"], e["defaults"][e["cursor"]]))
        if not re.fullmatch(r"[0-9]{1,9}", cursor):
            raise ValueError("INVALID_FEED_REFRESH_INDEX")
        values[e["cursor"]] = cursor
    result = []
    seen = set()
    seen_pages = {str(values.get(e["cursor"], e["defaults"].get(e["cursor"], "0")))}
    for page in range(pages):
        values["count"] = str(min(count - len(result), int(values.get("count", 20))))
        response = call(name, dict(values))
        batch = response.get(e["list"])
        cards = feed and batch is not None
        if feed and batch is None:
            batch = response.get("aweme_list")
        if not isinstance(batch, list):
            raise DouyinRequestError("PLATFORM_LIST_MISSING")
        if cards:
            decoded = []
            for card in batch:
                if not isinstance(card, dict):
                    raise DouyinRequestError("PLATFORM_CARD_INVALID")
                item = card.get("aweme")
                if item in (None, ""):
                    continue
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except (ValueError, TypeError) as exc:
                        raise DouyinRequestError("PLATFORM_CARD_INVALID") from exc
                if not isinstance(item, dict):
                    raise DouyinRequestError("PLATFORM_CARD_INVALID")
                if item.get("aweme_id"):
                    decoded.append(item)
            batch = decoded
        before = len(result)
        for item in batch:
            if not isinstance(item, dict):
                raise DouyinRequestError("PLATFORM_ITEM_INVALID")
            user = item.get("user_info")
            key = str(
                item.get("aweme_id")
                or item.get("cid")
                or item.get("uid")
                or (user.get("uid") if isinstance(user, dict) else None)
                or json.dumps(item, sort_keys=True)
            )
            if key not in seen:
                result.append(item)
                seen.add(key)
        if feed:
            values[e["cursor"]] = str(int(values[e["cursor"]]) + 1)
        if len(result) >= count or not response.get("has_more"):
            break
        if feed:
            if batch and len(result) == before:
                raise DouyinRequestError("PLATFORM_PAGE_NO_PROGRESS")
            continue
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
    output = {
        "ok": True,
        "items": result[:count],
        "count": min(count, len(result)),
        "pages": page + 1,
        "cursor": values.get(e["cursor"], "0"),
    }
    if feed:
        output.update(has_more=bool(response.get("has_more")),
                      complete=len(result) >= count or not bool(response.get("has_more")),
                      pagination="refresh-index")
    if name in {"comments", "replies"}:
        more = bool(response.get("has_more"))
        complete = len(result) >= count or not more
        output.update(has_more=more, complete=complete,
                      stop_reason="requested_count" if len(result) >= count else
                                  "platform_end" if not more else "page_limit")
    if name == "search_users" and values.get("search_filter_value"):
        output["filter_check"] = check_user_filters(output["items"], values)
        if output["filter_check"]["state"] == "mismatch":
            output.update(ok=False, error="SEARCH_FILTER_MISMATCH")
    return output
