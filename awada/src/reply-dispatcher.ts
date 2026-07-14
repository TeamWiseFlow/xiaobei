import type { ClawdbotConfig, RuntimeEnv } from "openclaw/plugin-sdk";
import { getAwadaRuntime } from "./runtime.js";
import type { FileObject, OutboundTarget } from "./redis-types.js";
import { buildMediaContentFromUrl, sendMediaToAwada, sendTextToAwada } from "./send.js";
import { stripThinkingFromText } from "./strip-thinking.js";
import { isNoReplyText } from "./silent-reply.js";
import type { AwadaConfig } from "./types.js";

/**
 * Regex to detect [SEND_FILE]{"file_id":"...","file_name":"..."}[/SEND_FILE] tags in reply text.
 * Agent uses this convention to request file delivery via awada outbound.
 */
const SEND_FILE_RE = /\[SEND_FILE\]\s*(\{[^}]+\})\s*\[\/SEND_FILE\]/g;

export type CreateAwadaReplyDispatcherParams = {
  cfg: ClawdbotConfig;
  agentId: string;
  runtime: RuntimeEnv;
  relayBaseUrl: string;
  ofbKey: string;
  lane: string;
  target: OutboundTarget;
  inboundEventId: string;
  correlationId: string;
  traceId: string;
  accountId?: string;
};

export function formatAwadaReplyRecipient(target: OutboundTarget): string {
  const userExternalId = target.user_id_external?.trim() ?? "";
  const channelId = target.channel_id?.trim() ?? "";
  if (!channelId) {
    return userExternalId || "[unknown-channel]";
  }
  if (!userExternalId) {
    return `[${channelId}]`;
  }
  return `${userExternalId}[${channelId}]`;
}

export function createAwadaReplyDispatcher(params: CreateAwadaReplyDispatcherParams) {
  const {
    cfg,
    runtime,
    relayBaseUrl,
    ofbKey,
    lane,
    target,
    inboundEventId,
    accountId,
  } = params;
  // correlationId / traceId are retained in the params type for caller compatibility but
  // are not used at the transport layer — relay derives correlation/trace from source_event_id.
  const log = runtime?.log ?? console.log;
  const error = runtime?.error ?? console.error;
  const core = getAwadaRuntime();

  const pendingSends: Promise<void>[] = [];
  let idleResolve: (() => void) | null = null;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _idlePromise = new Promise<void>((resolve) => {
    idleResolve = resolve;
  });

  const textChunkLimit = core.channel.text.resolveTextChunkLimit(cfg, "awada", accountId, {
    fallbackLimit: 2000,
  });

  const awadaCfg = cfg.channels?.awada as AwadaConfig | undefined;
  const effectiveChunkLimit = awadaCfg?.perMsgMaxLen ?? textChunkLimit;

  const queueSend = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const chunks =
      trimmed.length > effectiveChunkLimit
        ? core.channel.text.chunkMarkdownText(trimmed, effectiveChunkLimit)
        : [trimmed];
    for (const chunk of chunks) {
      const p = sendTextToAwada({
        relayBaseUrl,
        ofbKey,
        lane,
        target,
        text: chunk,
        sourceEventId: inboundEventId,
      })
        .then(() => {
          log(
            `awada[${accountId ?? "default"}]: reply sent to ${formatAwadaReplyRecipient(target)}`,
          );
        })
        .catch((err) => {
          error(`awada[${accountId ?? "default"}]: send failed: ${String(err)}`);
        });
      pendingSends.push(p);
    }
  };

  const queueMediaSend = (url: string) => {
    const media = buildMediaContentFromUrl(url);
    const p = sendMediaToAwada({
      relayBaseUrl,
      ofbKey,
      lane,
      target,
      media,
      sourceEventId: inboundEventId,
    })
      .then(() => {
        log(
          `awada[${accountId ?? "default"}]: media sent to ${formatAwadaReplyRecipient(target)} (${media.type})`,
        );
      })
      .catch((err) => {
        error(`awada[${accountId ?? "default"}]: media send failed: ${String(err)}`);
      });
    pendingSends.push(p);
  };

  const queueFileSend = (fileId: string, fileName: string) => {
    const media: FileObject = { type: "file", file_id: fileId, file_name: fileName };
    const p = sendMediaToAwada({
      relayBaseUrl,
      ofbKey,
      lane,
      target,
      media,
      sourceEventId: inboundEventId,
    })
      .then(() => {
        log(
          `awada[${accountId ?? "default"}]: file sent to ${formatAwadaReplyRecipient(target)} (${fileName})`,
        );
      })
      .catch((err) => {
        error(`awada[${accountId ?? "default"}]: file send failed: ${String(err)}`);
      });
    pendingSends.push(p);
  };

  /**
   * Extract [SEND_FILE]...[\SEND_FILE] tags from text, queue file sends,
   * and return the remaining text with tags stripped.
   */
  const extractAndSendFiles = (text: string): string => {
    const remaining = text.replace(SEND_FILE_RE, (_, jsonStr: string) => {
      try {
        const parsed = JSON.parse(jsonStr) as { file_id?: string; file_name?: string };
        const fileId = parsed.file_id?.trim();
        const fileName = parsed.file_name?.trim();
        if (fileId && fileName) {
          queueFileSend(fileId, fileName);
        } else {
          error(`awada[${accountId ?? "default"}]: [SEND_FILE] missing file_id or file_name`);
        }
      } catch {
        error(`awada[${accountId ?? "default"}]: [SEND_FILE] invalid JSON: ${jsonStr}`);
      }
      return ""; // strip the tag from text
    });
    return remaining;
  };

  const dispatcher = {
    sendFinalReply(payload: {
      text?: string;
      mediaUrl?: string;
      mediaUrls?: string[];
      isError?: boolean;
      isFallbackNotice?: boolean;
      isStatusNotice?: boolean;
      isCompactionNotice?: boolean;
    }): boolean {
      // Suppress internal notices and error warnings (model fallback, compaction,
      // tool-call failures, etc.) from external-facing channels — end users
      // should never see these.
      if (payload.isError || payload.isFallbackNotice || payload.isStatusNotice || payload.isCompactionNotice) {
        return true;
      }
      // Handle media attachments (URL-based)
      if (payload?.mediaUrl) queueMediaSend(payload.mediaUrl);
      if (payload?.mediaUrls) {
        for (const url of payload.mediaUrls) {
          queueMediaSend(url);
        }
      }
      // Handle text — strip leaked thinking tags, extract [SEND_FILE] tags, then send
      let text = stripThinkingFromText(payload?.text ?? "");
      text = extractAndSendFiles(text);
      if (isNoReplyText(text)) {
        return true;
      }
      if (text.trim()) queueSend(text);
      return true;
    },
    sendBlockReply(_payload: { text?: string }): boolean {
      // Awada doesn't support streaming/progressive blocks — skip partial blocks
      return false;
    },
    sendToolResult(_payload: unknown): boolean {
      return false;
    },
    async waitForIdle(): Promise<void> {
      await Promise.all(pendingSends);
    },
    getQueuedCounts() {
      return { tool: 0, block: 0, final: pendingSends.length };
    },
    getFailedCounts() {
      return { tool: 0, block: 0, final: 0 };
    },
    markComplete() {
      idleResolve?.();
    },
  };

  const markDispatchIdle = () => {
    idleResolve?.();
  };

  return { dispatcher, markDispatchIdle, textChunkLimit };
}
