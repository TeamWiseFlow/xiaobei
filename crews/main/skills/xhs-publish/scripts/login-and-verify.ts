#!/usr/bin/env -S node --experimental-strip-types
/**
 * login-and-verify.ts — xhs-publish 自管导出+验证（登录就位后调用）
 *
 * Agent 自己有头打开创作者登录页（camoufox-cli --session xhs-publish --persistent --headed
 * open "https://creator.xiaohongshu.com/publish/publish?source=official"）、通知用户扫码登录、
 * 对话确认登录完成后调本脚本。本脚本不打开浏览器、不轮询——只做：
 *   导出 cookie 到临时 → 创作者域两层探活（verifyCreator，裸 GET personal_info，新鲜）→
 *   通过才 commit 到中央存储 + identity export → close session。验证不过直接报错（不重试，避免风控）。
 *
 * 与 login-manager 的 export-and-verify 同构，但探活走创作者域 personal_info（非 edith user/me 签名），
 * 不依赖 relay-sign / OFB_KEY。xhs-publish cookie 仅供本技能使用，故自管、不进 login-manager。
 *
 * Usage:
 *   node --experimental-strip-types login-and-verify.ts
 *   前置：Agent 已 `camoufox-cli --session xhs-publish --persistent --headed open <creator登录Url>`
 *        且用户已完成扫码登录
 *
 * Exit:
 *   0  导出 + 验证通过，cookie+UA 已落中央存储
 *   1  crash
 *   2  SESSION_EXPIRED（探活不过，未 commit）
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join } from "node:path";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";

const execFileAsync = promisify(execFile);

const CAMOUFOX_CLI = process.env.CAMOUFOX_CLI ?? "camoufox-cli";
const LOGINS_DIR = join(homedir(), ".openclaw", "logins");
const PLATFORM = "xhs-publish";
const SESSION_FILE = join(LOGINS_DIR, `${PLATFORM}.json`);
const UA_FILE = join(LOGINS_DIR, `${PLATFORM}.ua.json`);
const TMP_FILE = `/tmp/xhs-publish-cookies.json`;

function printJson(data: unknown): void {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}
function errExit(msg: string, code = 1): never {
  printJson({ ok: false, error: msg });
  process.exit(code);
}

async function camoufox(args: string[]): Promise<unknown> {
  const { stdout } = await execFileAsync(
    CAMOUFOX_CLI,
    ["--session", PLATFORM, "--persistent", "--json", ...args],
    { maxBuffer: 64 * 1024 * 1024 },
  );
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error(`camoufox-cli 输出解析失败: ${stdout.slice(0, 200)}`);
  }
}

async function closeSession(): Promise<void> {
  try { await camoufox(["close"]); } catch { /* session 已退或卡死，忽略 */ }
}

function timestampLocal(): string {
  const d = new Date();
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

async function main(): Promise<void> {
  // 1. 导出 cookie 到临时（先验过再 commit 中央存储）
  try {
    await camoufox(["cookies", "export", TMP_FILE]);
  } catch (e) {
    await closeSession();
    errExit(`导出 cookie 失败（确认 Agent 已 open --headed session 且用户已登录）: ${(e as Error).message}`);
  }

  // 2. 读临时 cookie → verifyCreator（新鲜两层探活，裸 GET personal_info）
  const { verifyCreator, buildCookieMap } = await import("./creator-session.ts");
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(TMP_FILE, "utf-8"));
  } catch (e) {
    await closeSession();
    errExit(`读取导出 cookie 失败: ${(e as Error).message}`);
  }
  const map = buildCookieMap(raw);
  if (Object.keys(map).length === 0) {
    await closeSession();
    errExit("导出的 cookie 为空——session 内未登录，请确认用户已完成扫码登录", 2);
  }

  const r = await verifyCreator(map);
  if (!r.ok) {
    await closeSession();
    errExit(`登录后验证失败：${r.reason}（cookie 未落中央存储——不重试，请人工检查账号状态）`, 2);
  }

  // 3. 验过 → commit 中央存储（{platform, cookies, updated_at} 包壳，publish_xhs.py 期望此格式）+ identity export
  try {
    mkdirSync(LOGINS_DIR, { recursive: true });
    const arr = Array.isArray(raw) ? raw : (raw as { cookies?: unknown[] })?.cookies ?? [];
    writeFileSync(SESSION_FILE, `${JSON.stringify({ platform: PLATFORM, cookies: arr, updated_at: timestampLocal() }, null, 2)}\n`, "utf-8");
    await camoufox(["identity", "export", UA_FILE]);
  } catch (e) {
    await closeSession();
    errExit(`commit 中央存储失败: ${(e as Error).message}`);
  }

  // 4. close session——登录态已落磁盘 profile + 中央存储，不留浏览器进程占内存
  await closeSession();
  printJson({
    ok: true,
    platform: PLATFORM,
    session: SESSION_FILE,
    ua: UA_FILE,
    ping: r.ping ?? "skipped",
    diagnosisStatus: r.diagnosisStatus,
    fansCount: r.fansCount,
    message: "导出 + 验证通过，cookie + UA 已落中央存储（session 已关，登录态在磁盘 profile）",
  });
}

main().catch((e: unknown) => errExit(`crash: ${e instanceof Error ? e.message : String(e)}`));
