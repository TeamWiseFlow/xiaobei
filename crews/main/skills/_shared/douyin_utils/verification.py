"""Validate verification summaries while keeping account challenges private."""

from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qs, urlsplit

SMS_METHODS = ("mobile_sms_verify", "mobile_up_sms_verify")
MFA_METHODS = (*SMS_METHODS, "face_verify")
MFA_STATUSES = {"prepared", "awaiting-code", "awaiting-up-sms", "awaiting-face",
                "ticket-issued", "login-confirmed", "expired", "unsupported"}


def validate_creator_verification(value):
    required = {"id", "scene", "log_id", "methods", "expires_at", "status",
                "ticket_present", "publish_gate_verified"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {"method", "evidence", "user_action"}:
        raise ValueError("INVALID_RELAY_RESPONSE")
    methods = value["methods"]
    ticket = value["status"] == "ticket-issued"
    if (not isinstance(value["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", value["id"])
            or value["scene"] != "creator"
            or not isinstance(value["log_id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value["log_id"])
            or not isinstance(methods, list) or not 1 <= len(methods) <= 2
            or any(not isinstance(m, str) or m not in SMS_METHODS for m in methods)
            or len(set(methods)) != len(methods)
            or type(value["expires_at"]) is not int or value["expires_at"] <= 0
            or not isinstance(value["status"], str)
            or value["status"] not in {"prepared", "awaiting-code", "awaiting-up-sms", "ticket-issued"}
            or type(value["ticket_present"]) is not bool or value["ticket_present"] != ticket
            or value["publish_gate_verified"] is not False
            or (value.get("evidence") == "same-session-verification-ticket") != ticket
            or not ticket and "evidence" in value
            or "method" in value and value["method"] not in methods):
        raise ValueError("INVALID_RELAY_RESPONSE")
    if "user_action" in value:
        action = value["user_action"]
        if (value.get("method") != "mobile_up_sms_verify" or value["status"] != "awaiting-up-sms"
                or not isinstance(action, dict) or set(action) != {"kind", "destination", "text"}
                or action["kind"] != "send-sms" or not isinstance(action["destination"], str)
                or not re.fullmatch(r"\+?[0-9]{3,32}", action["destination"])
                or not isinstance(action["text"], str) or not 1 <= len(action["text"]) <= 1024
                or any(c in action["text"] for c in "\r\n\0")):
            raise ValueError("INVALID_RELAY_RESPONSE")
    return {**value, "methods": list(methods)}


def validate_login_verification(value):
    """Validate Relay's public MFA contract, including private user instructions."""
    required = {"id", "scene", "type", "methods", "expires_at", "status",
                "ticket_present", "login_confirmed"}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {"method", "user_action"}:
        raise ValueError("INVALID_RELAY_RESPONSE")
    methods = value["methods"]
    unsupported = value["scene"] == "sms_login" and value["type"] == "UNSUPPORTED"
    if (not isinstance(value["id"], str) or not re.fullmatch(r"[a-f0-9]{32}", value["id"])
            or value["scene"] not in {"qr_connect", "sms_login"} or value["type"] not in {"MFA", "UNSUPPORTED"}
            or value["type"] == "UNSUPPORTED" and not unsupported
            or not isinstance(methods, list) or (methods != [] if unsupported else not 1 <= len(methods) <= 3)
            or any(not isinstance(m, str) or m not in MFA_METHODS for m in methods)
            or len(set(methods)) != len(methods)
            or type(value["expires_at"]) is not int or value["expires_at"] <= 0
            or not isinstance(value["status"], str) or value["status"] not in MFA_STATUSES
            or type(value["ticket_present"]) is not bool or type(value["login_confirmed"]) is not bool
            or value["login_confirmed"] != (value["status"] == "login-confirmed")
            or (value["status"] != "expired" and value["ticket_present"] != (value["status"] in {"ticket-issued", "login-confirmed"}))
            or unsupported and (value["status"] not in {"unsupported", "expired"} or value["ticket_present"]
                                or "method" in value or "user_action" in value)
            or not unsupported and value["status"] == "unsupported"
            or ("method" in value and value["method"] not in methods)):
        raise ValueError("INVALID_RELAY_RESPONSE")
    result = {**value, "methods": list(methods)}
    if "user_action" in value:
        action = value["user_action"]
        if not isinstance(action, dict):
            raise ValueError("INVALID_RELAY_RESPONSE")
        if value.get("method") == "mobile_up_sms_verify" and value["status"] == "awaiting-up-sms":
            if (set(action) != {"kind", "destination", "text"} or action["kind"] != "send-sms"
                    or not isinstance(action["destination"], str) or not re.fullmatch(r"\+?[0-9]{3,32}", action["destination"])
                    or not isinstance(action["text"], str) or not 1 <= len(action["text"]) <= 1024
                    or any(c in action["text"] for c in "\r\n\0")):
                raise ValueError("INVALID_RELAY_RESPONSE")
        elif value.get("method") == "face_verify" and value["status"] == "awaiting-face":
            if set(action) != {"kind", "uri"} or action["kind"] != "scan-face-qr" or not isinstance(action["uri"], str):
                raise ValueError("INVALID_RELAY_RESPONSE")
            uri = urlsplit(action["uri"])
            query = parse_qs(uri.query, keep_blank_values=True)
            if (len(action["uri"]) > 32768 or any(c in action["uri"] for c in "\r\n\0")
                    or uri.scheme != "aweme" or uri.netloc != "aweme" or uri.path != "/cert/verify" or uri.fragment
                    or set(query) != {"cert_app_id", "flow", "ignore_result", "scene", "ticket"}
                    or query["ignore_result"] != ["true"]
                    or any(len(values) != 1 or not values[0] or len(values[0]) > 16384 for values in query.values())):
                raise ValueError("INVALID_RELAY_RESPONSE")
        else:
            raise ValueError("INVALID_RELAY_RESPONSE")
        result["user_action"] = dict(action)
    return result


def public_login_verification(value):
    """Never print the SMS destination/text or the face verification ticket URI."""
    return {key: item for key, item in value.items() if key != "user_action"}


def login_verification_status(state):
    value = state.get("login_verification")
    if value:
        value = public_login_verification(validate_login_verification(value))
        if value["status"] != "login-confirmed" and value["expires_at"] <= time.time():
            value["status"] = "expired"
        return value
    pending = state.get("login_flow", {})
    result = pending.get("verification_result")
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if result.get("error_code", data.get("error_code")) == 2046:
            return {"required": True, "status": "verification_required", "error_code": 2046,
                    "source_action": pending.get("action")}
    return login_verification((pending.get("response") or {}).get("body")) if pending.get("action") == "poll" else None


def login_verification(body):
    """Recognize the observed QR login MFA response; keep its challenge private."""
    if not isinstance(body, str) or len(body.encode()) > 256 * 1024:
        return None
    try:
        response = json.loads(body)
    except (ValueError, RecursionError):
        return None
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict) or data.get("account_flow") != "verify" or data.get("passport_scene") != "login":
        return None
    event = data.get("event_params")
    if not isinstance(event, dict) or event.get("verify_scene") != "qr_connect":
        return None
    types = [container["std_verify_type"] for container in
             (data.get("biz_params"), data.get("common_params"), event)
             if isinstance(container, dict) and "std_verify_type" in container]
    if not types or any(value != "MFA" for value in types):
        return None
    ways = data.get("verify_ways")
    methods = [way.get("verify_way") for way in ways if isinstance(way, dict)] if isinstance(ways, list) else []
    return {
        "required": True,
        "scene": "qr_connect",
        "type": "MFA",
        "methods": [method for method in (*SMS_METHODS, "face_verify") if method in methods],
    }


def creator_verification(headers):
    if not isinstance(headers, dict):
        return None
    values = {str(key).lower(): value for key, value in headers.items()}
    raw = values.get("x-tt-verify-passport-decision")
    if not isinstance(raw, str) or len(raw) > 8192:
        return None
    try:
        decision = json.loads(raw)
    except (ValueError, RecursionError):
        return None
    if not isinstance(decision, dict) or decision.get("account_flow") != "verify":
        return None
    event = decision.get("event_params")
    if (
        not isinstance(event, dict)
        or event.get("verify_scene") != "creator"
        or event.get("verify_reason") != "gateway_web_authlv_check"
    ):
        return None
    ways = decision.get("verify_way_name_list")
    if isinstance(ways, str):
        ways = [way.strip() for way in ways.split(",")]
    if not isinstance(ways, list) or not ways or any(not isinstance(way, str) for way in ways):
        return None
    methods = [way for way in SMS_METHODS if way in ways]
    if not methods:
        return None
    log_id = event.get("log_id")
    if not isinstance(log_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", log_id):
        return None
    if values.get("x-tt-logid") and values["x-tt-logid"] != log_id:
        return None
    return {
        "required": True,
        "scene": "creator",
        "reason": "gateway_web_authlv_check",
        "methods": methods,
        "log_id": log_id,
    }
