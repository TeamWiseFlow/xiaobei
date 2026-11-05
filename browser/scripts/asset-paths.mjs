import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export const lock = JSON.parse(readFileSync(new URL("../assets.lock.json", import.meta.url), "utf8"));
export function assetPaths() {
  const home = resolve(process.env.XIAOBEI_BROWSER_HOME || join(homedir(), ".camoufox-cli"));
  const directory = resolve(process.env.XIAOBEI_BROWSER_ASSETS || join(process.env.CAMOUFOX_INSTALL_DIR || home, "assets", `${lock.version}-${lock.release}`));
  return {
    directory,
    launcher: join(directory, process.platform === "darwin" ? "Camoufox.app/Contents/MacOS/camoufox" : process.platform === "win32" ? "camoufox.exe" : "camoufox-bin"),
    addon: join(directory, "addons", "UBO"),
    model: join(directory, "fpgen"),
    geoip: join(directory, `geoip-aio-all-${lock.geoip.version}.mmdb`),
  };
}
