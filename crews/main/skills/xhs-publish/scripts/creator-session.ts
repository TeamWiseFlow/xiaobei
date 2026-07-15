/**
 * creator-session.ts — xhs-publish 创作者域会话探活库（自包含）
 *
 * xhs-publish cookie 是创作者域（creator.xiaohongshu.com）会话，与 xhs-browse 的消费者域
 * （www.xiaohongshu.com，web_session）是两套独立登录，不能共用（见 memory 17 / check-session.ts）。
 * 故 xhs-publish 探活不进共享 _shared/check-session.ts，在本技能内自营。
 *
 * 探活端点：GET https://creator.xiaohongshu.com/api/galaxy/creator/home/personal_info
 *   裸 GET + 创作者 cookie + Referer: creator.xiaohongshu.com/ → success===true && code===0 = online
 *   实测：有效 cookie 返回 200/code=0/data.fans_count/data.name/data.diagnosis_status。
 *
 * 关键：**无需 xhs 签名**（不调 relay-sign、不依赖 OFB_KEY）。创作者 cookie 打 edith user/me
 *   （xhs-browse 那套签名 pong）会返回 -101「无登录信息」——创作者 cookie 认不了消费者域 user/me，
 *   创作者域 personal_info 才是它认的端点。借鉴 Ai2Earn `loginCheck`（electron/plat/xiaohongshu）。
 *
 * 导出：
 *   buildCookieMap(raw) — camoufox-cli cookies export 输出（裸数组或 {cookies:[...]}）→ CookieMap
 *   loadCreatorSession() — 从中央存储读 xhs-publish.json + .ua.json
 *   presenceCheckCreator(map) — Tier1 创作者会话 cookie 字段存在性（cheap，无网络）
 *   pingCreator(map, ua) — Tier2 裸 GET personal_info
 *   verifyCreator(map) — presence + ping（新鲜，导出前验证用）
 *   checkCreator() — load + presence + ping（抓取/发布前探活用）
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

type CookieRecord = { name: string; value: string; domain?: string; expires?: number };
type CookieMap = Record<string, CookieRecord>;

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins");
const SESSION_FILE = join(SESSIONS_DIR, "xhs-publish.json");
const UA_FILE = join(SESSIONS_DIR, "xhs-publish.ua.json");
const DEFAULT_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const PING_URL = "https://creator.xiaohongshu.com/api/galaxy/creator/home/personal_info";
const REFERER = "https://creator.xiaohongshu.com/";

/** 创作者会话 cookie 候选（任一在即视为有创作者会话；a1 是设备指纹，单独要求） */
const CREATOR_SESSION_KEYS = [
  "galaxy_creator_session_id",
  "galaxy.creator.beaker.session.id",
  "access-token-creator.xiaohongshu.com",
  "customer-sso-sid",
];

export function buildCookieMap(raw: unknown): CookieMap {
  const arr: CookieRecord[] = Array.isArray(raw) ? raw : ((raw as { cookies?: CookieRecord[] })?.cookies ?? []);
  const map: CookieMap = {};
  for (const c of arr) if (c && typeof c.name === "string") map[c.name] = c;
  return map;
}

function expired(c?: CookieRecord): boolean {
  if (!c || typeof c.expires !== "number" || c.expires <= 0) return false;
  return c.expires * 1000 < Date.now();
}

function cookieHeader(map: CookieMap): string {
  return Object.entries(map).filter(([, c]) => c?.value).map(([k, c]) => `${k}=${c.value}`).join("; ");
}

export function loadUa(): string {
  if (!existsSync(UA_FILE)) return DEFAULT_UA;
  try {
    return (JSON.parse(readFileSync(UA_FILE, "utf-8")) as { userAgent?: string }).userAgent || DEFAULT_UA;
  } catch {
    return DEFAULT_UA;
  }
}

export function loadCreatorSession(): { map: CookieMap; ua: string } | null {
  if (!existsSync(SESSION_FILE)) return null;
  const map = buildCookieMap(JSON.parse(readFileSync(SESSION_FILE, "utf-8")));
  return { map, ua: loadUa() };
}

// ── Tier 1: 创作者会话字段存在性 ─────────────────────────────────────────────

export function presenceCheckCreator(map: CookieMap): { ok: boolean; reason?: string; detail?: string } {
  const a1 = map["a1"];
  if (!a1?.value || expired(a1)) return { ok: false, reason: "missing/expired a1 (device fingerprint)" };
  const sessionKey = CREATOR_SESSION_KEYS.find((k) => map[k]?.value && !expired(map[k]));
  if (!sessionKey) return { ok: false, reason: `missing creator session cookie (none of ${CREATOR_SESSION_KEYS.join("|")})` };
  return { ok: true, detail: `a1+${sessionKey}` };
}

// ── Tier 2: 裸 GET personal_info ─────────────────────────────────────────────

export async function pingCreator(
  map: CookieMap,
  ua: string,
): Promise<{ ok: boolean; reason?: string; diagnosisStatus?: number; fansCount?: number }> {
  try {
    const resp = await fetch(PING_URL, {
      method: "GET",
      headers: {
        Cookie: cookieHeader(map),
        "User-Agent": ua,
        Referer: REFERER,
        Origin: "https://creator.xiaohongshu.com",
        Accept: "application/json, text/plain, */*",
      },
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok) return { ok: false, reason: `personal_info HTTP ${resp.status}` };
    const data = (await resp.json()) as {
      success?: boolean;
      code?: number;
      data?: { fans_count?: number; diagnosis_status?: number; name?: string };
    };
    if (data.success === true && data.code === 0) {
      return {
        ok: true,
        diagnosisStatus: data.data?.diagnosis_status,
        fansCount: data.data?.fans_count,
      };
    }
    return { ok: false, reason: `personal_info success=${data.success} code=${data.code}` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, reason: `personal_info error: ${msg.slice(0, 120)}` };
  }
}

export interface CreatorCheckResult {
  ok: boolean;
  error?: "SESSION_EXPIRED";
  reason?: string;
  detail?: string;
  ping?: "skipped" | "ok" | "fail";
  diagnosisStatus?: number;
  fansCount?: number;
}

/** 新鲜探活（给定 map，不读文件）——导出前验证用 */
export async function verifyCreator(map: CookieMap, opts: { noPing?: boolean } = {}): Promise<CreatorCheckResult> {
  const pres = presenceCheckCreator(map);
  if (!pres.ok) return { ok: false, error: "SESSION_EXPIRED", reason: pres.reason };
  if (opts.noPing) return { ok: true, detail: pres.detail, ping: "skipped" };
  const r = await pingCreator(map, loadUa());
  if (r.ok) return { ok: true, detail: pres.detail, ping: "ok", diagnosisStatus: r.diagnosisStatus, fansCount: r.fansCount };
  return { ok: false, error: "SESSION_EXPIRED", reason: r.reason, ping: "fail" };
}

/** 从中央存储读 + 探活——发布前探活用 */
export async function checkCreator(opts: { noPing?: boolean } = {}): Promise<CreatorCheckResult> {
  const loaded = loadCreatorSession();
  if (!loaded) return { ok: false, error: "SESSION_EXPIRED", reason: "login file not found" };
  const pres = presenceCheckCreator(loaded.map);
  if (!pres.ok) return { ok: false, error: "SESSION_EXPIRED", reason: pres.reason };
  if (opts.noPing) return { ok: true, detail: pres.detail, ping: "skipped" };
  const r = await pingCreator(loaded.map, loaded.ua);
  if (r.ok) return { ok: true, detail: pres.detail, ping: "ok", diagnosisStatus: r.diagnosisStatus, fansCount: r.fansCount };
  return { ok: false, error: "SESSION_EXPIRED", reason: r.reason, ping: "fail" };
}
