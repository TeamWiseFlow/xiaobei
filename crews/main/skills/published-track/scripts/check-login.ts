#!/usr/bin/env -S node --experimental-strip-types
/**
 * check-login.ts — 登录探活 CLI（两层）薄包装
 *
 * 实际逻辑在 _shared/check-session.ts（viral-chaser / xhs-content-ops 等共用）。
 * 本脚本只做 argv 解析 + exit code 约定，供 fetch-and-update-metrics.sh 调用。
 *
 * Usage:
 *   node --experimental-strip-types check-login.ts --platform <p> [--no-ping]
 * Exit: 0=有效 / 2=SESSION_EXPIRED（cookie 失效，应重登）/ 1=参数错或 SIGN_UNAVAILABLE 或 crash
 */
import { checkSession, sessionName } from "../../_shared/check-session.ts";

function out(obj: unknown): void {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  let platform = "";
  let noPing = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--platform" && args[i + 1]) platform = args[++i];
    else if (args[i] === "--no-ping") noPing = true;
  }
  if (!platform) {
    out({ ok: false, error: "missing --platform" });
    process.exit(1);
  }

  const r = await checkSession(platform, { noPing });
  if (r.ok) {
    out({ ok: true, platform, session: sessionName(platform), detail: r.detail, ping: r.ping });
    process.exit(0);
  }
  // SIGN_UNAVAILABLE → exit 1（重登救不了，别误导 heartbeat 触发重登）
  if (r.error === "SIGN_UNAVAILABLE") {
    out({ ok: false, error: "SIGN_UNAVAILABLE", platform, session: sessionName(platform), reason: r.reason });
    process.exit(1);
  }
  // SESSION_EXPIRED → exit 2
  out({ ok: false, error: "SESSION_EXPIRED", platform, session: sessionName(platform), reason: r.reason, ping: r.ping });
  process.exit(2);
}

main().catch((e: unknown) => {
  out({ ok: false, error: "CHECK_LOGIN_CRASH", message: e instanceof Error ? e.message : String(e) });
  process.exit(1);
});
