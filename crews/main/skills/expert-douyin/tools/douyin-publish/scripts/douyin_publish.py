#!/usr/bin/env python3
"""Creator publishing with durable submission state and local media transfer."""

from __future__ import annotations
import argparse
import base64
import fcntl
import json
import os
import re
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
from douyin_utils.login import security_fields, refresh_security, flow
from douyin_utils.verification import creator_verification, validate_creator_verification, SMS_METHODS

STATE_DIR = Path.home() / ".openclaw/douyin-api/publish"


def publication_params(state):
    params = {"read_aid": "2906", **common("creator", state)}
    if state.state.get("tokens", {}).get("msToken"):
        params["msToken"] = state.state["tokens"]["msToken"]
    return params


def publication_headers(kind):
    page = (
        "image?enter_from=publish_page&media_type=image&type=new"
        if kind == "image" else "video?enter_from=publish_page"
    )
    return {
        "accept": "application/json, text/plain, */*",
        "referer": "https://creator.douyin.com/creator-micro/content/post/" + page,
        "origin": "https://creator.douyin.com",
    }


def preflight(kind, uid):
    state = session()
    if state.state.get("relay_runtime") and state.state.get("relay_security_expires_at", 0) <= time.time() + 60:
        refresh_security(uid)
    csrf("creator.douyin.com")
    state = session()
    url = "https://creator.douyin.com/web/api/media/aweme/create_v2/"
    security = state.security("creator.douyin.com")
    missing = [
        k
        for k in ("ticket", "ts_sign", "private_key", "dtrait_blob", "csrf_token")
        if not security.get(k) and not (
            state.state.get("relay_runtime") and k in security_fields(state)
        )
    ]
    if missing:
        raise DouyinRequestError("PUBLISH_SECURITY_MISSING", missing_fields=missing)
    prepare(
        "creator",
        "publish-security",
        url,
        security=security,
        fields={"work_type": kind},
        expected_uid=uid,
    )


def declaration_fields(choice, kind, creation_id, uid):
    if choice == "none":
        return {}
    result = call(
        "declaration",
        {
            "creation_id": creation_id,
            "user_decl_judge_feats": json.dumps(
                {
                    "has_ai_metadata": False,
                    "is_xing_tu_submit": False,
                    "has_marketing_poi": False,
                    "item_type": kind,
                },
                separators=(",", ":"),
            ),
        },
        expected_uid=uid,
    )
    data = result.get("data")
    options = data.get("options") if isinstance(data, dict) else None
    if not isinstance(options, list):
        raise DouyinRequestError("DECLARATION_RESPONSE_INVALID")
    matches = [
        o for o in options if isinstance(o, dict) and o.get("choose_value") == choice
    ]
    if len(matches) != 1 or (
        data.get("selectable") is False and not matches[0].get("choosen")
    ):
        raise DouyinRequestError("DECLARATION_UNAVAILABLE")
    if matches[0].get("show_type") not in (None, ""):
        raise DouyinRequestError("DECLARATION_RESPONSE_INVALID")
    return {
        "user_declare_info": json.dumps({"choose_value": choice}, separators=(",", ":"))
    }


def account_uid():
    user = call("self").get("user") or {}
    uid = str(user.get("uid") or user.get("uid_str") or "")
    if not uid.isdigit():
        raise DouyinRequestError("SELF_PROFILE_MISSING")
    if str(session().state.get("uid", "")) != uid:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    return uid


def check_readiness(a):
    uid = account_uid()
    kind = "image" if a.kind == "note" else "video"
    creation_id = uuid.uuid4().hex[:8] + str(int(time.time() * 1000))
    declaration_fields(a.declaration, kind, creation_id, uid)
    preflight(kind, uid)
    return {
        "ok": True,
        "ready": True,
        "kind": a.kind,
        "uid": uid,
        "declaration": a.declaration,
    }


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
        uid = account_uid()
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
        creation_id = uuid.uuid4().hex[:8] + str(int(time.time() * 1000))
        declared = declaration_fields(a.declaration, kind, creation_id, uid)
        preflight(kind, uid)
        job_file = STATE_DIR / f"job-{creation_id}.json"
        job = {
            "creation_id": creation_id,
            "options": options,
            "uid": uid,
            "kind": kind,
            "declaration": a.declaration,
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
        common_body.update(declared)
        if a.music_id:
            common_body.update(music_id=a.music_id, music_source=1)
        job.update(status="prepared", payload=item)
        write_private(job_file, job)
        # Media processing can outlast the security lease. Refresh before marking a submission.
        preflight(kind, uid)
        # Mark before sending: timeout, auth errors or interrupts never cause an automatic resend.
        job.update(status="submission_unknown", submitted_at=time.time())
        write_private(job_file, job)
        try:
            current = session()
            params = publication_params(current)
            result = request(
                "creator",
                "publish-security",
                "POST",
                "https://creator.douyin.com/web/api/media/aweme/create_v2/",
                expected_uid=uid,
                params=params,
                body=item,
                capture_response=True,
                fields={"work_type": kind},
                static_headers=publication_headers(kind),
            )
        except DouyinRequestError as exc:
            failure = {"code": exc.code}
            if exc.response_info is not None:
                failure["response_info"] = exc.response_info
            if exc.verification is not None:
                failure["verification"] = exc.verification
            if exc.response_prefix is not None:
                diagnostic_file = job_file.with_name("response-" + creation_id + ".json")
                # Response text can contain private tokens; expose only its path and summary.
                write_private(diagnostic_file, {
                    "response_info": exc.response_info,
                    "body_prefix_base64": base64.b64encode(exc.response_prefix).decode(),
                    "response_headers": exc.response_headers or {},
                })
                failure["diagnostic_file"] = str(diagnostic_file)
            job["last_error"] = failure
            write_private(job_file, job)
            return {
                "ok": False,
                "error": "PUBLISH_RESULT_UNKNOWN",
                "reason": exc.code,
                "job_file": str(job_file),
                **{k: v for k, v in failure.items() if k != "code"},
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


def job_verification(job, job_file):
    failure = job.get("last_error")
    creation_id = job.get("creation_id")
    if not isinstance(failure, dict) or not isinstance(creation_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,64}", creation_id):
        return None
    path = Path(job_file).expanduser().with_name("response-" + creation_id + ".json")
    if Path(failure.get("diagnostic_file") or "").expanduser() != path:
        return None
    try:
        saved = read_private(path)
    except (SessionError, OSError):
        return None
    verification = creator_verification(saved.get("response_headers"))
    info = failure.get("response_info")
    if verification and isinstance(info, dict) and info.get("log_id") == verification["log_id"]:
        return verification
    return None


def verification_result(value, job_file, *, output=None, export_instructions=False):
    value = validate_creator_verification(value)
    public = {key: item for key, item in value.items() if key != "user_action"}
    expired = value["expires_at"] <= time.time()
    if expired:
        public["status"] = "expired"
    next_step = {
        "prepared": "verify-send", "awaiting-code": "verify-code",
        "awaiting-up-sms": "send-sms-then-verify-confirm", "ticket-issued": "status-and-resolve",
    }[value["status"]]
    result = {"ok": True, "verification": public, "job_file": str(job_file),
              "next": "report-verification" if expired else next_step}
    if value.get("user_action") and not expired and export_instructions:
        path = Path(output).expanduser() if output else (
            session().path.parent / "verification" / f"creator-{value['id']}.json"
        )
        write_private(path, {"verification_id": value["id"], **value["user_action"]})
        result["instruction_file"] = str(path)
    return result


def verify_job(a):
    """Continue creator verification; never retry or resolve the publication."""
    job = read_private(a.job_file)
    state = session()
    if str(state.state.get("uid", "")) != str(job.get("uid")):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    if job.get("status") != "submission_unknown":
        raise ValueError("JOB_NOT_UNCERTAIN")
    challenge = job_verification(job, a.job_file)
    if not challenge:
        raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
    value = state.state.get("creator_verification")
    if value and value.get("log_id") != challenge["log_id"]:
        value = None
    output = getattr(a, "output", None)
    if a.command == "verify-status":
        if value:
            return verification_result(value, a.job_file)
        return {"ok": True, "verification": challenge, "next": "verify-prepare", "job_file": str(a.job_file)}
    if a.command == "verify-prepare":
        if value:
            return verification_result(value, a.job_file)
        diagnostic = read_private(job["last_error"]["diagnostic_file"])
        fields = {"uid": str(job["uid"]), "cookie": state.cookies("https://creator.douyin.com/"),
                  "decision": diagnostic["response_headers"]["x-tt-verify-passport-decision"],
                  "log_id": challenge["log_id"]}
    else:
        if not value:
            raise DouyinRequestError("VERIFICATION_INIT_REQUIRED")
        value = validate_creator_verification(value)
        if value["expires_at"] <= time.time():
            raise DouyinRequestError("VERIFICATION_EXPIRED")
        if a.method not in value["methods"]:
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        if value.get("method") and value["method"] != a.method:
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        if value["status"] == "ticket-issued" or (a.command == "verify-send" and value["status"] in {"awaiting-code", "awaiting-up-sms"}):
            return verification_result(value, a.job_file, output=output, export_instructions=a.command == "verify-send")
        if a.command in {"verify-send", "verify-confirm"} and not a.confirm:
            return {"ok": True, "preview": True, "action": a.command, "method": a.method,
                    "verification": {k: v for k, v in value.items() if k != "user_action"}}
        fields = {"uid": str(job["uid"]), "cookie": state.cookies("https://creator.douyin.com/"),
                  "verification_id": value["id"], "method": a.method}
        if a.command == "verify-code":
            path = Path(a.code_file).expanduser()
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise SessionError("API_SESSION_UNSAFE")
            code = path.read_text().strip()
            if not re.fullmatch(r"[0-9]{4,6}", code):
                raise ValueError("INVALID_SMS_CODE")
            fields["code"] = code
    pending = state.state.get("creator_verification_flow")
    if pending and pending.get("action") == a.command:
        saved_fields = pending.get("fields", {})
        if {k: v for k, v in saved_fields.items() if k != "cookie"} == {k: v for k, v in fields.items() if k != "cookie"}:
            fields = saved_fields
    result = flow(a.command, fields)
    return verification_result(result["verification"], a.job_file, output=output, export_instructions=a.command == "verify-send")


def status_job(a):
    job = read_private(a.job_file)
    failure = job.get("last_error")
    diagnostic = {
        "last_error": {k: failure[k] for k in ("code", "response_info", "diagnostic_file") if k in failure}
    } if isinstance(failure, dict) else {}
    if str(session().state.get("uid", "")) != str(job.get("uid")):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    verification = job_verification(job, a.job_file) if job["status"] == "submission_unknown" else None
    if verification:
        diagnostic["verification"] = verification
    if job["status"] == "confirmed":
        return {
            "ok": True,
            "status": job["status"],
            "content_id": job["content_id"],
            "url": job["url"],
            **diagnostic,
        }
    if job["status"] in ("not_published", "uploading", "prepared"):
        return {"ok": True, "status": job["status"], **diagnostic}
    user = call("self", expected_uid=job["uid"]).get("user") or {}
    if str(user.get("uid") or user.get("uid_str") or "") != str(job["uid"]):
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    result = call(
        "preview_videos", {"count": "50", "max_cursor": "0"}, expected_uid=job["uid"]
    )
    items = result.get("aweme_list")
    if not isinstance(items, list):
        raise DouyinRequestError("PLATFORM_LIST_MISSING")
    candidates = []
    for item in items[:50]:
        if not isinstance(item, dict):
            continue
        author = item.get("author") or {}
        title = item.get("desc", "")
        created = item.get("create_time")
        if not isinstance(author, dict) or not isinstance(title, str) or not isinstance(created, int):
            continue
        if (
            str(author.get("uid_str") or author.get("uid") or "") == str(job["uid"])
            and job["title"] in title
            and created >= job.get("submitted_at", 0) - 120
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
        "source": "douyin:creator_work_list",
        "checked": min(len(items), 50),
        **diagnostic,
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
    s = sub.add_parser(
        "check",
        help="Check account, declaration and signing readiness without uploading or publishing",
    )
    s.add_argument("--kind", choices=("video", "note"), default="video")
    s.add_argument("--declaration", choices=("aigc", "none"), default="aigc")
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
    for name in ("verify-prepare", "verify-status", "verify-send", "verify-code", "verify-confirm"):
        s = sub.add_parser(name, help="Creator verification bound to the original publication and API session")
        s.add_argument("--job-file", required=True)
        if name in {"verify-send", "verify-code", "verify-confirm"}:
            s.add_argument("--method", required=True, choices=SMS_METHODS)
        if name in {"verify-send", "verify-confirm"}:
            s.add_argument("--confirm", action="store_true")
        if name == "verify-send":
            s.add_argument("--output")
        if name == "verify-code":
            s.add_argument("--code-file", required=True)
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
    if a.command.startswith("verify-"):
        return verify_job(a)
    if a.command == "check":
        return check_readiness(a)
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
        result = {"ok": False, "error": code}
        if isinstance(e, DouyinRequestError) and e.missing_fields:
            result["missing_fields"] = e.missing_fields
        if isinstance(e, DouyinRequestError) and e.verification is not None:
            result["verification"] = e.verification
        print(json.dumps(result))
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
