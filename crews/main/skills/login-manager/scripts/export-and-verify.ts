#!/usr/bin/env -S node --experimental-strip-types
/**
 * export-and-verify.ts — login-manager 导出+验证（登录就位后调用）
 *
 * Agent 自己有头打开登录页（camoufox-cli --session <p> --persistent --headed open <url>）、
 * 通知用户登录、与用户对话确认登录完成后，调本脚本。本脚本不打开浏览器、不轮询——
 * 只做：导出 cookie 到临时 → 两层探活验证（verifyCookies，新鲜 pong）→ 通过才 commit 到中央存储
 * + identity export → close session。验证不过直接报错（不重试，避免风控）。
 *
 * 验证在 commit 前：导出到临时文件验过才落中央存储，避免把失效/不完整 cookie 写给下游。
 * 借鉴 ~/wiseflow-pro/wiseflow/nodriver_helper_reference.py _check_login_status（字段）
 * + MediaCrawlerPro 各平台 client.py pong + Ai2Earn xhs getUserInfo（user/me）。
 *
 * Usage:
 *   node --experimental-strip-types export-and-verify.ts --platform <p>
 *   平台 ∈ douyin | bilibili | kuaishou | xhs-browse
 *   前置：Agent 已 `camoufox-cli --session <p> --persistent --headed open <loginUrl>` 且用户已登录
 *
 * Exit:
 *   0  导出 + 验证通过，cookie+UA 已落中央存储
 *   1  参数错 / crash
 *   2  SESSION_EXPIRED（探活不过，未 commit 中央存储）
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join } from "node:path";
import { writeFileSync, mkdirSync } from "node:fs";

const execFileAsync = promisify(execFile);

const CAMOUFOX_CLI = process.env.CAMOUFOX_CLI ?? "camoufox-cli";
const LOGINS_DIR = join(homedir(), ".openclaw", "logins");

type Platform = "douyin" | "bilibili" | "kuaishou" | "xhs-browse";
const SUPPORTED: Platform[] = ["douyin", "bilibili", "kuaishou", "xhs-browse"];

function printJson(data: unknown): void {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}
function errExit(msg: string, code = 1): never {
  printJson({ ok: false, error: msg });
  process.exit(code);
}

/** camoufox-cli 调用封装：复用 Agent 已开的持久化 session（不加 --headed）。 */
async function camoufox(platform: string, args: string[]): Promise<unknown> {
  const { stdout } = await execFileAsync(
    CAMOUFOX_CLI,
    ["--session", platform, "--persistent", "--json", ...args],
    { maxBuffer: 64 * 1024 * 1024 },
  );
  try {
    return JSON.parse(stdout);
  } catch {
    throw new Error(`camoufox-cli 输出解析失败: ${stdout.slice(0, 200)}`);
  }
}

async function closeSession(platform: string): Promise<void> {
  try { await camoufox(platform, ["close"]); } catch { /* session 已退或卡死，忽略 */ }
}

function timestampLocal(): string {
  const d = new Date();
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  let platform = "";
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i];
  }
  if (!platform) errExit("missing --platform");
  if (!SUPPORTED.includes(platform as Platform)) {
    errExit(`unsupported platform: ${platform}（仅支持 douyin/bilibili/kuaishou/xhs-browse；xhs-publish 自管登录）`);
  }

  const sessionFile = join(LOGINS_DIR, `${platform}.json`);
  const uaFile = join(LOGINS_DIR, `${platform}.ua.json`);
  const tmpFile = `/tmp/lm-cookies-${platform}.json`;

  // 1. 导出 cookie 到临时文件（不直接落中央存储——先验过再 commit）
  try {
    await camoufox(platform, ["cookies", "export", tmpFile]);
  } catch (e) {
    await closeSession(platform);
    errExit(`导出 cookie 失败（确认 Agent 已 open --headed session 且用户已登录）: ${(e as Error).message}`);
  }

  // 2. 读临时 cookie → verifyCookies（新鲜两层探活，不读缓存）
  const { verifyCookies, buildCookieMap } = await import("../../_shared/check-session.ts");
  let raw: unknown;
  try {
    raw = JSON.parse(await import("node:fs").then((fs) => fs.readFileSync(tmpFile, "utf-8")));
  } catch (e) {
    await closeSession(platform);
    errExit(`读取导出 cookie 失败: ${(e as Error).message}`);
  }
  const map = buildCookieMap(raw);
  if (Object.keys(map).length === 0) {
    await closeSession(platform);
    errExit("导出的 cookie 为空——session 内未登录，请确认用户已完成登录", 2);
  }

  const r = await verifyCookies(platform, map);
  // SIGN_UNAVAILABLE：签名缺凭证，presence 已过，登录本身成功——仅警告，照常 commit
  // （下游业务 fetch 同样会撞 SIGN_UNAVAILABLE，那是 IT engineer 配凭证问题，非本次登录问题）
  if (!r.ok && r.error === "SIGN_UNAVAILABLE") {
    process.stderr.write(`[login-manager] ⚠️ ${r.reason}（cookie 字段已过，跳过 pong 验证，照常导出）\n`);
  } else if (!r.ok) {
    await closeSession(platform);
    errExit(`登录后验证失败：${r.reason}（cookie 未落中央存储——不重试，请人工检查账号状态）`, 2);
  }

  // 3. 验过 → commit 到中央存储 + identity export
  try {
    mkdirSync(LOGINS_DIR, { recursive: true });
    const arr = Array.isArray(raw) ? raw : (raw as { cookies?: unknown[] })?.cookies ?? [];
    writeFileSync(sessionFile, `${JSON.stringify({ platform, cookies: arr, updated_at: timestampLocal() }, null, 2)}\n`, "utf-8");
    await camoufox(platform, ["identity", "export", uaFile]);
  } catch (e) {
    await closeSession(platform);
    errExit(`commit 中央存储失败: ${(e as Error).message}`);
  }

  // 4. close session——登录态已落磁盘 profile + 中央存储，不留浏览器进程占内存
  await closeSession(platform);
  printJson({
    ok: true,
    platform,
    session: sessionFile,
    ua: uaFile,
    ping: r.ping ?? "skipped",
    message: "导出 + 验证通过，cookie + UA 已落中央存储（session 已关，登录态在磁盘 profile）",
  });
}

main().catch((e: unknown) => errExit(`crash: ${e instanceof Error ? e.message : String(e)}`));
