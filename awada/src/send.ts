import type {
  ContentObject,
  FileObject,
  ImageObject,
  OutboundMeta,
  OutboundTarget,
} from "./redis-types.js";

/**
 * Outbound send — POST /api/v1/awada/outbound?lane=<lane> to the relay gateway.
 * See docs/AWADA-CLIENT-TRANSPORT.md §3. The relay writes the event onto the outbound
 * Redis stream and the awada-server dispatcher delivers it back to the platform.
 *
 * `meta.platform` / `channel_id` / `user_id_external` are REQUIRED for the relay to route
 * the reply back to the platform. We build them from the cached OutboundTarget (which was
 * populated from the inbound event.meta) and override `source_event_id`.
 */
export type GatewaySendParams = {
  relayBaseUrl: string;
  ofbKey: string;
  lane: string;
  target: OutboundTarget;
  payload: ContentObject[];
  /** event_id of the inbound event that triggered this reply (for correlation/tracing). */
  sourceEventId?: string;
};

export function encodeAwadaTo(target: OutboundTarget): string {
  return `awada:${Buffer.from(JSON.stringify(target)).toString("base64")}`;
}

export function decodeAwadaTo(to: string): OutboundTarget | null {
  if (!to.startsWith("awada:")) return null;
  try {
    return JSON.parse(Buffer.from(to.slice(6), "base64").toString("utf8")) as OutboundTarget;
  } catch {
    return null;
  }
}

export function buildOutboundTarget(meta: {
  lane: string;
  tenant_id: string;
  channel_id: string;
  user_id_external: string;
  platform: string;
  conversation_id?: string;
}): OutboundTarget {
  const target: OutboundTarget = {
    platform: meta.platform,
    tenant_id: meta.tenant_id,
    lane: meta.lane,
    user_id_external: meta.user_id_external,
    channel_id: meta.channel_id,
  };
  if (meta.conversation_id) {
    target.conversation_id = meta.conversation_id;
  }
  return target;
}

/** Build the OutboundMeta required by POST /outbound from a target + source event id. */
export function buildOutboundMeta(target: OutboundTarget, sourceEventId?: string): OutboundMeta {
  const meta: OutboundMeta = {
    platform: target.platform,
    channel_id: target.channel_id,
    user_id_external: target.user_id_external,
  };
  if (target.tenant_id) meta.tenant_id = target.tenant_id;
  if (target.conversation_id) meta.session_id = target.conversation_id;
  if (sourceEventId) meta.source_event_id = sourceEventId;
  return meta;
}

function outboundUrl(relayBaseUrl: string, lane: string): string {
  const base = relayBaseUrl.trim().replace(/\/+$/, "");
  return `${base}/api/v1/awada/outbound?lane=${encodeURIComponent(lane)}`;
}

export async function postOutbound(params: GatewaySendParams): Promise<{ streamId: string; eventId: string }> {
  const { relayBaseUrl, ofbKey, lane, target, payload, sourceEventId } = params;
  const meta = buildOutboundMeta(target, sourceEventId);
  const res = await fetch(outboundUrl(relayBaseUrl, lane), {
    method: "POST",
    headers: {
      "X-OFB-Key": ofbKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ payload, meta }),
  });
  if (!res.ok) {
    let code: string | undefined;
    let message: string | undefined;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      code = body?.error?.code;
      message = body?.error?.message;
    } catch {
      // non-json error body
    }
    throw new Error(
      `[awada] outbound POST ${res.status}: ${code ?? message ?? res.statusText ?? "unknown"}`,
    );
  }
  const json = (await res.json()) as { data?: { streamId?: string; eventId?: string } };
  return {
    streamId: json.data?.streamId ?? "",
    eventId: json.data?.eventId ?? "",
  };
}

export async function sendTextToAwada(params: {
  relayBaseUrl: string;
  ofbKey: string;
  lane: string;
  target: OutboundTarget;
  text: string;
  sourceEventId?: string;
}): Promise<string> {
  const { relayBaseUrl, ofbKey, lane, target, text, sourceEventId } = params;
  const result = await postOutbound({
    relayBaseUrl,
    ofbKey,
    lane,
    target,
    payload: [{ type: "text", text }],
    sourceEventId,
  });
  return result.streamId;
}

/**
 * Send a media item (file, image, or audio) to the relay outbound endpoint.
 */
export async function sendMediaToAwada(params: {
  relayBaseUrl: string;
  ofbKey: string;
  lane: string;
  target: OutboundTarget;
  media: ContentObject;
  sourceEventId?: string;
}): Promise<string> {
  const { relayBaseUrl, ofbKey, lane, target, media, sourceEventId } = params;
  const result = await postOutbound({
    relayBaseUrl,
    ofbKey,
    lane,
    target,
    payload: [media],
    sourceEventId,
  });
  return result.streamId;
}

const IMAGE_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".webp",
  ".bmp",
  ".svg",
]);

/**
 * Build a ContentObject from a file_name (and optional file_id), for pre-stored
 * WeChat cloud files. Type is determined by extension: image extensions → ImageObject,
 * everything else → FileObject.
 */
export function buildMediaContentFromName(params: {
  file_name: string;
  file_id?: string;
}): ImageObject | FileObject {
  const { file_name, file_id } = params;
  const ext = file_name.slice(file_name.lastIndexOf(".")).toLowerCase();
  if (IMAGE_EXTENSIONS.has(ext)) {
    return {
      type: "image",
      file_name,
      ...(file_id ? { file_id } : {}),
    };
  }
  return {
    type: "file",
    file_name,
    ...(file_id ? { file_id } : {}),
  };
}

/**
 * Build a ContentObject from a URL.
 * file_name is extracted from the URL path; file_url is set to the URL.
 * Type is determined by extension: image extensions → ImageObject, everything else → FileObject.
 */
export function buildMediaContentFromUrl(url: string): ImageObject | FileObject {
  const pathname = new URL(url).pathname;
  const raw = pathname.split("/").pop() ?? "";
  const file_name = raw || "file";
  const ext = file_name.slice(file_name.lastIndexOf(".")).toLowerCase();
  if (IMAGE_EXTENSIONS.has(ext)) {
    return { type: "image", file_name, file_url: url };
  }
  return { type: "file", file_name, file_url: url };
}
