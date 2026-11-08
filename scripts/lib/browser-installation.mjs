import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Read-only verification shared by source, tarball and Docker installation.
// Never launch a browser, redraw an identity, or touch a user's profile here.
export async function verifyBrowserInstallation(root, { assets = true } = {}) {
  const directory = join(root, "browser");
  const json = path => JSON.parse(readFileSync(path, "utf8"));
  const manifest = json(join(directory, "package.json"));
  const lock = json(join(directory, "assets.lock.json"));
  for (const name of ["camoufox", "fpgen-js", "playwright-core"]) {
    const expected = manifest.dependencies[name];
    const installed = json(join(directory, "node_modules", name, "package.json")).version;
    if (!expected || installed !== expected)
      throw new Error(`Browser dependency ${name}: expected ${expected}, installed ${installed}`);
  }
  if (lock.sdk.name !== "camoufox" || lock.sdk.version !== manifest.dependencies.camoufox)
    throw new Error("Browser SDK pin differs between package.json and assets.lock.json");
  const identity = await import(pathToFileURL(join(directory, "dist/state/identity-schema.js")));
  if (identity.SDK !== `camoufox@${lock.sdk.version}`)
    throw new Error("Built browser identity schema differs from the installed SDK; rebuild the browser");
  // Importing also detects incompatible SDK entry points in a stale dist.
  const driver = await import(pathToFileURL(join(directory, "dist/driver/sdk.js")));
  if (assets) driver.requireAssets(true);
  return {
    sdk: lock.sdk.version,
    playwright: manifest.dependencies["playwright-core"],
    fpgen: manifest.dependencies["fpgen-js"],
    browser: `${lock.version}-${lock.release}`,
    assetsChecked: assets,
  };
}
