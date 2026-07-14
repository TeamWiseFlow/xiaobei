#!/usr/bin/env bash
set -euo pipefail

# get-xhs-user-id.sh — 获取 xhs-browse 登录账号的 user_id
#
# 小红书 feed API 现在强制要求 xsec_token，取 xsec_token 需要先拿到 self user_id
# 拼 profile URL。本脚本调 /api/sns/web/v1/user/me（XYW 签名）取 user_id，
# 结果缓存到 xhs-user-id.cache（user_id 不变，cookie 换了才需 --refresh）。
#
# Usage:
#   ./skills/published-track/scripts/get-xhs-user-id.sh [--refresh]
#
# stdout: user_id（hex）
# exit 0: 成功 | 2: cookie 失效 | 1: 其他错误

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
CACHE_FILE="$ROOT/skills/published-track/xhs-user-id.cache"
LOGIN_FILE="$HOME/.openclaw/logins/xhs-browse.json"

REFRESH=false
[[ "${1:-}" == "--refresh" ]] && REFRESH=true

if [ "$REFRESH" = false ] && [ -f "$CACHE_FILE" ]; then
  cat "$CACHE_FILE"
  exit 0
fi

if [ ! -f "$LOGIN_FILE" ]; then
  echo '{"ok":false,"error":"NO_XHS_BROWSE_COOKIE","hint":"请用 login-manager login xhs-browse 登录"}' >&2
  exit 2
fi

OUT=$(python3 -c '
import json, os, sys, requests
sys.path.insert(0, sys.argv[2])
from relay_sign import xhs_headers
d = json.load(open(sys.argv[1]))
cookies = {}
for it in d["cookies"].split(";"):
    it = it.strip()
    if "=" in it:
        k, v = it.split("=", 1)
        cookies[k.strip()] = v.strip()
if not cookies.get("a1") or not cookies.get("web_session"):
    print(json.dumps({"ok": False, "error": "SESSION_EXPIRED"}))
    sys.exit(2)
ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
origin = "https://www.xiaohongshu.com"
edith = "https://edith.xiaohongshu.com"
# /api/sns/web/v1/user/me 是 data-fetching API，必须 xyw 签名（xys 会 406）
sign_h = xhs_headers(
    uri="/api/sns/web/v1/user/me",
    cookies=cookies,
    method="get",
    sign_format="xyw",
)
h = {"User-Agent": ua, "Origin": origin, "Referer": origin + "/", "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
h.update({k: v for k, v in sign_h.items() if k.lower().startswith("x-")})
r = requests.get(edith + "/api/sns/web/v1/user/me", headers=h, timeout=15)
j = r.json()
uid = (j.get("data") or {}).get("user_id")
if not uid:
    print(json.dumps({"ok": False, "error": "NO_USER_ID", "msg": r.text[:200]}))
    sys.exit(1)
print(uid)
' "$LOGIN_FILE" "$ROOT/skills/_shared" 2>&1) || EXIT=$?
EXIT=${EXIT:-0}

if [ "$EXIT" -ne 0 ]; then
  echo "$OUT" >&2
  exit "$EXIT"
fi

if echo "$OUT" | grep -qE '^[0-9a-f]{20,}$'; then
  echo "$OUT" > "$CACHE_FILE"
  echo "$OUT"
else
  echo "$OUT" >&2
  exit 1
fi
