#!/usr/bin/env python3
"""Creator publishing with durable submission state and local media transfer."""

from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "_shared"))
from douyin_utils.api import ENDPOINTS, call, common, csrf
from douyin_utils.http import DouyinRequestError, prepare, request, session
from douyin_utils.media import upload
from douyin_utils.payload import PublishPayload
from douyin_utils.session import write_private, read_private, SessionError

STATE_DIR = Path.home() / ".openclaw/douyin-api/publish"


def preflight(kind, uid):
    csrf("creator.douyin.com")
    state = session()
    url = "https://creator.douyin.com/web/api/media/aweme/create_v2/"
    security = state.security("creator.douyin.com")
    missing = [
        k
        for k in ("ticket", "ts_sign", "private_key", "dtrait_blob", "csrf_token")
        if not security.get(k)
    ]
    if missing:
        raise DouyinRequestError("PUBLISH_SECURITY_MISSING")
    prepare(
        "creator",
        "publish-security",
        url,
        security=security,
        fields={"work_type": kind},
        expected_uid=uid,
    )


def poll(name, params, done, timeout=180, body=None, expected_uid=None):
    deadline = time.monotonic() + timeout
    while True:
        r = call(name, params, body=body, confirm=True, expected_uid=expected_uid)
        state = done(r)
        if state == "done":
            return r
        if state == "fail":
            raise DouyinRequestError("CREATOR_TASK_FAILED")
        if body is not None and r.get("task_id"):
            body["task_id"] = r["task_id"]
        if time.monotonic() >= deadline:
            raise DouyinRequestError("CREATOR_TASK_TIMEOUT")
        time.sleep(3)


def publish(a):
    options = {}
    if getattr(a, "options_file", None):
        options = json.loads(Path(a.options_file).expanduser().read_text())
        allowed = {"challenges", "mentions", "activity", "poi", "mix_id", "hot_spot"}
        allowed |= (
            {"cover_uri"}
            if a.command == "note"
            else {
                "cover_delay",
                "cover_tools_extend_info",
                "cover_tools_info",
                "chapter",
            }
        )
        if not isinstance(options, dict) or set(options) - allowed:
            raise ValueError("INVALID_PUBLISH_OPTIONS")
    paths = [
        Path(p).expanduser().resolve()
        for p in (a.images if a.command == "note" else [a.video])
    ]
    if not 1 <= len(paths) <= 35 or any(
        not p.is_file() or not p.stat().st_size for p in paths
    ):
        raise ValueError("MEDIA_FILE_MISSING")
    title_limit = 20 if a.command == "note" else 30
    if not a.title.strip() or len(a.title) > title_limit:
        raise ValueError("TITLE_LENGTH_INVALID")
    if len(a.caption) > 1000:
        raise ValueError("CAPTION_TOO_LONG")
    if a.command == "note" and any(p.stat().st_size > 50 * 1024**2 for p in paths):
        raise ValueError("IMAGE_TOO_LARGE")
    if a.command == "note" and not 0 <= a.cover_index < len(paths):
        raise ValueError("INVALID_COVER_INDEX")
    if a.command == "video" and a.cover:
        cover = Path(a.cover).expanduser().resolve()
        if (
            not cover.is_file()
            or not cover.stat().st_size
            or cover.stat().st_size > 50 * 1024**2
        ):
            raise ValueError("COVER_FILE_INVALID")
    if a.music_id and a.original_sound:
        raise ValueError("MUSIC_OPTIONS_CONFLICT")
    if a.timing and a.timing <= time.time():
        raise ValueError("INVALID_PUBLISH_TIME")
    if not a.confirm:
        return {
            "ok": True,
            "preview": True,
            "kind": a.command,
            "files": [str(p) for p in paths],
            "title": a.title,
            "caption": a.caption,
            "visibility": a.visibility,
            "declaration": a.declaration,
            "timing": a.timing,
            "allow_download": not a.no_download,
            "cover": a.cover if a.command == "video" else a.cover_index,
            "music_id": a.music_id,
            "options": options,
        }
    kind = "image" if a.command == "note" else "video"
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE_DIR / ".lock").open("a") as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("PUBLISH_BUSY")
        # Do not start another upload while a prior submission needs inspection.
        jobs = [read_private(p) for p in STATE_DIR.glob("job-*.json")]
        uid = str((call("self").get("user") or {}).get("uid", ""))
        if not uid:
            raise DouyinRequestError("SELF_PROFILE_MISSING")
        state = session()
        if str(state.state.get("uid", "")) != uid:
            raise DouyinRequestError("API_ACCOUNT_MISMATCH")
        if any(
            j.get("uid") == uid and j.get("status") == "submission_unknown"
            for j in jobs
        ):
            raise ValueError("PREVIOUS_SUBMISSION_UNKNOWN")
        if (
            sum(
                j.get("uid") == uid and j.get("submitted_at", 0) > time.time() - 86400
                for j in jobs
            )
            >= 5
        ):
            raise ValueError("PUBLISH_DAILY_LIMIT")
        declaration_fields = state.state.get("creator_declarations", {}).get(
            a.declaration
        )
        if a.declaration != "none" and not isinstance(declaration_fields, dict):
            raise ValueError("DECLARATION_CONFIG_MISSING")
        preflight(kind, uid)
        creation_id = uuid.uuid4().hex[:8] + str(int(time.time() * 1000))
        job_file = STATE_DIR / f"job-{creation_id}.json"
        job = {
            "creation_id": creation_id,
            "options": options,
            "uid": uid,
            "kind": kind,
            "title": a.title,
            "status": "uploading",
            "created_at": time.time(),
            "files": [str(p) for p in paths],
        }
        write_private(job_file, job)
        kwargs = {
            "title": a.title,
            "desc": a.caption,
            "visibility": a.visibility,
            "allow_download": not a.no_download,
            "timing": a.timing,
            "creation_id": creation_id,
        }
        kwargs.update(options)
        if kind == "image":
            images = [upload(p, "image", user_id=uid) for p in paths]
            item = PublishPayload.build_image_create_item(
                images, cover_index=a.cover_index, **kwargs
            )
        else:
            info = upload(paths[0], "video", user_id=uid)
            call("video_enable", {"video_id": info["vid"]}, expected_uid=uid)
            call("video_transend", {"video_id": info["vid"]}, expected_uid=uid)
            body = {
                "resource_list": [
                    {
                        "type": 2,
                        "video_id": info["vid"],
                        "duration": int(round(info["duration"])),
                        "cover_uri": "",
                    }
                ],
                "source": 1,
                "is_redetect": False,
            }
            poll(
                "fast_detect",
                {},
                lambda r: (
                    "done"
                    if r.get("has_done")
                    else "fail"
                    if (r.get("base_resp") or {}).get("status_code", 0) != 0
                    else "wait"
                ),
                body=body,
                expected_uid=uid,
            )
            poster = (
                upload(Path(a.cover), "image", user_id=uid)["uri"]
                if a.cover
                else info["poster_uri"]
            )
            if not poster:
                raise DouyinRequestError("VIDEO_COVER_MISSING")
            item = PublishPayload.build_video_create_item(
                info, poster_uri=poster, **kwargs
            )
        common_body = item["item"]["common"]
        if declaration_fields:
            common_body.update(declaration_fields)
        if a.music_id:
            common_body.update(music_id=a.music_id, music_source=1)
        job.update(status="prepared", payload=item)
        write_private(job_file, job)
        # Mark before sending: timeout, auth errors or interrupts never cause an automatic resend.
        job.update(status="submission_unknown", submitted_at=time.time())
        write_private(job_file, job)
        try:
            current = session()
            params = common("creator", current)
            if current.state.get("tokens", {}).get("msToken"):
                params["msToken"] = current.state["tokens"]["msToken"]
            result = request(
                "creator",
                "publish-security",
                "POST",
                "https://creator.douyin.com/web/api/media/aweme/create_v2/",
                expected_uid=uid,
                params=params,
                body=item,
                fields={"work_type": kind},
                static_headers={
                    "referer": "https://creator.douyin.com/creator-micro/content/publish",
                    "origin": "https://creator.douyin.com",
                },
            )
        except DouyinRequestError as exc:
            return {
                "ok": False,
                "error": "PUBLISH_RESULT_UNKNOWN",
                "reason": exc.code,
                "job_file": str(job_file),
            }
        ident = str(
            result.get("aweme_id")
            or result.get("item_id")
            or (result.get("aweme") or {}).get("aweme_id")
            or ""
        )
        if not ident.isdigit():
            return {
                "ok": False,
                "error": "PUBLISH_RESULT_UNKNOWN",
                "job_file": str(job_file),
            }
        job.update(
            status="confirmed",
            content_id=ident,
            url="https://www.douyin.com/"
            + ("note/" if kind == "image" else "video/")
            + ident,
        )
        write_private(job_file, job)
        return {
            "ok": True,
            "content_id": ident,
            "url": job["url"],
            "job_file": str(job_file),
        }


def status_job(a):
    job = read_private(a.job_file)
    if str(session().state.get("uid", "")) != str(job.get("uid")):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    if job["status"] == "confirmed":
        return {
            "ok": True,
            "status": job["status"],
            "content_id": job["content_id"],
            "url": job["url"],
        }
    user = call("self", expected_uid=job["uid"]).get("user") or {}
    sec_uid = user.get("sec_uid")
    if not sec_uid:
        user = call("creator_profile", expected_uid=job["uid"]).get("user") or {}
        sec_uid = user.get("sec_uid")
    if not sec_uid:
        raise DouyinRequestError("SELF_SEC_UID_MISSING")
    result = call(
        "user_posts", {"sec_user_id": sec_uid, "count": "50"}, expected_uid=job["uid"]
    )
    items = result.get("aweme_list")
    if not isinstance(items, list):
        raise DouyinRequestError("PLATFORM_LIST_MISSING")
    candidates = []
    for item in items:
        author = item.get("author") or {}
        title = item.get("desc", "")
        if (
            str(author.get("uid_str") or author.get("uid") or "") == str(job["uid"])
            and job["title"] in title
            and item.get("create_time", 0) >= job.get("submitted_at", 0) - 120
            and str(item.get("aweme_id", "")).isdigit()
        ):
            candidates.append(
                {
                    "id": str(item["aweme_id"]),
                    "title": title,
                    "create_time": item["create_time"],
                }
            )
    return {
        "ok": False,
        "status": job["status"],
        "error": "PUBLISH_RESULT_UNKNOWN",
        "candidates": candidates,
    }


def resolve_job(a):
    job = read_private(a.job_file)
    if job.get("status") != "submission_unknown":
        raise ValueError("JOB_NOT_UNCERTAIN")
    if not a.confirm:
        return {
            "ok": True,
            "preview": True,
            "resolution": a.resolution,
            "content_id": a.content_id,
            "job_file": a.job_file,
        }
    if str(session().state.get("uid", "")) != str(job.get("uid")):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    if a.resolution == "confirmed":
        if not a.content_id or not a.content_id.isdigit():
            raise ValueError("CONTENT_ID_REQUIRED")
        detail = (
            call("detail", {"aweme_id": a.content_id}, expected_uid=job["uid"]).get(
                "aweme_detail"
            )
            or {}
        )
        author = detail.get("author") or {}
        if str(detail.get("aweme_id", "")) != a.content_id or str(
            author.get("uid_str") or author.get("uid") or ""
        ) != str(job["uid"]):
            raise ValueError("CONTENT_OWNER_MISMATCH")
        if detail.get("create_time", 0) < job.get("submitted_at", 0) - 120:
            raise ValueError("CONTENT_TIME_MISMATCH")
        text = detail.get("desc", "")
        if job["title"] not in text:
            raise ValueError("CONTENT_TITLE_MISMATCH")
        job.update(
            status="confirmed",
            content_id=a.content_id,
            url="https://www.douyin.com/"
            + ("note/" if job["kind"] == "image" else "video/")
            + a.content_id,
        )
    else:
        if a.content_id or not a.evidence or not a.evidence.strip():
            raise ValueError("OPERATOR_EVIDENCE_REQUIRED")
        job.update(status="not_published", resolution_evidence=a.evidence.strip())
    job["resolved_at"] = time.time()
    write_private(a.job_file, job)
    return {
        "ok": True,
        "status": job["status"],
        "job_file": a.job_file,
        **(
            {"content_id": job["content_id"], "url": job["url"]}
            if job.get("content_id")
            else {}
        ),
    }


def generate_cover(a):
    body = json.loads(Path(a.body_file).expanduser().read_text())
    if not isinstance(body, dict) or any(
        not body.get(k) for k in ("cover_uri", "img_uris", "creation_id", "uid")
    ):
        raise ValueError("COVER_BODY_INVALID")
    if not a.confirm:
        return {"ok": True, "preview": True, "body": body}
    uid = str(body["uid"])
    initial = call(
        "cover_generate", {"noToast": "true"}, body=body, confirm=True, expected_uid=uid
    )
    task = initial.get("task_id")
    if not task:
        raise DouyinRequestError("COVER_TASK_MISSING")
    target = Path(a.output).expanduser()
    write_private(target, {"task_id": str(task), "uid": uid, "status": "pending"})
    result = poll(
        "cover_result",
        {"task_id": str(task), "noToast": "true"},
        lambda r: (
            "done"
            if r.get("gen_code") == 2
            else "wait"
            if r.get("gen_code") in (0, 1, None)
            else "fail"
        ),
        expected_uid=uid,
    )
    if not (result.get("ai_cover") or {}).get("url_list"):
        raise DouyinRequestError("COVER_RESULT_MISSING")
    write_private(
        target, {"task_id": str(task), "uid": uid, "status": "done", "data": result}
    )
    return {"ok": True, "task_id": str(task), "output": str(target), "data": result}


def main():
    p = argparse.ArgumentParser(prog="douyin-publish")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("video", "note"):
        s = sub.add_parser(name)
        if name == "video":
            s.add_argument("--video", required=True)
            s.add_argument("--cover")
        else:
            s.add_argument("--images", nargs="+", required=True)
            s.add_argument("--cover-index", type=int, default=0)
        s.add_argument("--title", required=True)
        s.add_argument("--caption", default="")
        s.add_argument("--visibility", type=int, choices=(0, 1, 2), default=0)
        s.add_argument("--timing", type=int)
        s.add_argument("--no-download", action="store_true")
        s.add_argument("--declaration", choices=("aigc", "none"), default="aigc")
        s.add_argument("--music-id")
        s.add_argument("--original-sound", action="store_true")
        s.add_argument("--options-file")
        s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--job-file", required=True)
    s = sub.add_parser("resolve")
    s.add_argument("--job-file", required=True)
    s.add_argument(
        "--resolution", choices=("confirmed", "not-published"), required=True
    )
    s.add_argument("--content-id")
    s.add_argument("--evidence")
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("cover-generate")
    s.add_argument("--body-file", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--confirm", action="store_true")
    s = sub.add_parser("call")
    s.add_argument(
        "method",
        choices=[
            k
            for k, v in ENDPOINTS.items()
            if v["profile"] == "creator" and k not in ("create", "upload_auth")
        ],
    )
    s.add_argument("--params", default="{}")
    s.add_argument("--body-file")
    s.add_argument("--confirm", action="store_true")
    a = p.parse_args()
    if a.command == "resolve":
        return resolve_job(a)
    if a.command == "cover-generate":
        return generate_cover(a)
    if a.command == "status":
        return status_job(a)
    if a.command == "call":
        return {
            "ok": True,
            "data": call(
                a.method,
                json.loads(a.params),
                body=json.loads(Path(a.body_file).read_text()) if a.body_file else None,
                confirm=a.confirm,
            ),
        }
    return publish(a)


if __name__ == "__main__":
    try:
        r = main()
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r.get("ok") else 3)
    except (DouyinRequestError, SessionError, ValueError, OSError) as e:
        code = (
            e.code
            if isinstance(e, DouyinRequestError)
            else str(e)
            if isinstance(e, (SessionError, ValueError)) and str(e).isupper()
            else "PUBLISH_CLIENT_ERROR"
        )
        print(json.dumps({"ok": False, "error": code}))
        sys.exit(
            2
            if code
            in (
                "API_SESSION_MISSING",
                "API_SESSION_EXPIRED",
                "PLATFORM_AUTH_REJECTED",
                "PLATFORM_LOGIN_REJECTED",
            )
            else 1
        )
