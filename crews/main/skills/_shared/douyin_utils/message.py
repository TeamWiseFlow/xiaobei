"""Pure business content for IM cards and uploaded attachments."""

import json
import urllib.parse
import re
import time
import io
from PIL import Image


def _image_size(data):
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def _first(value, default=None):
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value if value is not None else default


def _url_object(value, *, width=0, height=0, data_size=None):
    if isinstance(value, dict):
        obj = dict(value)
        urls = obj.get("url_list") or obj.get("urlList") or obj.get("urls") or []
        if isinstance(urls, str):
            urls = [urls]
        else:
            urls = list(urls or [])
        uri = obj.get("uri") or obj.get("url") or (urls[0] if urls else "")
        obj["uri"] = uri or ""
        obj["url_list"] = urls or ([uri] if uri else [])
        if width and (not obj.get("width")):
            obj["width"] = int(width)
        if height and (not obj.get("height")):
            obj["height"] = int(height)
        if data_size is not None and "data_size" not in obj:
            obj["data_size"] = int(data_size)
        return obj
    if isinstance(value, (list, tuple)):
        value = _first(value, "")
    if value is None:
        value = ""
    value = str(value)
    obj = {"uri": value, "url_list": [value] if value else []}
    if width:
        obj["width"] = int(width)
    if height:
        obj["height"] = int(height)
    if data_size is not None:
        obj["data_size"] = int(data_size)
    return obj


def _detail_from_content(content):
    if not isinstance(content, dict):
        return content
    for key in ("aweme_detail", "detail"):
        value = content.get(key)
        if isinstance(value, dict):
            return value
    return content


def _is_card_payload(content, *, photos=False):
    if not isinstance(content, dict) or not content.get("itemId"):
        return False
    if photos:
        return content.get("awemeType") == 68 or content.get("aweType") == 0
    return content.get("aweType") == 800 or content.get("awemeType") == 0


def _author_values(detail):
    author = detail.get("author") or detail.get("user") or {}
    if not isinstance(author, dict):
        author = {}
    uid = (
        author.get("uid")
        or author.get("user_id")
        or detail.get("uid")
        or detail.get("profile_uid")
        or ""
    )
    sec_uid = (
        author.get("sec_uid")
        or author.get("sec_user_id")
        or detail.get("secUID")
        or detail.get("sec_uid")
        or ""
    )
    name = (
        author.get("nickname") or author.get("name") or detail.get("content_name") or ""
    )
    return (str(uid or ""), str(sec_uid or ""), str(name or ""))


def _detail_cover(detail, *, photos=False):
    video = detail.get("video") or {}
    if not isinstance(video, dict):
        video = {}
    if photos:
        images = (
            detail.get("images")
            or detail.get("image_list")
            or detail.get("image_infos")
            or []
        )
        first_image = _first(images, {})
        if not isinstance(first_image, dict):
            first_image = {"url_list": first_image}
        value = (
            first_image.get("display_image") or first_image.get("cover") or first_image
        )
        width = first_image.get("width") or detail.get("cover_width") or 0
        height = first_image.get("height") or detail.get("cover_height") or 0
    else:
        cover = video.get("cover") or video.get("origin_cover") or {}
        value = cover or detail.get("cover_url") or detail.get("cover") or ""
        width = (
            video.get("width")
            or (cover.get("width") if isinstance(cover, dict) else 0)
            or detail.get("cover_width")
            or 0
        )
        height = (
            video.get("height")
            or (cover.get("height") if isinstance(cover, dict) else 0)
            or detail.get("cover_height")
            or 0
        )
    if not width and isinstance(value, dict):
        width = value.get("width") or 0
    if not height and isinstance(value, dict):
        height = value.get("height") or 0
    return (
        _url_object(value, width=width, height=height),
        int(width or 0),
        int(height or 0),
    )


def _item_id_from_value(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if value.isdigit():
        return value
    match = re.search("/(?:video|note|slides)/(\\d+)", value)
    if match:
        return match.group(1)
    match = re.search("[?&]modal_id=(\\d+)", value)
    return match.group(1) if match else ""


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MessagePayload:
    @staticmethod
    def _encryption(item):
        return (item or {}).get("Encryption") or {}

    @staticmethod
    def _image_content(item, data, *, gif=False):
        enc = MessagePayload._encryption(item)
        extra = enc.get("Extra") or {}
        uri = enc.get("Uri") or item.get("Uri") or ""
        md5 = enc.get("SourceMd5") or item.get("SourceMd5") or ""
        secret = enc.get("SecretKey") or item.get("SecretKey") or ""
        width, height = _image_size(data)
        width = _as_int(extra.get("img_width"), width)
        height = _as_int(extra.get("img_height"), height)
        return {
            "resource_url": {
                "oid": uri,
                "skey": secret,
                "data_size": _as_int(extra.get("img_size"), len(data)),
                "md5": md5,
            },
            "cover_height": height,
            "cover_width": width,
            "check_pics": [],
            "md5": md5,
            "from_gallery": 1,
            "aweType": 2703 if gif else 2702,
        }

    @staticmethod
    def _plain_uri(item):
        enc = MessagePayload._encryption(item)
        return enc.get("Uri") or item.get("Uri") or item.get("uri") or ""

    @staticmethod
    def build_share_aweme_content(
        content,
        *,
        uid="",
        sec_uid="",
        name="",
        title="",
        item_id="",
        share_id="",
        timestamp=None,
        **extra,
    ) -> dict:
        if _is_card_payload(content):
            payload = dict(content)
            if not payload.get("share_id") and uid and payload.get("itemId"):
                stamp = int(timestamp if timestamp is not None else time.time() * 1000)
                payload["share_id"] = f"{uid}_{stamp}_{payload['itemId']}"
            payload.update(extra)
            return payload
        detail = _detail_from_content(content)
        if not isinstance(detail, dict):
            detail = {}
        author_uid, author_sec_uid, author_name = _author_values(detail)
        uid = str(uid or author_uid or "")
        sec_uid = str(sec_uid or author_sec_uid or "")
        name = str(name or author_name or "")
        item_id = str(
            item_id
            or detail.get("aweme_id")
            or detail.get("itemId")
            or detail.get("item_id")
            or _item_id_from_value(content)
            or ""
        )
        cover, width, height = _detail_cover(detail, photos=False)
        title = str(
            title
            or detail.get("desc")
            or detail.get("title")
            or detail.get("content_title")
            or ""
        )
        if not share_id and uid and item_id:
            stamp = int(timestamp if timestamp is not None else time.time() * 1000)
            share_id = f"{uid}_{stamp}_{item_id}"
        ai_ext = detail.get("ai_ext") or "{}"
        if isinstance(ai_ext, (dict, list)):
            ai_ext = json.dumps(ai_ext, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "aweType": 800,
            "awemeType": 0,
            "content_name": name,
            "content_title": title,
            "content_thumb": dict(cover),
            "cover_height": height,
            "cover_url": dict(cover),
            "cover_width": width,
            "itemId": item_id,
            "secUID": sec_uid,
            "uid": uid,
            "share_id": str(share_id or ""),
            "share_with_timestamp": 0,
            "is_aigc": bool(detail.get("is_aigc", False)),
            "is_hot_spot_video": bool(detail.get("is_hot_spot_video", False)),
            "is_live_photo": int(detail.get("is_live_photo", 0) or 0),
            "is_slides": bool(detail.get("is_slides", False)),
            "is_story": bool(detail.get("is_story", False)),
            "is_text": int(detail.get("is_text", 0) or 0),
            "create_id": str(detail.get("create_id") or ""),
            "share_info": detail.get("share_info") or [],
            "anchor_info": detail.get("anchor_info") or {},
            "poi_track_params": detail.get("poi_track_params") or {},
            "ai_ext": ai_ext,
        }
        for key in (
            "profile_uid",
            "profile_sec_uid",
            "scene_type",
            "send_source",
            "publish_way",
            "hot_spot_create_time",
            "ecom_share_track_params",
        ):
            if detail.get(key) is not None:
                payload[key] = detail[key]
        payload.update(extra)
        return payload

    @staticmethod
    def build_share_photos_content(
        content,
        *,
        uid="",
        sec_uid="",
        name="",
        title="",
        item_id="",
        share_id="",
        timestamp=None,
        image_count=None,
        image_index=0,
        **extra,
    ) -> dict:
        if _is_card_payload(content, photos=True):
            payload = dict(content)
            if not payload.get("share_id") and uid and payload.get("itemId"):
                stamp = int(timestamp if timestamp is not None else time.time() * 1000)
                payload["share_id"] = f"{uid}_{stamp}_{payload['itemId']}"
            payload.update(extra)
            return payload
        detail = _detail_from_content(content)
        if not isinstance(detail, dict):
            detail = {}
        author_uid, author_sec_uid, author_name = _author_values(detail)
        uid = str(uid or author_uid or "")
        sec_uid = str(sec_uid or author_sec_uid or "")
        name = str(name or author_name or "")
        item_id = str(
            item_id
            or detail.get("aweme_id")
            or detail.get("itemId")
            or detail.get("item_id")
            or _item_id_from_value(content)
            or ""
        )
        cover, width, height = _detail_cover(detail, photos=True)
        title = str(
            title
            or detail.get("desc")
            or detail.get("title")
            or detail.get("content_title")
            or ""
        )
        images = (
            detail.get("images")
            or detail.get("image_list")
            or detail.get("image_infos")
            or []
        )
        if image_count is None:
            image_count = detail.get("image_count") or len(images) or 1
        if not share_id and uid and item_id:
            stamp = int(timestamp if timestamp is not None else time.time() * 1000)
            share_id = f"{uid}_{stamp}_{item_id}"
        ai_ext = detail.get("ai_ext") or "{}"
        if isinstance(ai_ext, (dict, list)):
            ai_ext = json.dumps(ai_ext, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "aweType": 0,
            "awemeType": 68,
            "content_name": name,
            "content_title": title,
            "content_thumb": dict(cover),
            "cover_height": height,
            "cover_url": dict(cover),
            "cover_url_v2": dict(cover),
            "cover_width": width,
            "image_count": int(image_count or 1),
            "image_index": int(image_index or 0),
            "itemId": item_id,
            "secUID": sec_uid,
            "uid": uid,
            "share_id": str(share_id or ""),
            "share_with_timestamp": 0,
            "is_aigc": bool(detail.get("is_aigc", False)),
            "is_hot_spot_video": bool(detail.get("is_hot_spot_video", False)),
            "is_live_photo": int(detail.get("is_live_photo", 0) or 0),
            "is_slides": bool(detail.get("is_slides", False)),
            "is_story": bool(detail.get("is_story", False)),
            "is_text": int(detail.get("is_text", 0) or 0),
            "share_info": detail.get("share_info") or [],
            "anchor_info": detail.get("anchor_info") or {},
            "poi_track_params": detail.get("poi_track_params") or {},
            "ai_ext": ai_ext,
        }
        for key in (
            "profile_uid",
            "profile_sec_uid",
            "scene_type",
            "send_source",
            "publish_way",
            "hot_spot_create_time",
            "ecom_share_track_params",
        ):
            if detail.get(key) is not None:
                payload[key] = detail[key]
        payload.update(extra)
        return payload

    @staticmethod
    def build_share_web_content(
        content, *, title="", desc="", cover_url="", link_url="", **extra
    ) -> dict:
        if isinstance(content, dict):
            payload = dict(content)
            target = str(payload.get("link_url") or link_url or "")
            if title:
                payload["title"] = title
            if desc:
                payload["desc"] = desc
            if cover_url:
                payload["cover_url"] = cover_url
        else:
            payload = {}
            target = str(link_url or content or "")
        if target:
            parsed = urllib.parse.urlsplit(target)
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if not any((key == "pc_iframe_src" and value for key, value in query)):
                query.append(("pc_iframe_src", target))
                target = urllib.parse.urlunsplit(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        urllib.parse.urlencode(query),
                        parsed.fragment,
                    )
                )
        payload.setdefault("link_url", target)
        payload.setdefault("cover_url", str(cover_url or ""))
        payload.setdefault("title", str(title or ""))
        payload.setdefault("desc", str(desc or ""))
        payload["link_url"] = target
        payload.update(extra)
        return payload

    @staticmethod
    def build_user_card_content(
        content=None,
        *,
        uid="",
        sec_uid="",
        name="",
        avatar=None,
        cover_items=None,
        cover_url=None,
        **extra,
    ) -> dict:
        if isinstance(content, dict):
            source = dict(content)
        else:
            source = {}
        uid = str(uid or source.get("uid") or source.get("user_id") or "")
        sec_uid = str(
            sec_uid
            or source.get("secUID")
            or source.get("sec_uid")
            or source.get("sec_user_id")
            or ""
        )
        name = str(name or source.get("name") or source.get("nickname") or "")
        avatar = avatar if avatar is not None else source.get("avatar")
        if avatar is None:
            avatar = source.get("avatar_larger") or source.get("avatar_thumb") or ""
        covers = cover_url if cover_url is not None else source.get("cover_url")
        if covers is None:
            covers = source.get("cover_items") or []
        if isinstance(covers, (str, dict)):
            covers = [covers]
        cover_objects = [_url_object(value) for value in covers or []]
        items = (
            cover_items if cover_items is not None else source.get("cover_items") or []
        )
        payload = {
            "uid": uid,
            "secUID": sec_uid,
            "name": name,
            "avatar": _url_object(avatar),
            "cover_items": list(items or []),
            "cover_url": cover_objects,
        }
        payload.update({k: v for k, v in source.items() if k not in payload})
        payload.update(extra)
        return payload
