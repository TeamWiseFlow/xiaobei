#!/usr/bin/env -S node --experimental-strip-types
/**
 * xhs.ts — Xiaohongshu (小红书) API client
 *
 * 签名走 relay（/api/v1/sign/xhs/headers，xys 格式 + xRap），
 * client 拿签名 headers 后自行 fetch edith.xiaohongshu.com（client 端收尾）。
 * API reference: MediaCrawlerPro-Downloader DownloadServer/pkg/media_platform_api/xhs/
 * Video URL path: note_card.video.media.stream.h264[0].master_url
 *
 * Cookie source: xhs-browse（消费者域 www.xiaohongshu.com）
 */

import type { SessionData } from "../session.ts"
import { cookieDict } from "../session.ts"
import { xhsFetch } from "../../../_shared/relay-sign.ts"

const EDITH_BASE = "https://edith.xiaohongshu.com"
const DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

export interface VideoInfo {
  contentId: string
  title: string
  desc: string
  videoUrl: string
  coverUrl: string
  durationMs: number
  author: string
  stats: { playCount: number; likeCount: number; commentCount: number; collectCount: number; shareCount: number }
  mediaFormat?: string
}

// ── Feed API via relay 签名 ──────────────────────────────────────────────────

interface FeedItem {
  note_card?: {
    note_id?: string
    display_title?: string
    title?: string
    desc?: string
    type?: string  // "normal" = image post, "video" = video post
    user?: { nickname?: string }
    cover?: { url_default?: string; url?: string }
    interact_info?: {
      liked_count?: number
      comment_count?: number
      collected_count?: number
      share_count?: number
    }
    video?: {
      media?: { stream?: { h264?: Array<{ master_url?: string }> } }
      consumer?: { origin_video?: string }
      duration?: number | string
    }
  }
  note?: FeedItem["note_card"]
}

// ── Public API ─────────────────────────────────────────────────────────────

export async function getXhsVideo(
  noteId: string,
  session: SessionData,
  xsecToken: string = "",
  xsecSource: string = "",
): Promise<VideoInfo> {
  const dict = cookieDict(session)

  if (!dict.a1 || !dict.web_session) {
    throw new Error("小红书 cookie 缺少 a1 或 web_session，可能需要重新登录")
  }

  process.stderr.write(`[viral-chaser] XHS: 获取笔记详情 (noteId=${noteId})...\n`)

  const feedPayload: Record<string, unknown> = {
    source_note_id: noteId,
    image_formats: ["jpg", "webp", "avif"],
    extra: { need_body_topic: "1" },
  }
  if (xsecToken) {
    feedPayload.xsec_source = xsecSource || "pc_feed"
    feedPayload.xsec_token = xsecToken
  }

  const data = await xhsFetch<{ data?: { items?: FeedItem[] } }>({
    baseUrl: EDITH_BASE,
    uri: "/api/sns/web/v1/feed",
    method: "post",
    payload: feedPayload,
    cookies: dict,
    xsecToken: xsecToken || undefined,
    xsecSource: xsecSource || undefined,
    xRap: true,
  })

  const items = data?.data?.items ?? []
  let noteCard: FeedItem["note_card"] | undefined
  for (const it of items) {
    const nc = it.note_card ?? it.note ?? it
    if (nc && typeof nc === "object" && nc.note_id) {
      noteCard = nc
      break
    }
  }

  if (!noteCard) {
    throw new Error("note_card not found in feed response")
  }

  const noteType = noteCard.type ?? ""
  if (noteType !== "video") {
    throw new Error(
      `该小红书笔记是图文类型 (type=${noteType || "unknown"})，不含视频。` +
      `viral-chaser 仅支持视频笔记。`
    )
  }

  const ii = noteCard.interact_info ?? {}
  const videoInfo = noteCard.video ?? {}
  const media = videoInfo.media ?? {}
  const h264 = media.stream?.h264 ?? []

  let videoUrl = h264[0]?.master_url ?? ""
  if (!videoUrl) {
    videoUrl = videoInfo.consumer?.origin_video ?? ""
  }

  let durationMs = videoInfo.duration ?? 0
  if (typeof durationMs === "string") {
    try { durationMs = parseInt(durationMs, 10) || 0 }
    catch { durationMs = 0 }
  }

  if (!videoUrl) {
    throw new Error("未能从 feed 响应中提取视频下载地址（可能视频已删除或需要登录）")
  }

  process.stderr.write(
    `  ✓ 标题: ${String(noteCard.display_title || noteCard.title || "").slice(0, 40)}\n` +
    `  ✓ 视频URL: ${String(videoUrl).slice(0, 80)}...\n`,
  )

  return {
    contentId: noteId,
    title: noteCard.display_title || noteCard.title || "",
    desc: noteCard.desc || "",
    videoUrl,
    coverUrl: noteCard.cover?.url_default || noteCard.cover?.url || "",
    durationMs,
    author: noteCard.user?.nickname || "",
    stats: {
      playCount: 0,  // XHS 不返回笔记播放数
      likeCount: ii.liked_count ?? 0,
      commentCount: ii.comment_count ?? 0,
      collectCount: ii.collected_count ?? 0,
      shareCount: ii.share_count ?? 0,
    },
  }
}
