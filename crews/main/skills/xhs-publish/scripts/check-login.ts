#!/usr/bin/env -S node --experimental-strip-types
/**
 * check-login.ts — xhs-publish 创作者域探活 CLI（发布前批量探活一次）
 *
 * 裸 GET creator.xiaohongshu.com/api/galaxy/creator/home/personal_info + 创作者 cookie
 * → success && code===0 = online。无需签名 / OFB_KEY（见 creator-session.ts）。
 *
 * Usage:
 *   node --experimental-strip-types check-login.ts [--no-ping]
 *
 * Exit:
 *   0  有效（online）
 *   2  SESSION_EXPIRED（cookie 失效 → 走 xhs-publish 自管有头登录流）
 *   1  crash / 参数错
 */
import { checkCreator } from "./creator-session.ts";

async function main(): Promise<void> {
  const opts = { noPing: process.argv.includes("--no-ping") };
  const r = await checkCreator(opts);
  if (r.ok) {
    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          platform: "xhs-publish",
          ping: r.ping,
          diagnosisStatus: r.diagnosisStatus,
          fansCount: r.fansCount,
          detail: r.detail,
        },
        null,
        2,
      ) + "\n",
    );
    process.exit(0);
  }
  process.stdout.write(
    JSON.stringify({ ok: false, platform: "xhs-publish", error: r.error, reason: r.reason }, null, 2) + "\n",
  );
  process.exit(r.error === "SESSION_EXPIRED" ? 2 : 1);
}

main().catch((e: unknown) => {
  process.stderr.write(`[xhs-publish check-login] crash: ${e instanceof Error ? e.message : String(e)}\n`);
  process.exit(1);
});
