import { DEFAULT_ACCOUNT_ID } from "openclaw/plugin-sdk/channel-plugin-common";
import type { ClawdbotConfig } from "openclaw/plugin-sdk";
import type { AwadaConfig, ResolvedAwadaAccount } from "./types.js";

const DEFAULT_LANE = "user";

function getAwadaCfg(cfg: ClawdbotConfig): AwadaConfig | undefined {
  return cfg.channels?.awada as AwadaConfig | undefined;
}

export function resolveAwadaAccount(params: {
  cfg: ClawdbotConfig;
  accountId?: string | null;
}): ResolvedAwadaAccount {
  const awadaCfg = getAwadaCfg(params.cfg);
  const accountId = params.accountId?.trim() || DEFAULT_ACCOUNT_ID;
  const enabled = awadaCfg?.enabled !== false;
  const relayBaseUrl = awadaCfg?.relayBaseUrl?.trim() || undefined;
  const ofbKey = awadaCfg?.ofbKey?.trim() || undefined;
  // Configured only when both relay endpoint and key are present.
  const configured = Boolean(relayBaseUrl && ofbKey);

  return {
    accountId,
    enabled,
    configured,
    relayBaseUrl,
    ofbKey,
    lane: awadaCfg?.lane?.trim() || DEFAULT_LANE,
    platform: awadaCfg?.platform?.trim() || undefined,
    config: awadaCfg ?? {},
  };
}

export function listAwadaAccountIds(_cfg: ClawdbotConfig): string[] {
  return [DEFAULT_ACCOUNT_ID];
}

export function resolveDefaultAwadaAccountId(_cfg: ClawdbotConfig): string {
  return DEFAULT_ACCOUNT_ID;
}
