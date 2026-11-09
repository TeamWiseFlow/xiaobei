#!/usr/bin/env node
// Finish configuration/state work only after the pinned engine has been built.
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { inspectLegacyAccounts } from "./lib/automation-inference-check.mjs";

export function finalizeOpenClawUpgrade({ root, config, skipCrew = false, stopGateway = false }, run = spawnSync) {
  root = path.resolve(root);
  config = path.resolve(config);
  const pin = fs.readFileSync(path.join(root, "openclaw.version"), "utf8");
  const version = pin.match(/^OPENCLAW_VERSION=(.+)$/m)?.[1];
  const commit = pin.match(/^OPENCLAW_COMMIT=(.+)$/m)?.[1];
  const dist = path.join(root, "openclaw/dist");
  const build = JSON.parse(fs.readFileSync(path.join(dist, "build-info.json"), "utf8"));
  if (!version || !commit || build.version !== version || build.commit !== commit)
    throw new Error("Build the pinned OpenClaw before finalizing configuration or state; no migration was run.");
  if (!fs.existsSync(config)) return { version, skipped: true, reason: "no runtime configuration" };
  const env = { ...process.env, OPENCLAW_CONFIG_PATH: config };
  function step(command, argv, extraEnv = {}) {
    const result = run(command, argv, { cwd: root, env: { ...env, ...extraEnv }, stdio: "inherit" });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(`OpenClaw upgrade finalization failed (exit ${result.status}); daemon restart was not requested.`);
  }
  // Native stop is idempotent when no service is loaded. Let the service owner
  // release the old state worker before the new Doctor performs maintenance.
  if (stopGateway) step(process.execPath, [path.join(dist, "index.js"), "daemon", "stop", "--force"]);
  step(process.execPath, [path.join(root, "scripts/migrate-openclaw-config.mjs"), "--config", config, "--write"]);
  step(process.execPath, [path.join(root, "scripts/configure-browser-plugin.mjs"), "--root", root, "--config", config, "--write"]);
  step(process.execPath, [path.join(dist, "index.js"), "doctor", "--fix", "--non-interactive", "--no-workspace-suggestions"], { OPENCLAW_UPDATE_IN_PROGRESS: "1" });
  const runtimeConfig = JSON.parse(fs.readFileSync(config, "utf8"));
  let pendingAccounts = [];
  let accountCheck = "skipped-no-profiles";
  if (Object.values(runtimeConfig.auth?.profiles ?? {}).some(profile => profile?.provider)) {
    try {
      pendingAccounts = inspectLegacyAccounts(runtimeConfig, config);
      accountCheck = "completed";
    } catch (error) {
      pendingAccounts = null;
      accountCheck = "unavailable";
      console.warn(`⚠️  Pre-start automation account inspection was unavailable; it will be retried during required post-start migration: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  if (pendingAccounts?.length) {
    console.log(`ℹ️  ${pendingAccounts.length} legacy automations need account migration; the installer will adopt their configured accounts after Gateway starts. Ambiguous account selections will be reported before any job changes.`);
  }
  if (!skipCrew) {
    step("bash", ["-c", 'set -e; source "$1/scripts/lib/agent-skills.sh"; source "$1/scripts/lib/exec-tiers.sh"; apply_exec_tiers "$2" "$1/crews" "$1"', "xiaobei-finalize", root, config]);
  }
  return { version, skipped: false, finalized: true, approvalsSynchronized: !skipCrew, automationAccountCheck: accountCheck, pendingAutomationAccountAdoptions: pendingAccounts?.length ?? null };
}

function main() {
  const options = {
    root: path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
    config: process.env.OPENCLAW_CONFIG_PATH ?? process.env.OPENCLAW_JSON ?? path.join(process.env.OPENCLAW_STATE_DIR ?? path.join(os.homedir(), ".openclaw"), "openclaw.json"),
    skipCrew: false,
    stopGateway: false,
  };
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--root" && args[i + 1]) options.root = args[++i];
    else if (args[i] === "--config" && args[i + 1]) options.config = args[++i];
    else if (args[i] === "--skip-crew") options.skipCrew = true;
    else if (args[i] === "--stop-gateway") options.stopGateway = true;
    else throw new Error("Usage: finalize-openclaw-upgrade.mjs [--root PATH] [--config FILE] [--skip-crew] [--stop-gateway]");
  }
  console.log(JSON.stringify(finalizeOpenClawUpgrade(options)));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
