#!/usr/bin/env python3
"""twitter-interact — Twitter/X 互动操作技能

架构：
- camoufox-cli 主推（反指纹 headless Firefox）
- 持久化 session `twitter`（与 twitter-post 共用，靠 session 名约定共享登录态）
- run 一键跑全流程

子命令：
  like       <tweet_url>                点赞
  unlike     <tweet_url>                取消点赞
  retweet    <tweet_url>                转推
  unretweet  <tweet_url>                取消转推
  bookmark   <tweet_url>                收藏
  unbookmark <tweet_url>                取消收藏
  follow     <user_handle>              关注用户
  unfollow   <user_handle>              取关用户
  run        --tweet-url <url> --action <like|retweet|bookmark|follow>
                                    一键跑（脚本化主流程）

依赖：
- camoufox-cli（npm 全局）
- python3 stdlib（json / subprocess / secrets / re / urllib）

与 login-manager **完全无关**——Twitter 互动是纯浏览器操作，登录态在 session profile 里闭环，
不导出 cookie/UA 落中央存储。登录流程按 `browser-guide` skill 走有头手动登录，登录后不关 session。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ── 常量 ─────────────────────────────────────────────────────────────────────

CAMOUFOX_BIN = os.environ.get("CAMOUFOX_CLI", "camoufox-cli")

# 每平台一个且只一个持久化 session，顺次使用（forked cli fail-first 队列串行）。
# 不再每任务生成 nonce session——并发调用由 forked cli 的 fail-first 队列拒绝，脚本透传给调用方。
TWITTER_SESSION = os.environ.get("TWITTER_SESSION", "twitter")


class SessionBusyError(Exception):
    """forked cli fail-first 队列拒绝：session 正忙。调用方应等待重试，不自动排队。"""

# 频率限制（平台 anti-automation 阈值 + 经验值）
FREQ_LIMITS = {
    "like":      {"min_interval_s": 60,  "daily_max": 200},   # 1 min, 200/day
    "retweet":   {"min_interval_s": 300, "daily_max": 50},    # 5 min, 50/day
    "bookmark":  {"min_interval_s": 60,  "daily_max": 100},
    "follow":    {"min_interval_s": 300, "daily_max": 50},    # 5 min, 50/day
    "unfollow":  {"min_interval_s": 300, "daily_max": 50},
    "reply":     {"min_interval_s": 180, "daily_max": 30},    # 3 min, 30/day
    "quote":     {"min_interval_s": 300, "daily_max": 20},    # 5 min, 20/day
}
FREQ_TRACKER_PATH = Path(
    os.environ.get(
        "FREQ_TRACKER_PATH",
        "~/.openclaw/agents/main/sessions/twitter-interact-frequency.json",
    )
).expanduser()

CAMOUFOX_TIMEOUT_S = 60


# ── 平台工具 ───────────────────────────────────────────────────────────────

def session_name(purpose: str = "interact") -> str:
    """返回 twitter 持久化 session 名（单一 session）。

    保留 purpose 参数仅为向后兼容（调用方可标注意图），实际忽略——所有操作共享
    同一个 `twitter` session，由 forked cli fail-first 队列串行。
    """
    return TWITTER_SESSION


def _camoufox_json(cmd: list[str], timeout: int) -> dict:
    """跑 camoufox-cli 命令，解析 --json 信封。session 正忙时抛 SessionBusyError。"""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    stdout = result.stdout.strip()
    if not stdout:
        if result.returncode != 0:
            raise RuntimeError(f"camoufox-cli 退出码 {result.returncode}: {result.stderr.strip()}")
        return {}
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return {"data": stdout}
    # fail-first 队列拒绝
    if isinstance(env, dict) and env.get("success") is False:
        err = str(env.get("error", ""))
        if "正忙" in err:
            raise SessionBusyError(err)
        raise RuntimeError(f"camoufox-cli error: {err}")
    return env if isinstance(env, dict) else {"data": env}


def camoufox_open(session: str, url: str, *, headed: bool = False) -> None:
    """启 persistent 会话 + 打开 URL。

    headed=True 走有头模式（登录场景，与 browser-guide 一致）；
    headed=False 走默认无头模式（自动化操作场景，无需用户在场）。
    """
    cmd = [CAMOUFOX_BIN, "--session", session, "--persistent", "--json", "open", url]
    if headed:
        cmd.insert(2, "--headed")
    _camoufox_json(cmd, CAMOUFOX_TIMEOUT_S)


def camoufox_eval(session: str, js: str, timeout: int = 30) -> Optional[str]:
    """在 session 内 eval JS，返回 data 字段。"""
    cmd = [CAMOUFOX_BIN, "--session", session, "--json", "eval", js]
    env = _camoufox_json(cmd, timeout)
    data = env.get("data")
    return data if isinstance(data, str) else json.dumps(data)


def camoufox_close(session: str) -> None:
    """关闭 camoufox session——仅供 session 卡死时手动 teardown，不主动调。
    持久化 session `twitter` 登录态留着给下次操作复用，主动 close 会破坏复用。"""
    subprocess.run(
        [CAMOUFOX_BIN, "--session", session, "--json", "close"],
        capture_output=True, text=True, timeout=10, check=False,
    )


def _check_session_alive() -> bool:
    """探活：camoufox-cli open x.com 首页 + snapshot 看是否跳登录页。
    与 login-manager 无关——twitter 走自有持久化 session `twitter`。"""
    try:
        camoufox_open(TWITTER_SESSION, "https://x.com/")
        time.sleep(3)
        result = subprocess.run(
            [CAMOUFOX_BIN, "--session", TWITTER_SESSION, "--json", "snapshot"],
            capture_output=True, text=True, timeout=CAMOUFOX_TIMEOUT_S, check=False,
        )
        env = json.loads(result.stdout) if result.stdout.strip() else {}
        data = env.get("data", "") if isinstance(env, dict) else ""
        # 跳登录页 / 出现登录按钮 = 失效
        return "登录" not in str(data) and "log in" not in str(data).lower()
    except Exception:
        return False

@contextlib.contextmanager
def twitter_session():
    """单一持久化 session `twitter` 的生命周期（单一 session）。

    - 正常退出：**不 close** session——登录态留着下次操作复用（与 twitter-post 共用同一 session）
    - SessionBusyError：**不 close**（close 会 tear down 正在跑的另一个操作），透传 exit 3
    """
    session = TWITTER_SESSION
    try:
        yield session
    except SessionBusyError as e:
        sys.stderr.write(
            f"error: session {session} 正忙 — {e}\n"
            f"  forked cli fail-first 队列拒绝。请等待当前操作完成后再试。\n"
        )
        raise SystemExit(3)


# ── URL 解析 ───────────────────────────────────────────────────────────────

def extract_tweet_id(input_str: str) -> Optional[str]:
    """从 URL 或裸 ID 抽出 tweet ID。"""
    if not input_str:
        return None
    # 纯数字
    if input_str.isdigit():
        return input_str
    # URL 形式: https://x.com/<user>/status/<id>
    m = re.search(r"/status/(\d+)", input_str)
    if m:
        return m.group(1)
    return None


def extract_user_handle(input_str: str) -> Optional[str]:
    """从 URL 或 @handle 抽出 username。"""
    if not input_str:
        return None
    s = input_str.strip().lstrip("@")
    # URL 形式
    m = re.search(r"x\.com/([A-Za-z0-9_]+)/?(?:$|\?)", s)
    if m and m.group(1) not in ("i", "intent", "share", "home"):
        return m.group(1)
    # 裸 handle
    if re.match(r"^[A-Za-z0-9_]{1,15}$", s):
        return s
    return None


# ── 频率限制 ───────────────────────────────────────────────────────────────

def _load_freq() -> dict:
    """读频率跟踪 JSON（不存在则初始化）。"""
    if not FREQ_TRACKER_PATH.exists():
        return {"actions": {}, "today_count": 0, "week_count": 0,
                "last_action_at": None, "last_action_type": None}
    try:
        return json.loads(FREQ_TRACKER_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"actions": {}, "today_count": 0, "week_count": 0,
                "last_action_at": None, "last_action_type": None}


def _save_freq(data: dict) -> None:
    FREQ_TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FREQ_TRACKER_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, FREQ_TRACKER_PATH)


def check_freq_limit(action: str) -> tuple[bool, str]:
    """检查频率限制。返回 (ok, reason)。"""
    if action not in FREQ_LIMITS:
        return True, ""
    limit = FREQ_LIMITS[action]
    data = _load_freq()
    now = time.time()
    # 间隔检查
    last_at = data.get("last_action_at")
    if last_at:
        try:
            last_ts = time.mktime(time.strptime(last_at, "%Y-%m-%dT%H:%M:%S%z"))
        except (ValueError, OSError):
            last_ts = 0
        elapsed = now - last_ts
        if elapsed < limit["min_interval_s"]:
            wait = int(limit["min_interval_s"] - elapsed)
            return False, f"距离上次 {action} 才 {int(elapsed)}s，< {limit['min_interval_s']}s 限制（还需 {wait}s）"
    # 日上限检查
    if data.get("today_count", 0) >= limit["daily_max"]:
        return False, f"今日 {action} 次数 {data['today_count']} 已达日上限 {limit['daily_max']}"
    return True, ""


def record_action(action: str) -> None:
    """记录一次成功动作，更新频率跟踪。"""
    data = _load_freq()
    data["today_count"] = data.get("today_count", 0) + 1
    data["week_count"] = data.get("week_count", 0) + 1
    data["last_action_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
    data["last_action_type"] = action
    actions = data.get("actions", {})
    actions[action] = actions.get(action, 0) + 1
    data["actions"] = actions
    _save_freq(data)


# ── 互动操作子命令 ─────────────────────────────────────────────────────────

def _open_tweet(session: str, tweet_id: str) -> None:
    """打开推文页。"""
    camoufox_open(session, f"https://x.com/i/web/status/{tweet_id}")


def cmd_like(tweet: str) -> None:
    """点赞。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    ok, reason = check_freq_limit("like")
    if not ok:
        sys.stderr.write(f"error: 频率限制 — {reason}\n")
        sys.exit(1)

    with twitter_session() as session:
        _open_tweet(session, tid)
        # click like 按钮
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="like"]');
            if (!btn) return false;
            // 已是 liked 状态？按钮 aria-pressed="true"
            if (btn.getAttribute('aria-pressed') === 'true') return 'already';
            btn.click();
            return true;
        })()
        """
        result = camoufox_eval(session, js)
        if result is None:
            sys.stderr.write("error: eval 失败（可能 DOM 未加载完成）\n")
            sys.exit(1)
        if result == "already":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "like", "note": "已点赞"}))
        elif result == "true":
            record_action("like")
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "like", "session": session}))
        else:
            sys.stderr.write(f"error: like 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_unlike(tweet: str) -> None:
    """取消点赞。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    with twitter_session() as session:
        _open_tweet(session, tid)
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="like"]');
            if (!btn) return false;
            if (btn.getAttribute('aria-pressed') !== 'true') return 'not_liked';
            btn.click();
            return true;
        })()
        """
        result = camoufox_eval(session, js)
        if result == "true":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "unlike", "session": session}))
        elif result == "not_liked":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "unlike", "note": "未点赞"}))
        else:
            sys.stderr.write(f"error: unlike 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_retweet(tweet: str) -> None:
    """转推。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    ok, reason = check_freq_limit("retweet")
    if not ok:
        sys.stderr.write(f"error: 频率限制 — {reason}\n")
        sys.exit(1)

    with twitter_session() as session:
        _open_tweet(session, tid)
        # click retweet → confirm（不 quote，单纯转推）
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="retweet"]');
            if (!btn) return false;
            if (btn.getAttribute('aria-pressed') === 'true') return 'already';
            btn.click();
            // 弹出 confirm 菜单 → click "Repost"（不是 Quote）
            return 'pending_confirm';
        })()
        """
        result = camoufox_eval(session, js)
        if result == "pending_confirm":
            time.sleep(1)  # 等菜单弹出
            confirm_js = """
            (function() {
                // X confirm 菜单的 Repost 按钮（不含 Quote）
                var items = document.querySelectorAll('[role="menuitem"]');
                for (var i = 0; i < items.length; i++) {
                    var text = items[i].textContent || '';
                    if (text.includes('Repost') && !text.includes('Quote')) {
                        items[i].click();
                        return true;
                    }
                }
                return false;
            })()
            """
            confirmed = camoufox_eval(session, confirm_js)
            if confirmed == "true":
                record_action("retweet")
                sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "retweet", "session": session}))
            else:
                sys.stderr.write(f"error: retweet confirm 失败（result={confirmed}）\n")
                sys.exit(1)
        elif result == "already":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "retweet", "note": "已转推"}))
        else:
            sys.stderr.write(f"error: retweet 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_unretweet(tweet: str) -> None:
    """取消转推。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    with twitter_session() as session:
        _open_tweet(session, tid)
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="unretweet"]');
            if (!btn) return false;
            btn.click();
            return 'pending_confirm';
        })()
        """
        result = camoufox_eval(session, js)
        if result == "pending_confirm":
            time.sleep(1)
            confirm_js = """
            (function() {
                var items = document.querySelectorAll('[role="menuitem"]');
                for (var i = 0; i < items.length; i++) {
                    if ((items[i].textContent || '').includes('Undo repost')) {
                        items[i].click();
                        return true;
                    }
                }
                return false;
            })()
            """
            confirmed = camoufox_eval(session, confirm_js)
            if confirmed == "true":
                sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "unretweet"}))
            else:
                sys.stderr.write("error: unretweet confirm 失败\n")
                sys.exit(1)
        else:
            sys.stderr.write(f"error: unretweet 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_bookmark(tweet: str) -> None:
    """收藏。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    ok, reason = check_freq_limit("bookmark")
    if not ok:
        sys.stderr.write(f"error: 频率限制 — {reason}\n")
        sys.exit(1)

    with twitter_session() as session:
        _open_tweet(session, tid)
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="bookmark"]');
            if (!btn) return false;
            if (btn.getAttribute('aria-pressed') === 'true') return 'already';
            btn.click();
            return true;
        })()
        """
        result = camoufox_eval(session, js)
        if result == "true":
            record_action("bookmark")
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "bookmark"}))
        elif result == "already":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "bookmark", "note": "已收藏"}))
        else:
            sys.stderr.write(f"error: bookmark 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_unbookmark(tweet: str) -> None:
    """取消收藏。"""
    tid = extract_tweet_id(tweet)
    if not tid:
        sys.stderr.write(f"error: 无法从 '{tweet}' 提取 tweet ID\n")
        sys.exit(1)
    with twitter_session() as session:
        _open_tweet(session, tid)
        js = """
        (function() {
            var btn = document.querySelector('[data-testid="removeBookmark"]');
            if (!btn) return false;
            btn.click();
            return true;
        })()
        """
        result = camoufox_eval(session, js)
        if result == "true":
            sys.stdout.write(json.dumps({"ok": True, "tweet_id": tid, "action": "unbookmark"}))
        else:
            sys.stderr.write(f"error: unbookmark 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_follow(user: str) -> None:
    """关注用户。"""
    handle = extract_user_handle(user)
    if not handle:
        sys.stderr.write(f"error: 无法从 '{user}' 提取 username\n")
        sys.exit(1)
    ok, reason = check_freq_limit("follow")
    if not ok:
        sys.stderr.write(f"error: 频率限制 — {reason}\n")
        sys.exit(1)

    with twitter_session() as session:
        camoufox_open(session, f"https://x.com/{handle}")
        js = """
        (function() {
            var btns = document.querySelectorAll('[data-testid$="-follow"]');
            for (var i = 0; i < btns.length; i++) {
                var btn = btns[i];
                var pressed = btn.getAttribute('aria-pressed') || btn.getAttribute('data-testid');
                if (btn.getAttribute('data-testid') === '-follow' || btn.getAttribute('data-testid') === 'follow') {
                    // 简化：用 text 判断
                    var text = (btn.textContent || '').trim();
                    if (text === 'Follow' || text === '关注' || text === 'Follow back') {
                        btn.click();
                        return true;
                    }
                }
            }
            return 'not_found';
        })()
        """
        result = camoufox_eval(session, js)
        if result == "true":
            record_action("follow")
            sys.stdout.write(json.dumps({"ok": True, "user": handle, "action": "follow"}))
        elif result == "not_found":
            sys.stdout.write(json.dumps({"ok": True, "user": handle, "action": "follow", "note": "已关注或按钮不在"}))
        else:
            sys.stderr.write(f"error: follow 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_unfollow(user: str) -> None:
    """取关用户。"""
    handle = extract_user_handle(user)
    if not handle:
        sys.stderr.write(f"error: 无法从 '{user}' 提取 username\n")
        sys.exit(1)
    with twitter_session() as session:
        camoufox_open(session, f"https://x.com/{handle}")
        js = """
        (function() {
            // X profile 页的 Following 按钮（aria-pressed="true" 表示已关注）
            var btns = document.querySelectorAll('[data-testid$="-follow"]');
            for (var i = 0; i < btns.length; i++) {
                var btn = btns[i];
                if (btn.getAttribute('data-testid') === '-follow' || btn.textContent === 'Following') {
                    btn.click();
                    return 'pending_confirm';
                }
            }
            return 'not_following';
        })()
        """
        result = camoufox_eval(session, js)
        if result == "pending_confirm":
            time.sleep(1)
            confirm_js = """
            (function() {
                var items = document.querySelectorAll('[role="menuitem"]');
                for (var i = 0; i < items.length; i++) {
                    var text = items[i].textContent || '';
                    if (text.includes('Unfollow') || text.includes('取消关注')) {
                        items[i].click();
                        return true;
                    }
                }
                return false;
            })()
            """
            confirmed = camoufox_eval(session, confirm_js)
            if confirmed == "true":
                sys.stdout.write(json.dumps({"ok": True, "user": handle, "action": "unfollow"}))
            else:
                sys.stderr.write("error: unfollow confirm 失败\n")
                sys.exit(1)
        elif result == "not_following":
            sys.stdout.write(json.dumps({"ok": True, "user": handle, "action": "unfollow", "note": "未关注"}))
        else:
            sys.stderr.write(f"error: unfollow 失败（result={result}）\n")
            sys.exit(1)
        sys.stdout.write("\n")


def cmd_run(*, tweet_url: str = "", action: str = "like", user: str = "") -> None:
    """一键跑（脚本化主流程）。探活走 camoufox-cli open + snapshot 看 session 内登录态。"""
    if not _check_session_alive():
        sys.stderr.write(
            f"error: twitter session 失效；先按 browser-guide skill 走有头手动登录\n"
            f"  流程：camoufox-cli --session twitter --persistent --headed open \"https://x.com/\" → 用户在浏览器完成登录 → 不 close session（留着下次用）。\n"
        )
        sys.exit(2)

    if tweet_url:
        if action == "like": cmd_like(tweet_url)
        elif action == "retweet": cmd_retweet(tweet_url)
        elif action == "bookmark": cmd_bookmark(tweet_url)
        else:
            sys.stderr.write(f"error: unknown action '{action}' for tweet_url\n")
            sys.exit(1)
    elif user:
        if action == "follow": cmd_follow(user)
        elif action == "unfollow": cmd_unfollow(user)
        else:
            sys.stderr.write(f"error: unknown action '{action}' for user\n")
            sys.exit(1)
    else:
        sys.stderr.write("error: --tweet-url or --user required\n")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="twitter_interact",
        description="Twitter/X 互动操作",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, help_text in [
        ("like", "点赞"),
        ("unlike", "取消点赞"),
        ("retweet", "转推"),
        ("unretweet", "取消转推"),
        ("bookmark", "收藏"),
        ("unbookmark", "取消收藏"),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("tweet", help="tweet URL 或裸 ID")
        sp.set_defaults(func=lambda a, n=name: globals()[f"cmd_{n}"](a.tweet))

    sp = sub.add_parser("follow", help="关注用户")
    sp.add_argument("user", help="@handle 或 x.com URL")
    sp.set_defaults(func=lambda a: cmd_follow(a.user))

    sp = sub.add_parser("unfollow", help="取关用户")
    sp.add_argument("user", help="@handle 或 x.com URL")
    sp.set_defaults(func=lambda a: cmd_unfollow(a.user))

    sp = sub.add_parser("run", help="一键跑")
    sp.add_argument("--tweet-url", default="")
    sp.add_argument("--user", default="")
    sp.add_argument("--action", default="like",
                    choices=["like", "retweet", "bookmark", "follow", "unfollow"])
    sp.set_defaults(func=lambda a: cmd_run(tweet_url=a.tweet_url, action=a.action, user=a.user))

    return p


def main(argv: Optional[list[str]] = None) -> int:
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
