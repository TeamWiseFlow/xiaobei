// Resolve latest only during explicit preparation; ship the verified snapshot.
import {
  existsSync, readFileSync, mkdirSync, mkdtempSync, writeFileSync,
  copyFileSync, renameSync, rmSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { homedir } from "node:os";
import { downloadAsset, verify } from "./download-asset.mjs";
import { githubDownloadUrl } from "./download-network.mjs";

export const geoipName = "geoip-aio-all-latest.mmdb";
export const geoipMetadataName = `${geoipName}.json`;
const releaseRoot = "https://github.com/daijro/geoip-all-in-one/releases/download/";

function validate(snapshot) {
  if (!snapshot || typeof snapshot.version !== "string" || !/^[\w.-]{1,128}$/.test(snapshot.version) ||
      !/^[a-f0-9]{64}$/.test(snapshot.sha256 || "") ||
      snapshot.url !== `${releaseRoot}${snapshot.version}/geoip-aio-all.mmdb`)
    throw new Error("Invalid GeoIP snapshot metadata");
  return snapshot;
}

async function readSnapshot(directory) {
  const file = join(directory, geoipName), metadata = join(directory, geoipMetadataName);
  if (!existsSync(file) && !existsSync(metadata)) return null;
  if (!existsSync(file) || !existsSync(metadata)) throw new Error("Incomplete GeoIP snapshot");
  const snapshot = validate(JSON.parse(readFileSync(metadata, "utf8")));
  await verify(file, snapshot.sha256);
  return snapshot;
}

export async function latestGeoip(pin) {
  const api = "https://api.github.com/repos/daijro/geoip-all-in-one/releases/latest";
  if (pin.releaseApi !== api) throw new Error("Invalid GeoIP latest release API");
  const url = githubDownloadUrl(api);
  const headers = { Accept: "application/vnd.github+json" };
  // Installation proxies receive no GitHub credentials.
  if (url === api && process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  const response = await fetch(url, { headers, signal: AbortSignal.timeout(30000) });
  if (!response.ok) throw new Error(`Latest GeoIP release lookup failed: HTTP ${response.status}`);
  const release = await response.json();
  const asset = release.assets?.find(item => item.name === "geoip-aio-all.mmdb");
  if (release.draft || release.prerelease || !asset || !/^sha256:[a-f0-9]{64}$/.test(asset.digest || ""))
    throw new Error("Latest GeoIP release lacks the database or its SHA-256 digest");
  return validate({ version: release.tag_name, url: asset.browser_download_url, sha256: asset.digest.slice(7) });
}

export async function prepareGeoipData(output, pin, { bundledDirectory } = {}) {
  const directory = resolve(output);
  mkdirSync(directory, { recursive: true });
  const installed = await readSnapshot(directory);
  const bundled = bundledDirectory ? await readSnapshot(bundledDirectory) : null;
  if (installed && (!bundled || installed.sha256 === bundled.sha256)) return join(directory, geoipName);
  const snapshot = bundled || await latestGeoip(pin);
  const stage = mkdtempSync(join(directory, ".geoip-"));
  let preserveStage = false;
  try {
    const partial = join(stage, geoipName);
    const cache = process.env.XIAOBEI_BROWSER_DOWNLOADS || process.env.XIAOBEI_CACHE_DIR || join(homedir(), ".xiaobei/cache");
    const cached = join(cache, `geoip-aio-all-${snapshot.sha256}.mmdb`);
    if (bundled) copyFileSync(join(bundledDirectory, geoipName), partial);
    else if (existsSync(cached)) {
      await verify(cached, snapshot.sha256);
      copyFileSync(cached, partial);
    } else await downloadAsset(githubDownloadUrl(snapshot.url), partial, snapshot.sha256);
    writeFileSync(join(stage, geoipMetadataName), JSON.stringify(snapshot, null, 2) + "\n");
    const replaced = [], backups = [];
    try {
      for (const name of [geoipName, geoipMetadataName]) {
        if (existsSync(join(directory, name))) {
          renameSync(join(directory, name), join(stage, `previous-${name}`));
          backups.push(name);
        }
        renameSync(join(stage, name), join(directory, name));
        replaced.push(name);
      }
    } catch (error) {
      try {
        for (const name of replaced.reverse()) rmSync(join(directory, name), { force: true });
        for (const name of backups.reverse()) renameSync(join(stage, `previous-${name}`), join(directory, name));
      } catch (restoreError) {
        preserveStage = true;
        throw new Error(`GeoIP replacement and rollback failed; old files retained in ${stage}: ${restoreError.message}`);
      }
      throw error;
    }
    return join(directory, geoipName);
  } finally {
    if (!preserveStage) rmSync(stage, { recursive: true, force: true });
  }
}
