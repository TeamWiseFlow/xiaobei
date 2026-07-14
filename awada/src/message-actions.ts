import { jsonResult, readStringParam } from "openclaw/plugin-sdk/agent-runtime";
import type { ChannelMessageActionAdapter } from "openclaw/plugin-sdk/channel-contract";
import { resolveAwadaAccount } from "./accounts.js";
import { buildMediaContentFromName, decodeAwadaTo, sendMediaToAwada } from "./send.js";
import { getCachedOutboundTarget } from "./target-cache.js";

export const awadaMessageActions: ChannelMessageActionAdapter = {
  describeMessageTool: ({ cfg }) => {
    const account = resolveAwadaAccount({ cfg });
    if (!account.configured) return null;
    return { actions: ["sendAttachment"] };
  },

  supportsAction: ({ action }) => action === "sendAttachment",

  handleAction: async (ctx) => {
    if (ctx.action !== "sendAttachment") {
      throw new Error(`Unsupported awada action: ${ctx.action}`);
    }

    const fileName = readStringParam(ctx.params, "file_name", {
      required: true,
      label: "file_name (pre-stored WeChat cloud file)",
    });

    const account = resolveAwadaAccount({ cfg: ctx.cfg, accountId: ctx.accountId });
    if (!account.relayBaseUrl || !account.ofbKey) {
      throw new Error("[awada] relayBaseUrl/ofbKey not configured");
    }

    // Prefer the resolved target from params.to (set by core's target resolver),
    // fall back to the in-memory cache populated on inbound messages.
    const toRaw = readStringParam(ctx.params, "to");
    const target = (toRaw ? decodeAwadaTo(toRaw) : null) ?? getCachedOutboundTarget(ctx.requesterSenderId ?? "");
    if (!target) {
      throw new Error(
        "[awada] Cannot resolve outbound target. " +
          "The customer must have sent a message before you can send attachments.",
      );
    }

    const media = buildMediaContentFromName({ file_name: fileName });
    const streamId = await sendMediaToAwada({
      relayBaseUrl: account.relayBaseUrl,
      ofbKey: account.ofbKey,
      lane: account.lane,
      target,
      media,
    });

    return jsonResult({ ok: true, type: media.type, file_name: fileName, streamId });
  },
};
