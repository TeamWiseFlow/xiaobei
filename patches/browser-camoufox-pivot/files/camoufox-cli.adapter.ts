/**
 * camoufox-cli adapter — Line 1 backend for the browser tool (spec §12.3).
 *
 * Translates the 17 browser-tool actions into forked camoufox-cli daemon
 * commands and talks to the daemon over its JSON-over-unix-socket protocol.
 * Completely bypasses routes/, pw-session, and chrome-mcp — this is the only
 * new extension code in the browser-stack pivot; browser-tool.ts gains a
 * `target === "camoufox"` branch (step 3 patch) that calls
 * executeCamoufoxCliAction().
 *
 * Daemon protocol: one JSON object per line, `{id, action, params}\n` →
 * `{id, success, data?, error?}\n`. Socket: `/tmp/camoufox-cli-<session>.sock`
 * (long session names >84 chars are sha256-shortened to stay under Linux's
 * 108-byte sockaddr_un path limit — see `shortenSession()` below).
 *
 * Unsupported browser-tool actions (console capture, dialog arming, act
 * drag/clickCoords/resize — camoufox-cli has no equivalents) return a clear
 * error guiding the agent to retry with target="host". This is the R4 residual
 * the spec acknowledges, scoped to this one module.
 */

import * as net from "node:net";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as crypto from "node:crypto";
import { spawn } from "node:child_process";
import type { AgentToolResult } from "openclaw/plugin-sdk/agent-core";
import { wrapExternalContent } from "./sdk-security-runtime.js";
import { neutralizeMediaDirectives } from "./browser/vision.js";

/** Session-level daemon config. Maps 1:1 onto camoufox-cli daemon flags. */
export interface CamoufoxCliSessionConfig {
  /** Daemon session name → socket/pid namespace + persistent profile dir key. */
  session: string;
  /** false → --headed (real Firefox window), true → headless. */
  headless: boolean;
  /** Daemon idle watchdog (seconds). Defaults to 1800. */
  timeout?: number;
  /** --persistent <dir>: freeze fingerprint on first launch, reuse profile. */
  persistentDir?: string | null;
  /** --proxy <url>. */
  proxy?: string | null;
  /** --no-geoip when false. Defaults true. */
  geoip?: boolean;
  /** --locale <tag>. */
  locale?: string | null;
}

interface CliResponse {
  id?: string;
  success: boolean;
  data?: unknown;
  error?: string;
}

// ---------------------------------------------------------------------------
// Daemon lifecycle
// ---------------------------------------------------------------------------

const SOCKET_PREFIX = "/tmp/camoufox-cli-";
// Linux sockaddr_un path limit is 108 bytes. With prefix "/tmp/camoufox-cli-"
// (19 chars) + suffix ".sock" (5 chars) = 24 chars overhead, session names
// up to 84 chars are safe. Longer names (e.g. cron session IDs) are hashed.
// MUST stay in sync with patches/camoufox-cli/src/cli.ts shortenSession() —
// the daemon uses the identical logic to compute its listen path; if these
// two diverge, ensureDaemon's waitForSocket waits on the wrong path and the
// browser never opens. Duplicated here (rather than imported) because the
// adapter is vendored into openclaw/extensions/browser/src and built as part
// of openclaw, not the camoufox-cli package.
const MAX_SESSION_LEN = 84;

/** Shorten a session name for use in socket/pid file paths if it would exceed
 * the 108-char Unix socket path limit. Short names are returned as-is; long
 * names are replaced with `s-<16-char-sha256-prefix>` (18 chars total). */
export function shortenSession(session: string): string {
  if (session.length <= MAX_SESSION_LEN) return session;
  const hash = crypto.createHash("sha256").update(session).digest("hex").slice(0, 16);
  return `s-${hash}`;
}

export function socketPath(session: string): string {
  return `${SOCKET_PREFIX}${shortenSession(session)}.sock`;
}

/**
 * Resolve the forked camoufox-cli's daemon.js by following the global
 * `camoufox-cli` bin symlink to its dist dir. The global install is a link to
 * patches/camoufox-cli/ (build.sh), so cli.js and daemon.js are siblings.
 */
function resolveDaemonJsPath(): string {
  const bin = findOnPath("camoufox-cli");
  if (!bin) throw new Error("camoufox-cli not found on PATH — run patches/camoufox-cli/build.sh");
  const real = fs.realpathSync(bin);
  return path.join(path.dirname(real), "daemon.js");
}

function findOnPath(name: string): string | null {
  const dirs = (process.env.PATH ?? "").split(path.delimiter);
  for (const dir of dirs) {
    if (!dir) continue;
    for (const candidate of [path.join(dir, name), path.join(dir, `${name}.js`)]) {
      try {
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
      } catch {}
    }
  }
  return null;
}

async function isSocketAlive(sock: string): Promise<boolean> {
  return new Promise((resolve) => {
    const s = net.createConnection(sock, () => { s.destroy(); resolve(true); });
    s.on("error", () => resolve(false));
    s.setTimeout(2000, () => { s.destroy(); resolve(false); });
  });
}

function spawnDaemon(config: CamoufoxCliSessionConfig): void {
  const daemonJs = resolveDaemonJsPath();
  const args = ["--session", config.session, "--timeout", String(config.timeout ?? 1800)];
  if (!config.headless) args.push("--headed");
  if (config.persistentDir) args.push("--persistent", config.persistentDir);
  if (config.proxy) args.push("--proxy", config.proxy);
  if (config.geoip === false) args.push("--no-geoip");
  if (config.locale) args.push("--locale", config.locale);
  // Detached + unref so the daemon outlives the openclaw process; stdio ignored
  // to keep the parent's stdout clean. forceExit in shutdown() guarantees the
  // daemon exits even if an interrupted command left a stray timer.
  spawn("node", [daemonJs, ...args], { detached: true, stdio: "ignore" }).unref();
}

async function waitForSocket(sock: string, timeoutMs = 15000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(sock) && await isSocketAlive(sock)) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`camoufox-cli daemon did not start within ${timeoutMs}ms (session=${configSession(sock)})`);
}

/** Extract the (possibly hashed) session identifier from a socket path, for
 * diagnostics only. For long sessions this returns the `s-<hash>` short form,
 * not the original session name — enough to identify the daemon in errors. */
function configSession(sock: string): string {
  return sock.replace(SOCKET_PREFIX, "").replace(".sock", "");
}

/** Ensure a daemon is running for the session; spawn one if the socket is dead/absent. */
export async function ensureDaemon(config: CamoufoxCliSessionConfig): Promise<void> {
  const sock = socketPath(config.session);
  if (fs.existsSync(sock) && await isSocketAlive(sock)) return;
  try { fs.unlinkSync(sock); } catch {}
  spawnDaemon(config);
  await waitForSocket(sock);
}

// ---------------------------------------------------------------------------
// Socket client
// ---------------------------------------------------------------------------

/** Send one command to the daemon and await its response. Spawns daemon if needed. */
export async function sendCommand<T = CliResponse>(
  config: CamoufoxCliSessionConfig,
  command: { id: string; action: string; params?: Record<string, unknown> },
  timeoutMs?: number,
): Promise<T> {
  await ensureDaemon(config);
  const sock = socketPath(config.session);
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sock, () => {
      client.end(JSON.stringify(command) + "\n");
    });
    let data = "";
    client.on("data", (chunk) => { data += chunk.toString(); });
    client.on("end", () => {
      try { resolve(JSON.parse(data.trim()) as T); }
      catch { reject(new Error(`camoufox-cli: unparseable response: ${data.slice(0, 200)}`)); }
    });
    client.on("error", reject);
    if (timeoutMs) client.setTimeout(timeoutMs, () => { client.destroy(); reject(new Error(`camoufox-cli: timeout after ${timeoutMs}ms`)); });
  });
}

/** Run a daemon command, throwing on {success:false} with the daemon's error. */
async function run(
  config: CamoufoxCliSessionConfig,
  action: string,
  params: Record<string, unknown> = {},
  timeoutMs?: number,
  transport?: Transport,
): Promise<unknown> {
  const resp = (await (transport ?? defaultTransport)(config, { id: "r1", action, params }, timeoutMs)) as CliResponse;
  if (!resp.success) throw new Error(`camoufox-cli ${action} failed: ${resp.error ?? "unknown error"}`);
  return resp.data;
}

/**
 * Transport signature: send one command, get the raw daemon response back.
 * Injectable so tests can verify action→command translation without a real
 * socket or daemon. Production uses defaultTransport (real unix socket).
 */
export type Transport = (
  config: CamoufoxCliSessionConfig,
  command: { id: string; action: string; params?: Record<string, unknown> },
  timeoutMs?: number,
) => Promise<CliResponse>;

const defaultTransport: Transport = (config, command, timeoutMs) =>
  sendCommand<CliResponse>(config, command, timeoutMs);

// ---------------------------------------------------------------------------
// Result shaping helpers (mirror browser-tool.actions.ts conventions)
// ---------------------------------------------------------------------------

function jsonResult(payload: unknown): AgentToolResult<unknown> {
  return { content: [{ type: "text", text: JSON.stringify(payload, null, 2) }], details: payload };
}

function wrapExternalJson(kind: "snapshot" | "tabs", payload: unknown): AgentToolResult<unknown> {
  const extracted = JSON.stringify(
    payload,
    (_k, v) => (typeof v === "string" ? neutralizeMediaDirectives(v) : v),
    2,
  );
  const wrappedText = wrapExternalContent(extracted, { source: "browser", includeWarning: true });
  return {
    content: [{ type: "text", text: wrappedText }],
    details: {
      ok: true,
      externalContent: { untrusted: true, source: "browser", kind, wrapped: true },
      ...(kind === "tabs" ? { tabs: (payload as { tabs?: unknown[] }).tabs ?? [] } : {}),
    },
  };
}

function unsupported(action: string, reason: string): AgentToolResult<unknown> {
  // Tell the agent exactly how to recover: the camoufox-cli backend can't do
  // this, so re-issue the action against the host/node line.
  const text = `camoufox-cli backend does not support action="${action}" (${reason}). Retry with target="host" (existing-session Chrome) or target="node" (remote-cdp).`;
  return { content: [{ type: "text", text }], details: { ok: false, unsupported: true, action, reason } };
}

// ---------------------------------------------------------------------------
// Param readers (local, no shared deps)
// ---------------------------------------------------------------------------

function readString(params: Record<string, unknown>, key: string, required = false): string | undefined {
  const v = params[key];
  if (typeof v === "string" && v.length > 0) return v;
  if (required) throw new Error(`Missing required parameter: ${key}`);
  return undefined;
}

function readBool(params: Record<string, unknown>, key: string): boolean | undefined {
  return typeof params[key] === "boolean" ? (params[key] as boolean) : undefined;
}

function readNumber(params: Record<string, unknown>, key: string): number | undefined {
  const v = params[key];
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function readTargetUrl(params: Record<string, unknown>): string {
  return readString(params, "targetUrl") ?? readString(params, "url", true)!;
}

/** Normalize a ref: accept "@e1" or "e1" → "@e1" (camoufox-cli refs are @-prefixed). */
function normalizeRef(ref: string): string {
  return ref.startsWith("@") ? ref : `@${ref}`;
}

// ---------------------------------------------------------------------------
// Action dispatch — the 17 browser-tool actions
// ---------------------------------------------------------------------------

/** Injectable dependencies for testability; production uses the real socket. */
export interface AdapterDeps {
  transport?: Transport;
  isAlive?: (session: string) => Promise<boolean>;
  ensureDaemon?: (config: CamoufoxCliSessionConfig) => Promise<void>;
}

/**
 * Execute a browser-tool action against the forked camoufox-cli daemon.
 * Returns an AgentToolResult shaped to match the host/node lines so the agent
 * loop and downstream consumers see a uniform result.
 */
export async function executeCamoufoxCliAction(
  params: Record<string, unknown>,
  config: CamoufoxCliSessionConfig,
  deps?: AdapterDeps,
): Promise<AgentToolResult<unknown>> {
  const action = readString(params, "action", true)!;
  const timeoutMs = readNumber(params, "timeoutMs");
  const isAlive = deps?.isAlive ?? ((session: string) => isSocketAlive(socketPath(session)));
  const ensure = deps?.ensureDaemon ?? ensureDaemon;
  const transport = deps?.transport;

  switch (action) {
    case "doctor": {
      const alive = await isAlive(config.session);
      return jsonResult({ ok: true, backend: "camoufox-cli", version: "0.6.2-wiseflow.1", session: config.session, daemonRunning: alive });
    }

    case "status": {
      const alive = await isAlive(config.session);
      return jsonResult({ running: alive, backend: "camoufox-cli", session: config.session, headless: config.headless });
    }

    case "start": {
      await ensure(config);
      return jsonResult({ ok: true, backend: "camoufox-cli", session: config.session, started: true });
    }

    case "stop": {
      try { await run(config, "close", {}, undefined, transport); } catch { /* daemon may already be gone */ }
      return jsonResult({ ok: true, stopped: true });
    }

    case "profiles": {
      // camoufox-cli has no daemon "list sessions" command; enumerate persistent
      // profile dirs on the host filesystem (spec §12.3: profiles land here).
      const profilesDir = path.join(os.homedir(), ".camoufox-cli", "profiles");
      let profiles: string[] = [];
      try { profiles = fs.readdirSync(profilesDir).filter((n) => fs.statSync(path.join(profilesDir, n)).isDirectory()); }
      catch { /* no profiles dir yet */ }
      return jsonResult({ profiles });
    }

    case "tabs": {
      const data = (await run(config, "tabs", {}, timeoutMs, transport)) as { tabs?: unknown[] };
      return wrapExternalJson("tabs", { tabs: data.tabs ?? [] });
    }

    case "open":
    case "navigate": {
      const url = readTargetUrl(params);
      const data = (await run(config, "open", { url }, timeoutMs, transport)) as { url?: string; title?: string };
      return jsonResult({ url: data.url ?? url, title: data.title, targetId: undefined });
    }

    case "focus": {
      // camoufox-cli `switch` takes a tab index; browser-tool focus takes a
      // targetId/tabId/label. Resolve via tabs, then switch.
      const targetId = readString(params, "targetId", true)!;
      const data = (await run(config, "tabs", {}, undefined, transport)) as { tabs?: Array<Record<string, unknown>> };
      const tabs = data.tabs ?? [];
      const idx = tabs.findIndex((t) => String(t.targetId ?? t.tabId ?? t.label ?? t.url) === targetId);
      if (idx < 0) return unsupported("focus", `no tab matching targetId="${targetId}"`);
      await run(config, "switch", { index: idx }, timeoutMs, transport);
      return jsonResult({ ok: true, focused: targetId });
    }

    case "close": {
      const targetId = readString(params, "targetId");
      if (targetId) {
        // camoufox-cli close-tab closes the CURRENT tab only; to close a specific
        // tab we'd switch to it first. For now, only support closing current tab.
        return unsupported("close", "closing a specific tab by targetId is not supported; omit targetId to close the current tab, or use target=\"host\"");
      }
      await run(config, "close-tab", {}, timeoutMs, transport);
      return jsonResult({ ok: true });
    }

    case "snapshot": {
      const interactive = readBool(params, "interactive") ?? false;
      const selector = readString(params, "selector");
      const cliParams: Record<string, unknown> = { interactive };
      if (selector) cliParams.selector = selector;
      const data = (await run(config, "snapshot", cliParams, timeoutMs, transport)) as { snapshot?: string };
      return wrapExternalJson("snapshot", { snapshot: data.snapshot ?? "", format: "aria" });
    }

    case "screenshot": {
      const fullPage = readBool(params, "fullPage") ?? false;
      const outPath = path.join(os.tmpdir(), `camoufox-cli-shot-${config.session}-${Date.now()}.png`);
      await run(config, "screenshot", { path: outPath, full_page: fullPage }, timeoutMs, transport);
      // Return the file path; step 3 may wire the existing vision-describe
      // pipeline around this. Plain-text pointer keeps it usable as-is.
      return {
        content: [{ type: "text", text: `[browser:screenshot] file://${outPath}` }],
        details: { path: outPath, backend: "camoufox-cli", fullPage },
      };
    }

    case "console":
      return unsupported("console", "camoufox-cli has no console-message capture");

    case "pdf": {
      const outPath = path.join(os.tmpdir(), `camoufox-cli-pdf-${config.session}-${Date.now()}.pdf`);
      await run(config, "pdf", { path: outPath }, timeoutMs, transport);
      return { content: [{ type: "text", text: `FILE:${outPath}` }], details: { path: outPath } };
    }

    case "upload": {
      const paths = Array.isArray(params.paths) ? params.paths.map((p) => String(p)) : [];
      if (paths.length === 0) throw new Error("paths required");
      const ref = readString(params, "ref");
      const inputRef = readString(params, "inputRef");
      const element = readString(params, "element");
      const cliParams: Record<string, unknown> = { paths };
      const refValue = ref ?? inputRef;
      if (refValue) cliParams.ref = normalizeRef(refValue);
      else if (element) cliParams.selector = element;
      else throw new Error("upload requires ref, inputRef, or element");
      const data = (await run(config, "upload", cliParams, timeoutMs, transport)) as { count?: number };
      return jsonResult({ ok: true, count: data.count ?? paths.length, paths });
    }

    case "dialog":
      return unsupported("dialog", "camoufox-cli has no dialog auto-handler; handle dialogs via eval or use target=\"host\"");

    case "act": {
      return await executeActAction(params, config, timeoutMs, transport);
    }

    default:
      throw new Error(`camoufox-cli adapter: unknown action "${action}"`);
  }
}

// ---------------------------------------------------------------------------
// act — translate the 12 act kinds onto camoufox-cli commands
// ---------------------------------------------------------------------------

async function executeActAction(
  params: Record<string, unknown>,
  config: CamoufoxCliSessionConfig,
  timeoutMs?: number,
  transport?: Transport,
): Promise<AgentToolResult<unknown>> {
  const request = (params.request ?? params) as Record<string, unknown>;
  const kind = readString(request, "kind", true)!;

  switch (kind) {
    case "click": {
      const ref = readString(request, "ref", true)!;
      await run(config, "click", { ref: normalizeRef(ref) }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "click" });
    }

    case "type": {
      const ref = readString(request, "ref", true)!;
      const text = readString(request, "text", true)!;
      await run(config, "type", { ref: normalizeRef(ref), text }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "type" });
    }

    case "fill": {
      // Browser-tool fill uses a `fields` array of {ref, value}; camoufox-cli
      // fill is one (ref, text) per call. Loop in order.
      const fields = request.fields;
      if (Array.isArray(fields) && fields.length > 0) {
        for (const f of fields) {
          const fo = f as Record<string, unknown>;
          const ref = readString(fo, "ref", true)!;
          const value = readString(fo, "value", true)!;
          await run(config, "fill", { ref: normalizeRef(ref), text: value }, timeoutMs, transport);
        }
        return jsonResult({ ok: true, kind: "fill", count: fields.length });
      }
      const ref = readString(request, "ref", true)!;
      const text = readString(request, "text", true)!;
      await run(config, "fill", { ref: normalizeRef(ref), text }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "fill" });
    }

    case "press": {
      const key = readString(request, "key", true)!;
      await run(config, "press", { key }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "press" });
    }

    case "hover": {
      const ref = readString(request, "ref", true)!;
      await run(config, "hover", { ref: normalizeRef(ref) }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "hover" });
    }

    case "select": {
      const ref = readString(request, "ref", true)!;
      const values = request.values;
      if (!Array.isArray(values) || values.length === 0) throw new Error("act select requires values");
      // camoufox-cli select takes a single value; loop for multi-select.
      for (const v of values) await run(config, "select", { ref: normalizeRef(ref), value: String(v) }, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "select", count: values.length });
    }

    case "wait": {
      const timeMs = readNumber(request, "timeMs");
      const selector = readString(request, "selector");
      const url = readString(request, "url");
      const textGone = readString(request, "textGone");
      const cliParams: Record<string, unknown> = {};
      if (timeMs !== undefined) cliParams.ms = timeMs;
      else if (selector) cliParams.selector = selector;
      else if (url) cliParams.url = url;
      else if (textGone) {
        // camoufox-cli has no "wait for text gone"; emulate via eval polling.
        await run(config, "eval", { expression: `await (async () => { while([...document.querySelectorAll('*')].some(e=>e.textContent.includes(${JSON.stringify(textGone)}))) { await new Promise(r=>setTimeout(r,100)); } })()` }, timeoutMs, transport);
        return jsonResult({ ok: true, kind: "wait", waitedFor: "textGone" });
      } else throw new Error("act wait requires timeMs, selector, url, or textGone");
      await run(config, "wait", cliParams, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "wait" });
    }

    case "evaluate": {
      const fn = readString(request, "fn", true)!;
      const data = (await run(config, "eval", { expression: fn }, timeoutMs, transport)) as { result?: unknown };
      return jsonResult({ ok: true, kind: "evaluate", result: data.result });
    }

    case "close": {
      await run(config, "close", {}, timeoutMs, transport);
      return jsonResult({ ok: true, kind: "close" });
    }

    case "clickCoords":
      return unsupported("act:clickCoords", "camoufox-cli click takes a ref, not coordinates");

    case "drag":
      return unsupported("act:drag", "camoufox-cli has no drag command");

    case "resize":
      return unsupported("act:resize", "camoufox-cli has no viewport resize command");

    default:
      return unsupported(`act:${kind}`, "unknown act kind for camoufox-cli backend");
  }
}
