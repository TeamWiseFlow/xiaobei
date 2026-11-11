#!/usr/bin/env node
// Installer adapter to the pinned engine's own approvals and local-state-owner APIs.
// Live writes use authenticated RPC; offline writes retain native ownership and CAS.
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export function mergeCrewApprovals(current, plans) {
  const next = structuredClone(current);
  next.version = 1;
  next.defaults ??= {};
  next.defaults.security ??= "deny";
  next.defaults.ask ??= "off";
  next.defaults.askFallback ??= "deny";
  next.defaults.autoAllowSkills ??= false;
  next.agents ??= {};
  for (const [id, plan] of Object.entries(plans)) {
    const previous = next.agents[id] ?? {};
    const agent = { ...previous, security: plan.security, ask: plan.ask, askFallback: plan.askFallback };
    if (plan.security !== "full") {
      // ALLOWED_COMMANDS owns declarative path rules. Keep bounded human grants,
      // stable ids/usage for unchanged rules, and all unrelated agent fields.
      const old = previous.allowlist ?? [];
      const patterns = [...new Set((plan.allowlist ?? []).map((entry) => entry.pattern))];
      agent.allowlist = patterns.map((pattern) => {
        const entry = old.find((item) => item.pattern === pattern && !item.argPattern && !item.source);
        return entry ?? { id: randomUUID(), pattern };
      });
      agent.allowlist.push(...old.filter((entry) => entry.source === "allow-always"));
    }
    next.agents[id] = agent;
  }
  return next;
}

async function loadNativeApi() {
  const dist = path.join(root, "openclaw/dist");
  const info = JSON.parse(fs.readFileSync(path.join(dist, "build-info.json"), "utf8"));
  const pin = fs.readFileSync(path.join(root, "openclaw.version"), "utf8");
  if (info.version !== pin.match(/^OPENCLAW_VERSION=(.+)$/m)?.[1] ||
      info.commit !== pin.match(/^OPENCLAW_COMMIT=(.+)$/m)?.[1]) {
    throw new Error("Build the pinned OpenClaw before synchronizing exec approvals.");
  }
  const files = fs.readdirSync(dist);
  // Like the Doctor adapter, resolve named functions from this exact build;
  // hashed chunk names and minified export aliases are not stable APIs.
  async function load(prefix, select) {
    for (const name of files.filter((name) => name.startsWith(prefix) && name.endsWith(".mjs"))) {
      const module = await import(pathToFileURL(path.join(dist, name)).href);
      const value = Object.values(module).find(select);
      if (value) return value;
    }
    throw new Error(`Pinned OpenClaw approvals adapter is incompatible (${prefix}); no policy was written.`);
  }
  const named = (prefix, name) => load(prefix, (value) => typeof value === "function" && value.name === name);
  return {
    owner: await named("local-state-owner-", "runWithLocalStateOwner"),
    read: await named("exec-approvals-store-", "readExecApprovalsSnapshotAsync"),
    update: await named("exec-approvals-store-", "updateExecApprovals"),
    normalize: await named("exec-approvals-config-", "normalizeExecApprovalsInternal"),
    close: await named("openclaw-state-db-cache-", "closeOpenClawStateDatabaseAsync"),
    caps: await load("server-capabilities-", (value) => value?.EXEC_APPROVALS_SET_OWNER),
  };
}

export async function synchronize(plans, api) {
  const target = "crew exec approvals";
  const snapshot = await api.owner({
    method: "exec.approvals.get", params: {}, target,
    requiredCapabilities: [api.caps.EXEC_APPROVALS_GET_OWNER],
    recoveryCommand: "openclaw approvals get --json",
    runLocal: async ({ assertCurrent }) => {
      assertCurrent();
      const snapshot = await api.read();
      assertCurrent();
      return snapshot;
    },
  });
  const file = api.normalize(mergeCrewApprovals(snapshot.file, plans));
  if (isDeepStrictEqual(file, api.normalize(snapshot.file))) {
    return { updated: false, agents: Object.keys(plans).length };
  }
  const baseHash = snapshot.hash;
  if (!baseHash) throw new Error("Exec approvals hash unavailable; no policy was written.");
  const result = await api.owner({
    method: "exec.approvals.set", params: { file, baseHash }, target,
    requiredCapabilities: [api.caps.EXEC_APPROVALS_SET_OWNER],
    recoveryCommand: "openclaw approvals get --json",
    runLocal: async ({ assertCurrent }) => {
      assertCurrent();
      return api.update({
        baseHash, assertCurrent,
        update: { kind: "replace", file, preserveSocket: true },
      });
    },
  });
  if (!result) throw new Error("Exec approvals changed during setup; inspect approvals before rerunning.");
  return { updated: true, agents: Object.keys(plans).length };
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2 || args[0] !== "--config") {
    throw new Error("Usage: sync-exec-approvals.mjs --config FILE < agent-policies.json");
  }
  const config = path.resolve(args[1]);
  process.env.OPENCLAW_CONFIG_PATH = config;
  process.env.OPENCLAW_STATE_DIR = path.dirname(config);
  let input = "";
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 4 * 1024 * 1024) throw new Error("Crew exec policy input is too large.");
  }
  const plans = JSON.parse(input);
  if (!plans || typeof plans !== "object" || Array.isArray(plans) ||
      Object.values(plans).some((plan) => !plan || !["deny", "allowlist", "full"].includes(plan.security) ||
        plan.ask !== "off" || plan.askFallback !== "deny" || !Array.isArray(plan.allowlist) ||
        plan.allowlist.some((entry) => typeof entry?.pattern !== "string" || !entry.pattern.trim()))) {
    throw new Error("Invalid generated crew exec policies; no policy was written.");
  }
  const api = await loadNativeApi();
  try {
    console.log(JSON.stringify(await synchronize(plans, api)));
  } finally {
    // This CLI owns its worker lifetime; drain it before returning to setup.
    await api.close();
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
