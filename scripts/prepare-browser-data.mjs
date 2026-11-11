#!/usr/bin/env node
// Ship pinned GeoIP and uBlock data so customer installation needs neither upstream.
import { existsSync, mkdirSync, mkdtempSync, renameSync, rmSync, copyFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { targetLock as lock } from "../browser/scripts/asset-paths.mjs";
import { downloadAsset, verify } from "../browser/scripts/download-asset.mjs";
import { githubDownloadUrl } from "../browser/scripts/download-network.mjs";

async function prepareAsset(output, pin, name) {
  const directory = resolve(output);
  mkdirSync(directory, { recursive: true });
  const file = join(directory, name);
  if (existsSync(file)) {
    await verify(file, pin.sha256);
    return file;
  }
  const stage = mkdtempSync(join(directory, ".browser-data-"));
  try {
    const partial = join(stage, name);
    const cache = process.env.XIAOBEI_BROWSER_DOWNLOADS || process.env.XIAOBEI_CACHE_DIR || join(homedir(), ".xiaobei", "cache");
    const cached = join(cache, new URL(pin.url).pathname.split("/").pop());
    if (existsSync(cached)) {
      await verify(cached, pin.sha256);
      copyFileSync(cached, partial);
    } else {
      await downloadAsset(githubDownloadUrl(pin.url), partial, pin.sha256);
    }
    renameSync(partial, file);
    return file;
  } finally {
    rmSync(stage, { recursive: true, force: true });
  }
}

export async function prepareBrowserData(output) {
  const geoip = await prepareAsset(output, lock.geoip, `geoip-aio-all-${lock.geoip.version}.mmdb`);
  const ublock = await prepareAsset(output, lock.ubo, `ublock_origin-${lock.ubo.version}.xpi`);
  return [geoip, ublock];
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== "--output") {
    console.error("Usage: node scripts/prepare-browser-data.mjs --output DIRECTORY");
    process.exitCode = 2;
  } else {
    prepareBrowserData(args[1]).then(files => {
      for (const file of files) console.log(`Bundled browser data: ${file}`);
    }).catch(error => {
      console.error(error.message);
      process.exitCode = 1;
    });
  }
}
