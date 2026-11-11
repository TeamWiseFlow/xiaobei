export const lock: {
  sdk: { name: string; version: string };
  version: string; release: string;
  model: { sha256: string; files: string[] };
  ubo: { version: string };
};
export const targetLock: typeof lock;
export function assetPaths(): { directory: string; launcher: string; addon: string; model: string; geoip: string };
export function fingerprintModelInstalled(directory: string): boolean;
