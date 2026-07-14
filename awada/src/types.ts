import type { BaseProbeResult } from "openclaw/plugin-sdk/core";
import type { AwadaConfigSchema, z } from "./config-schema.js";

export type AwadaConfig = z.infer<typeof AwadaConfigSchema>;

export type ResolvedAwadaAccount = {
  accountId: string;
  enabled: boolean;
  configured: boolean;
  relayBaseUrl?: string;
  ofbKey?: string;
  lane: string;
  platform?: string;
  config: AwadaConfig;
};

export type AwadaProbeResult = BaseProbeResult<string> & {
  relayBaseUrl?: string;
};

/** Parsed inbound message context extracted from an InboundEvent */
export type AwadaMessageContext = {
  /** user_id_external from awada meta */
  userId: string;
  /** session_id from awada meta */
  sessionId: string;
  /** event_id of the inbound event */
  eventId: string;
  /** source_message_id */
  sourceMessageId: string;
  /** lane name */
  lane: string;
  /** tenant_id */
  tenantId: string;
  /** channel_id */
  channelId: string;
  /** platform */
  platform: string;
  /** Extracted text content from payload */
  text: string;
  /** Actor type */
  actorType: string;
  /** correlation_id for reply */
  correlationId: string;
  /** trace_id */
  traceId: string;
  /** Raw payload for reference */
  rawPayload: unknown[];
};
