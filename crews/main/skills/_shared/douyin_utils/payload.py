"""Pure business payload builders for creator publishing."""

import json
import time
import uuid

CREATOR_ORIGIN = "https://creator.douyin.com"


def _js_string_length(value):
    return len(value.encode("utf-16-le")) // 2


def _now_s(context=None):
    return int(time.time())


class CreatorRequestContext:
    def frontend_uuid(self):
        return str(uuid.uuid4())


class PublishPayload:
    @staticmethod
    def _build_text_and_extra(title, desc):
        title = title or ""
        desc = desc or ""
        text = ""
        text_extra = []
        if title:
            text = title
            title_length = _js_string_length(title)
            text_extra.append(
                {
                    "start": 0,
                    "end": title_length,
                    "hashtag_id": 0,
                    "hashtag_name": "",
                    "type": 7,
                }
            )
        if desc:
            if text:
                sep_start = _js_string_length(text)
                text += "。"
                text_extra.append(
                    {
                        "start": sep_start,
                        "end": sep_start + 1,
                        "hashtag_id": 0,
                        "hashtag_name": "",
                        "type": 8,
                    }
                )
            text += desc
        return (text, text_extra)

    @staticmethod
    def _build_video_text(title, desc):
        title = (title or "").strip()
        desc = (desc or "").strip()
        return {
            "text": f"{title} {desc}" if title else desc,
            "item_title": title,
            "caption": desc,
            "text_extra": [],
            "challenges": [],
            "mentions": [],
            "activity": [],
            "hashtag_source": "",
        }

    @staticmethod
    def build_image_create_item(
        image_infos,
        *,
        title="",
        desc="",
        visibility=1,
        allow_download=True,
        timing=None,
        cover_index=0,
        cover_uri=None,
        challenges=None,
        mentions=None,
        activity=None,
        poi=None,
        mix_id=None,
        hot_spot=None,
        creation_id,
    ):
        text, text_extra = PublishPayload._build_text_and_extra(title, desc)
        cover = (
            cover_uri
            or image_infos[max(0, min(cover_index, len(image_infos) - 1))]["uri"]
        )
        dump = lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        )
        common = {
            "text": text,
            "text_extra": dump(text_extra),
            "activity": dump(activity or []),
            "challenges": dump(challenges or []),
            "hashtag_source": "",
            "mentions": dump(mentions or []),
            "visibility_type": int(visibility),
            "download": 1 if allow_download else 0,
            "timing": int(timing) if timing else -1,
            "media_type": 2,
            "images": [
                {"uri": info["uri"], "width": info["width"], "height": info["height"]}
                for info in image_infos
            ],
            "creation_id": str(creation_id),
        }
        if mix_id:
            common["mix_id"] = mix_id
        if poi:
            common["poi_id"] = poi.get("poi_id", "")
            common["poi_name"] = poi.get("poi_name", "")
        if hot_spot:
            common["hot_sentence"] = hot_spot.get("word", "")
        anchor = {"poi": poi} if poi else {}
        return {
            "item": {"common": common, "cover": {"poster": cover}, "anchor": anchor}
        }

    @staticmethod
    def build_video_create_item(
        info,
        *,
        title="",
        desc="",
        visibility=1,
        allow_download=True,
        timing=None,
        poster_uri=None,
        cover_delay=0,
        challenges=None,
        mentions=None,
        activity=None,
        poi=None,
        mix_id=None,
        hot_spot=None,
        creation_id,
        cover_tools_extend_info=None,
        cover_tools_info=None,
        chapter=None,
        request_context=None,
    ):
        parts = PublishPayload._build_video_text(title, desc)
        dump = lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        )
        common = {
            "text": parts["text"],
            "caption": parts["caption"],
            "item_title": parts["item_title"],
            "activity": dump(activity if activity is not None else parts["activity"]),
            "text_extra": dump(parts["text_extra"]),
            "challenges": dump(
                challenges if challenges is not None else parts["challenges"]
            ),
            "mentions": dump(mentions if mentions is not None else parts["mentions"]),
            "hashtag_source": parts["hashtag_source"],
            "hot_sentence": (hot_spot or {}).get("word", ""),
            "interaction_stickers": "[]",
            "visibility_type": int(visibility),
            "download": 1 if allow_download else 0,
            "timing": int(timing) if timing else 0,
            "creation_id": str(creation_id),
            "media_type": 4,
            "video_id": info["vid"],
            "music_source": 0,
            "music_id": None,
        }
        if mix_id:
            common["mix_id"] = mix_id
        if poi:
            common["poi_id"] = poi.get("poi_id", "")
            common["poi_name"] = poi.get("poi_name", "")
        poster_uri = poster_uri or info.get("poster_uri") or ""
        extend = (
            cover_tools_extend_info
            if cover_tools_extend_info is not None
            else PublishPayload._cover_tools_extend_info(poster_uri)
        )
        cover_section = {
            "cover_text_uri": None,
            "cover_text": None,
            "poster": poster_uri,
            "poster_delay": int(cover_delay),
            "cover_tools_extend_info": dump(extend),
            "cover_tools_info": dump(cover_tools_info or {}),
        }
        anchor = {"poi": poi} if poi else {}
        chapter = (
            chapter
            if chapter is not None
            else PublishPayload._empty_chapter(request_context)
        )
        return {
            "item": {
                "common": common,
                "cover": cover_section,
                "mix": {},
                "selected_member": {"is_selected_member_video": False},
                "chapter": {"chapter": dump(chapter)},
                "anchor": anchor,
                "sync": {"should_sync": False, "sync_to_toutiao": 0},
                "open_platform": {},
                "assistant": {"is_preview": 0, "is_post_assistant": 1},
            }
        }

    @staticmethod
    def _empty_chapter(request_context=None):
        return {
            "chapter_abstract": "",
            "chapter_details": [],
            "chapter_type": 1,
            "chapter_tools_info": {
                "chapter_recommend_detail": [],
                "chapter_recommend_abstract": "",
                "chapter_source": 2,
                "chapter_recommend_type": -2,
                "create_date": _now_s(request_context),
                "is_pc": "1",
                "is_pre_generated": "0",
                "is_syn": "1",
            },
        }

    @staticmethod
    def build_video_cover_tools_extend_info(
        poster_uri,
        *,
        video_name="",
        cover_url="",
        recommend_frames=None,
        ai_uri="",
        preview_video_list=None,
        request_context=None,
    ):
        context = request_context

        def frontend_uuid():
            if context is not None:
                return context.frontend_uuid()
            return CreatorRequestContext().frontend_uuid()

        def blob_url():
            if context is not None:
                return context.blob_url()
            return f"blob:{CREATOR_ORIGIN}/{uuid.uuid4()}"

        cover_list = []
        for index, frame in enumerate(recommend_frames or []):
            value = frame.get("time", 0)
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            preview_blob = (
                frame.get("previewBlobSrc")
                or frame.get("preview_blob_src")
                or blob_url()
            )
            source_blob = frame.get("src") or blob_url()
            is_ai = bool(frame.get("isAIGen", index == 0 and ai_uri))
            uri1 = frame.get("uri1") or (ai_uri if is_ai else "NOT_READY")
            cover_list.append(
                {
                    "id": frame.get("id") or frontend_uuid(),
                    "time": value,
                    "uri": frame.get("uri", "NOT_READY"),
                    "frameIndex": int(
                        frame.get("frameIndex", frame.get("frame_index", index))
                    ),
                    "previewBlobSrc": preview_blob,
                    "cropHeight": int(
                        frame.get("cropHeight", frame.get("crop_height", 360))
                    ),
                    "cropWidth": int(
                        frame.get("cropWidth", frame.get("crop_width", 480))
                    ),
                    "cropBox": frame.get(
                        "cropBox", frame.get("crop_box", [0, 0, 0.75, 1])
                    ),
                    "cropBox2": frame.get(
                        "cropBox2",
                        frame.get(
                            "crop_box2", [0.08695652335882187, 0, 0.508695662021637, 1]
                        ),
                    ),
                    "src": source_blob,
                    "rawBlob": {},
                    "fileName": frame.get(
                        "fileName", frame.get("file_name", video_name)
                    ),
                    "isAIGen": is_ai,
                    "uri1": uri1,
                }
            )
        return {
            "recommendServerInfo": {"res": [], "times": []},
            "recommendCoverList": cover_list,
            "recommendCoverInfo": {
                "isFromRecommend": bool(cover_list),
                "isDefaultSelect": False,
                "isRecommendClickFrom": "",
                "selectInfo": {},
                "editingInfo": {},
            },
            "recommendCoverTime": 0,
            "coverInfo": {
                "firstFrameCoverUri": poster_uri,
                "videoName": video_name,
                "uri": poster_uri,
                "url": cover_url,
                "posterDelay": 0,
            },
            "coverUrl": cover_url,
            "coverHorizontalInfo": None,
            "coverHorizontalUrl": "",
            "pasterInfo": None,
            "stateInfo": None,
            "croppedCoverInfo": None,
            "uploadBackgroundInfo": None,
            "uploadPasterInfo": None,
            "uploadCoverStateInfo": None,
            "xiguaCoverInfo": {"posterDelay": 0},
            "xiguaPasterInfo": None,
            "xiguaStateInfo": None,
            "xiguaUploadCoverStateInfo": None,
            "xiguaUploadBackgroundInfo": None,
            "xiguaUploadPasterInfo": None,
            "editXigua": False,
            "coverSource": "",
            "previewVideoList": preview_video_list or [],
        }

    @staticmethod
    def _cover_tools_extend_info(poster_uri):
        return PublishPayload.build_video_cover_tools_extend_info(poster_uri)
