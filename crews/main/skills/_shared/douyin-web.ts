/**
 * douyin-web.ts — 抖音 web API 统一请求入口（a_bogus 走 relay）
 *
 * 抽自 viral-chaser platforms/douyin.ts，供 viral-chaser / published-track 共用。
 * 封装 COMMON_PARAMS + webid + msToken + verifyFp + fp + a_bogus 签名 + fetch，
 * 消费方只需给 uri / extraParams / cookieStr / ua。
 *
 * 关键：抖音 Janus 网关要求请求带全套 COMMON_PARAMS（device_platform / aid / channel /
 * version_code / browser_* / …）+ webid + verifyFp + fp，缺则 404 Unsupported path(Janus)
 * 或 200 空体。早期 published-track fetchDouyin 只发 aweme_id+msToken+a_bogus，故长期取不到数。
 */

import { douyinSign } from "./relay-sign.ts"

const DOUYIN_API = "https://www.douyin.com"
export const DOUYIN_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
const WEBID_URL = "https://mcs.zijieapi.com/webid?aid=6383&sdk_version=5.1.18_zip&device_platform=web"

// ─── Token helpers ──────────────────────────────────────────────────────────

// Douyin web detail endpoint accepts a random msToken. Real mssdk.bytedance.com
// signing (encrypted strData via mssdk wasm) is not implemented — the random token
// below is the intended path here, not a fallback.
export function genMsToken(_ua?: string): string {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
  let token = ""
  for (let i = 0; i < 126; i++) token += chars[Math.floor(Math.random() * chars.length)]
  return token + "=="
}

function genWebIdLocal(): string {
  function e(t?: number): string {
    if (t !== undefined) return String(t ^ (Math.floor(16 * Math.random()) >> (t / 4)))
    return "10000000-1000-4000-8000-100000000000"
  }
  return e().replace(/[018]/g, x => e(parseInt(x))).replace(/-/g, "").slice(0, 19)
}

export async function getWebId(ua: string): Promise<string> {
  try {
    const resp = await fetch(WEBID_URL, {
      method: "POST",
      headers: { "User-Agent": ua, "Content-Type": "application/json; charset=UTF-8", "Referer": "https://www.douyin.com/" },
      body: JSON.stringify({ app_id: 6383, referer: "https://www.douyin.com/", url: "https://www.douyin.com/", user_agent: ua, user_unique_id: "" }),
      signal: AbortSignal.timeout(5_000),
    })
    const data = await resp.json() as { web_id?: string }
    if (data.web_id) return data.web_id
  } catch { /* fallback */ }
  return genWebIdLocal()
}

export function genVerifyFp(): string {
  const base = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
  let ms = Date.now()
  let r = ""
  while (ms > 0) { const rem = ms % 36; r = (rem < 10 ? String(rem) : String.fromCharCode(87 + rem)) + r; ms = Math.floor(ms / 36) }
  const o = Array(36).fill("")
  o[8] = o[13] = o[18] = o[23] = "_"; o[14] = "4"
  for (let i = 0; i < 36; i++) if (!o[i]) { let n = Math.floor(Math.random() * 62); if (i === 19) n = (3 & n) | 8; o[i] = base[n] }
  return "verify_" + r + "_" + o.join("")
}

// ─── Common request params ──────────────────────────────────────────────────

export const COMMON_PARAMS: Record<string, string | number> = {
  device_platform: "webapp", aid: "6383", channel: "channel_pc_web",
  publish_video_strategy_type: 2, update_version_code: 170400, pc_client_type: 1,
  version_code: 170400, version_name: "17.4.0", cookie_enabled: "true",
  screen_width: 2560, screen_height: 1440, browser_language: "zh-CN",
  browser_platform: "MacIntel", browser_name: "Chrome", browser_version: "127.0.0.0",
  browser_online: "true", engine_name: "Blink", engine_version: "127.0.0.0",
  os_name: "Mac+OS", os_version: "10.15.7", cpu_core_num: 8, device_memory: 8,
  platform: "PC", downlink: 4.45, effective_type: "4g", round_trip_time: 100,
}

// ─── Signed GET（a_bogus 走 relay）──────────────────────────────────────────

export interface DouyinWebGetResult<T = unknown> {
  status: number
  ok: boolean
  data: T | null
  /** 原始响应体（JSON.parse 失败时用于诊断） */
  text: string
}

/**
 * 发起抖音 web API 签名 GET。
 * @param uri    路径，如 `/aweme/v1/web/aweme/detail/`
 * @param extraParams 业务参数，如 `{ aweme_id }` / `{ sec_uid, count, max_cursor }`
 * @param cookieStr   Cookie 头值（可空，但 detail/post 等接口无 cookie 多半 200 空体）
 * @param ua          User-Agent（缺省 DOUYIN_UA）
 */
export async function douyinWebGet<T = unknown>(
  uri: string,
  extraParams: Record<string, string | number>,
  cookieStr: string,
  ua: string = DOUYIN_UA,
): Promise<DouyinWebGetResult<T>> {
  const [msToken, webid, verifyFp] = await Promise.all([
    genMsToken(ua), getWebId(ua), Promise.resolve(genVerifyFp()),
  ])

  const allParams: Record<string, string> = {}
  for (const [k, v] of Object.entries({ ...COMMON_PARAMS, ...extraParams })) {
    allParams[k] = String(v)
  }
  allParams["webid"] = webid
  allParams["msToken"] = msToken
  allParams["verifyFp"] = verifyFp
  allParams["fp"] = verifyFp

  const queryString = new URLSearchParams(allParams).toString()
  const aBogus = await douyinSign({ queryString, postData: "", ua })
  allParams["a_bogus"] = aBogus

  const fullUrl = `${DOUYIN_API}${uri}?${new URLSearchParams(allParams).toString()}`

  const resp = await fetch(fullUrl, {
    headers: {
      "Cookie": cookieStr,
      "User-Agent": ua,
      "Referer": "https://www.douyin.com/",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "zh-CN,zh;q=0.9",
    },
    signal: AbortSignal.timeout(30_000),
  })
  const text = await resp.text()
  let data: T | null = null
  try { data = JSON.parse(text) as T } catch { /* 非 JSON，交消费方看 text */ }
  return { status: resp.status, ok: resp.ok, data, text }
}
