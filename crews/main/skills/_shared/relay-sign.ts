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
 *   xhsFetch(input)                  → 调 xhsHeaders 拿签名 + client 自己 fetch xhs.com（client 端收尾）
 * todo: 这里还缺一个bilibili签名接口，后续需要加上
 */

const RELAY_BASE_URL =
  process.env.RELAY_BASE_URL ?? "http://localhost:3020";
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

  // 1) 拿签名 headers（signFormat 透传：xys 默认，xyw 用于 user/me 等 data API）
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
  return (await resp.json()) as T
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

export { RELAY_BASE_URL };
