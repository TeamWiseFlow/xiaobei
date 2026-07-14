import type { ChannelMeta, ChannelPlugin } from "openclaw/plugin-sdk/core";
import type { ClawdbotConfig } from "openclaw/plugin-sdk";
import {
  buildProbeChannelStatusSummary,
  buildRuntimeAccountStatusSnapshot,
  createDefaultChannelRuntimeState,
} from "openclaw/plugin-sdk/status-helpers";
import { DEFAULT_ACCOUNT_ID } from "openclaw/plugin-sdk/channel-plugin-common";
import {
  resolveAwadaAccount,
  listAwadaAccountIds,
  resolveDefaultAwadaAccountId,
} from "./accounts.js";
import { awadaSetupWizard } from "./onboarding.js";
import { awadaMessageActions } from "./message-actions.js";
import { awadaOutbound } from "./outbound.js";
import { probeAwada } from "./probe.js";
import { decodeAwadaTo } from "./send.js";
import type { ResolvedAwadaAccount, AwadaConfig } from "./types.js";

const meta: ChannelMeta = {
  id: "awada",
  label: "Awada",
  selectionLabel: "Awada (WeChat via relay gateway)",
  docsPath: "/channels/awada",
  docsLabel: "awada",
  blurb: "WeChat (enterprise/personal) via awada relay gateway (HTTP/WS transport).",
  aliases: [],
  order: 80,
};

export const awadaPlugin: ChannelPlugin<ResolvedAwadaAccount> = {
  id: "awada",
  meta,
  capabilities: {
    chatTypes: ["direct"],
    polls: false,
    threads: false,
    media: true,
    reactions: false,
    edit: false,
    reply: false,
  },
  agentPrompt: {
    messageToolHints: () => [
      "- Awada targeting: replies are routed back to the originating WeChat user automatically.",
      '- To send a pre-stored WeChat cloud file or image, use action="sendAttachment" with file_name="<filename>".',
      "  Example: message(action=\"sendAttachment\", file_name=\"company_logo.jpg\")",
    ],
  },
  reload: { configPrefixes: ["channels.awada"] },
  configSchema: {
    schema: {
      type: "object",
      additionalProperties: false,
      properties: {
        enabled: { type: "boolean" },
        relayBaseUrl: { type: "string" },
        ofbKey: { type: "string" },
        lane: { type: "string" },
        platform: { type: "string" },
        dmPolicy: { type: "string", enum: ["open", "pairing", "allowlist"] },
        allowFrom: { type: "array", items: { type: "string" } },
        perMsgMaxLen: { type: "integer", minimum: 1 },
      },
    },
  },
  config: {
    listAccountIds: (cfg) => listAwadaAccountIds(cfg),
    resolveAccount: (cfg, accountId) => resolveAwadaAccount({ cfg, accountId }),
    defaultAccountId: (cfg) => resolveDefaultAwadaAccountId(cfg),
    setAccountEnabled: ({ cfg, accountId: _accountId, enabled }) => ({
      ...cfg,
      channels: {
        ...cfg.channels,
        awada: {
          ...(cfg.channels?.awada as AwadaConfig | undefined),
          enabled,
        },
      },
    }),
    deleteAccount: ({ cfg, accountId: _accountId }) => {
      const next = { ...cfg } as ClawdbotConfig;
      const nextChannels = { ...cfg.channels };
      delete (nextChannels as Record<string, unknown>).awada;
      if (Object.keys(nextChannels).length > 0) {
        next.channels = nextChannels;
      } else {
        delete next.channels;
      }
      return next;
    },
    isConfigured: (account) => account.configured,
    describeAccount: (account) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
      relayBaseUrl: account.relayBaseUrl,
    }),
    resolveAllowFrom: ({ cfg, accountId }) => {
      const account = resolveAwadaAccount({ cfg, accountId });
      return (account.config?.allowFrom ?? []).map((entry) => String(entry));
    },
    formatAllowFrom: ({ allowFrom }) =>
      allowFrom
        .map((entry) => String(entry).trim())
        .filter(Boolean),
  },
  setup: {
    resolveAccountId: () => DEFAULT_ACCOUNT_ID,
    applyAccountConfig: ({ cfg, accountId: _accountId, input: _input }) => ({
      ...cfg,
      channels: {
        ...cfg.channels,
        awada: {
          ...(cfg.channels?.awada as AwadaConfig | undefined),
          enabled: true,
        },
      },
    }),
  },
  setupWizard: awadaSetupWizard,
  outbound: awadaOutbound,
  actions: awadaMessageActions,
  messaging: {
    targetResolver: {
      looksLikeId: (raw) => raw.startsWith("awada:"),
      resolveTarget: async ({ input }) => {
        const decoded = decodeAwadaTo(input);
        if (!decoded) return null;
        return { to: input, kind: "user" as const, source: "normalized" as const };
      },
    },
  },
  status: {
    defaultRuntime: createDefaultChannelRuntimeState(DEFAULT_ACCOUNT_ID, { port: null }),
    buildChannelSummary: ({ snapshot }) =>
      buildProbeChannelStatusSummary(snapshot, { port: null }),
    probeAccount: async ({ account }) =>
      probeAwada({ relayBaseUrl: account.relayBaseUrl, accountId: account.accountId }),
    buildAccountSnapshot: ({ account, runtime, probe }) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
      relayBaseUrl: account.relayBaseUrl,
      ...buildRuntimeAccountStatusSnapshot({ runtime, probe }),
      port: null,
    }),
  },
  gateway: {
    startAccount: async (ctx) => {
      const { monitorAwadaProvider } = await import("./monitor.js");
      ctx.log?.info(`starting awada[${ctx.accountId}]`);
      return monitorAwadaProvider({
        config: ctx.cfg,
        runtime: ctx.runtime,
        abortSignal: ctx.abortSignal,
        accountId: ctx.accountId,
      });
    },
  },
};
