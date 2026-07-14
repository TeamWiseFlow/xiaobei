import type { ChannelOutboundAdapter } from "openclaw/plugin-sdk/core";
import type { ClawdbotConfig } from "openclaw/plugin-sdk";
import { resolveAwadaAccount } from "./accounts.js";
import { getAwadaRuntime } from "./runtime.js";
import {
  buildMediaContentFromName,
  buildMediaContentFromUrl,
  decodeAwadaTo,
  sendMediaToAwada,
  sendTextToAwada,
} from "./send.js";
import type { AwadaConfig } from "./types.js";

import { isNoReplyText } from "./silent-reply.js";

/**
 * Resolve the gateway send params (relayBaseUrl/ofbKey/lane) for an account.
 * Throws if the account isn't configured for gateway transport.
 */
function resolveGatewaySend(params: {
  cfg: ClawdbotConfig;
  accountId?: string | null;
}) {
  const account = resolveAwadaAccount({ cfg: params.cfg, accountId: params.accountId ?? undefined });
  if (!account.relayBaseUrl || !account.ofbKey) {
    throw new Error("[awada] relayBaseUrl/ofbKey not configured");
  }
  return {
    relayBaseUrl: account.relayBaseUrl,
    ofbKey: account.ofbKey,
    lane: account.lane,
    account,
  };
}

/**
 * Split text by perMsgMaxLen if configured, then send each chunk.
 * Returns the stream ID of the last sent chunk (for delivery tracking).
 */
async function sendChunked(params: {
  cfg: ClawdbotConfig;
  relayBaseUrl: string;
  ofbKey: string;
  lane: string;
  target: ReturnType<typeof decodeAwadaTo>;
  text: string;
  sourceEventId?: string;
}): Promise<string> {
  const { cfg, relayBaseUrl, ofbKey, lane, target, sourceEventId } = params;
  const awadaCfg = cfg.channels?.awada as AwadaConfig | undefined;
  const perMsgMaxLen = awadaCfg?.perMsgMaxLen;
  const chunks =
    perMsgMaxLen && params.text.length > perMsgMaxLen
      ? getAwadaRuntime().channel.text.chunkMarkdownText(params.text, perMsgMaxLen)
      : [params.text];

  let lastId = "";
  for (const chunk of chunks) {
    lastId = await sendTextToAwada({
      relayBaseUrl,
      ofbKey,
      lane,
      target: target!,
      text: chunk,
      sourceEventId,
    });
  }
  return lastId;
}

export const awadaOutbound: ChannelOutboundAdapter = {
  deliveryMode: "direct",
  chunker: (text, limit) => getAwadaRuntime().channel.text.chunkMarkdownText(text, limit),
  chunkerMode: "markdown",
  textChunkLimit: 2000,
  sendText: async ({ cfg, to, text, accountId }) => {
    if (isNoReplyText(text)) {
      return { channel: "awada", messageId: "no_reply_suppressed" };
    }
    const target = decodeAwadaTo(to);
    if (!target) {
      throw new Error(`[awada] Cannot decode target: ${to}`);
    }
    const gw = resolveGatewaySend({ cfg, accountId });
    const streamId = await sendChunked({
      cfg,
      relayBaseUrl: gw.relayBaseUrl,
      ofbKey: gw.ofbKey,
      lane: gw.lane,
      target,
      text: text ?? "",
    });
    return { channel: "awada", messageId: streamId };
  },
  sendMedia: async ({ cfg, to, text, mediaUrl, accountId }) => {
    const target = decodeAwadaTo(to);
    if (!target) {
      throw new Error(`[awada] Cannot decode target: ${to}`);
    }
    const gw = resolveGatewaySend({ cfg, accountId });

    // Route mediaUrl to sendMediaToAwada:
    // - http/https URL → file_url
    // - plain filename (no path separators) → file_name for pre-stored WeChat cloud files
    // - local absolute path or anything else → fall back to text (not supported)
    if (mediaUrl?.trim()) {
      const url = mediaUrl.trim();
      if (/^https?:\/\//i.test(url)) {
        const media = buildMediaContentFromUrl(url);
        const streamId = await sendMediaToAwada({
          relayBaseUrl: gw.relayBaseUrl,
          ofbKey: gw.ofbKey,
          lane: gw.lane,
          target,
          media,
        });
        return { channel: "awada", messageId: streamId };
      }
      if (!url.includes("/") && !url.includes("\\")) {
        const media = buildMediaContentFromName({ file_name: url });
        const streamId = await sendMediaToAwada({
          relayBaseUrl: gw.relayBaseUrl,
          ofbKey: gw.ofbKey,
          lane: gw.lane,
          target,
          media,
        });
        return { channel: "awada", messageId: streamId };
      }
      // Local path or unsupported scheme — fall through to text fallback
    }

    // No media reference — fall back to text body
    const body = text?.trim() ?? "[media]";
    const streamId = await sendChunked({
      cfg,
      relayBaseUrl: gw.relayBaseUrl,
      ofbKey: gw.ofbKey,
      lane: gw.lane,
      target,
      text: body,
    });
    return { channel: "awada", messageId: streamId };
  },
};
