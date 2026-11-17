"""Creator HTTP publishing with durable submission and reconciliation state."""

import json
import base64
import hashlib
import os
from pathlib import Path
import secrets
import time
import io
import tempfile
from contextlib import contextmanager

from .api import call, common, csrf
from .http import (DouyinRequestError, prepare, request, session, public_error_info,
                   private_response_headers, response_info)
from .login import flow, refresh_channel, refresh_security
from .media import upload
from .payload import PublishPayload
from .session import read_private, write_private, session_lock, identity_binding, SessionError
from .verification import creator_verification, validate_creator_verification, decode_verification_qr, validate_face_action

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


def payload_digest(job):
    return hashlib.sha256(json.dumps(job["payload"], ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def pending():
    if not STATE_PATH.exists():
        return None
    job = read_private(STATE_PATH)
    return job if job.get("state") not in {"confirmed", "cancelled"} else None


def owner(*, max_age=60):
    current = session()
    if max_age > 0 and current.state.get("login_error") in {"PLATFORM_LOGIN_REJECTED", "PLATFORM_AUTH_REJECTED"}:
        raise DouyinRequestError(current.state["login_error"])
    checked = current.state.get("identity_check") or {}
    stamp = checked.get("at", 0)
    age = time.time() - stamp if type(stamp) in (int, float) else float("inf")
    if (max_age > 0 and 0 <= age < max_age and checked.get("uid") == current.state.get("uid")
            and checked.get("binding") and checked["binding"] == identity_binding(current)
            and not current.runtime_expired and not current.state.get("login_identity_pending")
            and not current.state.get("login_error")):
        return checked["uid"]
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


def publication_verification(job):
    """Reclassify old receipts from their latest private response, without writes."""
    if job.get("diagnostic"):
        try:
            decision = creator_verification(read_private(job["diagnostic"]).get("headers"))
            if decision:
                return decision
        except (OSError, ValueError, SessionError):
            pass
    return job.get("verification") or {}


def verification_next(value):
    status = value.get("status")
    if status == "prepared":
        methods = value.get("methods", [])
        return ("verify-send" if "mobile_sms_verify" in methods or "mobile_up_sms_verify" in methods else
                "verify-face-prepare" if "face_verify" in methods else "verify-qr")
    return {"awaiting-code": "verify-code", "awaiting-up-sms": "verify-confirm",
            "awaiting-face": "verify-face-check", "awaiting-scan": "verify-poll", "scanned": "verify-poll",
            "ticket-issued": "retry-verified", "expired": "verify-prepare --restart",
            "refused": "verify-prepare --restart"}.get(status)


def summary(job):
    result = {k: job[k] for k in ("attempt_id", "uid", "kind", "state", "submission_attempted", "item_id", "url", "error", "verification", "evidence",
                                "preparation_step", "preparation_completed_steps", "failed_at", "relay_info", "http_status",
                                "request_info", "response_info", "diagnostic_file") if k in job}
    result.update(ok=job["state"] in {"confirmed", "cancelled"}, receipt=str(STATE_PATH), session_source="api",
                  publication_confirmed=job["state"] == "confirmed",
                  accepted=True if job["state"] == "confirmed" else None,
                  next=None if job["state"] in {"confirmed", "cancelled"} else
                       "resume" if job.get("submission_attempted") else "publish" if job["state"] == "prepared" else "close")
    verification = publication_verification(job) if job["state"] not in {"confirmed", "cancelled"} else {}
    if verification:
        result["verification"] = verification
    progress = job.get("verification_progress") or {}
    if (job["state"] not in {"confirmed", "cancelled"} and verification
            and progress.get("log_id") == verification.get("log_id")):
        result["verification_status"] = progress.get("status")
        result["next"] = verification_next(progress)
        if progress.get("expires_at", 0) <= time.time():
            result["verification_status"] = "expired"
            result["next"] = "verify-prepare --restart"
    elif job["state"] == "awaiting_verification" and verification.get("reason") in {
            "gateway_web_authlv_check", "gateway_biz_verify_with_face"}:
        result["next"] = "verify-prepare"
    ready = job.get("verified_retry_ready") or {}
    if (job["state"] not in {"confirmed", "cancelled"} and ready.get("expires_at", 0) > time.time()
            and ready.get("log_id") == verification.get("log_id")
            and not any(a.get("log_id") == ready.get("log_id") for a in job.get("verified_retries", []))):
        result["next"] = "retry-verified"
    if verification.get("supported") is False:
        result.update(ok=False, error="VERIFICATION_METHOD_UNSUPPORTED", next="resume",
                      hint="平台要求的人脸或二维码验证尚不支持；停止短信验证和发布续接，仅核查原作品")
    if (result.get("next") == "retry-verified" and any(
            entry.get("log_id") == verification.get("log_id") for entry in job.get("verified_retries", []))):
        result["next"] = "resume"
    result["verified_retry_count"] = len(job.get("verified_retries", []))
    return result


def confirm(job, ident, *, evidence="platform-item-id"):
    if not ident.isdigit() or not 15 <= len(ident) <= 22:
        raise DouyinRequestError("PUBLISH_ITEM_ID_INVALID")
    job.update(state="confirmed", item_id=ident, evidence=evidence,
               url="https://www.douyin.com/" + ("video/" if job["kind"] == "video" else "note/") + ident)
    job.pop("error", None)
    if job.get("verification"):
        job["completed_verification"] = job.pop("verification")
    job.pop("verified_retry_ready", None)
    write_private(STATE_PATH, job)
    return summary(job)


def reconcile(job, *, force=False):
    if job["state"] in {"confirmed", "cancelled"}:
        return summary(job)
    if job.get("submission_payload_sha256", payload_digest(job)) != payload_digest(job):
        raise DouyinRequestError("PUBLISH_PAYLOAD_CHANGED")
    checked = job.get("last_reconciliation") or {}
    age = time.time() - checked.get("at", 0)
    if (not force and checked and 0 <= age < 15 and checked.get("payload_sha256") == payload_digest(job)):
        ensure_owner(job["uid"])
        if checked.get("binding") and checked["binding"] == identity_binding(session()):
            return {**summary(job), "candidates": checked["candidates"], "cached": True,
                    "checked_at": checked["at"], "retry_after_seconds": max(1, int(15 - age))}
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
    job["last_reconciliation"] = {"at": time.time(), "candidates": candidates,
                                  "payload_sha256": payload_digest(job), "binding": identity_binding(session())}
    job["state"] = "submission_unknown"
    write_private(STATE_PATH, job)
    result = {**summary(job), "candidates": candidates, "cached": False,
              "checked_at": job["last_reconciliation"]["at"], "retry_after_seconds": 15}
    result.setdefault("hint", "保留原任务，继续只读核查；验证后续接使用 retry-verified")
    return result


def publish(job):
    if job.get("submission_attempted"):
        return reconcile(job)
    ensure_session(job["uid"])
    ensure_owner(job["uid"])
    # Validate signing inputs before recording the once-only submission intent.
    query = common("creator", session())
    query.update(read_aid="2906", msToken=session().state["tokens"]["creator_msToken"])
    from .http import append_params
    with preparation_step(job, "publish_security"):
        prepare("creator", "publish-security", append_params(CREATOR + CREATE_PATH, query),
                fields={"work_type": "video" if job["kind"] == "video" else "image"},
                expected_uid=job["uid"])
    job.update(state="submitting", submission_attempted=True, submitted_at=time.time(),
               submission_payload_sha256=payload_digest(job))
    write_private(STATE_PATH, job)
    return _submit(job)


def _submit(job, *, before_send=None):
    """Send only after the caller has durably recorded a distinct send intent."""
    suffix = ("-retry-" + str(len(job["verified_retries"])) if job.get("verified_retries") else
              "-operator-" + str(len(job["operator_retries"])) if job.get("operator_retries") else "")
    diagnostic = STATE_PATH.parent / "diagnostics" / (job["attempt_id"] + suffix + ".json")

    def capture(response):
        # Persist the platform evidence before cookie harvesting or parsing can
        # fail. An unrecognized decision must remain available for diagnosis.
        current = session()
        headers = private_response_headers(response)
        write_private(diagnostic, {"formatVersion": 2, "captured_at": time.time(),
                                  "attempt_id": job["attempt_id"], "creation_id": job["creation_id"],
                                  "payload_sha256": payload_digest(job),
                                  "response": response_info(response),
                                  "headers": headers,
                                  "header_bytes": {name: len(str(response.headers.get(name, "")).encode())
                                                   for name in headers},
                                  "body_prefix_base64": base64.b64encode(response.content[:512]).decode(),
                                  "security_expires_at": current.state.get("relay_security_expires_at"),
                                  "creator_channel_expires_at": current.state.get("session_channels", {}).get("creator")})
        job["diagnostic"] = str(diagnostic)
        job["diagnostic_file"] = str(diagnostic)
        job["response_info"] = response_info(response)
        job["http_status"] = response.status_code
        write_private(STATE_PATH, job)

    try:
        response = call("create", {"read_aid": "2906"}, body=job["payload"], confirm=True, expected_uid=job["uid"],
                        on_response=capture,
                        **({"before_send": before_send} if before_send is not None else {}))
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
            if (job.get("verification_progress") or {}).get("log_id") != exc.verification.get("log_id"):
                job.pop("verification_progress", None)
        job.pop("verified_retry_ready", None)
        if getattr(exc, "response_headers", None) is not None and not diagnostic.exists():
            write_private(diagnostic, {"headers": getattr(exc, "response_headers", {}) or {}})
            job["diagnostic"] = str(diagnostic)
            job["diagnostic_file"] = str(diagnostic)
        job["error"] = getattr(exc, "code", "PUBLISH_RESULT_UNKNOWN")
        write_private(STATE_PATH, job)
        result = summary(job)
        result.setdefault("hint", "已尝试提交，先核查或完成本任务验证；不要重发")
        return result


def retry_verified(job, args):
    """One explicit continuation per verified challenge, retaining the original payload."""
    if job["state"] in {"confirmed", "cancelled"}:
        return summary(job)
    if publication_verification(job).get("supported") is False:
        return summary(job)
    if not getattr(args, "confirm", False):
        return {"ok": True, "preview": True, "action": "retry-verified", "attempt_id": job["attempt_id"],
                "requires": ["valid-creator-verification", "original-work-confirmed-not-published"]}
    confirmation = getattr(args, "not_published_confirmation", "")
    if not isinstance(confirmation, str) or not confirmation.strip():
        raise ValueError("USER_CONFIRMATION_REQUIRED")
    if job["state"] == "submitting" and job.get("verified_retries"):
        return reconcile(job)
    if not job.get("submission_attempted") or job.get("state") not in {"awaiting_verification", "submission_unknown"}:
        raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
    current = session()
    ensure_owner(job["uid"])
    if (not current.state.get("creator_verification_binding")
            or current.state["creator_verification_binding"] != identity_binding(current)):
        raise DouyinRequestError("VERIFICATION_CONTEXT_MISMATCH")
    expected_binding = current.state["creator_verification_binding"]
    try:
        value = validate_creator_verification(current.state.get("creator_verification"))
    except ValueError as exc:
        raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING") from exc
    if value["status"] != "ticket-issued" or value["ticket_present"] is not True:
        raise DouyinRequestError("VERIFICATION_TICKET_MISSING")
    if any(a.get("log_id") == value["log_id"] for a in job.get("verified_retries", [])):
        return reconcile(job)
    if value["expires_at"] <= time.time():
        raise DouyinRequestError("VERIFICATION_EXPIRED")
    decision = creator_verification(read_private(job["diagnostic"])["headers"])
    if (not decision or decision.get("reason") not in {"gateway_web_authlv_check", "gateway_biz_verify_with_face"}
            or decision["log_id"] != value["log_id"] or value["log_id"] != job.get("verification", {}).get("log_id")):
        raise DouyinRequestError("VERIFICATION_CONTEXT_MISMATCH")
    if value.get("method") not in decision.get("methods", []):
        raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
    digest = payload_digest(job)
    if job.get("submission_payload_sha256", digest) != digest:
        raise DouyinRequestError("PUBLISH_PAYLOAD_CHANGED")
    creation = str(job["payload"].get("item", {}).get("common", {}).get("creation_id", ""))
    if not creation or creation != str(job.get("creation_id", "")):
        raise DouyinRequestError("PUBLISH_PAYLOAD_CHANGED")
    if owner(max_age=0) != job["uid"]:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    check = reconcile(job, force=True)
    if check["ok"] or check.get("candidates"):
        return check
    if job.get("verification_materials_refreshed") != value["id"]:
        current = session()
        current.state.pop("relay_security_expires_at", None)
        current.state.get("session_channels", {}).pop("creator", None)
        current.save()
    ensure_session(job["uid"])
    job["verification_materials_refreshed"] = value["id"]
    job.setdefault("submission_payload_sha256", digest)
    write_private(STATE_PATH, job)
    if value["expires_at"] <= time.time():
        raise DouyinRequestError("VERIFICATION_EXPIRED")
    query = common("creator", session())
    query.update(read_aid="2906", msToken=session().state["tokens"]["creator_msToken"])
    from .http import append_params
    prepare("creator", "publish-security", append_params(CREATOR + CREATE_PATH, query),
            fields={"work_type": "video" if job["kind"] == "video" else "image"}, expected_uid=job["uid"])
    if value["expires_at"] <= time.time():
        raise DouyinRequestError("VERIFICATION_EXPIRED")
    # Persist before computation/transport. An interrupted or uncertain attempt
    # is only reconciled on every later invocation, including the same command.
    job.setdefault("verified_retries", []).append({"verification_id": value["id"], "log_id": value["log_id"],
        "at": time.time(), "payload_sha256": digest, "confirmation": confirmation.strip(),
        "previous_error": job.get("error"), "diagnostic": job.get("diagnostic")})
    job.update(state="submitting", submission_payload_sha256=digest)
    job.pop("verified_retry_ready", None)
    job.pop("last_reconciliation", None)
    write_private(STATE_PATH, job)
    def check_before_send():
        # The transport holds the API-session lock while invoking this check
        # and sending, so a concurrent login cannot swap the account here.
        latest = session()
        verification = latest.state.get("creator_verification") or {}
        if (str(latest.state.get("uid", "")) != job["uid"]
                or identity_binding(latest) != expected_binding
                or verification.get("id") != value["id"] or verification.get("log_id") != value["log_id"]):
            raise DouyinRequestError("VERIFICATION_CONTEXT_MISMATCH")
        if value["expires_at"] <= time.time():
            raise DouyinRequestError("VERIFICATION_EXPIRED")
    return _submit(job, before_send=check_before_send)


def verification_qr(job, action):
    extension = ".jpg" if action.get("mime_type") == "image/jpeg" else ".png"
    target = STATE_PATH.parent / (job["attempt_id"] + "-verification" + extension)
    if target.is_symlink():
        raise ValueError("API_SESSION_UNSAFE")
    if action["kind"] == "scan-face-qr":
        import qrcode
        validate_face_action(action)
        stream = io.BytesIO()
        qrcode.make(action["uri"]).save(stream, format="PNG")
        raw = stream.getvalue()
    else:
        from PIL import Image
        raw = decode_verification_qr(action)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG"} or max(image.size) > 4096 or min(image.size) <= 0:
                raise ValueError("INVALID_RELAY_RESPONSE")
            image.verify()
    fd, temporary = tempfile.mkstemp(prefix=".verification-", dir=STATE_PATH.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(target)


def verification_result(job, value, *, cached=False):
    """Report completion of this verification step separately from publication."""
    result = summary(job)
    previous = result.pop("error", None)
    if previous:
        result["publication_error"] = previous
    action_path = None
    qr_file = None
    if value.get("user_action"):
        action_path = STATE_PATH.parent / (job["attempt_id"] + "-user-action.json")
        write_private(action_path, value["user_action"])
        if value["user_action"].get("kind") in {"scan-face-qr", "scan-device-qr"}:
            qr_file = verification_qr(job, value["user_action"])
    elif value.get("status") in {"ticket-issued", "expired", "refused"}:
        (STATE_PATH.parent / (job["attempt_id"] + "-verification.png")).unlink(missing_ok=True)
        (STATE_PATH.parent / (job["attempt_id"] + "-verification.jpg")).unlink(missing_ok=True)
        (STATE_PATH.parent / (job["attempt_id"] + "-user-action.json")).unlink(missing_ok=True)
    consumed = any(a.get("log_id") == value.get("log_id") for a in job.get("verified_retries", []))
    next_step = verification_next(value)
    if value.get("status") == "ticket-issued" and consumed:
        next_step = "resume"
    status = value.get("status")
    hints = {"prepared": "验证准备已完成，按可用方式继续；作品尚未确认发布",
             "awaiting-face": "请用抖音 App 扫描二维码并完成人脸验证，再执行 verify-face-check；不会自动提交作品",
             "awaiting-scan": "请用已登录原账号的抖音 App 扫描二维码，再执行 verify-poll；不会自动提交作品",
             "scanned": "已扫码，等待手机确认；执行 verify-poll 查询，不自动提交作品",
             "expired": "验证已过期；显式 verify-prepare --restart 后重新生成验证入口，不重发作品",
             "refused": "手机端已拒绝验证；确认后显式 verify-prepare --restart，不重发作品"}
    failure = {"expired": "VERIFICATION_EXPIRED", "refused": "VERIFICATION_REJECTED"}.get(status)
    return {**result, "ok": failure is None, **({"error": failure} if failure else {}),
            "publication_confirmed": job["state"] == "confirmed",
            "verification": {k: v for k, v in value.items() if k != "user_action"},
            "verification_status": value.get("status"), "cached": cached,
            "user_action_file": str(action_path) if action_path else None,
            "qr_file": qr_file,
            "next": next_step, "verified_retry_consumed": consumed,
            "hint": hints.get(status, "此验证步骤已完成，作品尚待确认；续接原请求使用 retry-verified")}


def verify(job, args):
    decision = publication_verification(job)
    if decision.get("supported") is False:
        return summary(job)
    if args.action in {"verify-send", "verify-confirm"} and not getattr(args, "confirm", False):
        return {"ok": True, "preview": True, "action": args.action}
    method = {"verify-code": "mobile_sms_verify", "verify-face-prepare": "face_verify",
              "verify-face-check": "face_verify", "verify-qr": "qr_code_verify", "verify-poll": "qr_code_verify"}.get(
                  args.action, getattr(args, "method", None))
    legacy_qr = decision.get("reason") == "gateway_biz_verify" and args.action in {"verify-qr", "verify-poll"}
    if args.action != "verify-prepare" and not legacy_qr and method not in decision.get("methods", []):
        raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
    if not job.get("submission_attempted") or not job.get("diagnostic"):
        raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
    if decision.get("reason") == "passport_verify":
        raise DouyinRequestError("VERIFICATION_CHALLENGE_INCOMPLETE", diagnostic_file=job["diagnostic"])
    current = session()
    value = current.state.get("creator_verification") or {}
    if (args.action == "verify-prepare" and not getattr(args, "restart", False)
            and not current.state.get("creator_verification_flow")
            and value.get("log_id") == decision.get("log_id")
            and value.get("status") in {"prepared", "awaiting-code", "awaiting-up-sms", "awaiting-face", "awaiting-scan", "scanned", "ticket-issued"}
            and current.state.get("creator_verification_binding")
            and current.state.get("creator_verification_binding") == identity_binding(current)):
        ensure_owner(job["uid"])
        if value["expires_at"] <= time.time():
            raise DouyinRequestError("VERIFICATION_EXPIRED")
        value = validate_creator_verification(value)
        return verification_result(job, value, cached=True)
    if owner() != job["uid"]:
        raise DouyinRequestError("API_ACCOUNT_MISMATCH")
    headers = read_private(job["diagnostic"])["headers"]
    cookie = session().cookies(CREATOR + "/")
    base = {"uid": job["uid"], "cookie": cookie}
    if legacy_qr:
        if decision.get("reason") != "gateway_biz_verify":
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        if args.action == "verify-qr":
            result = flow("creator-qr", {**base, "decision": headers["x-tt-verify-passport-decision"],
                                         "log_id": decision["log_id"]})
        else:
            challenge = job.get("creator_challenge") or {}
            if not challenge.get("id"):
                raise DouyinRequestError("VERIFICATION_CHALLENGE_MISSING")
            result = flow("creator-poll", {**base, "verification_id": challenge["id"]})
        challenge = result.get("creator_challenge")
        import re
        if (not isinstance(challenge, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(challenge.get("id", "")))
                or challenge.get("log_id") != decision["log_id"]
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
                                         "log_id": decision["log_id"]}, restart=getattr(args, "restart", False))
    else:
        value = session().state.get("creator_verification") or {}
        if (not value.get("id") or method not in value.get("methods", [])
                or value.get("log_id") != decision.get("log_id")
                or session().state.get("creator_verification_binding") != identity_binding(session())):
            raise DouyinRequestError("VERIFICATION_METHOD_UNSUPPORTED")
        value = validate_creator_verification(value)
        if value["expires_at"] <= time.time():
            raise DouyinRequestError("VERIFICATION_EXPIRED")
        fields = {**base, "verification_id": value["id"], "method": method}
        if args.action == "verify-code":
            path = Path(args.code_file).expanduser()
            if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
                raise ValueError("API_SESSION_UNSAFE")
            code = path.read_text().strip()
            if not code.isdigit() or not 4 <= len(code) <= 6:
                raise ValueError("INVALID_VERIFICATION_CODE")
            fields["code"] = code
        flow_action = {"verify-qr": "verify-qr-prepare", "verify-poll": "verify-qr-check"}.get(args.action, args.action)
        result = flow(flow_action, fields)
    value = validate_creator_verification(result.get("verification"))
    if value["log_id"] != decision.get("log_id"):
        raise DouyinRequestError("VERIFICATION_CONTEXT_MISMATCH")
    job["verification"] = decision
    job["verification_progress"] = {k: v for k, v in value.items() if k != "user_action"}
    if value.get("status") == "ticket-issued":
        job["verified_retry_ready"] = {k: value[k] for k in ("id", "log_id", "expires_at")}
    else:
        job.pop("verified_retry_ready", None)
    write_private(STATE_PATH, job)
    return verification_result(job, value)


def wait_video_ready(uid, media):
    deadline, delay = time.monotonic() + 180, 2
    detect = {"resource_list": [{"type": 2, "video_id": media["vid"],
                                 "duration": round(media["duration"]), "cover_uri": ""}],
              "source": 1, "is_redetect": False}
    while True:
        if time.monotonic() >= deadline:
            raise DouyinRequestError("VIDEO_PROCESSING_TIMEOUT")
        checked = call("fast_detect", body=detect, confirm=True, expected_uid=uid)
        if checked.get("has_done") is True:
            return
        if checked.get("task_id"):
            detect["task_id"] = str(checked["task_id"])
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DouyinRequestError("VIDEO_PROCESSING_TIMEOUT")
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 8)


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
                with preparation_step(job, "video_processing"):
                    wait_video_ready(uid, media)
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
    supported = {"run", "publish", "close", "status", "get-link", "resume", "retry-verified", "verify-prepare",
                 "verify-qr", "verify-poll", "verify-send", "verify-code", "verify-confirm", "verify-face-prepare", "verify-face-check"}
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
        if args.action == "retry-verified":
            return retry_verified(job, args)
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
