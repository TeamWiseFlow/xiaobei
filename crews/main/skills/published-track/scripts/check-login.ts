#!/usr/bin/env -S node --experimental-strip-types
/**
 * check-login.ts — 登录探活（两层）
 *
 * Tier 1  cookie 关键字段存在性（cheap，无网络）
 *   借鉴 docs/nodriver_helper_reference.py _check_login_status：按平台查关键 cookie。
 *   缺失必失效 → 直接判 expired，不必 pong。
 *
 * Tier 2  pong：轻量 authenticated 请求验证 session 服务端是否真有效
 *   借鉴 ~/wiseflow-pro/MediaCrawlerPro-Python media_platform/<p>/client.py pong：
 *     bilibili GET /x/web-interface/nav → code==0 && data.isLogin
 *     kuaishou POST graphql visionProfileUserList → data.visionProfileUserList.result==1
 *     xhs      GET /api/sns/web/v2/user/me（xhsFetch 签名）→ success
 *     douyin   GET /aweme/v1/web/history/read/（a_bogus 签名）→ status_code==0
 *   wx_mp 不在本脚本——走 wx-mp-hunter check（cgi-bin/home <h2>「新的创作」）。
 *
 *   pong 结果落 ~/.cache/wiseflow-check-login/<platform>.json，TTL 600s。
 *   复盘 Step 2 每条记录调一次本脚本，缓存把 N 次 pong 压成 1 次，避免批量签名触风控。
 *
 * Usage:
 *   node --experimental-strip-types check-login.ts --platform <p> [--no-ping]
 * Exit: 0=有效 / 2=失效 / 1=参数或读取错误
 */
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

type CookieRecord = { name: string; value: string; domain?: string; expires?: number };
type CookieMap = Record<string, CookieRecord>;

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins");
const CACHE_DIR = join(homedir(), ".cache", "wiseflow-check-login");
const PING_TTL_MS = 10 * 60 * 1000;
const DEFAULT_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";

function sessionName(platform: string): string {
  return platform === "xhs" ? "xhs-browse" : platform;
}

function loadCookies(platform: string): { map: CookieMap; raw: CookieRecord[] } | null {
  const path = join(SESSIONS_DIR, `${sessionName(platform)}.json`);
  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  const arr: CookieRecord[] = Array.isArray(raw) ? raw : (raw?.cookies ?? []);
  const map: CookieMap = {};
  for (const c of arr) if (c && typeof c.name === "string") map[c.name] = c;
  return { map, raw: arr };
}

function loadUa(platform: string): string {
  const path = join(SESSIONS_DIR, `${sessionName(platform)}.ua.json`);
  if (!existsSync(path)) return DEFAULT_UA;
  try {
    return (JSON.parse(readFileSync(path, "utf-8")) as { userAgent?: string }).userAgent || DEFAULT_UA;
  } catch {
    return DEFAULT_UA;
  }
}

function cookieHeader(map: CookieMap): string {
  return Object.entries(map).filter(([, c]) => c?.value).map(([k, c]) => `${k}=${c.value}`).join("; ");
}

function expired(c?: CookieRecord): boolean {
  if (!c || typeof c.expires !== "number" || c.expires <= 0) return false;
  return c.expires * 1000 < Date.now();
}

function out(obj: unknown): void {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

// ── Tier 1: 关键字段存在性 ──────────────────────────────────────────────────

function presenceCheck(platform: string, map: CookieMap): { ok: boolean; reason?: string; detail?: string } {
  switch (platform) {
    case "xhs": {
      const ws = map["web_session"];
      if (!ws?.value) return { ok: false, reason: "missing web_session" };
      if (expired(ws)) return { ok: false, reason: "web_session expired" };
      return { ok: true, detail: map["a1"]?.value ? "web_session+a1" : "web_session (a1 missing)" };
    }
    case "bilibili": {
      const sd = map["SESSDATA"];
      const uid = map["DedeUserID"];
      if ((sd?.value && !expired(sd)) || (uid?.value && !expired(uid))) return { ok: true };
      return { ok: false, reason: "missing SESSDATA/DedeUserID" };
    }
    case "douyin": {
      const required = ["sessionid", "sid_tt", "uid_tt"];
      const stale = ["sid_ucp_sso_v1", "ssid_ucp_sso_v1", "sso_uid_tt", "toutiao_sso_user", "toutiao_sso_user_ss"];
      const missing = required.filter((k) => !map[k]?.value);
      if (missing.length) return { ok: false, reason: `missing ${missing.join(",")}` };
      const staleHit = stale.filter((k) => map[k]);
      if (staleHit.length) return { ok: false, reason: `stale ${staleHit.join(",")}` };
      return { ok: true };
    }
    case "kuaishou": {
      const keys = ["kuaishou.server.webday7_st", "userId", "kuaishou.server.webday7_ph", "passToken"];
      const hit = keys.find((k) => map[k]?.value && !expired(map[k]));
      return hit ? { ok: true, detail: hit } : { ok: false, reason: "missing kuaishou login keys" };
    }
    default:
      return { ok: false, reason: `unknown platform: ${platform}` };
  }
}

// ── Tier 2: pong ─────────────────────────────────────────────────────────────

async function pongBilibili(map: CookieMap): Promise<{ ok: boolean; reason?: string }> {
  const resp = await fetch("https://api.bilibili.com/x/web-interface/nav", {
    headers: { "User-Agent": DEFAULT_UA, Cookie: cookieHeader(map), Referer: "https://www.bilibili.com/" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!resp.ok) return { ok: false, reason: `nav HTTP ${resp.status}` };
  const data = (await resp.json()) as { code?: number; data?: { isLogin?: boolean } };
  if (data.code === 0 && data.data?.isLogin) return { ok: true };
  return { ok: false, reason: `nav code=${data.code} isLogin=${data.data?.isLogin}` };
}

async function pongKuaishou(map: CookieMap): Promise<{ ok: boolean; reason?: string }> {
  const query =
    "query visionProfileUserList($pcursor: String, $ftype: Int) { visionProfileUserList(pcursor: $pcursor, ftype: $ftype) { result fols { user_name } hostName pcursor } }";
  const resp = await fetch("https://www.kuaishou.com/graphql", {
    method: "POST",
    headers: {
      "User-Agent": loadUa("kuaishou"),
      Cookie: cookieHeader(map),
      "Content-Type": "application/json",
      Referer: "https://www.kuaishou.com/",
      Origin: "https://www.kuaishou.com",
    },
    body: JSON.stringify({ operationName: "visionProfileUserList", variables: { ftype: 1 }, query }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!resp.ok) return { ok: false, reason: `graphql HTTP ${resp.status}` };
  const data = (await resp.json()) as { data?: { visionProfileUserList?: { result?: number } } };
  if (data.data?.visionProfileUserList?.result === 1) return { ok: true };
  return { ok: false, reason: `visionProfileUserList.result=${data.data?.visionProfileUserList?.result}` };
}

async function pongXhs(map: CookieMap): Promise<{ ok: boolean; reason?: string }> {
  const { xhsFetch } = await import("../../_shared/relay-sign.ts");
  const cookies: Record<string, string> = {};
  for (const [k, c] of Object.entries(map)) if (c?.value) cookies[k] = c.value;
  try {
    const r = await xhsFetch<{ success?: boolean; code?: number }>({
      baseUrl: "https://edith.xiaohongshu.com",
      uri: "/api/sns/web/v2/user/me",
      method: "get",
      cookies,
      signFormat: "xyw", // user/me 等 data API 用 xyw（见 relay-sign.ts 注释）
      timeoutMs: 15_000,
    });
    if (r?.success) return { ok: true };
    return { ok: false, reason: `user/me success=${r?.success} code=${r?.code}` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, reason: `user/me error: ${msg.slice(0, 120)}` };
  }
}

function genFakeMsToken(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  let t = "";
  for (let i = 0; i < 126; i++) t += chars[Math.floor(Math.random() * chars.length)];
  return t + "==";
}

async function pongDouyin(map: CookieMap): Promise<{ ok: boolean; reason?: string }> {
  const { douyinSign } = await import("../../_shared/relay-sign.ts");
  const ua = loadUa("douyin");
  const params = new URLSearchParams({ max_cursor: "0", count: "20", msToken: genFakeMsToken() }).toString();
  const aBogus = await douyinSign({ queryString: params, postData: "", ua });
  const url = `https://www.douyin.com/aweme/v1/web/history/read/?${params}&a_bogus=${aBogus}`;
  try {
    const resp = await fetch(url, {
      headers: { "User-Agent": ua, Cookie: cookieHeader(map), Referer: "https://www.douyin.com/", Accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok) return { ok: false, reason: `history/read HTTP ${resp.status}` };
    const data = (await resp.json()) as { status_code?: number };
    // status_code==0 已登录；==8 未登录
    return data.status_code === 0 ? { ok: true } : { ok: false, reason: `status_code=${data.status_code}` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, reason: `history/read error: ${msg.slice(0, 120)}` };
  }
}

async function pong(platform: string, map: CookieMap): Promise<{ ok: boolean; reason?: string }> {
  switch (platform) {
    case "bilibili": return pongBilibili(map);
    case "kuaishou": return pongKuaishou(map);
    case "xhs": return pongXhs(map);
    case "douyin": return pongDouyin(map);
    default: return { ok: true }; // 未知平台不 pong，交上层
  }
}

// ── pong 缓存 ────────────────────────────────────────────────────────────────

interface CacheEntry {
  ok: boolean;
  reason?: string;
  at: number;
}

function readCache(platform: string): CacheEntry | null {
  const p = join(CACHE_DIR, `${platform}.json`);
  if (!existsSync(p)) return null;
  try {
    const e = JSON.parse(readFileSync(p, "utf-8")) as CacheEntry;
    if (typeof e.at === "number" && Date.now() - e.at < PING_TTL_MS) return e;
    return null;
  } catch {
    return null;
  }
}

function writeCache(platform: string, entry: CacheEntry): void {
  try {
    mkdirSync(CACHE_DIR, { recursive: true });
    writeFileSync(join(CACHE_DIR, `${platform}.json`), `${JSON.stringify(entry)}\n`);
  } catch {
    /* 缓存写失败不影响探活结论 */
  }
}

// ── main ─────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  let platform = "";
  let noPing = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i];
    else if (args[i] === "--no-ping") noPing = true;
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

  // Tier 1
  const pres = presenceCheck(platform, loaded.map);
  if (!pres.ok) {
    out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: pres.reason });
    process.exit(2);
  }

  // wx_mp 委托 wx-mp-hunter，本脚本只做 presence（不会走到这，fetch-and-update 对 wx_mp 早退）
  if (platform === "wx_mp" || noPing) {
    out({ ok: true, platform, session: sessionName(platform), cookies: loaded.raw.length, detail: pres.detail, ping: "skipped" });
    process.exit(0);
  }

  // Tier 2: pong（带缓存）
  const cached = readCache(platform);
  if (cached) {
    if (cached.ok) {
      out({ ok: true, platform, session: sessionName(platform), cookies: loaded.raw.length, detail: pres.detail, ping: "cached" });
      process.exit(0);
    }
    out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: cached.reason, ping: "cached" });
    process.exit(2);
  }

  const r = await pong(platform, loaded.map);
  writeCache(platform, { ok: r.ok, reason: r.reason, at: Date.now() });
  if (r.ok) {
    out({ ok: true, platform, session: sessionName(platform), cookies: loaded.raw.length, detail: pres.detail, ping: "ok" });
    process.exit(0);
  }
  out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: r.reason, ping: "fail" });
  process.exit(2);
}

main().catch((e: unknown) => {
  out({ ok: false, error: "CHECK_LOGIN_CRASH", message: e instanceof Error ? e.message : String(e) });
  process.exit(1);
});
