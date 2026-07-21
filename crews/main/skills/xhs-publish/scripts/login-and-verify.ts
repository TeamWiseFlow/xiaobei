#!/usr/bin/env -S node --experimental-strip-types
/**
 * login-and-verify.ts — xhs-publish 创作者 SSO 导出+验证（AiToEarn 两步登录对齐）
 *
 * 与 xhs-browse 共享 camoufox profile（session=xhs-browse，login-manager 已把 www 登录态
 * 预热进该 profile）。本脚本在共享 session 上：
 *   ① open creator.xiaohongshu.com/login?source=official → www 已登录则自动 SSO 重定向，
 *      落 galaxy_creator_session_id / access-token-creator 等创作者 cookie（无需扫码）；
 *   ② 轮询 cookie 直到创作者 token 出现（SSO 完成），超时则 exit 2（提示先 login-manager 重登 www）；
 *   ③ 导出全部 cookie（含 .xiaohongshu.com 的 web_session + 创作者 token）→ 临时 →
 *     verifyCreator（裸 GET personal_info，新鲜两层探活）→ 通过才 commit 到 xhs-publish.json；
 *   ④ identity export → xhs-publish.ua.json → close session。
 *
 * 不重试、不扫码——验证不过直接报错（避免风控）。前置：Agent 已 `login-manager check xhs-browse`
 * （exit 2 则先重登 www）确保共享 profile 内 web_session 存活。
 *
 * Usage:
 *   node --experimental-strip-types login-and-verify.ts
 *
 * Exit:
 *   0  SSO + 验证通过，创作者 cookie+UA 已落 ~/.openclaw/logins/xhs-publish.{json,ua.json}
 *   1  crash
 *   2  SESSION_EXPIRED（SSO 未完成 / 探活不过，未 commit）
 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import { join } from "node:path";
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";

const execFileAsync = promisify(execFile);

const CAMOUFOX_CLI = process.env.CAMOUFOX_CLI ?? "camoufox-cli";
const LOGINS_DIR = join(homedir(), ".openclaw", "logins");
/** 共享 profile——login-manager 在此 session 内管 www 登录态，xhs-publish 借用做创作者 SSO */
const SHARED_SESSION = "xhs-browse";
const CREATOR_SSO_URL = "https://creator.xiaohongshu.com/login?source=official";
const PLATFORM = "xhs-publish";
const SESSION_FILE = join(LOGINS_DIR, `${PLATFORM}.json`);
const UA_FILE = join(LOGINS_DIR, `${PLATFORM}.ua.json`);
const TMP_FILE = `/tmp/xhs-publish-cookies.json`;
const SSO_TIMEOUT_MS = 30_000;
const SSO_POLL_INTERVAL_MS = 2_000;

function printJson(data: unknown): void {
  process.stdout.write(`${JSON.stringify(data, null, 2)}\n`);
}
function errExit(msg: string, code = 1): never {
  printJson({ ok: false, error: msg });
  process.exit(code);
}
function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function camoufox(args: string[]): Promise<unknown> {
  const { stdout } = await execFileAsync(
    CAMOUFOX_CLI,
    ["--session", SHARED_SESSION, "--persistent", "--json", ...args],
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

/** 轮询导出 cookie，直到创作者 SSO token 出现（SSO 重定向完成） */
async function waitForCreatorSso(): Promise<unknown | null> {
  const deadline = Date.now() + SSO_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      await camoufox(["cookies", "export", TMP_FILE]);
      const raw = JSON.parse(readFileSync(TMP_FILE, "utf-8"));
      const { buildCookieMap } = await import("./creator-session.ts");
      const map = buildCookieMap(raw);
      if (
        map["galaxy_creator_session_id"]?.value ||
        map["access-token-creator.xiaohongshu.com"]?.value ||
        map["customer-sso-sid"]?.value
      ) {
        return raw;
      }
    } catch {
      /* 轮询中导出/解析偶发失败，继续等 */
    }
    await sleep(SSO_POLL_INTERVAL_MS);
  }
  return null;
}

async function main(): Promise<void> {
  // 0. 前置自检：共享 profile 内需有 web_session（login-manager 已登录 www）
  try {
    await camoufox(["cookies", "export", TMP_FILE]);
    const preMap = (await import("./creator-session.ts")).buildCookieMap(
      JSON.parse(readFileSync(TMP_FILE, "utf-8")),
    );
    if (!preMap["web_session"]?.value) {
      await closeSession();
      errExit(
        "共享 session(xhs-browse) 内无 web_session——请先 `login-manager check xhs-browse`（exit 2 则 `login-manager login xhs-browse` 重登 www）后再调本脚本",
        2,
      );
    }
  } catch (e) {
    await closeSession();
    errExit(`前置 web_session 自检失败: ${(e as Error).message}`);
  }

  // 1. open creator SSO 页（www 已登录 → 自动重定向落创作者 cookie，无需扫码）
  try {
    await camoufox(["open", CREATOR_SSO_URL]);
  } catch (e) {
    await closeSession();
    errExit(`打开 creator SSO 页失败: ${(e as Error).message}`);
  }

  // 2. 轮询等 SSO 完成（创作者 token 出现）
  const raw = await waitForCreatorSso();
  if (!raw) {
    await closeSession();
    errExit(
      "SSO 未完成——创作者会话 cookie 在 30s 内未出现。确认共享 session 内 web_session 仍存活后重试",
      2,
    );
  }

  // 3. verifyCreator（新鲜两层探活，裸 GET personal_info）
  const { verifyCreator, buildCookieMap } = await import("./creator-session.ts");
  const map = buildCookieMap(raw);
  if (Object.keys(map).length === 0) {
    await closeSession();
    errExit("导出的 cookie 为空——SSO 后 session 内无 cookie，请人工检查账号状态", 2);
  }
  const r = await verifyCreator(map);
  if (!r.ok) {
    await closeSession();
    errExit(`SSO 后验证失败：${r.reason}（cookie 未落中央存储——不重试，请人工检查账号状态）`, 2);
  }

  // 4. 验过 → commit 中央存储（裸数组格式，与 xhs-browse.json 对称，publish_xhs.py 合并读取）
  try {
    mkdirSync(LOGINS_DIR, { recursive: true });
    const arr = Array.isArray(raw) ? raw : (raw as { cookies?: unknown[] })?.cookies ?? [];
    writeFileSync(SESSION_FILE, `${JSON.stringify(arr, null, 2)}\n`, "utf-8");
    await camoufox(["identity", "export", UA_FILE]);
  } catch (e) {
    await closeSession();
    errExit(`commit 中央存储失败: ${(e as Error).message}`);
  }

  // 5. close session——登录态已落磁盘 profile + 中央存储，不留浏览器进程占内存
  await closeSession();
  printJson({
    ok: true,
    platform: PLATFORM,
    session: SESSION_FILE,
    ua: UA_FILE,
    sharedSession: SHARED_SESSION,
    ping: r.ping ?? "skipped",
    diagnosisStatus: r.diagnosisStatus,
    fansCount: r.fansCount,
    message: "SSO + 验证通过，创作者 cookie + UA 已落中央存储（session 已关，登录态在磁盘 profile）",
  });
}

main().catch((e: unknown) => errExit(`crash: ${e instanceof Error ? e.message : String(e)}`));
