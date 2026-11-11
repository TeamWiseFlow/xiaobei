/** All version-sensitive SDK imports live here. Assets are installed explicitly. */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Reader } from "maxmind";
import { NewBrowser, type NewBrowserOptions } from "camoufox";
import { LIBRARY_VERSION } from "camoufox/dist/__version__.js";
import { generateFingerprint } from "camoufox/dist/fingerprints.js";
import { MODEL_PIN, setModelDir } from "fpgen-js";
import { publicIP, validIPv4, validIPv6 } from "camoufox/dist/ip.js";
import { Geolocation, SELECTOR } from "camoufox/dist/locales.js";
import { firefox, type Browser, type BrowserContext } from "playwright-core";
import { assetPaths, fingerprintModelInstalled, lock } from "../../scripts/asset-paths.mjs";
import { RuntimeError } from "../protocol/index.js";
import { parseProxySettings } from "../state/proxy.js";

export { assetPaths, lock };
export function assetStatus() {
  const paths = assetPaths();
  let version: string | null = null;
  let addonInstalled = false;
  try { const v = JSON.parse(readFileSync(join(paths.directory, "version.json"), "utf8")); version = `${v.version}-${v.release}`; } catch {}
  try { addonInstalled = JSON.parse(readFileSync(join(paths.addon, "manifest.json"), "utf8")).version === lock.ubo.version; } catch {}
  return { ...paths, installed: existsSync(paths.launcher), version,
    versionMatches: version === `${lock.version}-${lock.release}`,
    modelInstalled: fingerprintModelInstalled(paths.model),
    geoipInstalled: existsSync(paths.geoip), addonInstalled };
}
export function requireAssets(geoip = false): ReturnType<typeof assetPaths> {
  const status = assetStatus();
  if (!status.installed || !status.versionMatches || !status.addonInstalled || !status.modelInstalled || (geoip && !status.geoipInstalled))
    throw new RuntimeError("ASSET_MISSING", "Pinned Camoufox/browser model/addon or requested GeoIP asset missing; run xiaobei-browser install before starting");
  if (lock.sdk.name !== "camoufox" || LIBRARY_VERSION !== lock.sdk.version || MODEL_PIN.sha256 !== lock.model.sha256)
    throw new RuntimeError("ASSET_MISSING", "SDK or fingerprint model differs from assets.lock.json");
  // The SDK configures fpgen during module import; changing an env var afterwards
  // leaves it pointing at the SDK cache. Set the public model directory explicitly.
  setModelDir(status.model);
  return status;
}
export function newFingerprint(os: string, window?: [number, number] | null): Record<string, unknown> {
  requireAssets();
  return generateFingerprint({ os, ...(window ? { window } : {}) });
}
export async function launchBrowser(options: NewBrowserOptions): Promise<Browser | BrowserContext> {
  const paths = requireAssets();
  // Explicit paths and an installed fpgen model prevent SDK auto-install paths.
  // NewBrowser also applies the SDK's viewport/media defaults for persistent contexts.
  return NewBrowser(firefox, { ...options, executable_path: paths.launcher,
    addons: [paths.addon], exclude_addons: ["UBO"], geoip: false });
}
export async function proxyGeo(proxy: string, previous: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  const paths = requireAssets(true);
  const settings = parseProxySettings(proxy).proxy;
  const url = new URL(settings.server);
  if (settings.username) { url.username = settings.username; url.password = settings.password ?? ""; }
  const ip = await publicIP(url.href);
  if (!validIPv4(ip) && !validIPv6(ip)) throw new RuntimeError("INVALID_STATE", "Proxy public IP is invalid");
  // Read only the pinned local database. The SDK's default GeoIP path refreshes online.
  const reader = new Reader<any>(readFileSync(paths.geoip));
  const record = reader.get(ip);
  const region = record?.country?.iso_code;
  const location = record?.location;
  if (typeof region !== "string" || typeof location?.time_zone !== "string" ||
      !Number.isFinite(location?.longitude) || !Number.isFinite(location?.latitude))
    throw new RuntimeError("INVALID_STATE", "Proxy GeoIP record lacks country, timezone or coordinates");
  const locale = await SELECTOR.fromRegion(region);
  const config = new Geolocation(locale, location.longitude, location.latitude, location.time_zone).asConfig();
  if (previous["locale:region"] === region)
    for (const key of ["locale:language", "locale:region", "locale:script"]) if (key in previous) config[key] = previous[key];
  config[validIPv4(ip) ? "webrtc:ipv4" : "webrtc:ipv6"] = ip;
  return config;
}
