"""Typed user-search filters and checks against returned public metadata."""

import json

FAN_RANGES = {"0_1k": (0, 1000), "1k_1w": (1000, 10000), "1w_10w": (10000, 100000),
              "10w_100w": (100000, 1000000), "100w_": (1000000, None)}
USER_TYPES = {"common_user", "enterprise_user", "personal_user"}
FILTER_KEYS = ("douyin_user_fans", "douyin_user_type")


def user_filters(params):
    values = dict(params)
    flat = {k: values.pop(k) for k in FILTER_KEYS if k in values}
    encoded = values.get("search_filter_value")
    if encoded is not None:
        try:
            selected = json.loads(encoded)
        except (ValueError, TypeError):
            raise ValueError("INVALID_USER_SEARCH_FILTER") from None
        if not isinstance(selected, dict) or set(selected) != set(FILTER_KEYS):
            raise ValueError("INVALID_USER_SEARCH_FILTER")
    else:
        selected = {k: [flat.get(k, "")] for k in FILTER_KEYS}
    for k, options in ((FILTER_KEYS[0], FAN_RANGES), (FILTER_KEYS[1], USER_TYPES)):
        item = selected[k]
        if (not isinstance(item, list) or len(item) != 1 or not isinstance(item[0], str)
                or item[0] not in {"", *options}):
            raise ValueError("INVALID_USER_SEARCH_FILTER")
        if k in flat and flat[k] != item[0]:
            raise ValueError("USER_SEARCH_FILTER_CONFLICT")
    active = any(selected[k][0] for k in FILTER_KEYS)
    values["is_filter_search"] = "1" if active else "0"
    values["search_source"] = "normal_search"
    if active:
        values["search_filter_value"] = json.dumps(selected, separators=(",", ":"))
    else:
        values.pop("search_filter_value", None)
    return values


def check_user_filters(items, params):
    selected = json.loads(params["search_filter_value"])
    fans, kind = (selected[k][0] for k in FILTER_KEYS)
    checked = {k: 0 for k, v in (("fans", fans), ("user_type", kind)) if v}
    mismatches = []
    for index, item in enumerate(items):
        user = item.get("user_info") or item
        if not isinstance(user, dict):
            continue
        wrong = []
        count = user.get("follower_count")
        if fans and type(count) is int and count >= 0:
            checked["fans"] += 1
            low, high = FAN_RANGES[fans]
            if count < low or high is not None and count >= high:
                wrong.append("fans")
        enterprise, personal = user.get("enterprise_verify_reason"), user.get("custom_verify")
        actual = ("enterprise_user" if isinstance(enterprise, str) and enterprise else
                  "personal_user" if enterprise == "" and isinstance(personal, str) and personal else
                  "common_user" if enterprise == personal == "" else None)
        if kind and actual:
            checked["user_type"] += 1
            if actual != kind:
                wrong.append("user_type")
        if wrong:
            mismatches.append({"index": index, "fields": wrong})
    verified = bool(items) and all(value == len(items) for value in checked.values())
    return {"state": "mismatch" if mismatches else "verified" if verified else "unverified",
            "inspected": len(items), "checked": checked, "mismatches": mismatches,
            "requested": selected}
