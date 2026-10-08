/** Public-detail lane; accepts the ephemeral browser session over stdin. */
import { pathToFileURL } from "node:url";
import { douyinWebGet } from "./douyin-web.ts";

export async function fetchDouyin(awemeId: string, cookieStr: string, ua: string) {
  const result: { ok: boolean; stats: Record<string, number>; error?: string } = {
    ok: false, stats: {},
  };
  if (!process.env.OFB_KEY) return { ...result, error: "SIGN_UNAVAILABLE" };
  try {
    const { status, data } = await douyinWebGet<any>(
      "/aweme/v1/web/aweme/detail/", { aweme_id: awemeId }, cookieStr, ua,
    );
    const aweme = data?.aweme_detail;
    // Avoid precision loss on JSON numeric work IDs and reject a different work.
    if (status !== 200 || !aweme || String(aweme.aweme_id) !== awemeId) {
      result.error = "PUBLIC_DETAIL_UNAVAILABLE";
      return result;
    }
    const mapping: Record<string, string> = {
      digg_count: "likeCount", comment_count: "commentCount",
      share_count: "shareCount", collect_count: "collectCount",
    };
    for (const [key, target] of Object.entries(mapping)) {
      const value = aweme.statistics?.[key];
      if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) {
        result.stats[target] = value;
      }
    }
    // Public play_count is not a source of creator views.
    result.ok = Object.keys(result.stats).length > 0;
    if (!result.ok) result.error = "PUBLIC_METRICS_UNAVAILABLE";
  } catch {
    result.error = "PUBLIC_DETAIL_REQUEST_FAILED";
  }
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    let input = "";
    for await (const part of process.stdin) input += part;
    const { identifiers, cookieStr, ua } = JSON.parse(input);
    if (!Array.isArray(identifiers) || identifiers.length > 30 ||
        identifiers.some(id => typeof id !== "string" || !/^\d{15,22}$/.test(id)) ||
        typeof cookieStr !== "string" || !cookieStr || typeof ua !== "string" || !ua) {
      throw new Error("INVALID_INPUT");
    }
    const results: Record<string, unknown> = {};
    for (const id of new Set<string>(identifiers)) results[id] = await fetchDouyin(id, cookieStr, ua);
    console.log(JSON.stringify({ ok: true, results }));
  } catch {
    console.log(JSON.stringify({ ok: false, error: "PUBLIC_DETAIL_INPUT_FAILED" }));
    process.exitCode = 1;
  }
}
