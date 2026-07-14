/**
 * In-memory cache of outbound targets keyed by user_id_external.
 * Populated when inbound messages arrive; consumed by message actions
 * so handleAction can send to the correct peer without requiring the
 * full OutboundTarget in the tool params.
 */
import type { OutboundTarget } from "./redis-types.js";

const cache = new Map<string, OutboundTarget>();

export function cacheOutboundTarget(userIdExternal: string, target: OutboundTarget): void {
  cache.set(userIdExternal, target);
}

export function getCachedOutboundTarget(userIdExternal: string): OutboundTarget | undefined {
  return cache.get(userIdExternal);
}
