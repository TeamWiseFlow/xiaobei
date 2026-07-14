import type { ClawdbotConfig, RuntimeEnv } from "openclaw/plugin-sdk";
import { resolveAwadaAccount } from "./accounts.js";
import { handleAwadaMessage } from "./message-handler.js";
import { runGatewayClient } from "./transport.js";

export type MonitorAwadaOpts = {
  config?: ClawdbotConfig;
  runtime?: RuntimeEnv;
  abortSignal?: AbortSignal;
  accountId?: string;
};

/**
 * Monitor an awada lane via the relay gateway WS inbound channel.
 * Replaces the former direct-Redis XREADGROUP consumer — the bot now reads inbound
 * exclusively through the relay gateway (docs/AWADA-CLIENT-TRANSPORT.md §4).
 */
export async function monitorAwadaProvider(opts: MonitorAwadaOpts = {}): Promise<void> {
  const { config: cfg, runtime, abortSignal, accountId } = opts;
  if (!cfg) throw new Error("Config is required for awada monitor");

  const account = resolveAwadaAccount({ cfg, accountId });
  if (!account.enabled || !account.configured || !account.relayBaseUrl || !account.ofbKey) {
    throw new Error("Awada channel not enabled or configured (missing relayBaseUrl/ofbKey)");
  }

  const log = runtime?.log ?? console.log;
  const error = runtime?.error ?? console.error;
  const resolvedAccountId = account.accountId;

  await runGatewayClient({
    relayBaseUrl: account.relayBaseUrl,
    ofbKey: account.ofbKey,
    lane: account.lane,
    abortSignal,
    log,
    error,
    onEvent: async (id, event) => {
      await handleAwadaMessage({ cfg, event, runtime, accountId: resolvedAccountId });
    },
  });
}
