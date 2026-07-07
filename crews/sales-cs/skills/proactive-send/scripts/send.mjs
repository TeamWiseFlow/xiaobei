#!/usr/bin/env node
/**
 * send.mjs — Proactive awada message sender (HTTP gateway transport)
 *
 * Usage:
 *   node scripts/send.mjs \
 *     --user-id-external "黄子奇ᐪᒻ" \
 *     --text "您好，昨天咱们聊过专业版的事，不知道今天方便看看吗？"
 *
 * 走 relay 网关 POST /api/v1/awada/outbound?lane=<lane>（见 awada-extension/src/send.ts
 * 的 postOutbound，契约见 docs/AWADA-CLIENT-TRANSPORT.md §3）。
 * relayBaseUrl / ofbKey / platform / lane 从 ~/.openclaw/openclaw.json 的 channels.awada 读取。
 * channel_id 和 tenant_id 固定为 "0"（私聊）。
 * 成功：打印 streamId（exit 0）；失败：打印错误到 stderr（exit 1）。
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

// ── Arg parsing ──────────────────────────────────────────────────────────────

function getArg(name) {
  const idx = process.argv.indexOf(name);
  if (idx === -1 || idx >= process.argv.length - 1) return null;
  return process.argv[idx + 1];
}

const userIdExternal = getArg("--user-id-external");
const text = getArg("--text");

if (!userIdExternal || !text) {
  console.error("Usage: node send.mjs --user-id-external <id> --text <message>");
  process.exit(1);
}

// ── Load openclaw config ─────────────────────────────────────────────────────

const configPath = join(homedir(), ".openclaw", "openclaw.json");
let cfg;
try {
  cfg = JSON.parse(readFileSync(configPath, "utf8"));
} catch (err) {
  console.error(`❌ Cannot read config: ${configPath}: ${err.message}`);
  process.exit(1);
}

const awadaCfg = cfg?.channels?.awada ?? {};
const { relayBaseUrl, ofbKey } = awadaCfg;
const platform = awadaCfg.platform || "wechat";
const lane = awadaCfg.lane || "user";

if (!relayBaseUrl || !ofbKey) {
  console.error(
    "❌ channels.awada.relayBaseUrl / ofbKey not set in ~/.openclaw/openclaw.json",
  );
  process.exit(1);
}

// ── POST /outbound ───────────────────────────────────────────────────────────
// meta.platform / channel_id / user_id_external 必填（relay 据此路由回 platform）。

const url = `${relayBaseUrl.replace(/\/+$/, "")}/api/v1/awada/outbound?lane=${encodeURIComponent(lane)}`;
const body = {
  payload: [{ type: "text", text }],
  meta: {
    platform,
    channel_id: "0",
    user_id_external: userIdExternal,
    tenant_id: "0",
  },
};

try {
  const res = await fetch(url, {
    method: "POST",
    headers: { "X-OFB-Key": ofbKey, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const errBody = await res.json();
      if (errBody?.error?.code || errBody?.error?.message) {
        detail = `${res.status}: ${errBody.error.code ?? ""} ${errBody.error.message ?? ""}`.trim();
      }
    } catch {
      // non-json error body
    }
    console.error(`❌ outbound POST failed: ${detail}`);
    process.exit(1);
  }
  const json = await res.json();
  const streamId = json?.data?.streamId ?? "";
  console.log(streamId);
} catch (err) {
  console.error(`❌ outbound POST error: ${err.message}`);
  process.exit(1);
}
