#!/usr/bin/env -S node --experimental-strip-types
/**
 * douyin.ts — Douyin (抖音) API client
 *
 * 签名走 relay（/api/v1/sign/douyin，算 a_bogus，relay 子进程隔离 vendor）。
 * client 自带 msToken/webid/verifyFp，拼 URL 后自行发请求。
 * API reference: MediaCrawlerPro-Downloader DownloadServer/pkg/media_platform_api/douyin/
 */

import type { SessionData } from "../session.ts"
import { cookieDict, readUserAgent } from "../session.ts"

const DOUYIN_API = "https://www.douyin.com"
const DOUYIN_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
const WEBID_URL = "https://mcs.zijieapi.com/webid?aid=6383&sdk_version=5.1.18_zip&device_platform=web"

export interface VideoInfo {
  contentId: string
  title: string
  desc: string
  videoUrl: string
  coverUrl: string
  durationMs: number
  author: string
  stats: { playCount: number; likeCount: number; commentCount: number }
}

// ── Token helpers ──────────────────────────────────────────────────────────

// Douyin web detail endpoint accepts a random msToken. Real mssdk.bytedance.com
// signing (encrypted strData via mssdk wasm) is not implemented — the random token
// below is the intended path here, not a fallback.
function getMsToken(_ua: string): string {
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

async function getWebId(ua: string): Promise<string> {
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

function genVerifyFp(): string {
  const base = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
  let ms = Date.now()
  let r = ""
  while (ms > 0) { const rem = ms % 36; r = (rem < 10 ? String(rem) : String.fromCharCode(87 + rem)) + r; ms = Math.floor(ms / 36) }
  const o = Array(36).fill("")
  o[8] = o[13] = o[18] = o[23] = "_"; o[14] = "4"
  for (let i = 0; i < 36; i++) if (!o[i]) { let n = Math.floor(Math.random() * 62); if (i === 19) n = (3 & n) | 8; o[i] = base[n] }
  return "verify_" + r + "_" + o.join("")
}

// ── Common request params ──────────────────────────────────────────────────

const COMMON_PARAMS: Record<string, string | number> = {
  device_platform: "webapp", aid: "6383", channel: "channel_pc_web",
  publish_video_strategy_type: 2, update_version_code: 170400, pc_client_type: 1,
  version_code: 170400, version_name: "17.4.0", cookie_enabled: "true",
  screen_width: 2560, screen_height: 1440, browser_language: "zh-CN",
  browser_platform: "MacIntel", browser_name: "Chrome", browser_version: "127.0.0.0",
  browser_online: "true", engine_name: "Blink", engine_version: "127.0.0.0",
  os_name: "Mac+OS", os_version: "10.15.7", cpu_core_num: 8, device_memory: 8,
  platform: "PC", downlink: 4.45, effective_type: "4g", round_trip_time: 100,
}

// ── Signed GET request（a_bogus 走 relay）──────────────────────────────────

async function douyinGet(
  uri: string,
  extraParams: Record<string, string | number>,
  session: SessionData,
): Promise<unknown> {
  const ua = readUserAgent(session.platform) || DOUYIN_UA
  const [msToken, webid, verifyFp] = await Promise.all([
    getMsToken(ua), getWebId(ua), Promise.resolve(genVerifyFp()),
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
  const { douyinSign } = await import("../../../_shared/relay-sign.ts")
  const aBogus = await douyinSign({ queryString, postData: "", ua })
  allParams["a_bogus"] = aBogus

  const fullUrl = `${DOUYIN_API}${uri}?${new URLSearchParams(allParams).toString()}`

  const dict = cookieDict(session)
  const cookieStr = Object.entries(dict).map(([k, v]) => `${k}=${v}`).join("; ")

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

  if (!resp.ok) throw new Error(`Douyin API ${resp.status}: ${resp.statusText}`)
  return resp.json()
}

// ── Video detail ───────────────────────────────────────────────────────────

export async function getDouyinVideo(awemeId: string, session: SessionData): Promise<VideoInfo> {
  const data = await douyinGet("/aweme/v1/web/aweme/detail/", { aweme_id: awemeId }, session) as Record<string, any>

  const detail = data?.aweme_detail
  if (!detail) throw new Error(`抖音 API 未返回视频详情，可能 cookie 已失效`)

  const video = detail.video ?? {}
  const urlList: string[] = (
    video.play_addr_h264?.url_list ??
    video.play_addr_256?.url_list ??
    video.play_addr?.url_list ??
    []
  )
  const videoUrl = urlList[1] ?? urlList[0] ?? ""

  const coverList: string[] = (
    video.raw_cover?.url_list ??
    video.origin_cover?.url_list ??
    []
  )
  const coverUrl = coverList[1] ?? coverList[0] ?? ""

  const stats = detail.statistics ?? {}

  return {
    contentId: awemeId,
    title: detail.desc ?? "",
    desc: detail.desc ?? "",
    videoUrl,
    coverUrl,
    durationMs: (video.duration ?? 0),
    author: detail.author?.nickname ?? "",
    stats: {
      playCount: stats.play_count ?? 0,
      likeCount: stats.digg_count ?? 0,
      commentCount: stats.comment_count ?? 0,
    },
  }
}
