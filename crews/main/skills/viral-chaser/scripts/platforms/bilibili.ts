#!/usr/bin/env -S node --experimental-strip-types
/**
 * bilibili.ts — Bilibili (B站) API client
 *
 * WBI 签名走 relay（/api/v1/sign/bilibili/wbi，仅算 {wts, w_rid}），
 * imgKey/subKey 拉取与缓存归 client（契约 docs/API-CONTRACT.md §sign/bilibili/wbi）。
 * API reference: MediaCrawlerPro-Downloader DownloadServer/pkg/media_platform_api/bilibili/
 */

import type { SessionData } from "../session.ts"
import { cookieDict, readUserAgent } from "../session.ts"

const BILI_API = "https://api.bilibili.com"
const BILI_INDEX = "https://www.bilibili.com"
const BILI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

export interface VideoInfo {
  contentId: string
  title: string
  desc: string
  videoUrl: string
  audioUrl: string          // separate audio stream (DASH), may be empty for durl
  coverUrl: string
  durationSeconds: number
  author: string
  bvid: string
  aid: number
  cid: number
  mediaFormat: "DASH" | "MP4"
  stats: { viewCount: number; likeCount: number; coinCount: number }
}

// ── WBI key 拉取 + 缓存（归 client，relay 不拉 nav）──────────────────────────

let wbiKeyCache: { imgKey: string; subKey: string; ts: number } | null = null

async function getWbiKeys(session: SessionData): Promise<{ imgKey: string; subKey: string }> {
  if (wbiKeyCache && Date.now() - wbiKeyCache.ts < 10 * 60 * 1000) {
    return { imgKey: wbiKeyCache.imgKey, subKey: wbiKeyCache.subKey }
  }

  const resp = await fetch(`${BILI_API}/x/web-interface/nav`, {
    headers: biliHeaders(session),
    signal: AbortSignal.timeout(10_000),
  })

  if (!resp.ok) throw new Error(`获取 WBI 密钥失败: ${resp.status}`)
  const data = await resp.json() as Record<string, any>
  const wbiImg = data?.data?.wbi_img
  if (!wbiImg) throw new Error("WBI 密钥字段不存在")

  function keyFromUrl(url: string): string {
    return url.split("/").pop()?.replace(/\.[^.]+$/, "") ?? ""
  }

  const imgKey = keyFromUrl(wbiImg.img_url)
  const subKey = keyFromUrl(wbiImg.sub_url)
  wbiKeyCache = { imgKey, subKey, ts: Date.now() }
  return { imgKey, subKey }
}

// ── HTTP helpers ───────────────────────────────────────────────────────────

function biliHeaders(session: SessionData): Record<string, string> {
  const dict = cookieDict(session)
  const cookieStr = Object.entries(dict).map(([k, v]) => `${k}=${v}`).join("; ")
  return {
    "Cookie": cookieStr,
    "User-Agent": readUserAgent(session.platform) || BILI_UA,
    "Referer": BILI_INDEX,
    "Origin": BILI_INDEX,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
  }
}

async function biliGet(
  path: string,
  params: Record<string, string | number>,
  session: SessionData,
  sign = false,
): Promise<Record<string, any>> {
  let finalParams = params

  if (sign) {
    const { bilibiliWbiSign } = await import("../../../_shared/relay-sign.ts")
    const { imgKey, subKey } = await getWbiKeys(session)
    const { wts, w_rid } = await bilibiliWbiSign({ params, imgKey, subKey })
    finalParams = { ...params, wts, w_rid }
  }

  const url = `${BILI_API}${path}?${new URLSearchParams(
    Object.fromEntries(Object.entries(finalParams).map(([k, v]) => [k, String(v)]))
  ).toString()}`

  const resp = await fetch(url, {
    headers: biliHeaders(session),
    signal: AbortSignal.timeout(20_000),
  })

  if (!resp.ok) throw new Error(`Bilibili API ${resp.status}: ${resp.statusText}`)
  const data = await resp.json() as Record<string, any>

  if (data.code !== 0) {
    if (data.code === -101) throw new Error("B站 cookie 已失效，请重新登录")
    if (data.code === -404) return {}
    throw new Error(`Bilibili API 错误 ${data.code}: ${data.message}`)
  }

  return data.data ?? {}
}

// ── Video detail ───────────────────────────────────────────────────────────

export async function getBilibiliVideo(bvid: string, session: SessionData): Promise<VideoInfo> {
  // Step 1: Get video info (no WBI sign required)
  const videoInfo = await biliGet("/x/web-interface/wbi/view", { bvid }, session, false)

  if (!videoInfo.bvid) {
    throw new Error(`B站视频不存在或 cookie 已失效: ${bvid}`)
  }

  const aid: number = videoInfo.aid
  const cid: number = videoInfo.cid
  const title: string = videoInfo.title ?? ""
  const desc: string = videoInfo.desc ?? ""
  const coverUrl: string = videoInfo.pic ?? ""
  const durationSeconds: number = videoInfo.duration ?? 0
  const author: string = videoInfo.owner?.name ?? ""
  const stats = videoInfo.stat ?? {}

  // Step 2: Get play URL (WBI sign required), request 480P MP4 format
  const playData = await biliGet("/x/player/wbi/playurl", {
    avid: aid,
    cid,
    qn: 32,      // 480P (falls back to available quality)
    fnval: 1,    // Legacy MP4 (durl format, single file)
    fnver: 0,
    fourk: 0,
    platform: "pc",
  }, session, true)

  let videoUrl = ""
  let audioUrl = ""
  let mediaFormat: "DASH" | "MP4" = "MP4"

  const durl = playData.durl as Array<Record<string, any>> | undefined
  const dash = playData.dash as Record<string, any> | undefined

  if (durl && durl.length > 0) {
    // Legacy MP4 format
    videoUrl = durl[0].url ?? ""
    mediaFormat = "MP4"
  } else if (dash) {
    // DASH format — pick lowest quality video + best audio
    mediaFormat = "DASH"
    const videoStreams = (dash.video as Array<Record<string, any>> | undefined) ?? []
    const audioStreams = (dash.audio as Array<Record<string, any>> | undefined) ?? []

    if (videoStreams.length > 0) {
      videoStreams.sort((a, b) => (a.id ?? 0) - (b.id ?? 0))  // lowest quality first
      videoUrl = videoStreams[0].baseUrl ?? videoStreams[0].base_url ?? ""
    }
    if (audioStreams.length > 0) {
      audioStreams.sort((a, b) => (b.id ?? 0) - (a.id ?? 0))  // highest quality first
      audioUrl = audioStreams[0].baseUrl ?? audioStreams[0].base_url ?? ""
    }
  }

  return {
    contentId: bvid,
    title, desc, videoUrl, audioUrl, coverUrl,
    durationSeconds, author, bvid, aid, cid, mediaFormat,
    stats: {
      viewCount: stats.view ?? 0,
      likeCount: stats.like ?? 0,
      coinCount: stats.coin ?? 0,
    },
  }
}
