#!/usr/bin/env -S node --experimental-strip-types
/**
 * session.ts — Read/write platform session files
 *
 * 中央存储格式（forked camoufox-cli 原生输出，= Playwright add_cookies 期望格式）：
 *   ~/.openclaw/logins/{platform}.json     → { platform, cookies: [{name, value, domain, ...}], updated_at }
 *   ~/.openclaw/logins/{platform}.ua.json  → { userAgent, platform, language, ... }
 * 本模块同时导入 cookie + UA（spec §4 原则 4）。
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs"
import { homedir } from "os"
import { join, dirname } from "path"

export type Platform = "douyin" | "bilibili" | "kuaishou" | "xhs" | "xhs-browse"

export interface CookieRecord { name: string; value: string; domain?: string }

export interface SessionData {
  platform: Platform
  /** camoufox-cli 原生格式：cookies 是对象数组；向后兼容旧字符串格式 */
  cookies?: CookieRecord[] | string
  /** 旧字段保留兼容；新格式下 UA 走独立 .ua.json 文件 */
  user_agent?: string
  updated_at?: string // ISO 8601
}

const SESSIONS_DIR = join(homedir(), ".openclaw", "logins")

function sessionPath(platform: Platform): string {
  return join(SESSIONS_DIR, `${platform}.json`)
}

function uaPath(platform: Platform): string {
  return join(SESSIONS_DIR, `${platform}.ua.json`)
}

export function readSession(platform: Platform): SessionData | null {
  const path = sessionPath(platform)
  if (!existsSync(path)) return null
  try {
    const raw = readFileSync(path, "utf-8")
    return JSON.parse(raw) as SessionData
  } catch {
    return null
  }
}

export function readUserAgent(platform: Platform): string {
  const path = uaPath(platform)
  if (!existsSync(path)) return ""
  try {
    const raw = readFileSync(path, "utf-8")
    const data = JSON.parse(raw) as { userAgent?: string }
    return data.userAgent || ""
  } catch {
    return ""
  }
}

export function writeSession(data: SessionData): void {
  mkdirSync(SESSIONS_DIR, { recursive: true })
  writeFileSync(sessionPath(data.platform), JSON.stringify(data, null, 2), "utf-8")
}

/** 把 cookies 字段统一展开成 dict（兼容新数组格式 + 旧字符串格式） */
export function cookieDict(data: SessionData): Record<string, string> {
  const dict: Record<string, string> = {}
  const raw = data.cookies
  if (Array.isArray(raw)) {
    for (const c of raw) {
      if (c && typeof c.name === "string" && typeof c.value === "string") {
        dict[c.name] = c.value
      }
    }
  } else if (typeof raw === "string" && raw) {
    for (const item of raw.split(";")) {
      const trimmed = item.trim()
      if (!trimmed || !trimmed.includes("=")) continue
      const [k, ...rest] = trimmed.split("=")
      dict[k.trim()] = rest.join("=").trim()
    }
  }
  return dict
}

/**
 * Read session or exit with code 2 (cookie invalid / not logged in).
 * The calling skill is expected to trigger login-manager on exit code 2.
 */
export function requireSession(platform: Platform): SessionData {
  const data = readSession(platform)
  if (!data || !data.cookies || (Array.isArray(data.cookies) && data.cookies.length === 0)) {
    process.stderr.write(
      JSON.stringify({ ok: false, error: "SESSION_EXPIRED", platform }) + "\n"
    )
    process.exit(2)
  }
  return data
}
