/**
 * Minimal subset of the awada Redis protocol types needed by this extension.
 * Mirrors awada-server/src/infrastructure/redis/types.ts without importing from it.
 */

export type InboundEventType = "MESSAGE_NEW" | "PAYMENT_SUCCESS" | "BUTTON_CLICK";
export type OutboundEventType = "REPLY_MESSAGE" | "COMMAND_EXECUTE";

export interface TextObject {
  type: "text";
  text: string;
}

export interface ImageObject {
  type: "image";
  file_name: string;
  file_url?: string;
  file_id?: string;
}

export interface AudioObject {
  type: "audio";
  file_path?: string;
  file_url?: string;
  file_id?: string;
}

export interface FileObject {
  type: "file";
  file_name: string;
  file_url?: string;
  file_id?: string;
}

export type ContentObject = TextObject | ImageObject | AudioObject | FileObject;
export type Payload = ContentObject[];

export interface InboundMeta {
  platform: string;
  tenant_id: string;
  channel_id: string;
  lane: string;
  actor_type: string;
  user_id_external: string;
  session_id: string;
  session_seq: number;
  source_message_id: string;
  raw_ref?: string;
  conversation_id?: string;
}

export interface InboundEvent {
  schema_version: number;
  event_id: string;
  type: InboundEventType;
  timestamp: number;
  correlation_id: string;
  trace_id: string;
  meta: InboundMeta;
  payload: Payload;
}

export interface OutboundTarget {
  platform: string;
  tenant_id: string;
  lane: string;
  user_id_external: string;
  channel_id: string;
  reply_token?: string;
  conversation_id?: string;
  action_ask?: [number, string[]];
}

export interface OutboundEvent {
  schema_version: number;
  event_id: string;
  reply_to_event_id: string;
  type: OutboundEventType;
  timestamp: number;
  correlation_id: string;
  trace_id: string;
  target: OutboundTarget;
  payload: Payload;
}

/**
 * Meta sent on POST /outbound (and WS reply frames) — see docs/AWADA-CLIENT-TRANSPORT.md §3.
 * `platform` / `channel_id` / `user_id_external` are REQUIRED: relay routes the reply back to
 * the platform solely from these fields (it does NOT reverse-lookup the inbound by source_event_id).
 * The simplest correct construction is to passthrough the inbound `event.meta` and override
 * `source_event_id` with the inbound `event_id`.
 */
export interface OutboundMeta {
  platform: string;
  channel_id: string;
  user_id_external: string;
  tenant_id?: string;
  session_id?: string;
  /** event_id of the inbound event that triggered this reply (reply correlation / tracing). */
  source_event_id?: string;
  /** Platform-native message id to reply to (e.g. 企微 reply_to). */
  reply_to_message_id?: string;
}
