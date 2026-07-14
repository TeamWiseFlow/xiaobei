/** Persistent identity: freeze fingerprint/OS into a persistent dir.
 *
 * When a user launches with `--persistent <dir>`, a `camoufox-cli.json` file
 * is written on first launch capturing the generated fingerprint, OS, locale,
 * and derived timezone/geolocation. Subsequent launches reload it so the browser
 * reports the same device identity to every site.
 *
 * Fingerprint/OS/canvas+font seeds are frozen for the lifetime of the identity.
 * User-controllable fields (locale; proxy-derived timezone/geolocation) are
 * updated to match the command line whenever it's explicitly passed — so the
 * stored identity always reflects the most recent intent.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import type { Fingerprint } from "fingerprint-generator";
import { generateFingerprint } from "camoufox-js/dist/fingerprints.js";
import { publicIP, validIPv4, validIPv6 } from "camoufox-js/dist/ip.js";
import { getGeolocation } from "camoufox-js/dist/locale.js";
import { parseProxySettings } from "./proxy.js";

const IDENTITY_FILENAME = "camoufox-cli.json";
const IDENTITY_VERSION = 1;

export type HostOS = "windows" | "macos" | "linux";

export interface Identity {
  version: number;
  created_at: string;
  os: HostOS;
  locale: string | null;
  fingerprint: Fingerprint;
  config: Record<string, unknown>;
}

function hostOS(): HostOS {
  if (process.platform === "win32") return "windows";
  if (process.platform === "darwin") return "macos";
  return "linux";
}

function identityPath(persistentDir: string): string {
  return join(persistentDir, IDENTITY_FILENAME);
}

/**
 * Read a stable summary of the frozen identity (no generation, no mutation).
 *
 * Returns null when the persistent dir has no identity file yet (e.g. called
 * before the first launch that writes it). The fingerprint hash lets scripts
 * detect identity drift without hauling the full fingerprint around.
 */
export function readIdentitySummary(persistentDir: string): {
  os: HostOS;
  locale: string | null;
  fingerprintHash: string;
} | null {
  const p = identityPath(persistentDir);
  if (!existsSync(p)) return null;
  const identity = JSON.parse(readFileSync(p, "utf8")) as Identity;
  return {
    os: identity.os,
    locale: identity.locale,
    fingerprintHash: createHash("sha256")
      .update(JSON.stringify(identity.fingerprint))
      .digest("hex")
      .slice(0, 16),
  };
}

/**
 * Return the identity for this persistent directory.
 *
 * On first launch, a fresh identity is generated and written:
 *   - fingerprint: fingerprint-generator, firefox, host OS
 *   - canvas/font seeds: random, stored so future launches reproduce them
 *   - timezone/geolocation: derived via GeoIP if proxy is set and geoip=true
 *   - locale: recorded if passed on this first launch, else null
 *
 * On subsequent launches, `<persistentDir>/camoufox-cli.json` is loaded.
 * Fields the user explicitly passes on the command line overwrite the stored
 * values (`--locale`; `--proxy` + geoip re-derives timezone/geolocation).
 * Fingerprint, OS, and canvas/font seeds are never touched after first launch.
 */
export async function loadOrCreate(
  persistentDir: string,
  locale: string | null,
  proxy: string | null,
  geoip: boolean,
): Promise<Identity> {
  const path = identityPath(persistentDir);
  if (existsSync(path)) {
    const identity = JSON.parse(readFileSync(path, "utf8")) as Identity;
    const changed = await applyCliOverrides(identity, locale, proxy, geoip);
    if (changed) writeFileSync(path, JSON.stringify(identity, null, 2));
    return identity;
  }

  const os_ = hostOS();
  const fp = generateFingerprint(undefined, { operatingSystems: [os_] });

  const config: Record<string, unknown> = {
    "canvas:aaOffset": Math.floor(Math.random() * 101) - 50,
    "canvas:aaCapOffset": Math.random() < 0.5,
    "fonts:spacing_seed": Math.floor(Math.random() * 0x1_0000_0000),
  };

  if (proxy && geoip) {
    mergeGeo(config, await geolocateProxy(proxy));
  }

  const identity: Identity = {
    version: IDENTITY_VERSION,
    created_at: new Date().toISOString(),
    os: os_,
    locale,
    fingerprint: fp,
    config,
  };

  mkdirSync(persistentDir, { recursive: true });
  writeFileSync(path, JSON.stringify(identity, null, 2));
  return identity;
}

/** Mutate identity with CLI-passed values. Return true if anything changed. */
async function applyCliOverrides(
  identity: Identity,
  locale: string | null,
  proxy: string | null,
  geoip: boolean,
): Promise<boolean> {
  let changed = false;

  if (locale !== null && identity.locale !== locale) {
    identity.locale = locale;
    changed = true;
  }

  if (proxy && geoip) {
    if (!identity.config) identity.config = {};
    const derived = await geolocateProxy(proxy);
    if (mergeGeo(identity.config, derived)) changed = true;
  }

  return changed;
}

/** Merge proxy-derived geo into config. Return true if anything changed. */
function mergeGeo(config: Record<string, unknown>, derived: GeoInfo | null): boolean {
  if (!derived) return false;
  let changed = false;
  if (derived.timezone && config["timezone"] !== derived.timezone) {
    config["timezone"] = derived.timezone;
    changed = true;
  }
  if (derived.latitude !== undefined && derived.longitude !== undefined) {
    if (config["geolocation:latitude"] !== derived.latitude) {
      config["geolocation:latitude"] = derived.latitude;
      changed = true;
    }
    if (config["geolocation:longitude"] !== derived.longitude) {
      config["geolocation:longitude"] = derived.longitude;
      changed = true;
    }
    if (derived.accuracy !== undefined && config["geolocation:accuracy"] !== derived.accuracy) {
      config["geolocation:accuracy"] = derived.accuracy;
      changed = true;
    }
  }
  return changed;
}

/**
 * Translate identity into kwargs for Camoufox / launchOptions.
 *
 * Returns fingerprint/os/config (always) and locale (when set). Does NOT
 * set persistent_context / user_data_dir — the caller handles those.
 */
export function toLaunchOptions(identity: Identity): Record<string, unknown> {
  const opts: Record<string, unknown> = {
    fingerprint: identity.fingerprint,
    os: identity.os,
    config: { ...(identity.config || {}) },
  };

  if (identity.locale) {
    const parts = identity.locale.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length > 0) {
      opts.locale = parts.length > 1 ? parts : parts[0];
    }
  }

  return opts;
}

interface GeoInfo {
  timezone?: string;
  latitude?: number;
  longitude?: number;
  accuracy?: number;
}

/** Return {timezone, latitude, longitude, accuracy?} from the proxy's public
 * IP, or null if anything fails. */
async function geolocateProxy(proxyUrl: string): Promise<GeoInfo | null> {
  try {
    const ip = await publicIP(proxyUrlWithAuth(proxyUrl));
    if (!validIPv4(ip) && !validIPv6(ip)) return null;
    const geo = await getGeolocation(ip);
    const out: GeoInfo = {
      timezone: geo.timezone,
      latitude: geo.latitude,
      longitude: geo.longitude,
    };
    if (geo.accuracy !== undefined) out.accuracy = geo.accuracy;
    return out;
  } catch {
    return null;
  }
}

/** Rebuild proxy URL as scheme://user:pass@host:port for publicIP(). */
function proxyUrlWithAuth(proxyUrl: string): string {
  const settings = parseProxySettings(proxyUrl).proxy;
  if (!settings.username) return settings.server;
  const url = new URL(settings.server);
  url.username = encodeURIComponent(settings.username);
  url.password = encodeURIComponent(settings.password ?? "");
  return url.href;
}
