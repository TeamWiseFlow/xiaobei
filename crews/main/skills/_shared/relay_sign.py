"""relay_sign.py — client 侧调用 relay sign 服务的统一入口（Python）

平台规则：relay **只**算签名算法（xhs a_bogus / xsec_token / 抖音 _signature 等），
实际平台调用（登录 / 抓取 / 互动 / 上传 / 发布）**必须 client 端完成**。本模块供
xhs-publish 等 Python skill 共用。RELAY_BASE_URL + OFB_KEY 由 entrypoint 从 daemon.env 注入。

接口对应 relay 仓 services/sign/：
  POST /api/v1/sign/xhs/headers  → 仅签名（返回完整 headers，client 自行 fetch 平台）
  POST /api/v1/sign/douyin        → 算 a_bogus
"""

import json
import os
from typing import Any

import requests

# 默认指向官方中转 relay（VIP Club 会员默认走我们中转，零配置起手）。
# 仅当用户自建 relay 时才需要在 daemon.env 覆盖 RELAY_BASE_URL。
RELAY_BASE_URL = os.environ.get("RELAY_BASE_URL", "https://relay.openclaw-for-business.com")
_TIMEOUT = 30


def _ofb_key() -> str:
    key = os.environ.get("OFB_KEY")
    if not key:
        raise RuntimeError(
            "OFB_KEY 未配置。OFB_KEY 是 VIP Club 会员凭证，由 ofb 掌柜签发——"
            "请向 ofb 掌柜索取该 key，交由 IT engineer 写入 daemon.env 后重启实例。"
        )
    return key


def _post(path: str, body: dict) -> Any:
    resp = requests.post(
        f"{RELAY_BASE_URL}{path}",
        headers={"Content-Type": "application/json", "X-OFB-Key": _ofb_key()},
        json=body,
        timeout=_TIMEOUT,
    )
    env = resp.json()
    if not resp.ok or not env.get("success"):
        raise RuntimeError(f"relay {path} 失败 ({resp.status_code}): {env.get('error')}")
    return env["data"]


def xhs_headers(
    uri: str,
    cookies: dict,
    payload: dict | None = None,
    params: dict | None = None,
    method: str = "post",
    sign_format: str = "xys",
    x_rap: bool = False,
) -> dict:
    """仅签名，返回完整 headers（含 Cookie / UA / 签名头），client 自行发请求。

    xhs 两套独立 x-s 算法（见 relay services/sign/xhs.js）：
      - sign_format="xys"（默认，XYS_）→ note 创建 / feed / comment / search 等通用 endpoint
      - sign_format="xyw"（XYW_）→ data-fetching API：user/me、user_posted、otherinfo
        （这些 endpoint 自 ~2026-03 起对 xys 返回 HTTP 406，必须用 xyw）
    """
    return _post(
        "/api/v1/sign/xhs/headers",
        {
            "uri": uri,
            "method": method,
            "payload": payload or {},
            "params": params or {},
            "cookies": cookies,
            "sign_format": sign_format,
            "x_rap": x_rap,
        },
    )["headers"]


def douyin_sign(query_string: str, post_data: str = "", ua: str | None = None) -> str:
    """算 a_bogus（relay 子进程隔离 vendor），client 自行拼 URL 发请求"""
    return _post(
        "/api/v1/sign/douyin",
        {"queryString": query_string, "postData": post_data, "ua": ua},
    )["a_bogus"]
