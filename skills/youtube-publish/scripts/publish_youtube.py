#!/usr/bin/env python3
"""Upload videos to YouTube via YouTube Data API v3 with OAuth2."""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Session that retries on SSLEOF / ConnectionError / 5xx.
# (Google upload servers occasionally drop the long-lived SSL connection;
# resumable upload supports re-PUT, so retry is safe.)
# read=0: read retries cannot safely rewind our manual chunk body and would
# double up with the explicit resume logic in upload_video(); we handle read
# errors there via query_upload_status(). connect/status retries are safe.
_retry = Retry(
    total=5, connect=5, read=0, status=5,
    backoff_factor=1.5,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=frozenset(["GET", "POST", "PUT"]),
    raise_on_status=False,
    respect_retry_after_header=True,
)
_session = requests.Session()
_session.mount("https://", HTTPAdapter(max_retries=_retry, pool_maxsize=4))
_session.mount("http://", HTTPAdapter(max_retries=_retry, pool_maxsize=4))

CREDS_DIR = Path.home() / ".openclaw" / "credentials"
CLIENT_SECRET_FILE = CREDS_DIR / "youtube_client_secret.json"
TOKEN_FILE = CREDS_DIR / "youtube_token.json"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def output(data: dict) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")


def err_exit(msg: str, code: int = 1) -> None:
    sys.stderr.write(f"[youtube-publish] ERROR: {msg}\n")
    output({"ok": False, "error": msg})
    sys.exit(code)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        err_exit(f"UPLOAD_FAILED: env {name} not an integer: {raw!r}")


def load_token() -> dict:
    if not TOKEN_FILE.exists():
        err_exit("AUTH_REQUIRED", 2)
    try:
        return json.loads(TOKEN_FILE.read_text())
    except json.JSONDecodeError:
        err_exit("AUTH_REQUIRED", 2)


def refresh_access_token(token_data: dict) -> str:
    if not CLIENT_SECRET_FILE.exists():
        err_exit("AUTH_REQUIRED: no client_secret.json", 2)

    cs = json.loads(CLIENT_SECRET_FILE.read_text())
    installed = cs.get("installed", cs.get("web", {}))
    client_id = installed.get("client_id", "")
    client_secret = installed.get("client_secret", "")
    refresh_token = token_data.get("refresh_token", "")

    if not all([client_id, client_secret, refresh_token]):
        err_exit("AUTH_REQUIRED: incomplete credentials", 2)

    resp = _session.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        err_exit(f"AUTH_REQUIRED: refresh failed: {resp.text}", 2)

    new_token = resp.json()
    new_token["refresh_token"] = refresh_token
    CREDS_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(new_token, indent=2))
    return new_token.get("access_token", "")


def init_resumable_upload(
    access_token: str, title: str, description: str,
    tags: list[str], visibility: str, category_id: str,
    file_size: int | None = None, made_for_kids: bool = False,
) -> str:
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description or "",
            "tags": tags if tags else [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": visibility,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        # Disable Expect: 100-continue; some networks/proxies only surface the
        # interim 100 response and then drop the upload connection.
        "Expect": "",
    }
    if file_size is not None:
        headers["X-Upload-Content-Length"] = str(file_size)
        headers["X-Upload-Content-Type"] = "video/mp4"
    params = {"uploadType": "resumable", "part": "snippet,status"}
    resp = _session.post(
        YOUTUBE_UPLOAD_URL, headers=headers, params=params,
        json=metadata, timeout=30,
    )
    if resp.status_code in (401, 403):
        err_exit("AUTH_REQUIRED", 2)
    if resp.status_code not in (200, 201):
        err_exit(f"UPLOAD_FAILED: init HTTP {resp.status_code}: {resp.text}")

    upload_url = resp.headers.get("Location", "")
    if not upload_url:
        err_exit("UPLOAD_FAILED: no upload URL in response")
    return upload_url


def parse_range_end(range_header: str) -> int:
    """Return the last persisted byte from a Google resumable Range header."""
    match = re.search(r"bytes=0-(\d+)", range_header or "")
    return int(match.group(1)) if match else -1


def query_upload_status(upload_url: str, total: int) -> tuple[int, dict | None]:
    """Ask YouTube how many bytes are already persisted for this upload.

    The status query rides on the same flaky route as the chunk PUTs, so it
    gets its own small retry loop — a transient SSL EOF here must not abort
    an otherwise resumable upload.
    """
    headers = {
        "Content-Length": "0",
        "Content-Range": f"bytes */{total}",
        "Expect": "",
    }
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            resp = _session.put(upload_url, headers=headers, data=b"", timeout=(20, 120))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
            last_exc = e
            if attempt < 3:
                time.sleep(min(15, 2 ** attempt))
                continue
            err_exit(f"UPLOAD_FAILED: status query failed after retries: {type(e).__name__}: {e}")
        if resp.status_code == 308:
            return parse_range_end(resp.headers.get("Range", "")) + 1, None
        if resp.status_code in (200, 201):
            return total, resp.json()
        if resp.status_code in (401, 403):
            err_exit("AUTH_REQUIRED", 2)
        if resp.status_code == 404:
            err_exit("UPLOAD_FAILED: upload session expired or invalid (HTTP 404); re-init required")
        err_exit(f"UPLOAD_FAILED: status HTTP {resp.status_code}: {resp.text}")
    err_exit(f"UPLOAD_FAILED: status query failed: {last_exc}")


def upload_video(upload_url: str, video_path: str) -> dict:
    """Upload in resumable chunks and continue after SSL EOF/timeout.

    The old implementation streamed the whole file in one PUT. On flaky routes
    to www.googleapis.com this often failed with SSLEOFError or read timeout.
    YouTube resumable upload explicitly supports chunked PUT with 308 + Range;
    on any broken connection we query persisted offset and retry from there.
    """
    file_size = os.path.getsize(video_path)
    unit = 256 * 1024
    chunk_size = _env_int("YOUTUBE_UPLOAD_CHUNK_BYTES", unit)
    chunk_size = max(unit, (chunk_size // unit) * unit)
    max_errors = _env_int("YOUTUBE_UPLOAD_MAX_ERRORS", 100)
    read_timeout = _env_int("YOUTUBE_UPLOAD_READ_TIMEOUT", 300)
    offset = 0
    errors = 0
    started = time.monotonic()

    with open(video_path, "rb") as f:
        while offset < file_size:
            end = min(offset + chunk_size, file_size) - 1
            length = end - offset + 1
            f.seek(offset)
            data = f.read(length)
            if len(data) != length:
                err_exit(f"UPLOAD_FAILED: local short read {len(data)}/{length}")

            headers = {
                "Content-Length": str(length),
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes {offset}-{end}/{file_size}",
                "Expect": "",
            }
            try:
                resp = _session.put(upload_url, headers=headers, data=data, timeout=(20, read_timeout))
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
                errors += 1
                sys.stderr.write(
                    f"[youtube-publish] upload chunk {offset}-{end} failed: {type(e).__name__}: {e}; "
                    f"querying status ({errors}/{max_errors})\n"
                )
                if errors > max_errors:
                    err_exit(f"UPLOAD_FAILED: too many upload retries: {e}")
                time.sleep(min(30, 2 ** min(errors, 5)))
                offset, done = query_upload_status(upload_url, file_size)
                if done:
                    data = done
                    video_id = data.get("id", "")
                    return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}
                sys.stderr.write(f"[youtube-publish] resume offset: {offset}\n")
                continue

            if resp.status_code == 308:
                next_offset = parse_range_end(resp.headers.get("Range", "")) + 1
                if next_offset <= offset:
                    next_offset, done = query_upload_status(upload_url, file_size)
                    if done:
                        data = done
                        video_id = data.get("id", "")
                        return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}
                offset = next_offset
                elapsed = max(time.monotonic() - started, 0.1)
                sys.stderr.write(
                    f"[youtube-publish] progress {offset * 100 / file_size:.1f}% "
                    f"({offset}/{file_size}) avg={offset / elapsed / 1024 / 1024:.2f} MiB/s\n"
                )
                errors = 0
                continue

            if resp.status_code in (200, 201):
                data = resp.json()
                video_id = data.get("id", "")
                return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}

            if resp.status_code in (500, 502, 503, 504):
                errors += 1
                if errors > max_errors:
                    err_exit(f"UPLOAD_FAILED: upload HTTP {resp.status_code}: {resp.text}")
                time.sleep(min(30, 2 ** min(errors, 5)))
                offset, done = query_upload_status(upload_url, file_size)
                if done:
                    data = done
                    video_id = data.get("id", "")
                    return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}
                continue

            if resp.status_code in (401, 403):
                err_exit("AUTH_REQUIRED", 2)
            err_exit(f"UPLOAD_FAILED: upload HTTP {resp.status_code}: {resp.text}")

    offset, done = query_upload_status(upload_url, file_size)
    if done:
        video_id = done.get("id", "")
        return {"ok": True, "video_id": video_id, "url": f"https://youtu.be/{video_id}"}
    err_exit(f"UPLOAD_FAILED: all bytes sent but not finalized ({offset}/{file_size})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload video to YouTube")
    parser.add_argument("--title", required=True, help="Video title (max 100 chars)")
    parser.add_argument("--video", required=True, help="Video file path")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--visibility", default="private", choices=["public", "unlisted", "private"])
    parser.add_argument("--category-id", default="28", help="YouTube category ID (default: 28=Sci/Tech)")
    parser.add_argument("--made-for-kids", action="store_true", help="Mark as made for kids")
    args = parser.parse_args()

    if len(args.title) > 100:
        err_exit("TITLE_TOO_LONG")

    if not os.path.exists(args.video):
        err_exit(f"UPLOAD_FAILED: video not found: {args.video}")

    token_data = load_token()
    access_token = token_data.get("access_token", "")
    if not access_token:
        err_exit("AUTH_REQUIRED", 2)

    try:
        sys.stderr.write("[youtube-publish] refreshing access token...\n")
        access_token = refresh_access_token(token_data)
    except SystemExit:
        raise
    except Exception as e:
        err_exit(f"AUTH_REQUIRED: {e}", 2)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []

    sys.stderr.write("[youtube-publish] initializing resumable upload...\n")
    upload_url = init_resumable_upload(
        access_token, args.title, args.description,
        tags, args.visibility, args.category_id,
        os.path.getsize(args.video), args.made_for_kids,
    )

    sys.stderr.write("[youtube-publish] uploading video...\n")
    result = upload_video(upload_url, args.video)
    output(result)


if __name__ == "__main__":
    main()
