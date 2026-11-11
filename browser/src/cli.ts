#!/usr/bin/env node
import { createReadStream, realpathSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { BrowserClient } from "./client/index.js";
import { buildCommand } from "./compat/commands.js";
import { loadDefaults, parseViewport } from "./state/config.js";
import { stateHome, validateSession } from "./platform/paths.js";
import { failure, isObject, requestId, RuntimeError, type Params, type Response } from "./protocol/index.js";
import type { LaunchOptions } from "./state/registry.js";

const HELP = `xiaobei-browser [--session NAME] [--headed] [--persistent [PATH] | --ephemeral] [--json] COMMAND
Commands: start, open URL, snapshot [-i] [-s SELECTOR], click, fill, type, select,
check, hover, press, text, eval, upload, screenshot, pdf, scroll, wait, tabs,
switch, close-tab, cookies, identity, status, info, sessions, stop, close, doctor
Stable tabs: switch --tab ID, close-tab --tab ID (legacy switch INDEX remains supported)
Structured calls: --request-file PATH or --request-stdin (action, params, optional requestId)
Task ownership: lease acquire|renew|wait|release [--lease-token TOKEN]
Default profile: persistent default. This development package does not switch installed commands.`;

export async function main(argv = process.argv.slice(2), compatibility = false): Promise<void> {
  let json = argv.includes("--json");
  let action = "";
  try {
    if (!argv.length || argv.includes("--help") || argv.includes("-h")) { console.log(HELP); return; }
    if (argv.includes("--version")) { console.log("0.1.0-dev.0"); return; }
    let session = "default";
    let leaseToken: string | undefined;
    let source: string | undefined;
    let fromStdin = false;
    const explicit: Partial<LaunchOptions> = {};
    const rest: string[] = [];
    for (let i = 0; i < argv.length; i++) {
      const next = () => { const value = argv[++i]; if (!value) throw new RuntimeError("INVALID_ARGUMENT", `Missing value for ${argv[i - 1]}`); return value; };
      switch (argv[i]) {
        case "--session": session = next(); break;
        case "--json": break;
        case "--headed": explicit.headless = false; break;
        case "--headless": explicit.headless = true; break;
        case "--ephemeral": explicit.persistent = null; break;
        case "--persistent": {
          const value = argv[i + 1];
          explicit.persistent = value && (/[\\/]/.test(value) || /^[.~]/.test(value) || /^[a-z]:/i.test(value)) ? next() : "";
          break;
        }
        case "--proxy": explicit.proxy = next(); break;
        case "--no-geoip": explicit.geoip = false; break;
        case "--locale": explicit.locale = next(); break;
        case "--timeout": {
          const value = Number(next());
          if (!Number.isSafeInteger(value) || value < 0) throw new RuntimeError("INVALID_ARGUMENT", "Timeout must be non-negative seconds");
          explicit.idleTimeout = value; break;
        }
        case "--viewport": {
          const value = parseViewport(next());
          if (!Array.isArray(value) || value.some(n => n < 1)) throw new RuntimeError("INVALID_ARGUMENT", "Viewport must be positive WIDTHxHEIGHT");
          explicit.viewport = value; break;
        }
        case "--lease-token": leaseToken = next(); break;
        case "--request-file": source = next(); break;
        case "--request-stdin": fromStdin = true; break;
        default: rest.push(argv[i]);
      }
    }
    validateSession(session);
    const defaults = loadDefaults(session);
    json ||= defaults.json ?? false;
    const options: LaunchOptions = { headless: !(defaults.headed ?? false), persistent: compatibility ? null : "",
      proxy: defaults.proxy ?? null, geoip: defaults.geoip ?? true, locale: defaults.locale ?? null,
      viewport: defaults.viewport ?? null, idleTimeout: defaults.timeout ?? 0,
      ...(defaults.persistent !== undefined ? { persistent: defaults.persistent } : {}), ...explicit };
    if (options.persistent === "") options.persistent = join(stateHome(), "profiles", session);
    let command: Params;
    if (source || fromStdin) {
      if ((source && fromStdin) || rest.length) throw new RuntimeError("INVALID_ARGUMENT", "Use exactly one structured input source without a command");
      const chunks: Buffer[] = [];
      let size = 0;
      const stream = source ? createReadStream(source) : process.stdin;
      for await (const chunk of stream) {
        const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
        size += bytes.length;
        if (size > 1024 * 1024) throw new RuntimeError("PAYLOAD_TOO_LARGE", "Request input exceeds 1 MiB");
        chunks.push(bytes);
      }
      const raw = Buffer.concat(chunks);
      const parsed: unknown = JSON.parse(raw.toString("utf8"));
      if (!isObject(parsed) || typeof parsed.action !== "string" || !isObject(parsed.params ?? {})) throw new RuntimeError("INVALID_ARGUMENT", "Expected action and object params");
      command = { ...parsed, params: parsed.params ?? {} };
    } else {
      action = rest[0];
      if (["start", "stop", "status", "doctor"].includes(action)) command = { action, params: {} };
      else if (action === "lease" && ["acquire", "renew", "wait", "release"].includes(rest[1])) command = { action: `lease.${rest[1]}`, params: {} };
      else command = buildCommand(action, rest);
    }
    action = String(command.action);
    const client = new BrowserClient({ session });
    let response: Response;
    const local = (data: Params): Response => ({ protocolVersion: 1, requestId: requestId(), ok: true, data, meta: { generation: "local" } });
    if (action === "info" || action === "status") response = local(await client.status());
    else if (action === "sessions") response = local({ sessions: await client.sessions() });
    else if (action === "doctor") {
      const { assetStatus } = await import("./driver/runtime.js");
      response = local({ node: process.version, platform: process.platform, runtime: await client.status(),
        assets: assetStatus(), dependencies: { camoufox: "0.5.9", playwright: "1.62.1" },
        windowsNativeVerified: false });
    } else if (action === "install") {
      // The installer is shipped JS, intentionally outside the daemon/driver.
      const installer = await import(/* @vite-ignore */ new URL("../scripts/install-assets.mjs", import.meta.url).href);
      await installer.installAssets();
      response = local({ installed: true });
    }
    else if (action === "start") response = local(await client.start(options));
    else {
      const params = command.params as Params;
      if (action === "close" && params.all) throw new RuntimeError("ACTION_UNSUPPORTED", "close --all is intentionally unavailable while tasks may own sessions");
      if (action === "open") {
        const status = await client.status();
        if (!status.running) await client.start(options);
        else if (Object.keys(explicit).length) await client.start(options);
      }
      const stopping = action === "close" || action === "stop";
      if (stopping) response = await client.stop({ leaseToken });
      else {
        response = await client.request(action, params, { leaseToken,
          requestId: typeof command.requestId === "string" ? command.requestId : undefined });
      }
    }
    output(response, json, compatibility, action);
  } catch (e) {
    const error = e instanceof RuntimeError ? e : new RuntimeError("INVALID_ARGUMENT", e instanceof Error ? e.message : String(e));
    output(failure("?", "local", error), json, compatibility, action);
  }
}
function output(response: Response, json: boolean, compatibility: boolean, action: string): void {
  if (compatibility && response.ok && ["info", "sessions"].includes(action)) {
    const value = action === "sessions" ? (response.data?.sessions as Params[]).filter(s => s.running).map(s => s.session) : response.data;
    console.log(json ? JSON.stringify(value) : JSON.stringify(value, null, 2));
  } else if (json) {
    console.log(JSON.stringify(compatibility ? { id: "r1", success: response.ok, ...(response.ok ? { data: response.data } : { error: response.error?.message }) } : response));
  } else if (!response.ok) process.stderr.write(`${response.error?.code}: ${response.error?.message}\n`);
  else {
    const data = response.data ?? {};
    const value = "snapshot" in data ? data.snapshot : "text" in data ? data.text : "result" in data ? data.result : data;
    if (!data.closed) console.log(typeof value === "string" ? value : JSON.stringify(value, null, 2));
  }
  if (!response.ok) process.exitCode = response.error?.code === "INVALID_ARGUMENT" ? 2 :
    ["SESSION_BUSY", "CAPACITY_EXCEEDED", "PROFILE_IN_USE", "MODE_CONFLICT"].includes(response.error?.code ?? "") ? 4 :
    ["DAEMON_UNAVAILABLE", "PROTOCOL_MISMATCH", "INVALID_STATE", "PROFILE_RESET_REQUIRED", "ASSET_MISSING", "START_FAILED", "START_TIMEOUT"].includes(response.error?.code ?? "") ? 3 : 5;
}
if (process.argv[1] && fileURLToPath(import.meta.url) === realpathSync(process.argv[1])) void main();
