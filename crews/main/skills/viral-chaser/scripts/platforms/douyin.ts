#!/usr/bin/env -S node --experimental-strip-types
/**
 * douyin.ts — Douyin (抖音) API client
 *
 * 签名 + COMMON_PARAMS + webid/msToken/verifyFp 拼装抽到 _shared/douyin-web.ts，
 * 供 viral-chaser / published-track 共用（详见该文件注释）。
 * API reference: MediaCrawlerPro-Downloader DownloadServer/pkg/media_platform_api/douyin/
 */

import type { SessionData } from "../session.ts"
import { cookieDict, readUserAgent } from "../session.ts"
import { douyinWebGet, DOUYIN_UA } from "../../../_shared/douyin-web.ts"

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

// ── Signed GET request（a_bogus + COMMON_PARAMS 走 _shared）────────────────

async function douyinGet(
  uri: string,
  extraParams: Record<string, string | number>,
  session: SessionData,
): Promise<unknown> {
  const ua = readUserAgent(session.platform) || DOUYIN_UA
  const dict = cookieDict(session)
  const cookieStr = Object.entries(dict).map(([k, v]) => `${k}=${v}`).join("; ")

  const { status, ok, data, text } = await douyinWebGet<unknown>(uri, extraParams, cookieStr, ua)
  if (!ok) throw new Error(`Douyin API ${status}: ${text.slice(0, 120) || "HTTP error"}`)
  if (data == null) throw new Error(`Douyin API ${status} 返回非 JSON: ${text.slice(0, 120)}`)
  return data
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
