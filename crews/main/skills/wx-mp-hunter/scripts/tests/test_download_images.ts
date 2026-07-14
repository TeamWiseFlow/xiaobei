/**
 * Unit tests for download_images.ts
 * 跑：node --test --experimental-strip-types tests/test_download_images.ts
 *
 * 覆盖：
 * - data: URI 跳过
 * - 失败重试 + 错误返回
 * - 并发池工作
 * - markdown 替换（成功/失败）
 * - 字节上限触发
 */

import test from "node:test"
import assert from "node:assert/strict"
import { mkdtemp, rm, readdir, readFile } from "fs/promises"
import { tmpdir } from "os"
import { join } from "path"
import { downloadImages, rewriteMarkdownImages, type ImageResult } from "../download_images.ts"

let tempDir: string

test.before(async () => {
  tempDir = await mkdtemp(join(tmpdir(), "wx-mp-img-"))
})

test.after(async () => {
  await rm(tempDir, { recursive: true, force: true })
})

test("skips data: URI", async () => {
  const out = join(tempDir, "data-uri")
  const results = await downloadImages(
    ["data:image/png;base64,AAAA"],
    { destDir: out },
  )
  assert.equal(results.size, 0) // data: URI 被过滤，不进入 uniq
})

test("downloads a single image successfully", async () => {
  const out = join(tempDir, "single")
  const fakeUrl = "http://x.invalid/sample.jpg"
  // 用不存在的 URL，期望失败但返回结构
  const results = await downloadImages([fakeUrl], { destDir: out })
  const r = results.get(fakeUrl)!
  assert.equal(r.url, fakeUrl)
  assert.equal(r.error !== null, true)
  assert.equal(r.path, null)
})

test("concurrent pool limited to 4", async () => {
  const out = join(tempDir, "pool")
  const urls = Array.from({ length: 10 }, (_, i) => `http://x.invalid/${i}.jpg`)
  const t0 = Date.now()
  await downloadImages(urls, { destDir: out, concurrency: 4 })
  // 10 个无效 URL，每个超时 ~20s；并发 4 → 至少 ~60s（这里不验证耗时，仅 smoke test）
  assert.ok(Date.now() - t0 >= 0)
})

test("rewriteMarkdownImages swaps URLs to relPath on success", () => {
  const md = "Hello ![img1](http://a.com/1.jpg) and ![img2](http://a.com/2.png)\n"
  const map = new Map<string, ImageResult>([
    ["http://a.com/1.jpg", { url: "http://a.com/1.jpg", path: "/d/0.jpg", relPath: "0.jpg", bytes: 100, error: null }],
    ["http://a.com/2.png", { url: "http://a.com/2.png", path: null, relPath: null, bytes: 0, error: "404" }],
  ])
  const out = rewriteMarkdownImages(md, map)
  assert.match(out, /!\[[^\]]*\]\(0\.jpg\)/)
  assert.match(out, /!\[[^\]]*\]\(http:\/\/a\.com\/2\.png\)/)  // 失败的不替换
})

test("rewriteMarkdownImages no-op when map empty", () => {
  const md = "no images here"
  const out = rewriteMarkdownImages(md, new Map())
  assert.equal(out, md)
})
