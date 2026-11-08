import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export const targetLock = JSON.parse(readFileSync(new URL("../assets.lock.json", import.meta.url), "utf8"));
function installedLock() {
  // Source can be updated before the user runs the installer. Keep an already
  // installed older SDK on its paired assets until npm ci performs the cutover.
  try {
    const version = JSON.parse(readFileSync(new URL("../node_modules/camoufox/package.json", import.meta.url), "utf8")).version;
    if (version !== targetLock.sdk.version && /^\d+\.\d+\.\d+$/.test(version)) {
      const previous = JSON.parse(readFileSync(new URL(`../asset-locks/${version}.json`, import.meta.url), "utf8"));
      if (previous.sdk.name === "camoufox" && previous.sdk.version === version) return previous;
    }
  } catch {}
  return targetLock;
}
export const lock = installedLock();
// fpgen-js 1.3.0 shares this stamped model layout with the SDK's former port.
// This check is read-only: doctor/start must not call an installer or download.
export function fingerprintModelInstalled(directory) {
  try {
    if (readFileSync(join(directory, ".pinned-model"), "utf8").trim() !== lock.model.sha256) return false;
    return [...lock.model.files, "values.dat"].every(name => {
      const info = statSync(join(directory, name));
      return info.isFile() && info.size > 0;
    });
  } catch { return false; }
}
export function assetPaths() {
  const home = resolve(process.env.XIAOBEI_BROWSER_HOME || join(homedir(), ".camoufox-cli"));
  const directory = resolve(process.env.XIAOBEI_BROWSER_ASSETS || join(process.env.CAMOUFOX_INSTALL_DIR || home, "assets", `${lock.version}-${lock.release}`));
  return {
    directory,
    launcher: join(directory, process.platform === "darwin" ? "Camoufox.app/Contents/MacOS/camoufox" : process.platform === "win32" ? "camoufox.exe" : "camoufox-bin"),
    addon: join(directory, ...(process.platform === "darwin" && lock.ubo.bundled ? ["Camoufox.app", "Contents", "Resources"] : []), "addons", "UBO"),
    model: join(directory, "fpgen"),
    geoip: join(directory, `geoip-aio-all-${lock.geoip.version}.mmdb`),
  };
}
