#!/usr/bin/env -S node --experimental-strip-types
/**
 * wx_mp_hunter.ts — WeChat Official Account Hunter CLI (TypeScript)
 *
 * 登录走 camoufox-cli + 持久化 session `wx_mp`（无头截 QR 登录），
 * 登录就位后导出 cookie + UA + token 落中央存储 `~/.openclaw/logins/wx_mp.json`
 * + `wx_mp.ua.json`，业务命令（search/account-posts/fetch）走 mpFetch 纯 HTTP，
 * cookie + token + UA 从中央存储读。
 * 探活（check）也走 mpFetch 纯 HTTP（wx_mp _ping：GET /cgi-bin/home 解析 <h2>），不起浏览器。
 *
 * Commands:
 *   check                          探活（HTTP _ping /cgi-bin/home 解析 <h2>）
 *   login                          无头截 QR 登录 → 导出 cookie+UA+token 落中央存储
 *   search <keyword>               搜索公众号
 *   account-posts <fakeid>         拉账号最新文章列表
 *   fetch <url>                    抓文章全文
 */

import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile, unlink } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { load as loadHtml } from "cheerio";
import { downloadImages, rewriteMarkdownImages } from "./download_images.ts";
type CookieMap = Record<string, string>;
type JsonMap = Record<string, unknown>;

/** 中央存储 session 文件格式（camoufox-cli cookies export 原生输出 + 扩展 token/ua） */
interface SessionData {
  platform: "wx_mp";
  /** camoufox-cli cookies export 原生输出 = Playwright add_cookies 格式 */
  cookies?: Array<{ name: string; value: string; domain?: string; path?: string }>;
  /** 公众号后台会话 token（登录后从 redirect_url 提取，业务命令调 API 必带） */
  token: string;
  /** UA（来自 wx_mp.ua.json 的 userAgent，同步注入 mpFetch 避免指纹错配） */
  ua?: string;
  updated_at?: string;
}

interface AccountEntry {
  fakeid: string;
  nickname: string;
  alias: string;
  signature: string;
  service_type: number;
  avatar: string;
  cached_at: string;
}

interface AccountsCache {
  by_fakeid: Record<string, AccountEntry>;
}

const MP_BASE = "https://mp.weixin.qq.com";
const LOGINS_DIR = join(homedir(), ".openclaw", "logins");
const SESSION_FILE = process.env.WX_SESSION_FILE ?? join(LOGINS_DIR, "wx_mp.json");
const UA_FILE = process.env.WX_UA_FILE ?? join(LOGINS_DIR, "wx_mp.ua.json");
const ACCOUNTS_CACHE_FILE = process.env.WX_ACCOUNTS_CACHE_FILE ?? `${homedir()}/.wx_mp_hunter_accounts.json`;
const QR_FILE = "/tmp/qr-wx-mp.png";
const CAMOUFOX_CLI = process.env.CAMOUFOX_CLI ?? "camoufox-cli";
const SESSION_NAME = "wx_mp";
// 登录 in-progress 标记：防 agent 因延迟重复调 login 再 open mp.weixin.qq.com/，
// 每次 open 都会刷新 scanloginqrcode 的 scene_id，把用户正在扫的旧 QR 作废
// （手机端提示「系统错误」）。REUSE_WINDOW 内重复 login 直接 re-screenshot 同一 scene。
const LOGIN_INPROGRESS_FILE = "/tmp/wx-mp-login-in-progress";
const LOGIN_QR_REUSE_WINDOW_MS = 30_000;
// login-confirm 轮询当前页等用户手机确认的最长时间。scanloginqrcode 页在用户
// 点「确认登录」后会自动 redirect 到 /cgi-bin/home?token=xxx，原地轮询即可，
// 不要再 open（open 会刷新 scene 作废 QR）。
const LOGIN_CONFIRM_POLL_MAX_MS = 150_000;
const LOGIN_CONFIRM_POLL_INTERVAL_MS = 3000;
const execFileAsync = promisify(execFile);

function timestampLocal(): string {
  const d = new Date();
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(
    d.getMinutes()
  )}:${pad(d.getSeconds())}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function printJson(data: unknown): void {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}

function errExit(msg: string, code = 1): never {
  printJson({ ok: false, error: msg });
  process.exit(code);
}

function authExit(msg: string): never {
  errExit(msg, 2);
}

async function readJsonFile<T>(filePath: string): Promise<T | null> {
  if (!existsSync(filePath)) return null;
  try {
    const raw = await readFile(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function writeJsonFile(filePath: string, data: unknown): Promise<void> {
  await mkdir(dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf-8");
}

function getSetCookieHeaders(headers: Headers): string[] {
  const maybeHeaders = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof maybeHeaders.getSetCookie === "function") {
    return maybeHeaders.getSetCookie();
  }

  const single = headers.get("set-cookie");
  if (!single) return [];

  // Fallback for combined set-cookie header.
  return single
    .split(/,(?=\s*[^;,\s]+=)/g)
    .map((part) => part.trim())
    .filter(Boolean);
}

function applySetCookies(cookieJar: CookieMap, setCookieHeaders: string[]): void {
  for (const header of setCookieHeaders) {
    const first = header.split(";")[0]?.trim();
    if (!first || !first.includes("=")) continue;

    const idx = first.indexOf("=");
    const name = first.slice(0, idx).trim();
    const value = first.slice(idx + 1).trim();

    if (!name) continue;
    if (!value || value.toUpperCase() === "EXPIRED") {
      delete cookieJar[name];
      continue;
    }
    cookieJar[name] = value;
  }
}

function cookieHeaderValue(cookieJar: CookieMap): string {
  return Object.entries(cookieJar)
    .filter(([, value]) => Boolean(value))
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
}

/** UA 默认值；requireSession 后被 session.ua 覆盖（同步指纹，避免错配风控） */
let CURRENT_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) " +
  "Chrome/117.0.0.0 Safari/537.36";

function defaultHeaders(): Record<string, string> {
  return {
    "User-Agent": CURRENT_UA,
    Referer: "https://mp.weixin.qq.com/",
    Origin: "https://mp.weixin.qq.com",
    "Accept-Encoding": "identity",
  };
}

interface MpFetchOptions {
  method: "GET" | "POST";
  endpoint: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  form?: Record<string, string | number | boolean>;
  cookieJar: CookieMap;
  timeoutMs?: number;
}

async function mpFetch(options: MpFetchOptions): Promise<Response> {
  const timeoutMs = options.timeoutMs ?? 15000;

  const url = new URL(options.endpoint);
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }

  const headers = new Headers(defaultHeaders());
  const cookieHeader = cookieHeaderValue(options.cookieJar);
  if (cookieHeader) headers.set("Cookie", cookieHeader);

  let body: URLSearchParams | undefined;
  if (options.method === "POST" && options.form) {
    body = new URLSearchParams();
    for (const [key, value] of Object.entries(options.form)) {
      body.set(key, String(value));
    }
  }

  const response = await fetch(url, {
    method: options.method,
    headers,
    body,
    signal: AbortSignal.timeout(timeoutMs),
  });

  applySetCookies(options.cookieJar, getSetCookieHeaders(response.headers));
  return response;
}

async function loadSession(): Promise<SessionData | null> {
  return readJsonFile<SessionData>(SESSION_FILE);
}

/** 读 UA 文件（camoufox-cli identity export 输出）；不存在回空串 */
async function loadUa(): Promise<string> {
  try {
    const data = await readJsonFile<{ userAgent?: string }>(UA_FILE);
    return data?.userAgent ?? "";
  } catch {
    return "";
  }
}

/** cookies 数组（camoufox-cli 原生格式）→ dict；兼容旧字符串格式 */
function cookieDictFromSession(data: SessionData): CookieMap {
  const dict: CookieMap = {};
  const raw = data.cookies;
  if (Array.isArray(raw)) {
    for (const c of raw) {
      if (c && typeof c.name === "string" && typeof c.value === "string") {
        dict[c.name] = c.value;
      }
    }
  }
  return dict;
}

// ── Accounts cache ─────────────────────────────────────────────────────────────

async function loadAccountsCache(): Promise<AccountsCache> {
  const data = await readJsonFile<AccountsCache>(ACCOUNTS_CACHE_FILE);
  return data ?? { by_fakeid: {} };
}

async function saveAccountsCache(cache: AccountsCache): Promise<void> {
  await writeJsonFile(ACCOUNTS_CACHE_FILE, cache);
}

function searchCachedAccounts(cache: AccountsCache, keyword: string): AccountEntry[] {
  const kw = keyword.toLowerCase();
  return Object.values(cache.by_fakeid).filter(
    (a) => a.nickname.toLowerCase().includes(kw) || a.alias.toLowerCase().includes(kw)
  );
}

async function mergeAccountsToCache(
  accounts: Omit<AccountEntry, "cached_at">[]
): Promise<void> {
  const cache = await loadAccountsCache();
  for (const account of accounts) {
    cache.by_fakeid[account.fakeid] = { ...account, cached_at: timestampLocal() };
  }
  await saveAccountsCache(cache);
}

// ── camoufox-cli 辅助 ──────────────────────────────────────────────────────────
//
// 登录走 camoufox-cli + 持久化 session `wx_mp`（无头模式）。
// 业务命令（search/account-posts/fetch）与探活（check）均走 mpFetch 纯 HTTP，
// cookie + token + UA 从中央存储 SESSION_FILE / UA_FILE 读。

/** camoufox-cli 调用封装：固定 --session wx_mp --persistent --json（默认即 headless） */
async function camoufox(...args: string[]): Promise<JsonMap> {
  const { stdout } = await execFileAsync(CAMOUFOX_CLI, [
    "--session", SESSION_NAME,
    "--persistent",
    "--json",
    ...args,
  ]);
  try {
    return JSON.parse(stdout) as JsonMap;
  } catch {
    errExit(`camoufox-cli 输出解析失败: ${stdout.slice(0, 200)}`);
  }
}

/** camoufox-cli eval 拿页面 URL，看是否跳 login。
 * eval 信封形如 {id, success, data: {result: "<href>"}}——值在 data.result。 */
async function camoufoxCurrentUrl(): Promise<string> {
  const r = await camoufox("eval", "window.location.href");
  const data = (r.data as JsonMap | undefined) ?? {};
  return String(data.result ?? "");
}

function checkRet(data: JsonMap): void {
  const baseResp = (data.base_resp as JsonMap | undefined) ?? {};
  const ret = Number(baseResp.ret ?? 0);
  if (ret === 200003) {
    authExit("SESSION_EXPIRED");
  }
  if (ret !== 0) {
    const msg = String(baseResp.err_msg ?? "未知错误");
    errExit(`API 错误 (ret=${ret}): ${msg}`);
  }
}

/**
 * wx_mp `_ping`——带 cookie+token GET 公众号后台首页，解析 <h2> 判登录态。
 * 借鉴 ~/wiseflow-pro/wiseflow4-pro/core/wis/wx_crawler.py _ping：
 *   GET /cgi-bin/home?t=home/index&lang=zh_CN&token=<token>
 *   <h2> 含「新的创作」→ 有效；含「请重新」/scanloginqrcode → 失效。
 * 纯 HTTP，不起 camoufox，不依赖磁盘 profile，与 fetch/search 走同一 mpFetch 通道。
 * cmdCheck（探活）与 cmdLoginConfirm（登录后验证）共用，避免两处判据漂移。
 * 不抛——返回 {ok, reason, h2}，调用方决定 exit。
 */
async function pingWxMp(data: SessionData): Promise<{ ok: boolean; reason?: string; h2?: string }> {
  if (!data.token) return { ok: false, reason: "missing token" };
  const cookieJar = cookieDictFromSession(data);
  if (Object.keys(cookieJar).length === 0) return { ok: false, reason: "empty cookie jar" };

  let resp: Response;
  try {
    resp = await mpFetch({
      method: "GET",
      endpoint: `${MP_BASE}/cgi-bin/home`,
      query: { t: "home/index", lang: "zh_CN", token: data.token },
      cookieJar,
      timeoutMs: 15000,
    });
  } catch (e) {
    return { ok: false, reason: `home fetch error: ${(e as Error).message.slice(0, 120)}` };
  }
  if (!resp.ok) return { ok: false, reason: `home HTTP ${resp.status}` };

  const html = await resp.text();
  // 抽 <h2>...</h2> 文本：登录有效页有「新的创作」；失效页提示「请重新登录」
  const h2Match = html.match(/<h2[^>]*>([\s\S]*?)<\/h2>/i);
  const h2 = h2Match ? h2Match[1].replace(/<[^>]+>/g, "").trim() : "";
  if (h2.includes("新的创作")) return { ok: true, h2 };
  if (h2.includes("请重新") || html.includes("请重新登录") || html.includes("scanloginqrcode")) {
    return { ok: false, reason: "home 页提示请重新登录", h2 };
  }
  // 兜底：没命中已知标志，按失效处理（避免误报有效）
  return { ok: false, reason: "home 页未出现「新的创作」标志", h2 };
}

/**
 * 探活：读中央存储 session → pingWxMp。
 * exit 0 = 有效；exit 2 = 失效（session 文件缺 / token 缺 / 服务端判未登录 / 网络错）
 */
async function cmdCheck(): Promise<void> {
  const data = await loadSession();
  if (!data) authExit("SESSION_EXPIRED");
  const r = await pingWxMp(data);
  if (r.ok) {
    printJson({ ok: true, message: "session 有效", ping: "home", h2: r.h2 });
    return;
  }
  authExit(`SESSION_EXPIRED (${r.reason})`);
}

/** 登录 in-progress 标记：{ opened_at, qr_path, keepalive_pid? }。login 写、login-confirm 成功后清。 */
interface LoginMarker {
  opened_at: number;
  qr_path: string;
  keepalive_pid?: number;
}

async function readLoginMarker(): Promise<LoginMarker | null> {
  return readJsonFile<LoginMarker>(LOGIN_INPROGRESS_FILE);
}

async function writeLoginMarker(openedAt: number, keepalivePid?: number): Promise<void> {
  const marker: LoginMarker = { opened_at: openedAt, qr_path: QR_FILE };
  if (keepalivePid) marker.keepalive_pid = keepalivePid;
  await writeJsonFile(LOGIN_INPROGRESS_FILE, marker);
}

/** keep-alive 脚本路径（与本文件同目录）。detached spawn，撑过扫码间隙的 60s daemon 空闲超时。 */
const KEEPALIVE_SCRIPT = join(dirname(new URL(import.meta.url).pathname), "wx_mp_keepalive.mjs");

/** detached spawn keep-alive：每 20s ping daemon 重置 idle timer，撑到 login-confirm 接管。 */
function spawnKeepalive(): number {
  const child = spawn(process.execPath, [KEEPALIVE_SCRIPT, SESSION_NAME, CAMOUFOX_CLI], {
    detached: true,
    stdio: "ignore",
  });
  child.unref();
  return child.pid ?? 0;
}

/** 杀 keep-alive（若还在）。吞错——进程已退或 pid 无效都忽略。 */
function killKeepalive(pid?: number): void {
  if (!pid) return;
  try { process.kill(pid, "SIGTERM"); } catch { /* 已退或无效，忽略 */ }
}

async function clearLoginMarker(): Promise<void> {
  // 清前先停 keep-alive，避免孤儿 ping 进程残留
  const marker = await readLoginMarker();
  killKeepalive(marker?.keepalive_pid);
  try { await unlink(LOGIN_INPROGRESS_FILE); } catch { /* 已不在，忽略 */ }
}

/**
 * 无头截 QR 登录流：camoufox-cli open 公众号首页 → screenshot 截 QR PNG。
 * agent 拿 QR_FILE 用 image 工具发用户扫码，用户回复「已扫码」后再调 cmdLoginConfirm。
 *
 * 幂等：REUSE_WINDOW 内重复调 login 不再 open（每次 open 会刷新 scanloginqrcode 的
 * scene_id 作废用户正在扫的 QR），直接 re-screenshot 同一 scene。screenshot 失败
 * （daemon/页面已挂）才回退 open 新 scene，并提示 agent 新 QR 已生成。
 */
async function cmdLoginQr(): Promise<void> {
  try {
    const marker = await readLoginMarker();
    const now = Date.now();
    const canReuse =
      marker && now - marker.opened_at < LOGIN_QR_REUSE_WINDOW_MS && marker.qr_path === QR_FILE;

    // 先杀上一轮残留 keep-alive（若有），避免多份 ping 进程并存
    killKeepalive(marker?.keepalive_pid);

    let openedAt = marker?.opened_at ?? 0;
    let regenerated = false;
    if (canReuse) {
      // 复用现有 scene：只 re-screenshot，不 open。screenshot 失败 → 回退 open 新 scene。
      try {
        await camoufox("screenshot", QR_FILE);
      } catch {
        await camoufox("open", `${MP_BASE}/`);
        await sleep(3000);
        await camoufox("screenshot", QR_FILE);
        openedAt = Date.now();
        regenerated = true;
      }
    } else {
      await camoufox("open", `${MP_BASE}/`);
      await sleep(3000);
      await camoufox("screenshot", QR_FILE);
      openedAt = Date.now();
    }
    // detached keep-alive：撑过「login 返回 → agent 发图 → 用户扫码 → login-confirm 起」
    // 这段无命令间隙的 60s daemon 空闲超时，否则浏览器死、scanloginqrcode 服务端轮询死、
    // 手机「确认登录」无落地（2026-07-19 13:11 扫码失败根因）。login-confirm 起后 kill 它。
    const keepalivePid = spawnKeepalive();
    await writeLoginMarker(openedAt, keepalivePid);
    // 不 close session——留着给 cmdLoginConfirm 继续用
    printJson({
      ok: true,
      qr_path: QR_FILE,
      regenerated,
      message: regenerated
        ? "原 QR scene 已失效（daemon/页面挂了），已重新生成新二维码，请用微信（公众号管理员账号）扫码新图，完成后运行 login-confirm"
        : "二维码已截，请用微信（公众号管理员账号）扫码，完成后运行 login-confirm",
    });
  } catch (e: any) {
    errExit(`camoufox-cli 截 QR 失败: ${e?.message ?? String(e)}`);
  }
}

/**
 * 登录确认：用户扫码完成后调此命令。
 * 原地轮询当前页 URL（login 留下的 scanloginqrcode 页）等手机确认 → 页面自动 redirect
 * 到 /cgi-bin/home?token=xxx → 提 token → cookies export + identity export 落中央存储。
 *
 * ⚠️ 不再 `open mp.weixin.qq.com/`：未登录态下 open 会刷新 scanloginqrcode 的 scene_id，
 * 把用户正在扫的 QR 作废（手机端「系统错误」）。这是 2026-07-19 07:36 扫码混乱的根因。
 */
async function cmdLoginConfirm(): Promise<void> {
  try {
    // 接管轮询前先停 keep-alive（login 起的 detached ping），避免与本轮 eval 并存。
    const marker = await readLoginMarker();
    killKeepalive(marker?.keepalive_pid);

    // 轮询当前页 URL，等用户手机点「确认登录」后 scanloginqrcode 页自动 redirect 到 home。
    let url = "";
    const deadline = Date.now() + LOGIN_CONFIRM_POLL_MAX_MS;
    while (Date.now() < deadline) {
      url = await camoufoxCurrentUrl();
      if (url.includes("/cgi-bin/home") && url.includes("token=")) break;
      // 还在 scanloginqrcode/login 页 = 用户还没确认，继续等
      await sleep(LOGIN_CONFIRM_POLL_INTERVAL_MS);
    }

    if (!url.includes("/cgi-bin/home") || !url.includes("token=")) {
      // 轮询超时仍没就位。最后再读一次 URL 给出明确诊断。
      const finalUrl = url || (await camoufoxCurrentUrl().catch(() => ""));
      if (!finalUrl) {
        // 空 URL = 浏览器/daemon 已挂（eval 连不上）。QR 已失效——浏览器死则 scanloginqrcode
        // 服务端轮询早死，手机「确认登录」无落地。不重试 open（会刷新 scene 作废），让 agent 重 login。
        await clearLoginMarker();
        errExit(`登录态未就位——浏览器/daemon 已挂（eval 返回空 URL）。QR 在扫码间隙被 60s 空闲超时回收而失效，手机「确认登录」无落地。请重新运行 login 获取新 QR（keep-alive 已加固，新 QR 会撑过扫码间隙）`);
      }
      if (finalUrl.includes("login") || finalUrl.includes("scanloginqrcode")) {
        errExit(`登录态未就位——轮询 ${LOGIN_CONFIRM_POLL_MAX_MS / 1000}s 仍在 scanloginqrcode 页，用户可能没扫码或没点手机端「确认登录」。请确认手机端已完成确认后重试 login-confirm（不会作废当前 QR）`);
      }
      errExit(`登录态未就位——当前页 URL 异常: ${finalUrl.slice(0, 200)}`);
    }

    // 提 token
    const token = new URL(url, MP_BASE).searchParams.get("token");
    if (!token) {
      errExit(`无法从 redirect URL 提取 token: ${url}`);
    }

    // 导出 cookies 到临时文件（不直接落中央存储——先 _ping 验过再 commit）
    const tmpCookies = "/tmp/wx-mp-login-cookies.json";
    await camoufox("cookies", "export", tmpCookies);

    // 读导出的 cookies + token 组 sessionData，先 _ping 验证再 commit
    // camoufox-cli `cookies export` 写的是裸数组（见 patches/camoufox-cli/src/commands.ts），
    // 兼容裸数组与 {cookies:[...]} 两种形状，否则 exported.cookies 为 undefined →
    // cookies 落空，search/account-posts 无 Cookie 必失败。
    const exported = await readJsonFile<
      SessionData["cookies"] | { cookies?: SessionData["cookies"]; updated_at?: string }
    >(tmpCookies);
    const exportedCookies: SessionData["cookies"] = Array.isArray(exported)
      ? exported
      : (exported?.cookies ?? []);
    const ua = await loadUa();
    const sessionData: SessionData = {
      platform: "wx_mp",
      cookies: exportedCookies,
      token,
      ua: ua || undefined,
      updated_at: timestampLocal(),
    };

    // 导出前验证：_ping 后台首页，确认 cookie+token 真能用，通过才 commit 中央存储。
    // 落实「验证后再导出」原则——_ping 不过说明 cookie/token 不完整或账号异常，
    // 不写中央存储（避免把失效 cookie 喂给下游），直接报错让 Agent 人工排查。
    // 不重试（登录本身已走浏览器，再试只会触风控）。
    const ping = await pingWxMp(sessionData);
    if (!ping.ok) {
      try { await camoufox("close"); } catch { /* 尽力关 session，忽略 */ }
      errExit(`登录后 _ping 验证失败：${ping.reason}（后台首页未返回「新的创作」，cookie 未落中央存储——请人工检查账号状态，不重试避免风控）`);
    }

    // 验过 → commit 中央存储：写 SESSION_FILE（含 token）+ identity export UA
    await writeJsonFile(SESSION_FILE, sessionData);
    await camoufox("identity", "export", UA_FILE);

    // close 掉无头浏览器——登录态已在磁盘 profile + 中央存储，不留进程占内存。
    // 下游（wx-mp-engagement / 业务命令）按需重起无头 session，profile 桥接登录态。
    try { await camoufox("close"); } catch { /* session 已退或卡死，忽略 */ }
    await clearLoginMarker();

    printJson({ ok: true, message: "登录成功，cookie + UA + token 已落中央存储（session 已关，登录态在磁盘 profile）", token, ping: "home", h2: ping.h2 });
  } catch (e: any) {
    errExit(`camoufox-cli 登录确认失败: ${e?.message ?? String(e)}`);
  }
}

/**
 * 读中央存储 session：cookie + token + UA。
 * UA 同步注入 CURRENT_UA（mpFetch defaultHeaders 用），避免指纹错配风控。
 * 不验 TTL——camoufox session 自管生命周期，token 失效由 API ret=200003 标记。
 * exit 2 = SESSION_FILE 不存在 / 缺 token → 调用方触发 cmdLoginQr 重登。
 */
async function requireSession(): Promise<SessionData> {
  const data = await loadSession();
  if (!data || !data.token) {
    authExit("SESSION_EXPIRED");
  }
  // UA 同步注入（中央存储 → 全局变量 → defaultHeaders → mpFetch）
  const ua = data.ua ?? await loadUa();
  if (ua) {
    CURRENT_UA = ua;
  }
  return data;
}

/** cookies 数组 → CookieMap（给 mpFetch cookieJar 用） */
function sessionCookieJar(data: SessionData): CookieMap {
  return cookieDictFromSession(data);
}

async function cmdSearch(keyword: string, begin: number, size: number): Promise<void> {
  // Check local cache first (only for first-page queries)
  if (begin === 0) {
    const cache = await loadAccountsCache();
    const cached = searchCachedAccounts(cache, keyword);
    if (cached.length > 0) {
      printJson({ total: cached.length, accounts: cached.slice(0, size) });
      return;
    }
  }

  const session = await requireSession();
  const cookieJar: CookieMap = sessionCookieJar(session);

  const resp = await mpFetch({
    method: "GET",
    endpoint: `${MP_BASE}/cgi-bin/searchbiz`,
    query: {
      action: "search_biz",
      begin,
      count: Math.min(size, 20),
      query: keyword,
      token: session.token,
      lang: "zh_CN",
      f: "json",
      ajax: 1,
    },
    cookieJar,
    timeoutMs: 15000,
  });

  const data = (await resp.json()) as JsonMap;
  checkRet(data);

  const list = Array.isArray(data.list) ? (data.list as JsonMap[]) : [];
  const accounts = list.map((item) => ({
    fakeid: String(item.fakeid ?? ""),
    nickname: String(item.nickname ?? ""),
    alias: String(item.alias ?? ""),
    signature: String(item.signature ?? ""),
    service_type: Number(item.service_type ?? 0),
    avatar: String(item.round_head_img ?? ""),
  }));

  // Persist results to local cache for future lookups
  if (accounts.length > 0) {
    await mergeAccountsToCache(accounts);
  }

  printJson({
    total: Number(data.total ?? 0),
    accounts,
  });
}

async function cmdArticles(fakeid: string, begin: number, size: number, keyword: string): Promise<void> {
  const session = await requireSession();
  const cookieJar: CookieMap = sessionCookieJar(session);
  const isSearch = Boolean(keyword);

  const resp = await mpFetch({
    method: "GET",
    endpoint: `${MP_BASE}/cgi-bin/appmsgpublish`,
    query: {
      sub: isSearch ? "search" : "list",
      search_field: isSearch ? "7" : "null",
      begin,
      count: Math.min(size, 20),
      query: keyword,
      fakeid,
      type: "101_1",
      free_publish_type: 1,
      sub_action: "list_ex",
      token: session.token,
      lang: "zh_CN",
      f: "json",
      ajax: 1,
    },
    cookieJar,
    timeoutMs: 15000,
  });

  const data = (await resp.json()) as JsonMap;
  checkRet(data);

  let publishPage: JsonMap = {};
  try {
    publishPage = JSON.parse(String(data.publish_page ?? "{}")) as JsonMap;
  } catch {
    publishPage = {};
  }

  const publishList = Array.isArray(publishPage.publish_list) ? (publishPage.publish_list as JsonMap[]) : [];
  const articles: JsonMap[] = [];

  for (const item of publishList) {
    try {
      const info = JSON.parse(String(item.publish_info ?? "{}")) as JsonMap;
      const appmsgex = Array.isArray(info.appmsgex) ? (info.appmsgex as JsonMap[]) : [];

      for (const msg of appmsgex) {
        articles.push({
          aid: msg.aid ?? null,
          title: msg.title ?? "",
          link: msg.link ?? "",
          digest: msg.digest ?? "",
          author: msg.author_name ?? "",
          create_time: msg.create_time ?? null,
          cover: msg.cover ?? "",
          item_show_type: msg.item_show_type ?? 0,
          is_deleted: msg.is_deleted ?? false,
        });
      }
    } catch {
      // skip invalid item
    }
  }

  printJson({
    total: Number(publishPage.total_count ?? 0),
    begin,
    size,
    articles,
  });
}

function normalizedText(value: string): string {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n");
}

function normalizeImgUrl(raw: string): string {
  if (!raw) return "";
  return raw.startsWith("//") ? `https:${raw}` : raw;
}

function cleanContentHtml($: ReturnType<typeof loadHtml>, $content: any): any {
  const $clone = $content.clone();

  // Remove noise: scripts, styles, hidden elements
  $clone.find(
    'script, style, [style*="display:none"], [style*="display: none"], [aria-hidden="true"], .rich_media_area_extra'
  ).remove();

  // Move data-src → src on images (WeChat lazy-loads; Turndown-style prep)
  $clone.find("img").each((_, el) => {
    const $img = $(el);
    const dataSrc = $img.attr("data-src");
    if (dataSrc) {
      const url = normalizeImgUrl(dataSrc);
      if (url) $img.attr("src", url);
    }
    // Strip style/event handler attributes
    for (const attr of ["style", "data-type", "data-ratio", "data-w", "data-copyright", "onclick", "onerror"]) {
      $img.removeAttr(attr);
    }
  });

  // Remove inline styles from all elements
  $clone.find("[style]").removeAttr("style");
  $clone.find("[class]").removeAttr("class");

  return $clone;
}

function htmlToMarkdown(html: string): string {
  let md = html;

  // -- Block elements (order: innermost-first to avoid interference) --

  // Images → ![](url)  (do this before links so <a><img></a> doesn't double-wrap)
  md = md.replace(/<img[^>]*?\ssrc="([^"]*)"[^>]*?>/gi, (_, url: string) => `\n\n![](${url})\n\n`);

  // Headings
  for (let i = 6; i >= 1; i--) {
    const re = new RegExp(`<h${i}[^>]*?>(.*?)<\\/h${i}>`, "gi");
    md = md.replace(re, (_, c: string) => `\n\n${"#".repeat(i)} ${c.trim()}\n\n`);
  }

  // Paragraphs
  md = md.replace(/<p[^>]*?>(.*?)<\/p>/gi, (_, c: string) => `\n\n${c}\n\n`);

  // Line breaks
  md = md.replace(/<br\s*\/?>/gi, "\n");

  // -- Inline formatting (innermost first) --

  // Bold + italic combined
  md = md.replace(/<(?:strong|b)>[\s]*<(?:em|i)>(.*?)<\/(?:em|i)>[\s]*<\/(?:strong|b)>/gi, "***$1***");
  // Em/italic (inner)
  md = md.replace(/<(?:em|i)[^>]*?>(.*?)<\/(?:em|i)>/gi, "*$1*");
  // Strong/bold (outer)
  md = md.replace(/<(?:strong|b)[^>]*?>(.*?)<\/(?:strong|b)>/gi, "**$1**");
  // Links (after inline formatting)
  md = md.replace(/<a[^>]*?\shref="([^"]*)"[^>]*?>(.*?)<\/a>/gi, "[$2]($1)");

  // Strip remaining tags and decode entities
  md = md.replace(/<[^>]+>/g, "");
  md = md.replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&nbsp;/g, " ");

  // Clean up whitespace
  md = md.split("\n").map((line) => line.trimEnd()).join("\n");
  md = md.replace(/\n{3,}/g, "\n\n").trim();

  return md;
}

async function cmdFetch(url: string, includeHtml: boolean, outputDir = "", downloadImgs = false): Promise<void> {
  const session = await requireSession();
  const cookieJar: CookieMap = sessionCookieJar(session);

  const resp = await mpFetch({
    method: "GET",
    endpoint: url,
    cookieJar,
    timeoutMs: 20000,
  });

  if (resp.status !== 200) {
    errExit(`HTTP ${resp.status}: ${url}`);
  }

  const html = await resp.text();
  const $ = loadHtml(html);

  const getText = (selector: string): string => normalizedText($(selector).first().text());

  const title = getText("#activity-name") || getText(".rich_media_title");
  const author = getText("#js_name");
  const publishTime = getText("#publish_time");

  const contentEl = $("#js_content").first();
  if (!contentEl.length) {
    errExit("未找到文章正文 (#js_content)");
  }

  const contentText = normalizedText(contentEl.text());

  // Build markdown: clean DOM, then convert to markdown with inline images
  const $clean = cleanContentHtml($, contentEl);
  const cleanHtml = $.html($clean) || "";
  const contentMarkdown = htmlToMarkdown(cleanHtml);

  // Extract image URLs from markdown (already normalized by cleanContentHtml)
  const images: string[] = [];
  const seen = new Set<string>();
  const imgRe = /!\[\]\(([^)]+)\)/g;
  let match: RegExpExecArray | null;
  while ((match = imgRe.exec(contentMarkdown)) !== null) {
    const url = match[1];
    if (url && !seen.has(url)) {
      seen.add(url);
      images.push(url);
    }
  }

  const result: JsonMap = {
    url,
    title,
    author,
    publish_time: publishTime,
    content_text: contentText,
    content_markdown: contentMarkdown,
    images,
  };

  if (includeHtml) {
    result.content_html = $.html(contentEl) || "";
  }

  // 图片本地化：--download-images 时并发下载到 <outputDir>/images/<hash>.<ext>，
  // content_markdown 里的图片 URL 替换为 images/<hash>.<ext> 本地相对路径。
  // 早期版本只解析了 flag 却没调 downloadImages → 参数失效，此处补回。
  if (downloadImgs && images.length) {
    const baseDir = outputDir || process.cwd();
    const imgDir = join(baseDir, "images");
    const dl = await downloadImages(images, { destDir: imgDir });
    const downloaded: string[] = [];
    const failed: string[] = [];
    for (const [u, r] of dl) {
      if (r.relPath) downloaded.push(`images/${r.relPath}`);
      else failed.push(u);
    }
    result.content_markdown = contentMarkdown.replace(
      /!\[[^\]]*\]\(([^)]+)\)/g,
      (full, u: string) => {
        const r = dl.get(u);
        return r && r.relPath ? full.replace(`(${u})`, `(images/${r.relPath})`) : full;
      },
    );
    result.images_local = downloaded;
    result.images_failed = failed;
  }

  printJson(result);
}

function usage(): void {
  const lines = [
    "WeChat Official Account Hunter — 微信公众号内容获取工具",
    "",
    "登录走 camoufox-cli + 持久化 session `wx_mp`（无头截 QR），",
    "登录就位后导出 cookie + UA + token 落 ~/.openclaw/logins/wx_mp.{json,ua.json}。",
    "探活（check）走 mpFetch 纯 HTTP（_ping /cgi-bin/home 解析 <h2>），不起浏览器。",
    "",
    "Usage:",
    "  node --experimental-strip-types wx_mp_hunter.ts check",
    "    探活（HTTP _ping /cgi-bin/home 解析 <h2>）；exit 0=有效 / 2=失效",
    "  node --experimental-strip-types wx_mp_hunter.ts login",
    "    无头截 QR 登录 → 导出 cookie+UA+token 落中央存储",
    "    （agent 拿 /tmp/qr-wx-mp.png 发用户扫码，用户回复「已扫码」后再 login-confirm）",
    "  node --experimental-strip-types wx_mp_hunter.ts login-confirm",
    "    验登录态就位 → 导出 cookie+UA+token 落中央存储",
    "  node --experimental-strip-types wx_mp_hunter.ts logout",
    "    拆 session（camoufox close）；不动中央存储文件",
    "  node --experimental-strip-types wx_mp_hunter.ts search <keyword> [--begin 0] [--size 10]",
    "  node --experimental-strip-types wx_mp_hunter.ts account-posts <fakeid> [--begin 0] [--size 20] [--keyword xxx]",
    "  node --experimental-strip-types wx_mp_hunter.ts fetch <url> [--html] [--download-images --output-dir <dir>]",
  ];
  process.stdout.write(`${lines.join("\n")}\n`);
}

function readNumberFlag(args: string[], flag: string, defaultValue: number): number {
  const idx = args.indexOf(flag);
  if (idx < 0 || idx + 1 >= args.length) return defaultValue;
  const value = Number(args[idx + 1]);
  return Number.isFinite(value) ? value : defaultValue;
}

function readStringFlag(args: string[], flag: string, defaultValue = ""): string {
  const idx = args.indexOf(flag);
  if (idx < 0 || idx + 1 >= args.length) return defaultValue;
  return args[idx + 1] ?? defaultValue;
}

async function main(): Promise<void> {
  const [command, ...args] = process.argv.slice(2);

  if (!command || command === "--help" || command === "-h") {
    usage();
    process.exit(0);
  }

  switch (command) {
    case "check": {
      await cmdCheck();
      break;
    }
    case "login": {
      await cmdLoginQr();
      break;
    }
    case "login-confirm": {
      await cmdLoginConfirm();
      break;
    }
    case "logout": {
      try {
        await camoufox("close");
        printJson({ ok: true, message: "session 已关闭（中央存储文件未动）" });
      } catch (e: any) {
        errExit(`camoufox close 失败: ${e?.message ?? String(e)}`);
      }
      break;
    }
    case "search": {
      const keyword = args[0];
      if (!keyword || keyword.startsWith("--")) errExit("缺少参数: keyword");
      const begin = readNumberFlag(args, "--begin", 0);
      const size = readNumberFlag(args, "--size", 10);
      await cmdSearch(keyword, begin, size);
      break;
    }
    case "account-posts":
    case "articles": {
      const fakeid = args[0];
      if (!fakeid || fakeid.startsWith("--")) errExit("缺少参数: fakeid");
      const begin = readNumberFlag(args, "--begin", 0);
      const size = readNumberFlag(args, "--size", 20);
      const keyword = readStringFlag(args, "--keyword", "");
      await cmdArticles(fakeid, begin, size, keyword);
      break;
    }
    case "fetch": {
      const url = args[0];
      if (!url || url.startsWith("--")) errExit("缺少参数: url");
      const includeHtml = args.includes("--html");
      const outputDir = readStringFlag(args, "--output-dir", "");
      const downloadImgs = args.includes("--download-images");
      await cmdFetch(url, includeHtml, outputDir, downloadImgs);
      break;
    }
    default: {
      errExit(`未知命令: ${command}`);
    }
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  errExit(message);
});
