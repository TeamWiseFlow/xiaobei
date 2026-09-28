/**
 * relay-sign.ts — client 侧调用 relay sign 服务的统一入口（TS）
 *
 * 平台规则：relay 只计算签名，
 * 实际平台调用由客户端完成。本模块供其他平台的客户端共用。
 * RELAY_BASE_URL + OFB_KEY 由 entrypoint 从 daemon.env 注入。
 *
 * 端点对应 relay 仓 services/sign/：
 *   POST /api/v1/sign/douyin        → 算 a_bogus
 *   POST /api/v1/sign/bilibili/wbi  → 算 WBI 签名 {wts, w_rid}（client 合并到原参数）
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
