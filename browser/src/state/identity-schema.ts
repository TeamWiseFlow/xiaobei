import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { isObject, RuntimeError } from "../protocol/index.js";

export const IDENTITY_FILENAME = "camoufox-cli.json";
export const IDENTITY_VERSION = 2;
export const SDK = "camoufox@0.5.9";
// sdk records the identity's creator, not its most recent browser launch.
// These releases share v2/fpgen 1.3.0 and model-2/2026; keep the original
// fingerprint and creation tag instead of relabelling or redrawing it.
const COMPATIBLE_SDKS = new Set(["camoufox@0.5.8", SDK]);
export type HostOS = "windows" | "macos" | "linux";
export interface Identity {
  version: number; sdk: string; created_at: string; os: HostOS; locale: string | null;
  fingerprint: Record<string, unknown>; config: Record<string, unknown>;
}
export function hostOS(): HostOS {
  return process.platform === "win32" ? "windows" : process.platform === "darwin" ? "macos" : "linux";
}
export function validateProfile(directory: string): Identity | null {
  const path = join(directory, IDENTITY_FILENAME);
  const reset = () => new RuntimeError("PROFILE_RESET_REQUIRED", "Profile has an older, missing or invalid identity. Stop its session, archive the whole profile, then create a fresh profile and log in again.");
  if (!existsSync(path)) {
    if (existsSync(directory) && readdirSync(directory).some(name => name !== ".xiaobei-runtime")) throw reset();
    return null;
  }
  let identity: unknown;
  try { identity = JSON.parse(readFileSync(path, "utf8")); } catch { throw reset(); }
  if (!isObject(identity) || identity.version !== IDENTITY_VERSION || !COMPATIBLE_SDKS.has(identity.sdk as string) || identity.os !== hostOS() ||
      !isObject(identity.fingerprint) || !isObject(identity.fingerprint.navigator) || !isObject(identity.config) ||
      !(identity.locale === null || typeof identity.locale === "string")) throw reset();
  return identity as unknown as Identity;
}
