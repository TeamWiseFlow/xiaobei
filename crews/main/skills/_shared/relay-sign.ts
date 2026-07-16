/**
 * relay-sign.ts — client 侧调用 relay sign 服务的统一入口（TS）
 *
 * 平台规则：relay **只**算签名算法（xhs a_bogus / xsec_token / 抖音 _signature 等），
 * 实际平台调用（登录 / 抓取 / 互动 / 上传 / 发布）**必须 client 端完成**——不传 cookie 替 client
 * 调平台。本模块供 viral-chaser / xhs-content-ops / published-track / xhs-publish / 等共用。
 * RELAY_BASE_URL + OFB_KEY 由 entrypoint 从 daemon.env 注入。
 *
 * 端点对应 relay 仓 services/sign/：
 *   POST /api/v1/sign/xhs/headers  → 仅签名（返回完整 headers）
 *   POST /api/v1/sign/douyin        → 算 a_bogus
 *   POST /api/v1/sign/bilibili/wbi  → 算 WBI 签名 {wts, w_rid}（client 合并到原参数）
 *   xhsFetch(input)                  → 调 xhsHeaders 拿签名 + client 自己 fetch xhs.com（client 端收尾）
 */

// 默认指向官方中转 relay（VIP Club 会员默认走我们中转，零配置起手）。
// 仅当用户自建 relay 时才需要在 daemon.env 覆盖 RELAY_BASE_URL。
const RELAY_BASE_URL =
  process.env.RELAY_BASE_URL ?? "https://relay.openclaw-for-business.com";
const OFB_KEY = process.env.OFB_KEY;

function assertOfbKey(): string {
  if (!OFB_KEY) {
    throw new Error(
      "OFB_KEY 未配置。OFB_KEY 是 VIP Club 会员凭证，由 ofb 掌柜签发——请向 ofb 掌柜索取该 key，交由 IT engineer 写入 daemon.env 后重启实例。",
    );
  }
  return OFB_KEY;
}

interface RelayEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: Record<string, unknown>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const key = assertOfbKey();
  const resp = await fetch(`${RELAY_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-OFB-Key": key,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const env = (await resp.json()) as RelayEnvelope<T>;
  if (!resp.ok || !env.success) {
    throw new Error(`relay ${path} 失败 (${resp.status}): ${env.error ?? resp.statusText}`);
  }
  return env.data as T;
}

// ── 登录墙检测（借鉴 OpenCLI 229b3b0） ──────────────────────────────────────
//
// 期望 JSON 的平台 API 在 session 失效时可能返回 HTML 登录页（200 text/html 或 302→login）。
// 旧检测只匹配 `<!DOCTYPE`/`<!doctype`/`<html`/`<HTML` 几种大小写，漏 `<!Doctype`/`<Html`/`<HEAD`/
// `<body`/`<title` 等；这里用大小写不敏感正则，且覆盖 `<head`/`<body`/`<title` 开头（登录页常以
// `<head>` 起步）。命中 → 抛 LoginWallError（SESSION_EXPIRED），交下游脚本触发 login-manager
// 重登，而非让 resp.json() 抛 "Unexpected token <" 乱码错。
const HTML_LOGIN_WALL_RE = /^<(?:!doctype|html|head|body|title)(?:[\s>/]|$)/i;

/** 平台返回 HTML 登录墙（期望 JSON）。下游脚本应捕获并触发 login-manager 重登。 */
export class LoginWallError extends Error {
  readonly platform: string;
  constructor(platform: string, uri: string) {
    super(`SESSION_EXPIRED: ${platform} 返回 HTML 登录墙（期望 JSON）@ ${uri}`);
    this.name = "LoginWallError";
    this.platform = platform;
  }
}

// ── xhs ─────────────────────────────────────────────────────────────────────

export interface XhsSignInput {
  uri: string;
  method?: "get" | "post";
  payload?: Record<string, unknown>;
  params?: Record<string, unknown>;
  cookies: Record<string, string>;
  signFormat?: string;
  xRap?: boolean;
}

export interface XhsFetchInput extends XhsSignInput {
  /** xhs API base URL（发布域 edith.xiaohongshu.com / 消费者域 www.xiaohongshu.com） */
  baseUrl: string;
  xsecToken?: string;
  xsecSource?: string;
  /** 单次请求超时（ms），默认 30s */
  timeoutMs?: number;
}

/** 仅签名，返回完整 headers（含 Cookie / UA / 签名头），client 自行发请求 */
export async function xhsHeaders(input: XhsSignInput): Promise<Record<string, string>> {
  const data = await postJson<{ headers: Record<string, string> }>(
    "/api/v1/sign/xhs/headers",
    {
      uri: input.uri,
      method: input.method ?? "post",
      payload: input.payload ?? {},
      params: input.params ?? {},
      cookies: input.cookies,
      sign_format: input.signFormat ?? "xys",
      x_rap: Boolean(input.xRap),
    },
  );
  return data.headers
}

/**
 * 签名 + client 自己 fetch xhs.com。
 * 替代旧 `xhsProxy`（relay 端 fetch，已删除避免误用导致 cookie 复用 + 封号风险）。
 */
export async function xhsFetch<T = unknown>(input: XhsFetchInput): Promise<T> {
  const { baseUrl, uri, method = "post", params = {}, payload, cookies, xsecToken, xsecSource, xRap, timeoutMs = 30_000 } = input;

  // 1) 拿签名 headers（signFormat 透传）。xhs 两套独立 x-s 算法（见 relay services/sign/xhs.js）：
  //    - "xys"（默认，XYS_）→ note 创建 / feed / comment / search 等通用 endpoint
  //    - "xyw"（XYW_）→ data-fetching API：user/me、user_posted、otherinfo
  //      （这些 endpoint 自 ~2026-03 起对 xys 返回 HTTP 406，必须用 xyw）
  const headers = await xhsHeaders({ uri, method, payload, params, cookies, signFormat: input.signFormat, xRap });

  // 2) xsec_token / xsec_source 拼到 URL（xhs 协议）
  const allParams: Record<string, string> = {};
  for (const [k, v] of Object.entries(params)) allParams[k] = String(v);
  if (xsecToken) allParams["xsec_token"] = xsecToken;
  if (xsecSource) allParams["xsec_source"] = xsecSource;

  const qs = new URLSearchParams(allParams).toString();
  const url = `${baseUrl.replace(/\/$/, "")}${uri}${qs ? "?" + qs : ""}`;

  // 3) client 自己 fetch（带 cookie + 签名头 + 可选 body）
  const reqHeaders: Record<string, string> = { ...headers };
  if (cookies && Object.keys(cookies).length) {
    reqHeaders["Cookie"] = Object.entries(cookies)
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  }
  if (method.toLowerCase() !== "get" && payload) {
    reqHeaders["Content-Type"] ??= "application/json";
  }

  const resp = await fetch(url, {
    method: method.toUpperCase(),
    headers: reqHeaders,
    body: method.toLowerCase() === "get" ? undefined : JSON.stringify(payload),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`xhs ${method.toUpperCase()} ${uri} 失败 (${resp.status}): ${text.slice(0, 200)}`);
  }
  // 登录墙检测：期望 JSON，若拿到 HTML 登录页 → LoginWallError（SESSION_EXPIRED）。
  // 读一次 text 复用：先查 content-type + HTML 开头，再 JSON.parse，parse 失败再查一次 HTML。
  const contentType = (resp.headers.get("content-type") ?? "").toLowerCase();
  const body = await resp.text().catch(() => "");
  const head = body.trimStart().slice(0, 256);
  const looksLikeHtml = contentType.includes("text/html") || HTML_LOGIN_WALL_RE.test(head);
  if (looksLikeHtml) {
    throw new LoginWallError("xhs", `${method.toUpperCase()} ${uri}`);
  }
  try {
    return JSON.parse(body) as T;
  } catch {
    if (HTML_LOGIN_WALL_RE.test(head)) {
      throw new LoginWallError("xhs", `${method.toUpperCase()} ${uri}`);
    }
    throw new Error(`xhs ${method.toUpperCase()} ${uri} 返回非 JSON: ${body.slice(0, 200)}`);
  }
}

// ── douyin ──────────────────────────────────────────────────────────────────

export interface DouyinSignInput {
  queryString: string;
  postData?: string;
  ua?: string;
}

/** 算 a_bogus（relay 子进程隔离 vendor），client 自行拼 URL 发请求 */
export async function douyinSign(input: DouyinSignInput): Promise<string> {
  const data = await postJson<{ a_bogus: string }>("/api/v1/sign/douyin", {
    queryString: input.queryString,
    postData: input.postData ?? "",
    ua: input.ua,
  });
  return data.a_bogus
}

// ── bilibili ─────────────────────────────────────────────────────────────────

export interface BilibiliWbiSignInput {
  /** 待签字段（业务参数，不含 wts/w_rid）；relay 会加 wts 后算 w_rid */
  params: Record<string, string | number>;
  /** nav 拉 imgKey（client 负责 nav 拉取 + 缓存） */
  imgKey: string;
  /** nav 拉 subKey（client 负责 nav 拉取 + 缓存） */
  subKey: string;
}

/**
 * 算 WBI 签名 {wts, w_rid}（relay 只签字段，不拉 nav）。
 * client 拿到后合并到原 params 拼 URL 发请求。imgKey/subKey 拉取与缓存归 client。
 * （契约 docs/API-CONTRACT.md §sign/bilibili/wbi）
 */
export async function bilibiliWbiSign(input: BilibiliWbiSignInput): Promise<{ wts: string; w_rid: string }> {
  const data = await postJson<{ wts: string; w_rid: string }>("/api/v1/sign/bilibili/wbi", {
    params: input.params,
    imgKey: input.imgKey,
    subKey: input.subKey,
  });
  return { wts: String(data.wts), w_rid: data.w_rid }
}

export { RELAY_BASE_URL };
