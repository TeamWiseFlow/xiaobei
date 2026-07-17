#!/usr/bin/env -S node --experimental-strip-types
/**
 * xhs.ts — Xiaohongshu (小红书) 视频笔记取数
 *
 * 走 SSR HTML 路线（get_note_by_id_from_html）：GET 笔记详情页 HTML，
 * 解析 og:meta + window.__INITIAL_STATE__ 拿 title/cover/videoUrl/duration/互动计数。
 * 详见 _shared/xhs-html-note.ts。
 *
 * 为何不走 feed API（/api/sns/web/v1/feed）：feed 需 xRap relay 签名 + 极易 406/500/滑块，
 * 且探活（user/me）通过不代表 feed 签名路径被接受（不同端点/签名/方法，风控敏感度不同），
 * 会出现「探活绿、feed 红」假绿。HTML 路线是真实页面导航，风控远低；带 xsec_token 的公开
 * 视频笔记无 cookie 也能 SSR——viral-chaser 输入是分享链接（自带 xsec_token），故默认无 cookie。
 *
 * Cookie：可选回退。无 cookie 抓不到（滑块/空页）时，若调用方提供 xhs-browse session，
 * 用同指纹 UA + cookie 重试一次。无 xsec_token 直接报错（viral-chaser 只吃分享链接）。
 */

import type { SessionData } from "../session.ts"
import { cookieDict, readUserAgent } from "../session.ts"
import {
  fetchXhsNoteFromHtml,
  XhsCaptchaError,
  XhsNoteInaccessibleError,
} from "../../../_shared/xhs-html-note.ts"

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

const XHS_BROWSE_PLATFORM = "xhs-browse"

function cookieStrFromSession(session: SessionData | null | undefined): string {
  if (!session) return ""
  const dict = cookieDict(session)
  return Object.entries(dict).map(([k, v]) => `${k}=${v}`).join("; ")
}

// ── Public API ─────────────────────────────────────────────────────────────

export async function getXhsVideo(
  noteId: string,
  xsecToken: string,
  xsecSource: string = "",
  session?: SessionData | null,
): Promise<VideoInfo> {
  if (!xsecToken) {
    throw new Error(
      "小红书需要带 xsec_token 的分享链接。viral-chaser 不支持裸 noteId——" +
        "请把完整分享链接（xhslink.com 或 www.xiaohongshu.com/explore/...?xsec_token=...）整条传入。",
    )
  }

  process.stderr.write(`[viral-chaser] XHS: GET 笔记详情页 HTML (noteId=${noteId})...\n`)

  // 1. 无 cookie 优先（公开笔记带 xsec_token 即可 SSR，风控最低）
  let note
  try {
    note = await fetchXhsNoteFromHtml(noteId, { xsecToken, xsecSource })
  } catch (e) {
    if (e instanceof XhsCaptchaError) {
      // 滑块：有 cookie 就用同指纹 cookie 重试一次，否则直接抛
      if (!session) throw e
      process.stderr.write("[viral-chaser] XHS: 无 cookie 命中滑块，用 xhs-browse cookie 重试...\n")
      note = await fetchXhsNoteFromHtml(noteId, {
        xsecToken,
        xsecSource,
        cookieStr: cookieStrFromSession(session),
        ua: readUserAgent(XHS_BROWSE_PLATFORM),
      })
    } else if (e instanceof XhsNoteInaccessibleError) {
      // 无 cookie 抓不到：有 cookie 就回退重试，否则抛
      if (!session) throw e
      process.stderr.write("[viral-chaser] XHS: 无 cookie 未取到数据，用 xhs-browse cookie 回退...\n")
      note = await fetchXhsNoteFromHtml(noteId, {
        xsecToken,
        xsecSource,
        cookieStr: cookieStrFromSession(session),
        ua: readUserAgent(XHS_BROWSE_PLATFORM),
      })
    } else {
      throw e
    }
  }

  if (note.type && note.type !== "video") {
    throw new Error(
      `该小红书笔记是图文类型 (type=${note.type})，不含视频。` +
        "viral-chaser 仅支持视频笔记。",
    )
  }

  if (!note.videoUrl) {
    throw new Error("未能从笔记页提取视频下载地址（可能视频已删除或需要登录）")
  }

  process.stderr.write(
    `  ✓ 标题: ${note.title.slice(0, 40)}\n` +
      `  ✓ 视频URL: ${note.videoUrl.slice(0, 80)}...\n`,
  )

  return {
    contentId: noteId,
    title: note.title,
    desc: note.desc,
    videoUrl: note.videoUrl,
    coverUrl: note.coverUrl,
    durationMs: note.durationMs,
    author: note.author,
    stats: {
      playCount: 0, // XHS 不返回笔记播放数
      likeCount: note.stats.likeCount,
      commentCount: note.stats.commentCount,
      collectCount: note.stats.collectCount,
      shareCount: note.stats.shareCount,
    },
  }
}
