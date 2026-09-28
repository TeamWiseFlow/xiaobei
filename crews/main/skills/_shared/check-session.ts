/**
 * check-session.ts — 登录态探活（两层）可导入库
 *
 * 由 published-track/scripts/check-login.ts（CLI）和各下游脚本的 cookie 加载模块共用，
 * 实现「导入 cookie 后验有效性，失效则交 Agent 重登」（见 login-manager SKILL.md）。
 *
 * Tier 1  cookie 关键字段存在性（cheap，无网络）
 *   _check_login_status：按平台查关键 cookie。
 *   缺失必失效 → 直接判 expired，不必 pong。
 *
 * Tier 2  pong：轻量 authenticated 请求验证 session 服务端是否真有效
 *     bilibili GET /x/web-interface/nav → code==0 && data.isLogin
 *     kuaishou POST graphql visionProfileUserList → data.visionProfileUserList.result==1
 *     douyin   GET /aweme/v1/web/history/read/（a_bogus 签名）→ status_code==0
 *   wx_mp 不在本模块——走 wx-mp-hunter check（cgi-bin/home <h2>「新的创作」）。
 *
 *   pong 三态：ok / fail（明确未登录：douyin status_code=8）/ UNKNOWN
 *   （端点异常但无法证明未登录：douyin 除 0/8 外的 status_code、HTTP 层错误、网络异常）。
 *   UNKNOWN 不判死——gate 放行，由下游真实请求最终裁决。2026-09-01/02 连续两晚凌晨
 *   douyin pong 回 status_code=4 被判 SESSION_EXPIRED 触发误报重登，但同 cookie 真实
 *   取数成功（探活端点被风控/限流间歇拦截），见 workspace-main/douyin/20260902 排查文档。
 *
 *   pong 结果落 ~/.cache/wiseflow-check-login/<platform>.json，TTL 600s。
 *   批量调用复用同一缓存，把 N 次 pong 压成 1 次，避免批量签名触风控。
 *
 * 导出：
 *   verifyCookies(platform, map, opts?) — 给定 cookie map 新鲜探活（不读文件/缓存），导出前验证用
 *   checkSession(platform, opts?) — 从中央存储读 + TTL 缓存 pong，抓取前批量探活用
 *     error 仅在失效时填："SESSION_EXPIRED"（cookie 问题，应重登）或
 *     "SIGN_UNAVAILABLE"（签名缺 OFB_KEY，重登救不了，应让 IT engineer 配凭证）。
 *   buildCookieMap(raw) — 从 camoufox-cli cookies export 输出构建 CookieMap
 *   SessionExpiredError / SignUnavailableError 便于 throw 风格调用方使用。
 *
 */

import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

type CookieRecord = { name: string; value: string; domain?: string; expires?: number };
type CookieMap = Record<string, CookieRecord>;

/** 从 camoufox-cli cookies export 的裸数组 / {cookies:[...]} 构建 CookieMap */
export function buildCookieMap(raw: unknown): CookieMap {
  const arr: CookieRecord[] = Array.isArray(raw) ? raw : ((raw as { cookies?: CookieRecord[] })?.cookies ?? []);
  const map: CookieMap = {};
  for (const c of arr) if (c && typeof c.name === "string") map[c.name] = c;
  return map;
}

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins");
const CACHE_DIR = join(homedir(), ".cache", "wiseflow-check-login");
const PING_TTL_MS = 10 * 60 * 1000;
const SUPPORTED_PLATFORMS = new Set(["douyin", "bilibili", "kuaishou"]);
const DEFAULT_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36";

/** 需 relay 签名的平台：pong 前必须有 OFB_KEY，否则判 SIGN_UNAVAILABLE 而非 SESSION_EXPIRED */
const SIGNING_PLATFORMS = new Set(["douyin"]);

export class SessionExpiredError extends Error {
  readonly platform: string;
  readonly reason?: string;
  constructor(platform: string, reason?: string) {
    super(`SESSION_EXPIRED: ${platform}${reason ? ` (${reason})` : ""}`);
    this.name = "SessionExpiredError";
    this.platform = platform;
    this.reason = reason;
  }
}

export class SignUnavailableError extends Error {
  readonly platform: string;
  constructor(platform: string) {
    super(`SIGN_UNAVAILABLE: ${platform} (OFB_KEY 未配置)`);
    this.name = "SignUnavailableError";
    this.platform = platform;
  }
}

export interface CheckResult {
  ok: boolean;
  /** 失效时填：SESSION_EXPIRED（应重登）/ SIGN_UNAVAILABLE（应配凭证） */
  error?: "SESSION_EXPIRED" | "SIGN_UNAVAILABLE" | "UNSUPPORTED_PLATFORM";
  reason?: string;
  detail?: string;
  ping?: "skipped" | "cached" | "ok" | "fail" | "unknown";
}

/** 平台 key → 中央存储 session 文件名 */
export function sessionName(platform: string): string {
  return platform;
}

/** pong 用的平台 key */
function pongPlatform(platform: string): string {
  return platform;
}

export function loadCookies(platform: string): { map: CookieMap; raw: CookieRecord[] } | null {
  const path = join(SESSIONS_DIR, `${sessionName(platform)}.json`);
  if (!existsSync(path)) return null;
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  const arr: CookieRecord[] = Array.isArray(raw) ? raw : (raw?.cookies ?? []);
  const map: CookieMap = {};
  for (const c of arr) if (c && typeof c.name === "string") map[c.name] = c;
  return { map, raw: arr };
}

export function loadUa(platform: string): string {
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

function ofbKeyAvailable(): boolean {
  const k = process.env.OFB_KEY;
  return typeof k === "string" && k.length > 0;
}

// ── Tier 1: 关键字段存在性 ──────────────────────────────────────────────────

export function presenceCheck(platform: string, map: CookieMap): { ok: boolean; reason?: string; detail?: string } {
  const p = pongPlatform(platform);
  switch (p) {
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

function genFakeMsToken(): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  let t = "";
  for (let i = 0; i < 126; i++) t += chars[Math.floor(Math.random() * chars.length)];
  return t + "==";
}

async function pongDouyin(map: CookieMap): Promise<{ ok: boolean; reason?: string; unknown?: boolean }> {
  const { douyinSign } = await import("./relay-sign.ts");
  const ua = loadUa("douyin");
  const params = new URLSearchParams({ max_cursor: "0", count: "20", msToken: genFakeMsToken() }).toString();
  const aBogus = await douyinSign({ queryString: params, postData: "", ua });
  const url = `https://www.douyin.com/aweme/v1/web/history/read/?${params}&a_bogus=${aBogus}`;
  try {
    const resp = await fetch(url, {
      headers: { "User-Agent": ua, Cookie: cookieHeader(map), Referer: "https://www.douyin.com/", Accept: "application/json" },
      signal: AbortSignal.timeout(15_000),
    });
    // HTTP 层异常不能证明未登录（风控/限流同样落这里）——UNKNOWN 放行，真实请求裁决
    if (!resp.ok) return { ok: true, unknown: true, reason: `history/read HTTP ${resp.status}` };
    const text = await resp.text();
    let data: { status_code?: number } = {};
    try {
      data = JSON.parse(text) as { status_code?: number };
    } catch {
      /* 非 JSON 响应（如风控验证页）——落 UNKNOWN 分支 */
    }
    // status_code==0 已登录；==8 明确未登录。其余值语义未知（2026-09 误报教训，见模块头注释）：
    // 除 8 外一律 UNKNOWN 放行，由下游真实请求最终裁决；响应体片段保留在 reason 供观察。
    if (data.status_code === 0) return { ok: true };
    if (data.status_code === 8) return { ok: false, reason: "status_code=8（未登录）" };
    return { ok: true, unknown: true, reason: `status_code=${data.status_code}（语义未知） body=${text.slice(0, 120)}` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    // 网络异常同理不能证明未登录——UNKNOWN 放行（真实请求若同样失败会以自身错误上报）
    return { ok: true, unknown: true, reason: `history/read error: ${msg.slice(0, 120)}` };
  }
}

async function pong(platform: string, map: CookieMap): Promise<{ ok: boolean; reason?: string; unknown?: boolean }> {
  const p = pongPlatform(platform);
  switch (p) {
    case "bilibili": return pongBilibili(map);
    case "kuaishou": return pongKuaishou(map);
    case "douyin": return pongDouyin(map);
    default: return { ok: true }; // 未知平台不 pong，交上层
  }
}

// ── pong 缓存 ────────────────────────────────────────────────────────────────

interface CacheEntry {
  ok: boolean;
  reason?: string;
  unknown?: boolean;
  at: number;
}

function readCache(platform: string): CacheEntry | null {
  const p = join(CACHE_DIR, `${pongPlatform(platform)}.json`);
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
    writeFileSync(join(CACHE_DIR, `${pongPlatform(platform)}.json`), `${JSON.stringify(entry)}\n`);
  } catch {
    /* 缓存写失败不影响探活结论 */
  }
}

// ── 主入口 ───────────────────────────────────────────────────────────────────

/**
 * 两层探活（给定 cookie map，不读文件、不读缓存——始终新鲜 pong）。
 * 供 login-and-export / wx-mp-hunter cmdLoginConfirm 在**导出前**验 cookie：导出到临时 →
 * verifyCookies → 通过才 commit。新鲜 pong 是关键——登录验证不能用批量探活的 TTL 缓存
 * （缓存可能残留旧失效 session 的 fail 判定）。pong 后写缓存，让随后 checkSession 命中 ok。
 *
 * opts.noPing=true 只做 Tier1 字段检查（不起网络、不签名）。
 */
export async function verifyCookies(platform: string, map: CookieMap, opts: { noPing?: boolean } = {}): Promise<CheckResult> {
  if (!SUPPORTED_PLATFORMS.has(platform)) {
    return { ok: false, error: "UNSUPPORTED_PLATFORM", reason: `unsupported platform: ${platform}` };
  }
  // Tier 1
  const pres = presenceCheck(platform, map);
  if (!pres.ok) return { ok: false, error: "SESSION_EXPIRED", reason: pres.reason };

  // wx_mp 委托 wx-mp-hunter；noPing 止步于此——只做 presence
  if (platform === "wx_mp" || opts.noPing) return { ok: true, detail: pres.detail, ping: "skipped" };

  const p = pongPlatform(platform);
  if (SIGNING_PLATFORMS.has(p) && !ofbKeyAvailable()) {
    return {
      ok: false,
      error: "SIGN_UNAVAILABLE",
      reason: "OFB_KEY 未配置（relay 签名缺凭证，pong 与业务 fetch 均会失败；请 IT engineer 写入 daemon.env 后重启，非 cookie 问题）",
    };
  }

  const r = await pong(platform, map);
  writeCache(platform, { ok: r.ok, reason: r.reason, unknown: r.unknown, at: Date.now() });
  if (r.ok) {
    // UNKNOWN（pong 端点异常但无法证明未登录）——放行，detail 带原因供日志观察
    if (r.unknown) return { ok: true, ping: "unknown", detail: `pong UNKNOWN: ${r.reason}（放行，由真实请求最终裁决）` };
    return { ok: true, detail: pres.detail, ping: "ok" };
  }
  return { ok: false, error: "SESSION_EXPIRED", reason: r.reason, ping: "fail" };
}

/**
 * 两层探活（从中央存储读 cookie，pong 走 TTL 缓存）。供抓取前批量探活——
 * 复盘 N 条记录复用同一缓存，把 N 次 pong 压成 1 次，避免批量签名触风控。
 * 不抛——返回 {ok, error, reason}，调用方决定 exit/throw。wx_mp 不支持（走 wx-mp-hunter）。
 */
export async function checkSession(platform: string, opts: { noPing?: boolean } = {}): Promise<CheckResult> {
  if (!SUPPORTED_PLATFORMS.has(platform)) {
    return { ok: false, error: "UNSUPPORTED_PLATFORM", reason: `unsupported platform: ${platform}` };
  }
  const loaded = loadCookies(platform);
  if (!loaded) {
    return { ok: false, error: "SESSION_EXPIRED", reason: "login file not found" };
  }

  // Tier 1
  const pres = presenceCheck(platform, loaded.map);
  if (!pres.ok) {
    return { ok: false, error: "SESSION_EXPIRED", reason: pres.reason };
  }

  // wx_mp 委托 wx-mp-hunter；noPing 止步于此——只做 presence
  if (platform === "wx_mp" || opts.noPing) {
    return { ok: true, detail: pres.detail, ping: "skipped" };
  }

  const p = pongPlatform(platform);

  // 签名平台缺 OFB_KEY → SIGN_UNAVAILABLE（不混入 SESSION_EXPIRED 以免误导重登）
  if (SIGNING_PLATFORMS.has(p) && !ofbKeyAvailable()) {
    return {
      ok: false,
      error: "SIGN_UNAVAILABLE",
      reason: "OFB_KEY 未配置（relay 签名缺凭证，pong 与业务 fetch 均会失败；请 IT engineer 写入 daemon.env 后重启，非 cookie 问题）",
    };
  }

  // Tier 2: pong（带缓存）
  const cached = readCache(platform);
  if (cached) {
    if (cached.ok) {
      if (cached.unknown) {
        return { ok: true, ping: "unknown", detail: `pong UNKNOWN(缓存): ${cached.reason}（放行，由真实请求最终裁决）` };
      }
      return { ok: true, detail: pres.detail, ping: "cached" };
    }
    return { ok: false, error: "SESSION_EXPIRED", reason: cached.reason, ping: "cached" };
  }

  const r = await pong(platform, loaded.map);
  writeCache(platform, { ok: r.ok, reason: r.reason, unknown: r.unknown, at: Date.now() });
  if (r.ok) {
    // UNKNOWN（pong 端点异常但无法证明未登录）——放行，detail 带原因供日志观察
    if (r.unknown) return { ok: true, ping: "unknown", detail: `pong UNKNOWN: ${r.reason}（放行，由真实请求最终裁决）` };
    return { ok: true, detail: pres.detail, ping: "ok" };
  }
  return { ok: false, error: "SESSION_EXPIRED", reason: r.reason, ping: "fail" };
}
