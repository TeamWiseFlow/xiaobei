#!/usr/bin/env -S node --experimental-strip-types
/**
 * fetch-xhs-with-xsec.ts — 小红书取数闭环脚本（含 xsec_token 映射获取）
 *
 * 把「拿 user_id + navigate profile 页 + eval flatten JS 取映射 + 调 feed 抓数 + 写库」
 * 整段封进去，避免 agent 手动编排浏览器多步（spec §9 重构目标）。
 *
 * 流程（脚本内闭环，不靠 agent 手动编排）：
 *   1. 查 pub_xhs 行拿 publish_url → 提 note_id
 *   2. camoufox-cli open xhs-browse session 探活（失效 exit 2）
 *   3. 拿 self user_id（优先读 xhs-user-id.cache，无则调 get-xhs-user-id.sh）
 *   4. camoufox-cli open profile 页 + eval flatten JS 拿 note_id → xsec_token 映射
 *      （映射里找不到某 note_id 时向下滚动加载更多，最多 3 屏）
 *   5. 按行 note_id 查映射拿 xsec_token/xsec_source
 *   6. 调 fetch-retro-data.ts 抓 feed
 *   7. 解析结果 → 调 update-metrics.sh 写库
 *   8. 输出统一 JSON {ok, method, platform, content_id, metrics_params}
 *
 * Usage:
 *   node --experimental-strip-types fetch-xhs-with-xsec.ts --id <rowid>
 *
 * Exit codes:
 *   0  成功或 fetch 返回 ok:false（NOTE_INACCESSIBLE 等），stdout 输出 JSON
 *   1  一般错误（参数错、DB 错、camoufox-cli 不在等）
 *   2  SESSION_EXPIRED（xhs-browse 登录态失效）——心跳就跳过该平台
 */

import { execFileSync } from "child_process"
import { existsSync, readFileSync } from "fs"
import { join } from "path"

// ─── 常量 ────────────────────────────────────────────────────────────────────

const ROOT = join(import.meta.dirname, "../../..")
const DB = join(ROOT, "db", "published_track.db")
const SCRIPT_DIR = import.meta.dirname
const CACHE_FILE = join(ROOT, "skills", "published-track", "xhs-user-id.cache")

const CAMOUFOX_CLI = process.env.CAMOUFOX_CLI || "camoufox-cli"
const SESSION = "xhs-browse"
const PLATFORM_HOME = "https://www.xiaohongshu.com/"
const PROFILE_BASE = "https://www.xiaohongshu.com/user/profile/"

// 小红书 pub_xhs 表里可被 update-metrics.sh 写入的互动指标列名
// fetch-retro-data.ts 的 fetchXhs 返回 stats 字段名 → DB 列名映射
const XHS_METRIC_MAP: Record<string, string> = {
  likeCount: "likes",
  collectCount: "favorites",
  commentCount: "comments",
  shareCount: "shares",
}

// flatten __INITIAL_STATE__.user.notes 取 note_id → xsec_token 映射的 JS
// （从 HEARTBEAT.md 2026-06-29 验证可用的那段 CDP JS 移植过来）
const FLATTEN_JS = `(() => {
  const unref = v => (v && v.__v_isRef && v._rawValue !== undefined) ? v._rawValue : v;
  const notes = unref(window.__INITIAL_STATE__?.user?.notes);
  const map = {};
  if (Array.isArray(notes)) {
    for (const grp of notes) {
      const g = unref(grp);
      if (!Array.isArray(g)) continue;
      for (const n of g) {
        const nn = unref(n);
        const nid = nn.id, tok = nn.xsecToken;
        if (nid && tok) map[nid] = { xsec_token: tok, xsec_source: nn.xsecSource || "" };
      }
    }
  }
  return JSON.stringify(map);
})()`

// ─── 辅助 ───────────────────────────────────────────────────────────────────

function errJson(obj: Record<string, unknown>): void {
  process.stdout.write(JSON.stringify(obj) + "\n")
}

function die(obj: Record<string, unknown>, code = 1): never {
  errJson(obj)
  process.exit(code)
}

/** 同步跑 camoufox-cli，返回 stdout（去末尾换行） */
function camoufox(args: string[]): string {
  try {
    return execFileSync(CAMOUFOX_CLI, args, { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim()
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    // camoufox-cli 失败一般是 session 没起或命令错——视作 SESSION 失效或一般错
    if (/session|login|expired|no profile/i.test(msg)) {
      die({ ok: false, error: "CAMOUFOX_CLI_FAILED", msg, hint: "camoufox-cli 调用失败，可能是 session 损坏" }, 1)
    }
    die({ ok: false, error: "CAMOUFOX_CLI_FAILED", msg }, 1)
  }
}

/** 从 publish_url 提 note_id：https://www.xiaohongshu.com/explore/<id>?... → <id> */
function extractNoteId(url: string): string {
  const m = url.match(/\/explore\/([^/?]+)/)
  return m ? m[1] : ""
}

// ─── 主流程 ──────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  // 1. 解析 --id <rowid>
  const args = process.argv.slice(2)
  let rowId = ""
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--id" && args[i + 1]) rowId = args[++i]
  }
  if (!rowId || !/^[0-9]+$/.test(rowId)) {
    die({ ok: false, error: "missing required arg: --id <rowid> (positive integer)" }, 1)
  }

  if (!existsSync(DB)) {
    die({ ok: false, error: "database not initialized, run init-db.sh first" })
  }

  // 2. 查 pub_xhs 行拿 publish_url
  let publishUrl = ""
  try {
    publishUrl = execFileSync("sqlite3", [DB, `SELECT publish_url FROM pub_xhs WHERE id=${rowId};`], { encoding: "utf-8" }).trim()
  } catch {
    die({ ok: false, error: "QUERY_FAILED", hint: "sqlite3 查询 pub_xhs 失败" })
  }
  if (!publishUrl) {
    die({ ok: false, error: "no record found in pub_xhs", id: rowId, hint: "请确认 id 正确且已记录到 published-track DB" })
  }

  const noteId = extractNoteId(publishUrl)
  if (!noteId) {
    die({ ok: false, error: "CANNOT_EXTRACT_NOTE_ID", publish_url: publishUrl, hint: "无法从 publish_url 提取 note_id" })
  }

  // 3. camoufox-cli 探活：open 平台首页 + snapshot 看是否跳登录页（spec §11-6，对齐 login-manager 步骤 0）
  if (!commandExistsSync(CAMOUFOX_CLI)) {
    die({ ok: false, error: "CAMOUFOX_CLI_NOT_FOUND", hint: "camoufox-cli 未找到，请确认已全局可用" })
  }

  process.stderr.write(`[fetch-xhs] 探活 xhs-browse session...\n`)
  camoufox(["--session", SESSION, "--persistent", "--json", "open", PLATFORM_HOME])
  await sleep(3)
  const snap = camoufox(["--session", SESSION, "--json", "snapshot"])
  camoufox(["--session", SESSION, "--json", "close"])
  // snapshot 输出含登录标志 = 失效（跳登录页 / 出登录按钮 / 「请登录」文案）
  if (/login|登录|扫码|请登录|sign ?in/i.test(snap)) {
    process.stderr.write(`[fetch-xhs] xhs-browse 登录态失效\n`)
    die({ ok: false, error: "SESSION_EXPIRED", platform: "xhs", login_platform: SESSION, method: "script", hint: "Cookie 已失效，请白天用 login-manager 重新登录 xhs-browse" }, 2)
  }

  // 4. 拿 self user_id（优先读 cache，无则调 get-xhs-user-id.sh）
  let userId = ""
  if (existsSync(CACHE_FILE)) {
    userId = readFileSync(CACHE_FILE, "utf-8").trim()
  }
  if (!userId || !/^[0-9a-f]{20,}$/.test(userId)) {
    process.stderr.write(`[fetch-xhs] 调 get-xhs-user-id.sh 拿 user_id...\n`)
    try {
      userId = execFileSync("bash", [join(SCRIPT_DIR, "get-xhs-user-id.sh"), "--refresh"], { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim()
    } catch (e) {
      const exitCode = (e as { status?: number }).status ?? 1
      const msg = (e as { stdout?: string }).stdout?.trim() || String(e)
      if (exitCode === 2) {
        die({ ok: false, error: "SESSION_EXPIRED", platform: "xhs", login_platform: SESSION, method: "script", hint: "get-xhs-user-id.sh 返 exit 2，cookie 失效" }, 2)
      }
      die({ ok: false, error: "GET_USER_ID_FAILED", msg, exitCode })
    }
  }
  if (!userId) {
    die({ ok: false, error: "NO_USER_ID", hint: "get-xhs-user-id.sh 返空" })
  }

  // 5. navigate profile 页 + eval flatten JS 拿映射（滚动 3 屏补齐）
  process.stderr.write(`[fetch-xhs] open profile 页取 note_id→xsec_token 映射...\n`)
  camoufox(["--session", SESSION, "--persistent", "--json", "open", `${PROFILE_BASE}${userId}`])
  await sleep(3)

  let mapping: Record<string, { xsec_token: string; xsec_source: string }> = {}
  for (let screen = 0; screen < 3; screen++) {
    const raw = camoufox(["--session", SESSION, "--json", "eval", FLATTEN_JS])
    try {
      // eval 信封 {id, success, data: {result: "<map json>"}}——真实 map 在 data.result 里
      const env = JSON.parse(raw) as { data?: { result?: string } }
      const resultStr = env?.data?.result
      if (!resultStr) throw new Error("eval 信封缺 data.result")
      const parsed = JSON.parse(resultStr) as Record<string, { xsec_token: string; xsec_source: string }>
      mapping = { ...mapping, ...parsed }
    } catch {
      // eval 返非 JSON（页面没渲染好）——下一屏重试
    }
    if (mapping[noteId]) break
    // 向下滚动加载更多
    camoufox(["--session", SESSION, "--json", "eval", "window.scrollTo(0, document.body.scrollHeight)"])
    await sleep(2)
  }
  camoufox(["--session", SESSION, "--json", "close"])

  if (!mapping[noteId]) {
    die({ ok: false, error: "NOTE_NOT_IN_PROFILE", platform: "xhs", note_id: noteId, hint: "profile 页 3 屏内未加载到该笔记，可能已删除或被限流" })
  }

  const xsecToken = mapping[noteId].xsec_token
  const xsecSource = mapping[noteId].xsec_source || "pc_feed"

  // 6. 调 fetch-retro-data.ts 抓 feed
  process.stderr.write(`[fetch-xhs] 调 fetch-retro-data.ts 抓 feed (note_id=${noteId})...\n`)
  let fetchOutput = ""
  let fetchExit = 0
  try {
    fetchOutput = execFileSync("node", [
      "--experimental-strip-types", join(SCRIPT_DIR, "fetch-retro-data.ts"),
      "--platform", "xhs", "--content-id", noteId,
      "--xsec-token", xsecToken, "--xsec-source", xsecSource,
    ], { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim()
  } catch (e) {
    fetchExit = (e as { status?: number }).status ?? 1
    fetchOutput = (e as { stdout?: string }).stdout?.trim() || ""
  }

  if (fetchExit === 2) {
    die({ ok: false, error: "SESSION_EXPIRED", platform: "xhs", login_platform: SESSION, method: "script", hint: "fetch-retro-data.ts 返 exit 2，cookie 失效" }, 2)
  }
  if (fetchExit !== 0 || !fetchOutput) {
    die({ ok: false, error: "FETCH_FAILED", platform: "xhs", content_id: noteId, fetch_exit: fetchExit, hint: "fetch-retro-data.ts 执行失败" })
  }

  // 7. 解析 fetch 结果 → 调 update-metrics.sh 写库
  let fetchResult: { ok: boolean; error?: string; stats?: Record<string, number>; comments?: Array<{ text?: string }> }
  try {
    fetchResult = JSON.parse(fetchOutput)
  } catch {
    die({ ok: false, error: "FETCH_OUTPUT_NOT_JSON", platform: "xhs", content_id: noteId, raw: fetchOutput.slice(0, 200) })
  }

  if (!fetchResult.ok) {
    // fetch 返回 ok:false（如 NOTE_INACCESSIBLE：xsec_token 失效或笔记异常）
    die({ ok: false, error: fetchResult.error || "FETCH_RETURNED_FALSE", platform: "xhs", content_id: noteId })
  }

  const stats = fetchResult.stats || {}
  const updateArgs: string[] = ["--platform", "xhs", "--id", rowId]
  for (const [k, v] of Object.entries(stats)) {
    const col = XHS_METRIC_MAP[k]
    if (col && v > 0) updateArgs.push(`--${col}`, String(v))
  }
  // top_comment
  const top = fetchResult.comments?.[0]?.text
  if (top) updateArgs.push("--top_comment", top.slice(0, 200))

  if (updateArgs.length <= 3) {
    // 无指标数据但 API 调用成功——直接返回成功
    errJson({ ok: true, method: "script", platform: "xhs", content_id: noteId, note: "API 返回成功但无互动指标数据" })
    process.exit(0)
  }

  try {
    const out = execFileSync("bash", [join(SCRIPT_DIR, "update-metrics.sh"), ...updateArgs], { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] }).trim()
    // update-metrics.sh stdout 是 JSON，透传其 ok 字段
    const up = JSON.parse(out) as { ok: boolean; error?: string }
    if (!up.ok) {
      die({ ok: false, error: up.error || "UPDATE_FAILED", platform: "xhs", content_id: noteId, update_args: updateArgs.join(" ") })
    }
  } catch (e) {
    const msg = (e as { stdout?: string }).stdout?.trim() || String(e)
    die({ ok: false, error: "UPDATE_FAILED", platform: "xhs", content_id: noteId, msg })
  }

  // 8. 输出统一 JSON
  errJson({ ok: true, method: "script", platform: "xhs", content_id: noteId, metrics_params: updateArgs.slice(3).join(" ") })
}

// ─── 工具小函数 ──────────────────────────────────────────────────────────────

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function commandExistsSync(cmd: string): boolean {
  try {
    execFileSync("which", [cmd], { encoding: "utf-8", stdio: ["pipe", "pipe", "pipe"] })
    return true
  } catch {
    return false
  }
}

main().catch(e => die({ ok: false, error: "UNEXPECTED", msg: String(e) }))
