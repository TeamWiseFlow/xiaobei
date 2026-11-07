"""Creator HTTP publishing with durable submission and reconciliation state."""

import json
import os
from pathlib import Path
import secrets
import time
from contextlib import contextmanager

from .api import call, common, csrf
from .http import DouyinRequestError, prepare, request, session, public_error_info
from .login import flow, refresh_channel, refresh_security
from .media import upload
from .payload import PublishPayload
from .session import read_private, write_private, session_lock

CREATOR = "https://creator.douyin.com"
CREATE_PATH = "/web/api/media/aweme/create_v2/"
STATE_PATH = Path(os.environ.get("DOUYIN_API_PUBLICATION_STATE", str(Path.home() / ".openclaw/douyin-api/publication.json"))).expanduser()


@contextmanager
def publication_lock():
    with session_lock(STATE_PATH):
        yield


@contextmanager
def preparation_step(job, name):
    if job is not None:
        job["preparation_step"] = name
        write_private(STATE_PATH, job)
    try:
        yield
    except (DouyinRequestError, ValueError, OSError) as exc:
        exc.preparation_step = name
        raise
    else:
        if job is not None:
            job.setdefault("preparation_completed_steps", []).append(name)
            write_private(STATE_PATH, job)


def asset_metadata(value):
    return {key: value[key] for key in ("vid", "uri", "poster_uri", "width", "height", "duration") if key in value}


def pending():
    if not STATE_PATH.exists():
        return None
    job = read_private(STATE_PATH)
    return job if job.get("state") not in {"confirmed", "cancelled"} else None


def owner():
    result = call("self")
    uid = str((result.get("user") or {}).get("uid", ""))
    if not uid.isdigit():
        raise DouyinRequestError("SELF_PROFILE_MISSING")
    return uid


def ensure_owner(uid):
    if str(session().state.get("uid", "")) != uid:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")


def ensure_session(uid):
    ensure_owner(uid)
    state = session().state
    renewed = state.get("relay_security_expires_at", 0) < time.time() + 60
    if renewed:
        refresh_security(uid)
    if renewed or state.get("session_channels", {}).get("creator", 0) < time.time() + 60:
        refresh_channel("creator")
    csrf("creator.douyin.com")


def declaration_payload(value):
    if value in {"aigc", "ai"}:
        return {"user_declare_info": json.dumps({"choose_value": "aigc"}, separators=(",", ":"))}
    if value == "none":
        return None
    raise ValueError("INVALID_DECLARATION")


def add_publish_fields(payload, declaration, vertical=None, horizontal=None):
    declared = declaration_payload(declaration)
    if declared:
        payload["item"]["declare"] = declared
    if vertical is not None or horizontal is not None:
        if not vertical or not horizontal:
            raise ValueError("DUAL_COVER_MISSING")
        for image, ratio in ((vertical, 3 / 4), (horizontal, 4 / 3)):
            if (not isinstance(image.get("uri"), str) or not image["uri"]
                    or any(type(image.get(k)) is not int or image[k] <= 0 for k in ("width", "height"))
                    or abs(image["width"] / image["height"] - ratio) > 0.01):
                raise ValueError("COVER_METADATA_INVALID")
        cover = payload["item"]["cover"]
        cover.update(poster=vertical["uri"], poster_delay=0,
                     custom_cover_image_width=vertical["width"], custom_cover_image_height=vertical["height"],
                     horizontal_custom_cover_image_uri=horizontal["uri"], horizontal_cover_tsp=0,
                     horizontal_custom_cover_image_width=horizontal["width"], horizontal_custom_cover_image_height=horizontal["height"])
        tools = json.loads(cover["cover_tools_extend_info"])
        def info(image):
            return {"uri": image["uri"], "edited": True, "posterDelay": 0,
                    "customCoverImageWidth": image["width"], "customCoverImageHeight": image["height"]}
        tools.update(coverInfo={**tools.get("coverInfo", {}), **info(vertical)},
                     coverHorizontalInfo=info(horizontal))
        cover["cover_tools_extend_info"] = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
    return payload


def items(uid, *, pages=10):
    cursor, seen, result = "0", set(), []
    for _ in range(pages):
        body = call("creator_items", {"max_cursor": cursor}, expected_uid=uid)
        batch = body.get("items")
        if not isinstance(batch, list):
            raise DouyinRequestError("CREATOR_ITEMS_INVALID")
        result.extend(batch)
        if not body.get("has_more"):
            return result
        nxt = str(body.get("max_cursor", ""))
        if not nxt or nxt == cursor or nxt in seen:
            raise DouyinRequestError("CREATOR_CURSOR_INVALID")
        seen.add(cursor)
        cursor = nxt
    raise DouyinRequestError("CREATOR_PAGE_LIMIT")


def item_id(item):
    return str(item.get("item_id") or item.get("aweme_id") or item.get("id") or "")


def summary(job):
    result = {k: job[k] for k in ("attempt_id", "uid", "kind", "state", "submission_attempted", "item_id", "url", "error", "verification", "evidence",
                                "preparation_step", "preparation_completed_steps", "failed_at", "relay_info", "http_status",
                                "request_info", "response_info", "diagnostic_file") if k in job}
    result.update(ok=job["state"] in {"confirmed", "cancelled"}, receipt=str(STATE_PATH), session_source="api",
                  accepted=True if job["state"] == "confirmed" else None,
                  next=None if job["state"] in {"confirmed", "cancelled"} else
                       "resume" if job.get("submission_attempted") else "publish" if job["state"] == "prepared" else "close")
    return result


def confirm(job, ident, *, evidence="platform-item-id"):
    if not ident.isdigit() or not 15 <= len(ident) <= 22:
        raise DouyinRequestError("PUBLISH_ITEM_ID_INVALID")
    job.update(state="confirmed", item_id=ident, evidence=evidence,
               url="https://www.douyin.com/" + ("video/" if job["kind"] == "video" else "note/") + ident)
    job.pop("error", None)
    write_private(STATE_PATH, job)
    return summary(job)


def reconcile(job):
    if job["state"] in {"confirmed", "cancelled"}:
        return summary(job)
    if owner() != job["uid"]:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    if not job.get("submission_attempted"):
        return summary(job)
    candidates = []
    text = job["payload"]["item"]["common"]["text"]
    for item in items(job["uid"]):
        ident = item_id(item)
        if ident in job["baseline"] or not ident.isdigit():
            continue
        author = item.get("author") or {}
        if str(author.get("uid", job["uid"])) != job["uid"]:
            continue
        created = item.get("create_time")
        if not isinstance(created, (int, float)) or not job["submitted_at"] - 300 <= created <= time.time() + 60:
            continue
        if item.get("desc") != text:
            continue
        candidates.append(ident)
    if len(set(candidates)) == 1:
        return confirm(job, candidates[0], evidence="creator-list-match")
    job["state"] = "submission_unknown"
    write_private(STATE_PATH, job)
    return {**summary(job), "candidates": candidates, "hint": "保留原任务，继续只读核查；不要重新发布"}


def publish(job):
    if job.get("submission_attempted"):
        return reconcile(job)
    ensure_session(job["uid"])
    ensure_owner(job["uid"])
    body = job["payload"]
    # Validate signing inputs before recording the once-only submission intent.
    query = common("creator", session())
    query.update(read_aid="2906", msToken=session().state["tokens"]["creator_msToken"])
    from .http import append_params
    with preparation_step(job, "publish_security"):
        prepare("creator", "publish-security", append_params(CREATOR + CREATE_PATH, query),
                fields={"work_type": "video" if job["kind"] == "video" else "image"},
                expected_uid=job["uid"])
    job.update(state="submitting", submission_attempted=True, submitted_at=time.time())
    write_private(STATE_PATH, job)
    try:
        response = call("create", {"read_aid": "2906"}, body=body, confirm=True, expected_uid=job["uid"])
        ident = str(response.get("item_id") or "")
        if response.get("status_code") in (0, "0") and ident.isdigit():
            return confirm(job, ident)
        raise DouyinRequestError("PUBLISH_RESPONSE_UNCONFIRMED")
    except (DouyinRequestError, OSError, ValueError) as exc:
        job.update(state="awaiting_verification" if getattr(exc, "verification", None) else "submission_unknown",
                   error=getattr(exc, "code", "PUBLISH_RESULT_UNKNOWN"))
        job.update(public_error_info(exc))
        if getattr(exc, "verification", None):
            job["verification"] = exc.verification
            diagnostic = STATE_PATH.parent / "diagnostics" / (job["attempt_id"] + ".json")
            write_private(diagnostic, {"headers": getattr(exc, "response_headers", {}) or {}})
            job["diagnostic"] = str(diagnostic)
        job["error"] = getattr(exc, "code", "PUBLISH_RESULT_UNKNOWN")
        write_private(STATE_PATH, job)
        return {**summary(job), "hint": "已尝试提交，先核查或完成本任务验证；不要重发"}


def verify(job, args):
    if args.action in {"verify-send", "verify-confirm"} and not getattr(args, "confirm", False):
        return {"ok": True, "preview": True, "action": args.action}
    if not job.get("submission_attempted") or not job.get("diagnostic"):
        raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
    if owner() != job["uid"]:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    headers = read_private(job["diagnostic"])["headers"]
    cookie = session().cookies(CREATOR + "/")
    base = {"uid": job["uid"], "cookie": cookie}
    if args.action in {"verify-qr", "verify-poll"}:
        if job.get("verification", {}).get("reason") != "gateway_biz_verify":
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        if args.action == "verify-qr":
            result = flow("creator-qr", {**base, "decision": headers["x-tt-verify-passport-decision"],
                                         "log_id": job["verification"]["log_id"]})
        else:
            challenge = job.get("creator_challenge") or {}
            if not challenge.get("id"):
                raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
            result = flow("creator-poll", {**base, "verification_id": challenge["id"]})
        challenge = result.get("creator_challenge")
        import re
        if (not isinstance(challenge, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(challenge.get("id", "")))
                or challenge.get("log_id") != job["verification"]["log_id"]
                or challenge.get("status") not in {"awaiting-scan", "verified", "expired"}
                or type(challenge.get("expires_at")) is not int):
            raise DouyinRequestError("INVALID_RELAY_RESPONSE")
        job["creator_challenge"] = {k: v for k, v in challenge.items() if k != "qr_uri"}
        if challenge.get("qr_uri"):
            import qrcode
            from urllib.parse import urlsplit
            uri = urlsplit(challenge["qr_uri"])
            if (challenge["status"] != "awaiting-scan" or uri.scheme != "https"
                    or not (uri.hostname or "").endswith(".douyin.com")
                    or uri.username or uri.password or uri.port or uri.fragment):
                raise DouyinRequestError("INVALID_RELAY_RESPONSE")
            target = STATE_PATH.parent / (job["attempt_id"] + "-verification.png")
            if target.is_symlink():
                raise ValueError("API_SESSION_UNSAFE")
            qrcode.make(challenge["qr_uri"]).save(target)
            target.chmod(0o600)
            job["verification_qr"] = str(target)
        elif challenge["status"] in {"verified", "expired"}:
            (STATE_PATH.parent / (job["attempt_id"] + "-verification.png")).unlink(missing_ok=True)
            job.pop("verification_qr", None)
        write_private(STATE_PATH, job)
        return {**summary(job), "verification_status": challenge["status"],
                "qr_file": job.get("verification_qr"), "hint": "验证完成后 resume 核查原提交，不自动重发"}
    if args.action == "verify-prepare":
        result = flow("verify-prepare", {**base, "decision": headers["x-tt-verify-passport-decision"],
                                         "log_id": job["verification"]["log_id"]}, restart=getattr(args, "restart", False))
    else:
        value = session().state.get("creator_verification") or {}
        method = getattr(args, "method", None) or ("mobile_sms_verify" if args.action == "verify-code" else None)
        if not value.get("id") or method not in value.get("methods", []):
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        fields = {**base, "verification_id": value["id"], "method": method}
        if args.action == "verify-code":
            path = Path(args.code_file).expanduser()
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise ValueError("API_SESSION_UNSAFE")
            code = path.read_text().strip()
            if not code.isdigit() or not 4 <= len(code) <= 6:
                raise ValueError("INVALID_VERIFICATION_CODE")
            fields["code"] = code
        result = flow(args.action, fields)
    value = result.get("verification") or {}
    action_path = None
    if value.get("user_action"):
        action_path = STATE_PATH.parent / (job["attempt_id"] + "-user-action.json")
        write_private(action_path, value["user_action"])
    return {**summary(job), "verification": {k: v for k, v in value.items() if k != "user_action"},
            "user_action_file": str(action_path) if action_path else None, "verification_status": value.get("status"),
            "hint": "验证票据不等于发布成功；继续 resume 核查原提交"}


def run(args, *, stop_before_submit=False, prepare_cover=None):
    with publication_lock():
        if pending():
            raise DouyinRequestError("PUBLISH_PENDING")
        if STATE_PATH.exists():
            previous = read_private(STATE_PATH)
            archive = STATE_PATH.parent / "receipts" / (str(previous["attempt_id"]) + ".json")
            write_private(archive, previous)
        with preparation_step(None, "account_check"):
            uid = owner()
        with preparation_step(None, "session_prepare"):
            ensure_session(uid)
        with preparation_step(None, "baseline_read"):
            baseline = [item_id(item) for item in items(uid)]
        creation_id = secrets.token_hex(4) + str(int(time.time() * 1000))
        job = {"formatVersion": 1, "attempt_id": secrets.token_hex(16), "uid": uid,
               "kind": args.command, "created_at": time.time(), "creation_id": creation_id,
               "title": args.title, "caption": args.caption, "state": "uploading", "baseline": baseline,
               "submission_attempted": False}
        write_private(STATE_PATH, job)
        try:
            with preparation_step(job, "declaration_suggestion"):
                call("declaration_suggestion", {"creation_id": creation_id,
                     "user_decl_judge_feats": json.dumps({"has_ai_metadata": False, "is_xing_tu_submit": False,
                         "has_marketing_poi": False, "item_type": "image" if args.command == "note" else "video"},
                         separators=(",", ":"))}, expected_uid=uid)
            if args.command == "note":
                images = []
                for index, path in enumerate(args.images):
                    with preparation_step(job, "image_upload_" + str(index + 1)):
                        ensure_owner(uid)
                        image = upload(path, "image", user_id=uid, expected_uid=uid)
                        images.append(image)
                        job.setdefault("uploaded_images", []).append(asset_metadata(image))
                with preparation_step(job, "payload_build"):
                    payload = PublishPayload.build_image_create_item(images, title=args.title, desc=args.caption,
                                                                    visibility=args.visibility, creation_id=creation_id)
                    payload = add_publish_fields(payload, args.declaration)
            else:
                with preparation_step(job, "video_upload"):
                    ensure_owner(uid)
                    media = upload(args.video, "video", user_id=uid, expected_uid=uid)
                    job["uploaded_media"] = asset_metadata(media)
                    if min(media.get("width", 0), media.get("height", 0), media.get("duration", 0)) <= 0:
                        raise DouyinRequestError("VIDEO_METADATA_MISSING")
                with preparation_step(job, "video_enable"):
                    call("video_enable", {"video_id": media["vid"]}, expected_uid=uid)
                with preparation_step(job, "video_transend"):
                    call("video_transend", {"video_id": media["vid"]}, expected_uid=uid)
                deadline = time.monotonic() + 180
                detect = {"resource_list": [{"type": 2, "video_id": media["vid"],
                                             "duration": round(media["duration"]), "cover_uri": ""}],
                          "source": 1, "is_redetect": False}
                with preparation_step(job, "video_processing"):
                    while True:
                        checked = call("fast_detect", body=detect, confirm=True, expected_uid=uid)
                        if checked.get("has_done") is True:
                            break
                        if checked.get("task_id"):
                            detect["task_id"] = str(checked["task_id"])
                        if time.monotonic() >= deadline:
                            raise DouyinRequestError("VIDEO_PROCESSING_TIMEOUT")
                        time.sleep(2)
                covers = []
                directory = STATE_PATH.parent / ("covers-" + job["attempt_id"])
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                for name, source, ratio in (("vertical", args.cover_vertical, (3, 4)), ("horizontal", args.cover_horizontal, (4, 3))):
                    with preparation_step(job, "cover_" + name + "_prepare"):
                        target = directory / (name + ".jpg")
                        if prepare_cover is None:
                            raise ValueError("COVER_PROCESSOR_MISSING")
                        prepare_cover(source, target, ratio)
                    with preparation_step(job, "cover_" + name + "_upload"):
                        ensure_owner(uid)
                        cover = upload(target, "image", user_id=uid, expected_uid=uid)
                        covers.append(cover)
                        job.setdefault("uploaded_covers", []).append({"kind": name, **asset_metadata(cover)})
                with preparation_step(job, "payload_build"):
                    payload = PublishPayload.build_video_create_item(media, title=args.title, desc=args.caption,
                                                                    visibility=args.visibility, creation_id=creation_id,
                                                                    poster_uri=covers[0]["uri"])
                    payload = add_publish_fields(payload, args.declaration, *covers)
            job.update(state="prepared", payload=payload)
            write_private(STATE_PATH, job)
            return {**summary(job), "ok": True, "prepared": True} if stop_before_submit else publish(job)
        except (DouyinRequestError, ValueError, OSError) as exc:
            if not job.get("submission_attempted"):
                job.update(state="preparation_failed", failed_at=time.time(),
                           error=getattr(exc, "code", "PUBLISH_PREPARATION_FAILED"), **public_error_info(exc))
                write_private(STATE_PATH, job)
            raise


def execute(args, *, prepare_cover=None):
    supported = {"run", "publish", "close", "status", "get-link", "resume", "verify-prepare",
                 "verify-qr", "verify-poll", "verify-send", "verify-code", "verify-confirm"}
    if args.action not in supported:
        raise ValueError("HTTP_PUBLISH_ACTION_UNSUPPORTED")
    if args.action == "run":
        if not getattr(args, "confirm", False):
            return {"ok": True, "preview": True, "action": "run"}
        return run(args, stop_before_submit=getattr(args, "prepare_only", False), prepare_cover=prepare_cover)
    with publication_lock():
        if not STATE_PATH.exists():
            if args.action == "status":
                return {"ok": True, "state": "idle", "session_source": "api", "receipt": str(STATE_PATH),
                        "submission_attempted": False, "current_action_submission_attempted": False}
            raise ValueError("PUBLISH_RECEIPT_MISSING")
        job = read_private(STATE_PATH)
        if job["kind"] != args.command:
            raise ValueError("PUBLISH_KIND_MISMATCH")
        if args.action.startswith("verify-"):
            return verify(job, args)
        if args.action in {"status", "get-link", "resume"}:
            return reconcile(job) if args.action != "status" else summary(job)
        if args.action == "publish":
            if not getattr(args, "confirm", False):
                return {"ok": True, "preview": True, "action": "publish"}
            if job["state"] not in {"prepared", "confirmed", "submission_unknown", "awaiting_verification", "submitting"}:
                raise ValueError("PUBLISH_NOT_PREPARED")
            return publish(job)
        if args.action == "close":
            if not args.confirm:
                return {"ok": True, "preview": True}
            if not isinstance(args.confirmation, str) or not args.confirmation.strip():
                raise ValueError("USER_CONFIRMATION_REQUIRED")
            if args.outcome == "published":
                from .api import item_id as parse_id
                job["confirmation"] = args.confirmation
                return confirm(job, parse_id(args.url), evidence="user-confirmed")
            job.update(state="cancelled", confirmation=args.confirmation)
            write_private(STATE_PATH, job)
            return summary(job)
        raise ValueError("API_ACTION_UNSUPPORTED")
