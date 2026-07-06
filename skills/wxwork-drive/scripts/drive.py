#!/usr/bin/env python3
"""drive.py — 企业微信微盘文件管理（经 relay 透传凭据，relay 无状态）

子命令：
  空间管理（spaces.json，存于本技能目录，gitignore）：
    space-create <alias> <space_name> [--default]   经 relay 创建空间并登记
    space-add    <alias> <spaceid> [--default]       登记已有空间
    space-ls                                         列已登记空间
    space-default <alias>                            设默认空间
    folder-default <space_alias> <folderid>          设某空间的默认上传文件夹
  文件管理（<space> 接受 alias 或裸 spaceid）：
    mkdir   <space> <file_name> [--fatherid F] [--default-folder]   建文件夹（--fatherid 缺省=根）
    upload  <file> <space> [--fatherid F] [--name NAME]             上传（--fatherid 缺省=该空间 default_folderid）
    ls      <space> [--fatherid F] [sort_type] [limit] [start]      列目录（--fatherid 缺省=根）
    info    <fileid>
    rename  <fileid> <new_name>
    move    <fatherid> <fileid> [fileid...] [--replace]
    delete  <fileid> [fileid...]

凭据：WXWORK_CORP_ID + WXWORK_CORP_SECRET 来自 daemon.env（entrypoint 注入）。
relay：RELAY_BASE_URL + OFB_KEY 来自 daemon.env。

relay 端点（统一响应包络 { ok, ...业务字段, detail }）：
  POST /api/v1/wxwork/drive/space-create  JSON
  POST /api/v1/wxwork/drive/create-folder  JSON
  POST /api/v1/wxwork/drive/upload-image   multipart
  POST /api/v1/wxwork/drive/upload-video   multipart（分块，relay 侧负责）
  POST /api/v1/wxwork/drive/list-files     JSON
  POST /api/v1/wxwork/drive/file-info      JSON
  POST /api/v1/wxwork/drive/rename         JSON
  POST /api/v1/wxwork/drive/move           JSON
  POST /api/v1/wxwork/drive/delete         JSON

详见 docs/WXWORK-DRIVE-API.md。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPACES_FILE = SCRIPT_DIR.parent / "spaces.json"
DEFAULT_RELAY_BASE_URL = "https://relay.openclaw-for-business.com"
BASE_PATH = "/api/v1/wxwork/drive"
TIMEOUT_S = 300
IMAGE_MAX_BYTES = 10 * 1024 * 1024  # relay upload-image 上限 10M，超过走 upload-video
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".wmv")


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(f">>> {msg}", flush=True)


# ── env ──────────────────────────────────────────────────────────────────────

def load_env() -> tuple[str, str, str, str]:
    corp_id = os.environ.get("WXWORK_CORP_ID", "").strip()
    corp_secret = os.environ.get("WXWORK_CORP_SECRET", "").strip()
    relay = os.environ.get("RELAY_BASE_URL", "").rstrip("/") or DEFAULT_RELAY_BASE_URL
    ofb_key = os.environ.get("OFB_KEY", "").strip()
    if not corp_id or not corp_secret:
        die(
            "WXWORK_CORP_ID / WXWORK_CORP_SECRET 未配置（daemon.env）。\n"
            "  → 请让 Agent 按 REFERENCE.md 引导你获取企业 ID + corp_secret，\n"
            "    再由 IT engineer 写入 daemon.env 并重启实例。"
        )
    if not ofb_key:
        die("OFB_KEY 未配置（daemon.env）。请让 IT engineer 配置后重启实例。")
    return corp_id, corp_secret, relay, ofb_key


# ── spaces.json ──────────────────────────────────────────────────────────────

def load_spaces() -> dict:
    if not SPACES_FILE.exists():
        return {"default_space": None, "spaces": []}
    try:
        cfg = json.loads(SPACES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"spaces.json 解析失败: {e}")
    cfg.setdefault("spaces", [])
    return cfg


def save_spaces(cfg: dict) -> None:
    SPACES_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(SPACES_FILE, 0o600)
    except OSError:
        pass


def find_space(cfg: dict, alias: str) -> dict | None:
    for sp in cfg.get("spaces", []):
        if sp.get("alias") == alias:
            return sp
    return None


def resolve_space(space_arg: str, cfg: dict) -> tuple[str, str | None, dict | None]:
    """space_arg 可以是 alias 或裸 spaceid。返回 (spaceid, default_folderid, entry_or_None)。"""
    sp = find_space(cfg, space_arg)
    if sp:
        return sp["spaceid"], sp.get("default_folderid"), sp
    return space_arg, None, None


# ── HTTP ─────────────────────────────────────────────────────────────────────

def post_json(url: str, ofb_key: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8", "X-OFB-Key": ofb_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace")
        die(f"relay HTTP {e.code}: {text}")
    except urllib.error.URLError as e:
        die(f"relay 不可达: {e.reason}")


def post_multipart(url: str, ofb_key: str, fields: dict[str, str], file_path: str) -> dict:
    # 不用 -f：HTTP 4xx/5xx 时 -f 会吞掉 body，relay 的 {ok:false,error} 就看不到了。
    # 让 curl 始终返回 0，由 unwrap() 解包判定。
    cmd = ["curl", "-s", "--max-time", str(TIMEOUT_S), "-X", "POST", url,
           "-H", f"X-OFB-Key: {ofb_key}"]
    for k, v in fields.items():
        cmd += ["-F", f"{k}={v}"]
    cmd += ["-F", f"file=@{file_path}"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die(f"curl 传输失败: {res.stderr}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        die(f"relay 返回非 JSON: {res.stdout[:500]}")


def unwrap(resp: dict) -> dict:
    if not resp.get("ok"):
        err = resp.get("error") or resp.get("detail") or resp
        die(f"操作失败: {err}")
    return resp


# ── 空间管理子命令 ───────────────────────────────────────────────────────────

def cmd_space_create(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "space_name": args.space_name}
    log(f"创建空间: {args.space_name}（alias={args.alias}）")
    resp = post_json(f"{relay}{BASE_PATH}/space-create", ofb_key, body)
    data = unwrap(resp)
    spaceid = data["spaceid"]
    cfg = load_spaces()
    if find_space(cfg, args.alias):
        die(f"alias {args.alias!r} 已存在，换个名字或先 space-ls 查看。")
    cfg["spaces"].append({"alias": args.alias, "spaceid": spaceid})
    if args.default or not cfg.get("default_space"):
        cfg["default_space"] = args.alias
    save_spaces(cfg)
    print(json.dumps(data, ensure_ascii=False))
    print(f"✓ 空间已创建并登记为 alias={args.alias}（spaceid={spaceid}）")
    if cfg.get("default_space") == args.alias:
        print(f"  已设为默认空间")


def cmd_space_add(args, *_) -> None:
    cfg = load_spaces()
    if find_space(cfg, args.alias):
        die(f"alias {args.alias!r} 已存在。")
    cfg["spaces"].append({"alias": args.alias, "spaceid": args.spaceid})
    if args.default or not cfg.get("default_space"):
        cfg["default_space"] = args.alias
    save_spaces(cfg)
    print(f"✓ 已登记 alias={args.alias} → spaceid={args.spaceid}")


def cmd_space_ls(args, *_) -> None:
    cfg = load_spaces()
    spaces = cfg.get("spaces", [])
    if not spaces:
        print("（未登记任何空间。用 space-create 或 space-add 登记。）")
        return
    default = cfg.get("default_space")
    for sp in spaces:
        mark = " (default)" if sp.get("alias") == default else ""
        df = sp.get("default_folderid")
        print(f"  {sp['alias']}{mark}  spaceid={sp['spaceid']}" + (f"  default_folderid={df}" if df else ""))


def cmd_space_default(args, *_) -> None:
    cfg = load_spaces()
    if not find_space(cfg, args.alias):
        die(f"alias {args.alias!r} 未登记。先 space-add / space-create。")
    cfg["default_space"] = args.alias
    save_spaces(cfg)
    print(f"✓ 默认空间设为 {args.alias}")


def cmd_space_share(args, corp_id, corp_secret, relay, ofb_key) -> None:
    cfg = load_spaces()
    spaceid, _, _ = resolve_space(args.space, cfg)
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "spaceid": spaceid}
    log(f"取空间邀请链接: {spaceid}")
    resp = post_json(f"{relay}{BASE_PATH}/space-share", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    url = data.get("space_share_url")
    print(f"✓ 邀请链接: {url}")


def cmd_file_share(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "fileid": args.fileid}
    log(f"取文件分享链接: {args.fileid}")
    resp = post_json(f"{relay}{BASE_PATH}/file-share", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    url = data.get("share_url")
    print(f"✓ 文件分享链接: {url}")


def cmd_space_setting(args, corp_id, corp_secret, relay, ofb_key) -> None:
    cfg = load_spaces()
    spaceid, _, _ = resolve_space(args.space, cfg)
    body: dict = {"corp_id": corp_id, "corp_secret": corp_secret, "spaceid": spaceid}
    # 只把显式传入的字段带上游，未传的不带（上游保持原状）
    if args.share_url_no_approve is not None:
        body["share_url_no_approve"] = args.share_url_no_approve
    if args.share_url_default_auth is not None:
        body["share_url_no_approve_default_auth"] = args.share_url_default_auth
    if args.enable_watermark is not None:
        body["enable_watermark"] = args.enable_watermark
    if args.enable_confidential is not None:
        body["enable_confidential_mode"] = args.enable_confidential
    if args.default_file_scope is not None:
        body["default_file_scope"] = args.default_file_scope
    if args.ban_share_external is not None:
        body["ban_share_external"] = args.ban_share_external
    log(f"空间安全设置: {spaceid}  字段: {list(body.keys())[3:] or '(无)'}")
    resp = post_json(f"{relay}{BASE_PATH}/space-setting", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    print("✓ 空间设置已更新")


def cmd_folder_default(args, *_) -> None:
    cfg = load_spaces()
    sp = find_space(cfg, args.space_alias)
    if not sp:
        die(f"alias {args.space_alias!r} 未登记。先 space-add / space-create。")
    sp["default_folderid"] = args.folderid
    save_spaces(cfg)
    print(f"✓ {args.space_alias} 的默认上传文件夹设为 {args.folderid}")


# ── 文件管理子命令 ───────────────────────────────────────────────────────────

def cmd_mkdir(args, corp_id, corp_secret, relay, ofb_key) -> None:
    cfg = load_spaces()
    spaceid, _, entry = resolve_space(args.space, cfg)
    fatherid = args.fatherid or spaceid  # 缺省=根
    body = {
        "corp_id": corp_id, "corp_secret": corp_secret,
        "spaceid": spaceid, "fatherid": fatherid, "file_name": args.file_name,
    }
    log(f"建文件夹: {args.file_name}  space={spaceid}  父={fatherid}")
    resp = post_json(f"{relay}{BASE_PATH}/create-folder", ofb_key, body)
    data = unwrap(resp)
    fileid = data["fileid"]
    if args.default_folder:
        if entry is None:
            print("  ⚠️ --default-folder 忽略：space 未在 spaces.json 登记，无法保存。先 space-add 登记。", file=sys.stderr)
        else:
            entry["default_folderid"] = fileid
            save_spaces(cfg)
            print(f"  已记为 {entry['alias']} 的默认上传文件夹")
    print(json.dumps(data, ensure_ascii=False))
    print(f"✓ 文件夹已创建  fileid={fileid}")


def cmd_upload(args, corp_id, corp_secret, relay, ofb_key) -> None:
    file_path = args.file_path
    if not os.path.isfile(file_path):
        die(f"文件不存在: {file_path}")
    cfg = load_spaces()
    spaceid, default_folder, _ = resolve_space(args.space, cfg)
    if args.fatherid:
        fatherid = args.fatherid
    elif default_folder:
        fatherid = default_folder
    else:
        die(f"未指定 --fatherid，且 {args.space!r} 没设 default_folderid。用 folder-default 设一个，或显式传 --fatherid。")
    size = os.path.getsize(file_path)
    is_video = file_path.lower().endswith(VIDEO_EXTS)
    use_video = is_video or size > IMAGE_MAX_BYTES
    endpoint = "upload-video" if use_video else "upload-image"
    fields = {"corp_id": corp_id, "corp_secret": corp_secret, "spaceid": spaceid, "fatherid": fatherid}
    if args.name:
        fields["file_name"] = args.name
    log(f"端点: {endpoint}  文件: {file_path}  大小: {size}B  父: {fatherid}")
    resp = post_multipart(f"{relay}{BASE_PATH}/{endpoint}", ofb_key, fields, file_path)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    tag = "（秒传）" if data.get("fast_forward") else ""
    print(f"✓ 上传成功{tag}  fileid={data['fileid']}")


def cmd_ls(args, corp_id, corp_secret, relay, ofb_key) -> None:
    cfg = load_spaces()
    spaceid, _, _ = resolve_space(args.space, cfg)
    fatherid = args.fatherid or spaceid  # 缺省=根
    body = {
        "corp_id": corp_id, "corp_secret": corp_secret,
        "spaceid": spaceid, "fatherid": fatherid,
        "sort_type": args.sort_type, "start": args.start, "limit": args.limit,
    }
    log(f"列目录: space={spaceid} father={fatherid}")
    resp = post_json(f"{relay}{BASE_PATH}/list-files", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    detail = data.get("detail") or {}
    items = ((detail.get("file_list") or {}).get("item")) or []
    type_map = {1: "文件夹", 2: "文件", 3: "文档", 4: "表格", 5: "收集表"}
    more = "（has_more）" if detail.get("has_more") else ""
    print(f"✓ 共 {len(items)} 项{more}")
    for it in items:
        t = type_map.get(it.get("file_type"), "?")
        print(f"  [{t}] {it.get('file_name')}  fileid={it.get('fileid')}  size={it.get('file_size', 0)}")


def cmd_info(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "fileid": args.fileid}
    log(f"取信息: {args.fileid}")
    resp = post_json(f"{relay}{BASE_PATH}/file-info", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    fi = (data.get("detail") or {}).get("file_info") or {}
    print(f"✓ {fi.get('file_name')}  type={fi.get('file_type')}  size={fi.get('file_size', 0)}")


def cmd_rename(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "fileid": args.fileid, "new_name": args.new_name}
    log(f"重命名: {args.fileid} → {args.new_name}")
    resp = post_json(f"{relay}{BASE_PATH}/rename", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    print(f"✓ 已重命名为 {args.new_name}")


def cmd_move(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "fatherid": args.fatherid, "fileid": args.fileids}
    if args.replace:
        body["replace"] = True
    log(f"移动 {len(args.fileids)} 项 → {args.fatherid}")
    resp = post_json(f"{relay}{BASE_PATH}/move", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    print("✓ 已移动")


def cmd_delete(args, corp_id, corp_secret, relay, ofb_key) -> None:
    body = {"corp_id": corp_id, "corp_secret": corp_secret, "fileid": args.fileids}
    log(f"删除 {len(args.fileids)} 项")
    resp = post_json(f"{relay}{BASE_PATH}/delete", ofb_key, body)
    data = unwrap(resp)
    print(json.dumps(data, ensure_ascii=False))
    print("✓ 已删除")


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="企业微信微盘文件管理（经 relay）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("space-create", help="经 relay 创建空间并登记到 spaces.json")
    sp.add_argument("alias")
    sp.add_argument("space_name")
    sp.add_argument("--default", action="store_true", help="设为默认空间")
    sp.set_defaults(fn=cmd_space_create)

    sp = sub.add_parser("space-add", help="登记一个已有空间")
    sp.add_argument("alias")
    sp.add_argument("spaceid")
    sp.add_argument("--default", action="store_true", help="设为默认空间")
    sp.set_defaults(fn=cmd_space_add)

    sp = sub.add_parser("space-ls", help="列已登记空间")
    sp.set_defaults(fn=cmd_space_ls)

    sp = sub.add_parser("space-default", help="设默认空间")
    sp.add_argument("alias")
    sp.set_defaults(fn=cmd_space_default)

    sp = sub.add_parser("space-share", help="取空间邀请链接（发给同事加入空间）")
    sp.add_argument("space", help="alias 或裸 spaceid")
    sp.set_defaults(fn=cmd_space_share)

    sp = sub.add_parser("file-share", help="取文件分享链接（文件级，不依赖空间邀请链接功能）")
    sp.add_argument("fileid")
    sp.set_defaults(fn=cmd_file_share)

    sp = sub.add_parser("space-setting", help="空间安全设置（开启链接免审批等）")
    sp.add_argument("space", help="alias 或裸 spaceid")
    sp.add_argument("--share-url-no-approve", dest="share_url_no_approve", action="store_true", default=None, help="链接加入空间免审批（置 true）")
    sp.add_argument("--share-url-default-auth", dest="share_url_default_auth", type=int, default=None, help="邀请链接默认权限:1仅下载/2可编辑/4仅预览/5可上传下载/200自定义")
    sp.add_argument("--enable-watermark", dest="enable_watermark", action="store_true", default=None)
    sp.add_argument("--enable-confidential", dest="enable_confidential", action="store_true", default=None)
    sp.add_argument("--default-file-scope", dest="default_file_scope", type=int, default=None, help="1仅成员/2企业内")
    sp.add_argument("--ban-share-external", dest="ban_share_external", action="store_true", default=None)
    sp.set_defaults(fn=cmd_space_setting)

    sp = sub.add_parser("folder-default", help="设某空间的默认上传文件夹")
    sp.add_argument("space_alias")
    sp.add_argument("folderid")
    sp.set_defaults(fn=cmd_folder_default)

    sp = sub.add_parser("mkdir", help="新建文件夹")
    sp.add_argument("space", help="alias 或裸 spaceid")
    sp.add_argument("file_name")
    sp.add_argument("--fatherid", default=None, help="父目录 fileid；缺省=空间根")
    sp.add_argument("--default-folder", action="store_true", help="把新文件夹记为该空间的默认上传文件夹")
    sp.set_defaults(fn=cmd_mkdir)

    sp = sub.add_parser("upload", help="上传图片/视频")
    sp.add_argument("file_path")
    sp.add_argument("space", help="alias 或裸 spaceid")
    sp.add_argument("--fatherid", default=None, help="目标文件夹 fileid；缺省=该空间 default_folderid")
    sp.add_argument("--name", default=None, help="上传后的文件名，缺省用原名")
    sp.set_defaults(fn=cmd_upload)

    sp = sub.add_parser("ls", help="列目录")
    sp.add_argument("space", help="alias 或裸 spaceid")
    sp.add_argument("--fatherid", default=None, help="目录 fileid；缺省=空间根")
    sp.add_argument("sort_type", type=int, nargs="?", default=1, help="1名升2名降3大小升4大小降5mtime升6mtime降")
    sp.add_argument("limit", type=int, nargs="?", default=100)
    sp.add_argument("start", type=int, nargs="?", default=0)
    sp.set_defaults(fn=cmd_ls)

    sp = sub.add_parser("info", help="取文件/文件夹信息")
    sp.add_argument("fileid")
    sp.set_defaults(fn=cmd_info)

    sp = sub.add_parser("rename", help="重命名")
    sp.add_argument("fileid")
    sp.add_argument("new_name")
    sp.set_defaults(fn=cmd_rename)

    sp = sub.add_parser("move", help="移动到目标目录")
    sp.add_argument("fatherid", help="目标目录 fileid")
    sp.add_argument("fileids", nargs="+", help="要移动的 fileid（可多个）")
    sp.add_argument("--replace", action="store_true", help="重名覆盖")
    sp.set_defaults(fn=cmd_move)

    sp = sub.add_parser("delete", help="批量删除")
    sp.add_argument("fileids", nargs="+", help="要删除的 fileid（可多个）")
    sp.set_defaults(fn=cmd_delete)

    args = p.parse_args()
    corp_id, corp_secret, relay, ofb_key = load_env()
    args.fn(args, corp_id, corp_secret, relay, ofb_key)


if __name__ == "__main__":
    main()
