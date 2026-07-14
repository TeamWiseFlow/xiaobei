import type { AwadaProbeResult } from "./types.js";

const PROBE_TIMEOUT_MS = 5000;

export function validateAwadaRelayBaseUrl(relayBaseUrl: string): string | null {
  const value = relayBaseUrl.trim();
  if (!value) {
    return "missing relayBaseUrl";
  }
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return "invalid relayBaseUrl format";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "invalid relayBaseUrl protocol (expected http:// or https://)";
  }
  if (!parsed.hostname) {
    return "invalid relayBaseUrl host";
  }
  return null;
}

/**
 * Probe relay gateway connectivity for an awada account.
 * Hits GET /api/v1/awada/health (no auth). Returns ok=true if the gateway is reachable
 * and its Redis is up. Auth (OFB_KEY + lane scope) is verified on the first real call.
 */
export async function probeAwada(params: {
  relayBaseUrl?: string;
  accountId?: string;
}): Promise<AwadaProbeResult> {
  const { relayBaseUrl } = params;

  if (!relayBaseUrl) {
    return { ok: false, error: "missing relayBaseUrl" };
  }

  const normalized = relayBaseUrl.trim();
  const validationError = validateAwadaRelayBaseUrl(normalized);
  if (validationError) {
    return { ok: false, relayBaseUrl: normalized, error: validationError };
  }

  const url = `${normalized.replace(/\/+$/, "")}/api/v1/awada/health`;
  try {
    const res = await fetch(url, {
      method: "GET",
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    if (!res.ok) {
      return { ok: false, relayBaseUrl: normalized, error: `health ${res.status} ${res.statusText}` };
    }
    const json = (await res.json()) as { data?: { redis?: boolean } };
    if (!json?.data?.redis) {
      return { ok: false, relayBaseUrl: normalized, error: "relay reachable but redis down" };
    }
    return { ok: true, relayBaseUrl: normalized };
  } catch (err) {
    return {
      ok: false,
      relayBaseUrl: normalized,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}
