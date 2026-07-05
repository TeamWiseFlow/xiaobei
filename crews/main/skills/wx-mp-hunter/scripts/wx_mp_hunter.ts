#!/usr/bin/env -S node --experimental-strip-types
/**
 * wx_mp_hunter.ts — WeChat Official Account Hunter CLI (TypeScript)
 *
 * Login flow (requires user scan):
 *   Step 1: node --experimental-strip-types wx_mp_hunter.ts login-qr
 *   Step 2: node --experimental-strip-types wx_mp_hunter.ts login-confirm
 *
 * Other commands (after login):
 *   node --experimental-strip-types wx_mp_hunter.ts search <keyword>
 *   node --experimental-strip-types wx_mp_hunter.ts account-posts <fakeid>
 *   node --experimental-strip-types wx_mp_hunter.ts fetch <url>
 */

import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { load as loadHtml } from "cheerio";
import { downloadImages, rewriteMarkdownImages } from "./download_images.ts";
type CookieMap = Record<string, string>;
type JsonMap = Record<string, unknown>;

interface SessionData {
  token: string;
  cookies: CookieMap;
  created_at: string;
}

interface PendingData {
  sid: string;
  cookies: CookieMap;
  created_at: string;
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

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) " +
  "Chrome/117.0.0.0 Safari/537.36 WAE/1.0";
const MP_BASE = "https://mp.weixin.qq.com";
const LOGINS_DIR = join(homedir(), ".openclaw", "logins");
const SESSION_FILE = process.env.WX_SESSION_FILE ?? join(LOGINS_DIR, "wx_mp.json");
const ACCOUNTS_CACHE_FILE = process.env.WX_ACCOUNTS_CACHE_FILE ?? `${homedir()}/.wx_mp_hunter_accounts.json`;
const PENDING_FILE = "/tmp/wx_mp_hunter_pending.json";
const QR_FILE = "/tmp/wx_mp_qr.png";

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

const SESSION_TTL_MS = 4 * 24 * 60 * 60 * 1000; // 4 days

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

function defaultHeaders(): Record<string, string> {
  return {
    "User-Agent": USER_AGENT,
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

async function saveSession(token: string, cookies: CookieMap): Promise<void> {
  await writeJsonFile(SESSION_FILE, {
    token,
    cookies,
    created_at: timestampLocal(),
  } satisfies SessionData);
}

async function loadPending(): Promise<PendingData | null> {
  return readJsonFile<PendingData>(PENDING_FILE);
}

async function savePending(sid: string, cookies: CookieMap): Promise<void> {
  await writeJsonFile(PENDING_FILE, {
    sid,
    cookies,
    created_at: timestampLocal(),
  } satisfies PendingData);
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

async function cmdLoginQr(): Promise<void> {
  const cookieJar: CookieMap = {};
  const sid = randomUUID().replace(/-/g, "");

  const startResp = await mpFetch({
    method: "POST",
    endpoint: `${MP_BASE}/cgi-bin/bizlogin`,
    query: { action: "startlogin" },
    form: {
      userlang: "zh_CN",
      redirect_url: "",
      login_type: 3,
      sessionid: sid,
      token: "",
      lang: "zh_CN",
      f: "json",
      ajax: 1,
    },
    cookieJar,
    timeoutMs: 15000,
  });

  let startBody: JsonMap = {};
  try {
    startBody = (await startResp.json()) as JsonMap;
  } catch {
    errExit(`startlogin 响应解析失败 (HTTP ${startResp.status})`);
  }

  const startRet = Number((startBody.base_resp as JsonMap | undefined)?.ret ?? 0);
  if (startRet !== 0) {
    const msg = String((startBody.base_resp as JsonMap | undefined)?.err_msg ?? "未知错误");
    errExit(`startlogin 失败 (ret=${startRet}): ${msg}`);
  }

  const qrResp = await mpFetch({
    method: "GET",
    endpoint: `${MP_BASE}/cgi-bin/scanloginqrcode`,
    query: {
      action: "getqrcode",
      random: Date.now(),
    },
    cookieJar,
    timeoutMs: 15000,
  });

  if (!qrResp.ok) {
    errExit(`获取二维码失败 (HTTP ${qrResp.status})`);
  }

  const qrBuffer = Buffer.from(await qrResp.arrayBuffer());
  if (qrBuffer.length === 0) {
    const logicRet = qrResp.headers.get("logicret") ?? qrResp.headers.get("LogicRet") ?? "unknown";
    errExit(`二维码内容为空 (logicret=${logicRet})`);
  }

  await writeFile(QR_FILE, qrBuffer);
  await savePending(sid, cookieJar);

  // 不自动打开图片，agent 通过 qr_path / qr_base64 传递给用户
  printJson({
    ok: true,
    qr_path: QR_FILE,
    qr_base64: qrBuffer.toString("base64"),
    message: "二维码已保存，请用微信（公众号管理员账号）扫码，完成后运行 login-confirm",
  });
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

async function cmdLoginConfirm(timeoutSeconds: number): Promise<void> {
  const pending = await loadPending();
  if (!pending) {
    errExit("未找到待确认的登录状态，请先运行 login-qr");
  }

  const cookieJar: CookieMap = { ...pending.cookies };
  const deadline = Date.now() + timeoutSeconds * 1000;
  let lastStatus = -1;

  process.stderr.write("[INFO] 等待扫码...\n");

  while (Date.now() < deadline) {
    const askResp = await mpFetch({
      method: "GET",
      endpoint: `${MP_BASE}/cgi-bin/scanloginqrcode`,
      query: {
        action: "ask",
        token: "",
        lang: "zh_CN",
        f: "json",
        ajax: 1,
      },
      cookieJar,
      timeoutMs: 10000,
    });

    let askBody: JsonMap = {};
    try {
      askBody = (await askResp.json()) as JsonMap;
    } catch {
      errExit(`轮询响应解析失败 (HTTP ${askResp.status})`);
    }

    const askRet = Number(((askBody.base_resp as JsonMap | undefined) ?? {}).ret ?? 0);
    if (askRet !== 0) {
      const msg = String(((askBody.base_resp as JsonMap | undefined) ?? {}).err_msg ?? "");
      errExit(`轮询失败 (ret=${askRet}): ${msg}`);
    }

    const status = Number(askBody.status ?? 0);
    if (status === 1) {
      process.stderr.write("[INFO] 已确认，正在完成登录...\n");
      break;
    }
    if ((status === 4 || status === 6) && lastStatus !== status) {
      process.stderr.write("[INFO] 已扫码，请在手机上点击确认...\n");
    }
    if (status === 2 || status === 3) {
      errExit("二维码已过期，请重新运行 login-qr");
    }
    if (status === 5) {
      errExit("该账号尚未绑定邮箱，无法扫码登录");
    }

    lastStatus = status;
    await sleep(2000);
  }

  if (Date.now() >= deadline) {
    errExit(`等待超时（${timeoutSeconds}s），请重新运行 login-qr`);
  }

  const loginResp = await mpFetch({
    method: "POST",
    endpoint: `${MP_BASE}/cgi-bin/bizlogin`,
    query: { action: "login" },
    form: {
      userlang: "zh_CN",
      redirect_url: "",
      cookie_forbidden: 0,
      cookie_cleaned: 0,
      plugin_used: 0,
      login_type: 3,
      token: "",
      lang: "zh_CN",
      f: "json",
      ajax: 1,
    },
    cookieJar,
    timeoutMs: 15000,
  });

  let loginBody: JsonMap = {};
  try {
    loginBody = (await loginResp.json()) as JsonMap;
  } catch {
    errExit(`登录响应解析失败 (HTTP ${loginResp.status})`);
  }

  const redirectUrl = String(loginBody.redirect_url ?? "");
  if (!redirectUrl) {
    errExit(`登录失败，未获取到 redirect_url: ${JSON.stringify(loginBody)}`);
  }

  const token = new URL(redirectUrl, "https://mp.weixin.qq.com").searchParams.get("token");
  if (!token) {
    errExit(`无法从 redirect_url 提取 token: ${redirectUrl}`);
  }

  await saveSession(token, cookieJar);
  await unlink(PENDING_FILE).catch(() => undefined);

  printJson({ ok: true, message: "登录成功，session 已保存" });
}

async function requireSession(): Promise<SessionData> {
  const data = await loadSession();
  if (!data) {
    authExit("SESSION_EXPIRED");
  }
  const age = Date.now() - new Date(data.created_at).getTime();
  if (age > SESSION_TTL_MS) {
    authExit("SESSION_EXPIRED");
  }
  return data;
}

async function cmdCheckSession(): Promise<void> {
  const data = await loadSession();
  if (!data) {
    authExit("SESSION_EXPIRED");
  }
  const age = Date.now() - new Date(data.created_at).getTime();
  if (age > SESSION_TTL_MS) {
    authExit("SESSION_EXPIRED");
  }
  printJson({ ok: true, message: "session 有效" });
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
  const cookieJar: CookieMap = { ...session.cookies };

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
  const cookieJar: CookieMap = { ...session.cookies };
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
  const cookieJar: CookieMap = { ...session.cookies };

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

  printJson(result);
}

function usage(): void {
  const lines = [
    "WeChat Official Account Hunter — 微信公众号内容获取工具",
    "",
    "Usage:",
    "  node --experimental-strip-types wx_mp_hunter.ts login-qr",
    "  node --experimental-strip-types wx_mp_hunter.ts login-confirm [--timeout 300]",
    "  node --experimental-strip-types wx_mp_hunter.ts search <keyword> [--begin 0] [--size 10]",
    "  node --experimental-strip-types wx_mp_hunter.ts account-posts <fakeid> [--begin 0] [--size 20] [--keyword xxx]",
    "  node --experimental-strip-types wx_mp_hunter.ts fetch <url> [--html]",
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
    case "check-session": {
      await cmdCheckSession();
      break;
    }
    case "login-qr": {
      await cmdLoginQr();
      break;
    }
    case "login-confirm": {
      const timeout = readNumberFlag(args, "--timeout", 300);
      await cmdLoginConfirm(timeout);
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
