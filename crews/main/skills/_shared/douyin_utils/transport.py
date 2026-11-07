"""Reusable HTTP2 connections with explicit, caller-owned credentials."""

import atexit
import re
import threading
from collections.abc import Mapping

from curl_cffi.requests import Session
from curl_cffi.requests.impersonate import BrowserType

_local = threading.local()
_clients = []
_guard = threading.Lock()


def browser_profile(user_agent):
    match = re.search(r"Chrome/(\d+)", user_agent or "")
    requested = int(match.group(1)) if match else 150
    supported = [value.value for value in BrowserType]
    versions = [int(value[6:]) for value in supported if re.fullmatch(r"chrome\d+", value)]
    eligible = [version for version in versions if version <= requested]
    return "chrome" + str(max(eligible or versions))


def client(scope, user_agent):
    pool = getattr(_local, "pool", None)
    if pool is None:
        pool = _local.pool = {}
    key = (str(scope), user_agent)
    if key not in pool:
        pool[key] = Session(impersonate=browser_profile(user_agent), default_headers=False)
        with _guard:
            _clients.append(pool[key])
    return pool[key]


def send(method, url, *, headers, data, timeout, scope="douyin"):
    pairs = list(headers.items()) if isinstance(headers, Mapping) else list(headers)
    if any(not isinstance(pair, (tuple, list)) or len(pair) != 2
           or not all(isinstance(value, str) for value in pair) for pair in pairs):
        raise ValueError("INVALID_HTTP_HEADERS")
    ua = next((value for name, value in pairs if name.lower() == "user-agent"), "")
    http = client(scope, ua)
    # The platform jar lives in ApiSession. Do not let libcurl add hidden cookies
    # or retain upload credentials between independently signed requests.
    http.cookies.clear()
    try:
        return http.request(method, url, headers=pairs, data=data, timeout=timeout,
                            allow_redirects=False, default_headers=False,
                            http_version="v2", quote=False, discard_cookies=True)
    finally:
        http.cookies.clear()


def close_all():
    with _guard:
        clients, _clients[:] = list(_clients), []
    for http in clients:
        http.close()
    _local.pool = {}


atexit.register(close_all)
