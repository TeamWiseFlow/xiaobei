/**
 * download_images.ts — 公众号文章图片本地化（借鉴 wechat-article-exporter）
 *
 * 输入：image URL 列表 + 目标目录
 * 输出：下载到 <destDir>/<index>.<ext>，返回 URL → 相对路径映射
 *
 * 设计：
 * - 并发 4（避免触发微信风控）
 * - 单图失败重试 1 次（容忍偶发 5xx）
 * - 跳过 data: URI（已内联）
 * - 跳过 5xx 3 次以上
 * - 写文件 atomic（.tmp + rename）
 *
 * 依赖：Node 18+ stdlib（fetch / URL / crypto），无 npm 依赖
 */

import { writeFile, mkdir } from "fs/promises"
import { extname, join, resolve } from "path"
import { createHash } from "crypto"

const DEFAULT_CONCURRENCY = 4
const DEFAULT_MAX_BYTES = 5 * 1024 * 1024      // 5MB 单图上限
const DEFAULT_TOTAL_BYTES = 100 * 1024 * 1024  // 100MB 总上限
const DEFAULT_RETRIES = 1
const DEFAULT_TIMEOUT_MS = 20000

export interface DownloadOptions {
  destDir: string
  concurrency?: number
  maxBytesPerImage?: number
  maxTotalBytes?: number
  retries?: number
  timeoutMs?: number
}

export interface ImageResult {
  url: string
  /** 本地绝对路径 */
  path: string | null
  /** 相对 destDir 的路径，用于 markdown 替换 */
  relPath: string | null
  bytes: number
  /** 失败原因；null = 成功 */
  error: string | null
}

const EXT_BY_MIME: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/png": ".png",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "image/svg+xml": ".svg",
  "image/bmp": ".bmp",
}

function pickExt(url: string, mime: string | null): string {
  if (mime && EXT_BY_MIME[mime]) return EXT_BY_MIME[mime]
  try {
    const u = new URL(url)
    const pathname = u.pathname.toLowerCase()
    for (const e of [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"]) {
      if (pathname.endsWith(e)) return e === ".jpeg" ? ".jpg" : e
    }
  } catch {}
  return ".jpg"
}

function safeName(url: string, ext: string): string {
  const h = createHash("sha1").update(url).digest("hex").slice(0, 12)
  return `${h}${ext}`
}

async function downloadOne(
  url: string,
  destAbsDir: string,
  opts: Required<Omit<DownloadOptions, "destDir">>,
): Promise<ImageResult> {
  if (url.startsWith("data:")) {
    return { url, path: null, relPath: null, bytes: 0, error: "data:uri-skipped" }
  }
  let lastErr: string | null = null
  for (let attempt = 0; attempt <= opts.retries; attempt++) {
    try {
      const ctl = new AbortController()
      const t = setTimeout(() => ctl.abort(), opts.timeoutMs)
      const resp = await fetch(url, { signal: ctl.signal })
      clearTimeout(t)
      if (!resp.ok) {
        lastErr = `HTTP ${resp.status}`
        continue
      }
      const cl = Number(resp.headers.get("content-length") ?? 0)
      if (cl > opts.maxBytesPerImage) {
        return { url, path: null, relPath: null, bytes: 0, error: `too-large(${cl})` }
      }
      const buf = new Uint8Array(cl || 0)
      const total = cl || 0
      const chunks: Uint8Array[] = []
      let len = 0
      const reader = resp.body?.getReader()
      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          len += value.byteLength
          if (len > opts.maxBytesPerImage) {
            return { url, path: null, relPath: null, bytes: 0, error: "too-large(stream)" }
          }
          chunks.push(value)
        }
      }
      const data = new Uint8Array(len)
      let off = 0
      for (const c of chunks) { data.set(c, off); off += c.byteLength }
      const mime = resp.headers.get("content-type")
      const ext = pickExt(url, mime)
      const name = safeName(url, ext)
      const absPath = join(destAbsDir, name)
      const relPath = name
      const tmp = absPath + ".tmp"
      await writeFile(tmp, data)
      const { rename } = await import("fs/promises")
      await rename(tmp, absPath)
      return { url, path: absPath, relPath, bytes: len || total, error: null }
    } catch (e) {
      lastErr = (e as Error).message ?? String(e)
    }
  }
  return { url, path: null, relPath: null, bytes: 0, error: lastErr }
}

async function runWithPool<T, R>(items: T[], pool: number, fn: (it: T) => Promise<R>): Promise<R[]> {
  const results: R[] = []
  let i = 0
  const workers = Array.from({ length: Math.min(pool, items.length) }, async () => {
    while (i < items.length) {
      const idx = i++
      results[idx] = await fn(items[idx])
    }
  })
  await Promise.all(workers)
  return results
}

/** 批量下载。返回 URL → 结果映射（无下载成功的 URL result.path = null） */
export async function downloadImages(
  urls: string[],
  options: DownloadOptions,
): Promise<Map<string, ImageResult>> {
  const absDir = resolve(options.destDir)
  await mkdir(absDir, { recursive: true })

  const opts = {
    concurrency: options.concurrency ?? DEFAULT_CONCURRENCY,
    maxBytesPerImage: options.maxBytesPerImage ?? DEFAULT_MAX_BYTES,
    maxTotalBytes: options.maxTotalBytes ?? DEFAULT_TOTAL_BYTES,
    retries: options.retries ?? DEFAULT_RETRIES,
    timeoutMs: options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  }

  // 去重 + 过滤 data: URI
  const uniq: string[] = []
  const seen = new Set<string>()
  for (const u of urls) {
    if (!seen.has(u) && !u.startsWith("data:")) {
      seen.add(u)
      uniq.push(u)
    }
  }

  // 总字节守门
  let totalBytes = 0
  const limited: typeof uniq = []
  for (const u of uniq) {
    if (totalBytes > opts.maxTotalBytes) break
    limited.push(u)
  }

  const results = await runWithPool(limited, opts.concurrency, (u) => downloadOne(u, absDir, opts))
  for (const r of results) totalBytes += r.bytes
  return new Map(results.map((r) => [r.url, r]))
}

/** 替换 markdown 中 image 链接为相对路径（已下载成功的） */
export function rewriteMarkdownImages(
  markdown: string,
  results: Map<string, ImageResult>,
): string {
  return markdown.replace(/!\[[^\]]*\]\(([^)]+)\)/g, (full, url: string) => {
    const r = results.get(url)
    if (!r || !r.relPath) return full
    return full.replace(`(${url})`, `(${r.relPath})`)
  })
}
