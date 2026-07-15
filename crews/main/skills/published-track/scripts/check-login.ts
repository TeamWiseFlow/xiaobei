#!/usr/bin/env -S node --experimental-strip-types
/**
 * check-login.ts — 基于 cookie 关键字段的登录探活
 *
 * 思路借鉴 docs/nodriver_helper_reference.py `_check_login_status`：按平台查
 * 关键 cookie 是否存在（而非 snapshot 文案 grep），避免已登录页面里「登录」字样
 * 假阳性。探活与取数读同一份 ~/.openclaw/logins/<session>.json，两者状态对齐。
 *
 * cookie 存在未必有效（可能服务端已过期），但缺失必失效——真伪交 fetch-retro-data
 * 实际请求验证。本脚本只做 cheap gate。
 *
 * Usage:
 *   node --experimental-strip-types check-login.ts --platform <platform>
 *     platform 用 published-track 名（xhs/bilibili/douyin/kuaishou/wx_mp）
 *
 * Output (stdout JSON):
 *   {"ok":true,"platform":"xhs","session":"xhs-browse","cookies":18}
 *   {"ok":false,"error":"SESSION_EXPIRED","platform":"xhs","session":"xhs-browse","reason":"..."}
 *
 * Exit: 0=有效 / 2=失效 / 1=参数或读取错误
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

type CookieRecord = { name: string; value: string; domain?: string; expires?: number };
type CookieMap = Record<string, CookieRecord>;

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins");

/** published-track 平台名 → 中央存储 session 文件名（xhs 取数走浏览端） */
function sessionName(platform: string): string {
  if (platform === "xhs") return "xhs-browse";
  return platform;
}

/** 读 cookie 文件，归一化 camoufox-cli 裸数组与 {cookies:[...]} 两种形状 */
function loadCookies(platform: string): { cookies: CookieMap; raw: CookieRecord[] } | null {
  const path = join(SESSIONS_DIR, `${sessionName(platform)}.json`);
  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  const arr: CookieRecord[] = Array.isArray(raw) ? raw : (raw?.cookies ?? []);
  const map: CookieMap = {};
  for (const c of arr) {
    if (c && typeof c.name === "string") map[c.name] = c;
  }
  return { cookies: map, raw: arr };
}

/** 轻 cookie expires（秒级 epoch）已过当下 */
function expired(c?: CookieRecord): boolean {
  if (!c || typeof c.expires !== "number") return false;
  if (c.expires <= 0) return false; // session cookie 或 -1，不判
  return c.expires * 1000 < Date.now();
}

interface CheckResult {
  ok: boolean;
  reason?: string;
  detail?: string;
}

/** 各平台关键 cookie 判定，对齐 nodriver_helper_reference._check_login_status */
function checkPlatform(platform: string, cookies: CookieMap): CheckResult {
  switch (platform) {
    case "xhs": {
      const ws = cookies["web_session"];
      if (!ws || !ws.value) return { ok: false, reason: "missing web_session" };
      if (expired(ws)) return { ok: false, reason: "web_session expired" };
      // a1 为签名依赖，缺失则取数必失败——一并提示
      const a1 = cookies["a1"];
      return { ok: true, detail: a1?.value ? "web_session+a1" : "web_session (a1 missing!)" };
    }
    case "bilibili": {
      const sd = cookies["SESSDATA"];
      const uid = cookies["DedeUserID"];
      if ((sd && sd.value && !expired(sd)) || (uid && uid.value && !expired(uid))) return { ok: true };
      return { ok: false, reason: "missing SESSDATA/DedeUserID" };
    }
    case "douyin": {
      const required = ["sessionid", "sid_tt", "uid_tt"];
      const stale = ["sid_ucp_sso_v1", "ssid_ucp_sso_v1", "sso_uid_tt", "toutiao_sso_user", "toutiao_sso_user_ss"];
      const missing = required.filter((k) => !cookies[k] || !cookies[k].value);
      if (missing.length) return { ok: false, reason: `missing ${missing.join(",")}` };
      const staleHit = stale.filter((k) => cookies[k]);
      if (staleHit.length) return { ok: false, reason: `stale ${staleHit.join(",")}` };
      return { ok: true };
    }
    case "kuaishou": {
      const keys = ["kuaishou.server.webday7_st", "userId", "kuaishou.server.webday7_ph", "passToken"];
      const hit = keys.find((k) => cookies[k] && cookies[k].value && !expired(cookies[k]));
      if (hit) return { ok: true, detail: hit };
      return { ok: false, reason: "missing kuaishou login keys" };
    }
    case "wx_mp": {
      // wx_mp 走 wx-mp-hunter：token 在 session 文件顶层字段，cookie 数组另存。
      // 这里只判 cookie 文件非空；token 由 wx-mp-hunter 自管，不复用本脚本。
      return { ok: true, detail: "wx_mp cookie file present (token check delegated to wx-mp-hunter)" };
    }
    default:
      return { ok: false, reason: `unknown platform: ${platform}` };
  }
}

function out(obj: unknown): void {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

function main(): void {
  const args = process.argv.slice(2);
  let platform = "";
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i];
  }
  if (!platform) {
    out({ ok: false, error: "missing --platform" });
    process.exit(1);
  }

  const loaded = loadCookies(platform);
  if (!loaded) {
    out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: "login file not found" });
    process.exit(2);
  }

  const res = checkPlatform(platform, loaded.cookies);
  if (res.ok) {
    out({ ok: true, platform, session: sessionName(platform), cookies: loaded.raw.length, detail: res.detail });
    process.exit(0);
  }
  out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: res.reason });
  process.exit(2);
}

main();
