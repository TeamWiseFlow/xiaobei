#!/usr/bin/env python3
"""fetch_engagement.py - 微信公众号 engagement 数据抓取

通过 camoufox-cli + 创作者中心爬虫拿 wx_mp 文章的阅读数 / 点赞数 / 评论数 /
分享数 / 收藏数，写入 published-track 的 pub_wx_mp 表。

2026-07-09 真机验证通过，已更新为实际可用的实现。

CLI 形态：
    probe                          打开创作者中心 + dump DOM/截图，调试用
    list                           列出后台所有文章 + 行内 metrics
    fetch   --row-id <id>          抓单篇（按 title 在列表页匹配）
    fetch-all                      批量刷新（打开首页一次，解析页内全部文章，匹配 pub_wx_mp
                                 全部行写库；不翻页，首页没有的行报 unmatched 跳过）

依赖：
- camoufox-cli（npm 全局）
- published-track skill（同 crew 私有）
- python3 stdlib
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ── 常量 ─────────────────────────────────────────────────────────────────────

PLATFORM = "wx_mp"                              # published-track 表名前缀
SESSION_NAME = "wx_mp"                          # 本技能自管的 camoufox 持久化 session 名

# 创作者中心入口（登录后跳转到这里，带 token）
CREATOR_CENTER_URL = os.environ.get(
    "WX_MP_CREATOR_CENTER_URL", "https://mp.weixin.qq.com/"
)
# 发表记录列表页（已发布文章 + 行内 engagement 数据）
# 注意：必须带 token 参数，否则显示"请重新登录"
# token 从首页重定向 URL 中提取
PUBLISHED_LIST_URL_TEMPLATE = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    "?sub=list&begin=0&count=20&token={token}&lang=zh_CN"
)

PUBLISHED_TRACK_ROOT = Path(
    os.environ.get("PUBLISHED_TRACK_ROOT", "./db")
).expanduser()
PUBLISHED_TRACK_DB = PUBLISHED_TRACK_ROOT / "published_track.db"
PUBLISHED_TRACK_SCRIPTS = Path(
    os.environ.get(
        "PUBLISHED_TRACK_SCRIPTS",
        "~/.openclaw/workspace-main/skills/published-track/scripts",
    )
).expanduser()
UPDATE_METRICS_SH = PUBLISHED_TRACK_SCRIPTS / "update-metrics.sh"

CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")
FETCH_TIMEOUT_S = 30
SESSION_CLEANUP_ON_EXIT = True  # 仅 close camoufox session，不动中央存储

# 登录流程常量（本技能自管 wx_mp session 的扫码登录）
QR_FILE = "/tmp/qr-wx-mp.png"
# Stop-and-wait 模式（对齐 login-manager）：agent 在对话里等用户「已扫码/已完成」
# 信号后才调 login-confirm；confirm 只做短窗口 settle 验证（吸收手机确认后
# 页面 JS redirect 的尾巴），不承担「等用户」职责；不就位 → exit 2 交回对话。
LOGIN_CONFIRM_SETTLE_MAX_S = 30
LOGIN_CONFIRM_POLL_INTERVAL_S = 3

# spike dump 输出目录
PROBE_OUT_DIR = Path(
    os.environ.get("PROBE_OUT_DIR", "./wx-mp-engagement-probe")
).expanduser()


# ── 平台行查询 / 更新 ───────────────────────────────────────────────────────

def lookup_published_row(row_id: int) -> dict | None:
    if not PUBLISHED_TRACK_DB.exists():
        return None
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"SELECT id, title, publish_url, publish_date, source_folder "
            f"FROM pub_{PLATFORM} WHERE id = ?",
            (row_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_all_wx_mp_rows() -> list[int]:
    """取 pub_wx_mp 全部行 id。

    不按日期/指标过滤——发表记录页首页（count=20）本身就是天然窗口：
    页内有什么解析什么，匹配上的行写库，匹配不上的报 unmatched 跳过
    （老文章不在首页是常态，非错误）。"""
    if not PUBLISHED_TRACK_DB.exists():
        return []
    conn = sqlite3.connect(str(PUBLISHED_TRACK_DB))
    try:
        cur = conn.execute(
            f"SELECT id FROM pub_{PLATFORM} ORDER BY id DESC",
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def update_metrics_row(row_id: int, metrics: dict) -> dict:
    if not UPDATE_METRICS_SH.exists():
        return {"ok": False, "error": f"update-metrics.sh not found at {UPDATE_METRICS_SH}"}
    cmd = [
        str(UPDATE_METRICS_SH),
        "--platform", PLATFORM,
        "--id", str(row_id),
        "--reads", str(metrics.get("reads", 0)),
        "--likes", str(metrics.get("likes", 0)),
        "--comments", str(metrics.get("comments", 0)),
        "--shares", str(metrics.get("shares", 0)),
        "--favorites", str(metrics.get("favorites", 0)),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip(), "stdout": result.stdout.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": result.stdout.strip()}


# ── wx-mp-engagement 自管 wx_mp session ────────────────────────────────────
#
# wx-mp-engagement 自管 camoufox 持久化 session `wx_mp`：
# - 本技能自己负责 wx_mp session 的探活 + 登录 + 重登
# - 登录态在 wx_mp session profile 里就位即可，不导出 cookie/UA/token
# - 失效时 exit 2，由调用方（agent / HEARTBEAT）触发本技能自己的重登流程
# ── camoufox-cli 集成 ───────────────────────────────────────────────────────

def session_name() -> str:
    """返回本技能自管的固定 session 名 `wx_mp`。
    不再开独立 nonce session——wx_mp 持久化 session 里登录态已就位，
    camoufox-cli 直接复用即可（fail-first 队列管并发）。"""
    return SESSION_NAME


def camoufox_run(args: list[str], *, timeout: int = FETCH_TIMEOUT_S) -> subprocess.CompletedProcess:
    # --persistent 固定带：所有 camoufox-cli 命令复用同一 daemon + 同一 profile，
    # 避免每次命令重起 daemon 不带 profile（cookie/登录态不恢复）+ 多 daemon
    # 同 session 冲突互杀（SIGKILL）。--persistent 是 per-call flag，必须每次都带。
    cmd = [CAMOUFOX_BIN, "--persistent", "--json"] + args
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def camoufox_open(session: str, url: str) -> None:
    """打开 URL。camoufox-cli 默认 headless，不需要 --headless 参数。"""
    args = ["--session", session, "open", url]
    result = camoufox_run(args)
    if result.returncode != 0:
        raise RuntimeError(f"camoufox-cli open failed: {result.stderr.strip()}")


def camoufox_eval(session: str, expr: str) -> str:
    """在 session 内 eval JS，返回字符串结果"""
    result = camoufox_run(["--session", session, "eval", expr])
    if result.returncode != 0:
        return ""
    try:
        env = json.loads(result.stdout)
        data = env.get("data", "")
        if isinstance(data, dict) and "result" in data:
            # camoufox-cli eval 返回 {data: {result: "..."}}
            return data["result"]
        return data if isinstance(data, str) else json.dumps(data)
    except json.JSONDecodeError:
        return result.stdout


def camoufox_get_url(session: str) -> str:
    """获取当前页面 URL"""
    result = camoufox_run(["--session", session, "url"])
    if result.returncode != 0:
        return ""
    try:
        env = json.loads(result.stdout)
        return env.get("data", {}).get("url", "")
    except json.JSONDecodeError:
        return ""


def camoufox_screenshot(session: str, out_path: Path) -> bool:
    """截图。camoufox-cli 语法：screenshot <file>，不需要 --path。"""
    result = camoufox_run(
        ["--session", session, "screenshot", str(out_path)],
        timeout=FETCH_TIMEOUT_S,
    )
    return result.returncode == 0


def camoufox_close(session: str) -> None:
    """关闭 camoufox session"""
    camoufox_run(["--session", session, "close"], timeout=10)


# ── 登录流程（本技能自管 wx_mp session）─────────────────────────────────────
#
# 本技能自己负责 wx_mp session 的扫码登录 + 验登录就位。
# 登录态在 wx_mp session profile 里就位即可，不导出 cookie/UA/token。
# 本工具使用自己管理的 wx_mp session。

def cmd_login(args) -> None:
    """camoufox 无头打开公众号首页 → 截 QR PNG。

    agent 拿 QR_FILE 发用户扫码，用户回复「已扫码」后调 login-confirm。

    关键：camoufox-cli ``open`` 是「打开 + 立刻返回」，微信登录页的二维码是 JS
    动态注入的 ``<img>``（src 是 base64 或 JS 拼的），页面 onload 后才填。
    若 open 后立刻 screenshot，QR 还没注入完，截图空白。故 open 后先 wait
    等二维码 ``<img>`` 出现（或兜底等固定时间），再 screenshot。
    """
    # camoufox-cli open 公众号首页
    camoufox_open(SESSION_NAME, CREATOR_CENTER_URL)

    # 等二维码 <img> 出现：微信登录页 QR 是 JS 动态注入的 <img>，
    # camoufox-cli open 是「打开 + 立刻返回」，QR 还没注入完就截图会空白。
    # 不用 selector 锁 QR 元素（微信登录页结构不固定），直接轮询 eval
    # 验证 <img> 元素已出现 + 有 src，再截图。最多等 10s。
    deadline = time.time() + 10
    qr_ready = False
    while time.time() < deadline:
        raw = camoufox_eval(
            SESSION_NAME,
            "(() => { const imgs = document.querySelectorAll('img'); "
            "for (const i of imgs) { if (i.src && i.src.startsWith('data:image')) return '1'; } "
            "return String(imgs.length); })()",
        )
        if raw == "1":
            qr_ready = True
            break
        time.sleep(0.5)
    if not qr_ready:
        # �兜底等固定时间（onload + JS 注入完成），即使 eval 没拿到 QR img
        camoufox_run(
            ["--session", SESSION_NAME, "wait", "3000"],
            timeout=10,
        )

    # screenshot 截 QR PNG
    r = camoufox_run(
        ["--session", SESSION_NAME, "screenshot", QR_FILE],
        timeout=FETCH_TIMEOUT_S,
    )
    if r.returncode != 0:
        sys.stderr.write(f"error: camoufox screenshot failed: {r.stderr.strip()}\n")
        sys.exit(1)

    sys.stdout.write(json.dumps({
        "ok": True,
        "qr_path": QR_FILE,
        "message": "二维码已截，请用微信（公众号管理员账号）扫码，完成后回复「已扫码」",
    }, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_login_confirm(args) -> None:
    """验登录就位（用户在对话里给信号后调用）→ close session。Stop-and-wait 模式，对齐 login-manager。

    对话层 stop-and-wait：agent 发二维码 PNG 给用户后**停下等用户信号**（「已扫码」/
    「已完成」），收到信号才调本命令。本命令不承担「等用户」职责，只做短窗口
    settle 验证（LOGIN_CONFIRM_SETTLE_MAX_S，吸收手机确认后页面 JS redirect 的尾巴），
    不就位即 exit 2 交回对话，不长时间阻塞：
    - 用户只扫了码、还没在手机上点「确认登录」→ 提示用户点确认，再重跑本命令
      （二维码页还活着，无需重新扫码）
    - 已确认仍未就位 / 二维码过期 → 重新调 login 生成新二维码

    不导出 cookie/UA/token——登录态在 wx_mp session profile 里就位即可。

    就位判定（宽匹配，对齐 wx-channel-engagement 策略）：
    - URL 不含 login / scanloginqrcode（已离开登录页）
    - 且 URL 含 /cgi-bin/ 或含 token= 参数（已进入后台）

    历史（open-first 防御的由来，保留原因）：
    - 2026-08-16：旧版 camoufox-cli daemon 60s idle 自退，confirm 时 often 已是 fresh
      daemon，page 停在 about:blank（没执行过 open），直接轮询 url 永远读不到后台
      → 误判「未就位」。
    - 2026-08-22：camoufox-cli 默认关闭 idle 自退，二维码页一直活着等用户；但
      daemon 仍可能被 6 并发上限驱逐或手动 close。故仅当 url 为空/about:blank
      （fresh daemon）时才 ``open`` 首页触发 redirect；活着的登录页/后台页绝不
      导航走——导航走会重新生成新二维码，用户手里的二维码 PNG 作废。
      注意：``open`` 用 ``page.goto(waitUntil: "domcontentloaded")``，不跟随
      client-side JS redirect，而微信登录成功是 JS ``window.location`` 跳转
      （非 HTTP 302），故 open 后仍需轮询等 redirect 完成。
    """
    # 先读当前 url 决定是否 open-first——不盲目导航：
    # - 在登录页（login/scanloginqrcode）→ daemon 活着，二维码页正等用户扫码/确认
    #   （2026-08-22 起 camoufox-cli 默认不 idle 自退，该页可存活 >60s）。
    #   导航走会重新生成新二维码，用户手里的二维码 PNG 作废 → 只轮询 url，
    #   等页面在用户确认后自己 redirect。
    # - 已在后台（/cgi-bin/ 或 token=）→ 登录已在活页面里完成，同样不导航，
    #   轮询第一轮即判定就位。
    # - 其余（空/about:blank —— daemon 被并发上限驱逐或手动 close，
    #   ensureDaemon 新起了 fresh daemon，page 没执行过 open）→ 沿用
    #   2026-08-16 的 open-first：open 首页触发 redirect 再轮询。
    current_url = camoufox_get_url(SESSION_NAME)
    on_login_page = "login" in current_url or "scanloginqrcode" in current_url
    live_backend_page = (
        bool(current_url) and not on_login_page
        and ("/cgi-bin/" in current_url or "token=" in current_url)
    )
    if not on_login_page and not live_backend_page:
        try:
            camoufox_open(SESSION_NAME, CREATOR_CENTER_URL)
        except RuntimeError as e:
            sys.stderr.write(f"error: camoufox 打开首页失败: {e}\n")
            sys.exit(2)

    deadline = time.time() + LOGIN_CONFIRM_SETTLE_MAX_S
    token: str | None = None
    logged_in = False
    last_url = ""

    while time.time() < deadline:
        current_url = camoufox_get_url(SESSION_NAME)
        if current_url:
            last_url = current_url
            # 显式还在登录页 → 继续等
            if "login" in current_url or "scanloginqrcode" in current_url:
                time.sleep(LOGIN_CONFIRM_POLL_INTERVAL_S)
                continue
            # 已离开登录页：判是否进入后台
            # 后台 URL 特征：含 /cgi-bin/ 或含 token= 参数
            is_backend = "/cgi-bin/" in current_url or "token=" in current_url
            if is_backend:
                logged_in = True
                # 尝试提 token（诊断用，不强制要求）
                m = re.search(r"token=([^&]+)", current_url)
                if m:
                    token = m.group(1)
                break
        # 还在登录页或 redirect 中，等待
        time.sleep(LOGIN_CONFIRM_POLL_INTERVAL_S)

    if not logged_in:
        # 失败不 close（对齐 login-manager「失败时保留 session」）：daemon + 二维码页
        # 留着，用户在手机上补点「确认登录」后，agent 直接重跑 login-confirm 即可，
        # 无需重新扫码。
        sys.stderr.write(
            f"error: 登录态未就位（最后 URL: {last_url[:120]}）\n"
            f"  - 若用户只扫了码、还没在手机上点「确认登录」→ 提示用户点确认后"
            f"重跑 login-confirm（二维码页还活着，无需重新生成）\n"
            f"  - 若已确认仍未就位 / 二维码已过期 → 重新调 login 生成新二维码\n"
        )
        sys.exit(2)

    # 已从轮询 URL 拿到登录就位信号（已离开登录页、进入后台），证明登录态已就位。
    # 登录态在 profile 里就位，close session 不影响 profile 持久化。
    camoufox_close(SESSION_NAME)

    result = {
        "ok": True,
        "message": "登录成功，登录态已在 wx_mp session profile 就位",
    }
    if token:
        result["token"] = token
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


# ── token 提取 + 列表页导航 ─────────────────────────────────────────────────

def extract_token_from_url(url: str) -> str | None:
    """从 URL 中提取 token 参数"""
    m = re.search(r"token=(\d+)", url)
    return m.group(1) if m else None


def get_token_and_open_list(session: str) -> str:
    """访问首页拿 token，再打开发表记录页。返回当前 URL。"""
    # 1. 访问首页（cookie 生效后会重定向带 token）
    camoufox_open(session, CREATOR_CENTER_URL)
    # 2. 从当前 URL 提取 token
    current_url = camoufox_get_url(session)
    token = extract_token_from_url(current_url)
    if not token:
        raise RuntimeError(f"无法从首页 URL 提取 token: {current_url}")
    # 3. 打开发表记录页（带 token）
    list_url = PUBLISHED_LIST_URL_TEMPLATE.format(token=token)
    camoufox_open(session, list_url)
    return list_url


# ── 列表页解析（基于 innerText）─────────────────────────────────────────────

# 解析发表记录页 innerText 的 JS
# 页面结构：日期 -> "已发表" -> 标题 -> 类型(转载/原创/视频号) -> [已修改] -> 数字序列
_LIST_PARSE_JS = r"""
(() => {
  const text = document.body.innerText;
  const lines = text.split('\n').map(l => l.trim()).filter(l => l);
  const articles = [];
  const skipWords = new Set(['已发表', '全部', '已通知', '未通知', '置顶', '发表记录', '已修改', '首页', '内容管理', '草稿箱', '素材库', '原创', '合集', '话题', '互动管理', '数据分析', '收入变现', '广告与服务', '广告主', '客服', '电子发票', '小程序管理', '微信位置运营', '微信搜一搜', '微信支付', '服务市场', '设置与开发', '新的功能', '通知中心']);
  const typeWords = new Set(['转载', '原创', '视频号']);
  
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // 日期头：MM月DD日
    if (/^\d{1,2}月\d{1,2}日$/.test(line)) {
      i++;
      continue;
    }
    // 跳过无关键
    if (skipWords.has(line)) {
      i++;
      continue;
    }
    // 检查下一行是否是类型标记
    let nextIdx = i + 1;
    // 跳过"已修改"
    if (nextIdx < lines.length && lines[nextIdx] === '已修改') {
      nextIdx++;
    }
    if (nextIdx < lines.length && typeWords.has(lines[nextIdx])) {
      const title = line;
      const type = lines[nextIdx];
      // 收集后续连续数字
      const nums = [];
      let j = nextIdx + 1;
      // 跳过可能的"已修改"
      while (j < lines.length && lines[j] === '已修改') j++;
      while (j < lines.length && /^\d+$/.test(lines[j])) {
        nums.push(parseInt(lines[j]));
        j++;
      }
      if (nums.length >= 5) {
        articles.push({
          title: title,
          type: type,
          metrics: {
            // 页面真实列顺序（标签锚实证）：阅读 / 点赞 / 分享 / 喜欢(爱心icon,favorites列) / 留言(评论) / 划线 / 投票
            // 脚本旧版误把 nums[2] 当 comments、nums[3] 当 shares、nums[4] 当 favorites，已校正
            reads: nums[0] || 0,
            likes: nums[1] || 0,
            shares: nums[2] || 0,
            favorites: nums[3] || 0,
            comments: nums[4] || 0,
          },
          extra_nums: nums.slice(5),
        });
      }
      i = j;
    } else {
      i++;
    }
  }
  return JSON.stringify(articles);
})()
"""


def fetch_article_list(session: str) -> list[dict]:
    """打开发表记录页，eval JS 解析文章列表"""
    # 1. 先访问首页拿 token，再打开发表记录页
    get_token_and_open_list(session)
    # 2. eval JS 解析 innerText
    raw = camoufox_eval(session, _LIST_PARSE_JS)
    if not raw:
        return []
    # camoufox-cli eval 可能返回 JSON 字符串包在 data.result 里
    try:
        # 尝试解析为 JSON
        # eval 返回的可能是 JSON 字符串本身，也可能被包了一层
        data = json.loads(raw)
        if isinstance(data, str):
            # 双重编码
            return json.loads(data)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def parse_metrics_from_text(text: str) -> dict:
    """从行文本里提指标（保留用于兼容旧代码）"""
    metrics = {"reads": 0, "likes": 0, "comments": 0, "shares": 0, "favorites": 0}
    label_map = {
        "阅读": "reads", "阅读数": "reads",
        "点赞": "likes", "喜欢": "likes",
        "评论": "comments", "留言": "comments",
        "分享": "shares", "转发": "shares",
        "收藏": "favorites",
        "在看": "likes",
    }
    metric_re = re.compile(
        r"(阅读|阅读数|点赞|喜欢|评论|留言|分享|转发|收藏|在看)[^\d]*([\d,]+)",
    )
    for label, value in metric_re.findall(text):
        key = label_map.get(label)
        if key:
            num = int(value.replace(",", ""))
            if num > metrics[key]:
                metrics[key] = num
    return metrics


def normalize_title(s: str) -> str:
    """标题归一化用于匹配：去空白 + 去常见前缀符号"""
    return re.sub(r"\s+", "", s).strip("·*- ").lower()


def match_article(rows: list[dict], target_title: str) -> dict | None:
    """按标题在列表里找最匹配的行，返回 {title, metrics}"""
    norm_target = normalize_title(target_title)
    if not norm_target:
        return None
    # 精确匹配
    for row in rows:
        if normalize_title(row.get("title", "")) == norm_target:
            return {"title": row["title"], "metrics": row.get("metrics", {})}
    # 模糊包含
    for row in rows:
        nt = normalize_title(row.get("title", ""))
        if nt and (norm_target in nt or nt in norm_target):
            return {"title": row["title"], "metrics": row.get("metrics", {})}
    return None


# ── CLI 子命令 ──────────────────────────────────────────────────────────────

def _ensure_login() -> None:
    """判登录态：camoufox 打开创作者中心首页，轮询 redirect URL 等 token 出现。

    - 跳 /cgi-bin/home?...&token=xxx = 就位，return
    - 跳 login / scanloginqrcode / 超时仍无 token = 失效，exit 2

    关键：camoufox-cli ``open`` 是「打开 + 立刻返回」，不等页面 redirect 完成。
    微信首页在有登录态时会 redirect 到 /cgi-bin/home?token=xxx，但这个 redirect
    是浏览器拿到 HTML 后 JS 触发的，需要时间。open 后立刻读 URL 会读到首页 URL
    （无 token），误判失效。故 open 后轮询 URL，等 token 出现或超时判真失效。

    登录态在 wx_mp session profile 里就位即可，不导出 cookie/UA/token。
    """
    session = SESSION_NAME
    try:
        camoufox_open(session, CREATOR_CENTER_URL)
    except RuntimeError as e:
        sys.stderr.write(f"error: camoufox 打开首页失败: {e}\n")
        sys.exit(2)

    # 轮询 redirect URL，等 token 出现（最多 15s）
    deadline = time.time() + 15
    token: str | None = None
    current_url = ""
    while time.time() < deadline:
        current_url = camoufox_get_url(session)
        # 显式跳登录页 → 真失效，不等
        if "login" in current_url or "scanloginqrcode" in current_url:
            break
        token = extract_token_from_url(current_url)
        if token:
            return
        time.sleep(0.5)

    sys.stderr.write(
        f"error: wx_mp session 失效，请走 wx-mp-engagement login 流程重登\n"
        f"  (final url: {current_url[:100]})\n"
    )
    sys.exit(2)


def _prepare_session() -> str:
    """复用 wx_mp 持久化 session。

    不再开独立 nonce session、不再 import cookie——wx_mp session profile
    里登录态已就位（由本技能 login 流程落），camoufox-cli 直接用即可。
    返回固定 session 名 SESSION_NAME。"""
    return SESSION_NAME


def _cleanup_session(session: str) -> None:
    """用完即 close——登录态在磁盘 profile，不留进程占内存。
    下次 fetch 按需重起无头 session，profile 桥接登录态。"""
    camoufox_close(session)


def cmd_probe(args) -> None:
    """打开创作者中心 + 发表记录页，dump DOM/截图/文章列表 JSON"""
    _ensure_login()
    PROBE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = _prepare_session()
    try:
        # 1. 访问首页截图
        camoufox_open(session, CREATOR_CENTER_URL)
        camoufox_screenshot(session, PROBE_OUT_DIR / "01_center.png")
        # 2. 打开发表记录页（带 token）
        get_token_and_open_list(session)
        camoufox_screenshot(session, PROBE_OUT_DIR / "02_list.png")
        html = camoufox_eval(session, "document.documentElement.outerHTML")
        (PROBE_OUT_DIR / "02_list.html").write_text(html, encoding="utf-8")
        # 3. 解析列表
        rows = fetch_article_list(session)
        (PROBE_OUT_DIR / "03_articles.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = {
            "ok": True,
            "session": session,
            "out_dir": str(PROBE_OUT_DIR),
            "articles_found": len(rows),
            "first_3": rows[:3],
        }
    finally:
        _cleanup_session(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_list(args) -> None:
    """列出后台所有文章 + 行内 metrics"""
    _ensure_login()
    session = _prepare_session()
    try:
        rows = fetch_article_list(session)
        result = {"ok": True, "session": session, "total": len(rows), "articles": rows}
    finally:
        _cleanup_session(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_fetch(args) -> None:
    """抓单篇：按 row.title 在列表页匹配，拿行内 metrics 写库"""
    if not args.row_id and not args.source_folder:
        sys.stderr.write("error: must pass --row-id or --source-folder\n")
        sys.exit(1)
    _ensure_login()

    if args.row_id:
        row = lookup_published_row(args.row_id)
    else:
        sys.stderr.write("error: --source-folder 模式待实现\n")
        sys.exit(1)
    if row is None:
        sys.stderr.write(f"error: pub_wx_mp id={args.row_id} not found\n")
        sys.exit(1)

    session = _prepare_session()
    try:
        rows = fetch_article_list(session)
        matched = match_article(rows, row["title"] or "")
        if matched is None:
            sys.stderr.write(
                f"error: 发表记录页未找到标题匹配的 row id={row['id']} title={row['title']!r}\n"
                f"hint: 跑 probe 子命令检查页面是否正常加载\n"
            )
            sys.exit(1)
        metrics = matched["metrics"]
        update_result = update_metrics_row(row["id"], metrics)
        result = {
            "ok": True,
            "row_id": row["id"],
            "title": row["title"],
            "matched_title": matched["title"],
            "publish_url": row["publish_url"],
            "session": session,
            "metrics": metrics,
            "update": update_result,
        }
    finally:
        _cleanup_session(session)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


def cmd_fetch_all(args) -> None:
    """批量刷新：打开首页一次，解析页内全部文章，匹配 pub_wx_mp 全部行写库。

    不翻页——发表记录页首页（count=20）本身就是天然窗口：页内有什么解析什么，
    匹配上的行写库，匹配不上的报 unmatched 跳过（老文章不在首页是常态，非错误）。
    少操作一次页面就少一次风控暴露。
    """
    row_ids = list_all_wx_mp_rows()
    if not row_ids:
        sys.stdout.write(json.dumps({"ok": True, "total": 0, "matched": 0, "unmatched": 0, "results": []}, indent=2))
        sys.stdout.write("\n")
        return

    _ensure_login()
    session = _prepare_session()
    results = []
    n_matched = 0
    try:
        rows = fetch_article_list(session)
        for rid in row_ids:
            row = lookup_published_row(rid)
            if row is None:
                results.append({"row_id": rid, "ok": False, "error": "row not found"})
                continue
            matched = match_article(rows, row["title"] or "")
            if matched is None:
                # 不在首页（老文章超出 count=20 范围/已删除）——跳过，非错误
                results.append({"row_id": rid, "ok": False, "error": "NOT_ON_FIRST_PAGE", "title": row["title"]})
                continue
            upd = update_metrics_row(rid, matched["metrics"])
            n_matched += 1
            results.append({"row_id": rid, "ok": upd.get("ok", True), "metrics": matched["metrics"]})
    finally:
        _cleanup_session(session)
    sys.stdout.write(json.dumps({
        "ok": True,
        "total": len(row_ids),
        "matched": n_matched,
        "unmatched": len(row_ids) - n_matched,
        "results": results,
    }, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


# ── main ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetch_engagement",
        description="WeChat Official Account engagement fetcher",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", help="打开创作者中心 dump DOM/截图").set_defaults(func=cmd_probe)
    sub.add_parser("list", help="列出后台所有文章 + 行内 metrics").set_defaults(func=cmd_list)

    sub.add_parser("login", help="camoufox 无头截 QR PNG").set_defaults(func=cmd_login)
    sub.add_parser("login-confirm", help="确认登录 + close session").set_defaults(func=cmd_login_confirm)

    p_fetch = sub.add_parser("fetch", help="抓单篇 engagement（按 title 在列表页匹配）")
    g = p_fetch.add_mutually_exclusive_group(required=True)
    g.add_argument("--row-id", type=int)
    g.add_argument("--source-folder", type=str)
    p_fetch.set_defaults(func=cmd_fetch)

    sub.add_parser("fetch-all", help="批量刷新（打开首页一次，匹配 pub_wx_mp 全部行写库；不翻页）").set_defaults(func=cmd_fetch_all)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
