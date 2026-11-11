#!/usr/bin/env node
// Use the exact built OpenClaw's Doctor migrations, then validate before replacing the source.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
let write = false;
let config =
  process.env.OPENCLAW_CONFIG_PATH ??
  process.env.OPENCLAW_JSON ??
  path.join(
    process.env.OPENCLAW_STATE_DIR ?? path.join(os.homedir(), ".openclaw"),
    "openclaw.json",
  );
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--write") write = true;
  else if (args[i] === "--config" && args[i + 1]) config = args[++i];
  else throw new Error("Usage: migrate-openclaw-config.mjs [--config FILE] [--write]");
}
config = path.resolve(config);
const dist = path.join(root, "openclaw/dist");
const info = JSON.parse(fs.readFileSync(path.join(dist, "build-info.json"), "utf8"));
const pin = fs.readFileSync(path.join(root, "openclaw.version"), "utf8");
if (
  info.version !== pin.match(/^OPENCLAW_VERSION=(.+)$/m)?.[1] ||
  info.commit !== pin.match(/^OPENCLAW_COMMIT=(.+)$/m)?.[1]
)
  throw new Error("Built OpenClaw differs from the pin; build it before migrating config");
const original = fs.readFileSync(config);
const raw = JSON.parse(original);
if (Object.hasOwn(raw, "$include"))
  throw new Error("Included configs require the upstream Doctor ownership-aware workflow");
// A build can emit several chunks with this prefix, including re-export shims.
// Hash ordering must not decide whether the native migration entry is available.
const names = fs.readdirSync(dist).filter((name) => /^config-flow-steps-.+\.mjs$/.test(name));
if (!names.length) throw new Error("Built Doctor migration module missing");
let migrate;
for (const name of names) {
  const mod = await import(pathToFileURL(path.join(dist, name)).href);
  migrate = Object.values(mod).find(
    (value) => typeof value === "function" && value.name === "migrateLegacyConfig",
  );
  if (migrate) break;
}
if (!migrate) throw new Error("This OpenClaw build has no compatible Doctor migration entry");
const result = migrate(raw, {});
if (result.partiallyValid)
  throw new Error("Doctor migration found remaining validation errors; config was not changed");
const candidate = structuredClone(result.sourceConfig ?? result.config ?? raw);
// xiaobei owns the pinned engine upgrade. Native discovery fetches the upstream
// development branch even for a detached release and can leave large partial packs.
candidate.update ??= {};
candidate.update.checkOnStart = false;
candidate.update.auto ??= {};
candidate.update.auto.enabled = false;
const changed = JSON.stringify(candidate) !== JSON.stringify(raw);
if (write) {
  candidate.meta ??= {};
  candidate.meta.lastTouchedVersion = info.version;
  delete candidate.meta.lastTouchedAt;
}
const directory = fs.mkdtempSync(path.join(path.dirname(config), ".xiaobei-config-"));
fs.chmodSync(directory, 0o700);
const staged = path.join(directory, "openclaw.json");
try {
  fs.writeFileSync(staged, JSON.stringify(candidate, null, 2) + "\n", { mode: 0o600 });
  const validation = spawnSync(
    process.execPath,
    [path.join(dist, "index.js"), "config", "validate", "--json"],
    { env: { ...process.env, OPENCLAW_CONFIG_PATH: staged }, encoding: "utf8" },
  );
  if (validation.status !== 0)
    throw new Error(
      "Migrated config failed OpenClaw validation; source unchanged. Run config validate for diagnostics.",
    );
  const summary = {
    version: info.version,
    migrationCount: result.changes?.length ?? 0,
    changed,
    metaUpdated: write,
    written: false,
  };
  if (write) {
    if (!fs.readFileSync(config).equals(original))
      throw new Error("Config changed during migration; retry against the current file");
    const backup = `${config}.bak-${Date.now()}`;
    fs.writeFileSync(backup, original, { mode: 0o600, flag: "wx" });
    fs.renameSync(staged, config);
    summary.backup = backup;
    summary.written = true;
  }
  console.log(JSON.stringify(summary));
} finally {
  fs.rmSync(directory, { recursive: true, force: true });
}
