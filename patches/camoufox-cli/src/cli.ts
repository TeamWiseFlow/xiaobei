#!/usr/bin/env node
/** CLI client: parses args, starts daemon if needed, sends command via Unix socket. */

import * as net from "node:net";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import * as crypto from "node:crypto";
import { loadDefaults, parseViewport } from "./config.js";

const SOCKET_PREFIX = "/tmp/camoufox-cli-";
// Linux sockaddr_un path limit is 108 bytes. With prefix "/tmp/camoufox-cli-"
// (19 chars) + suffix ".sock" (5 chars) = 24 chars overhead, session names
// up to 84 chars are safe. Longer names (e.g. cron session IDs) are hashed.
const MAX_SESSION_LEN = 84;

/** Shorten a session name for use in socket/pid file paths if it would exceed
 * the 108-char Unix socket path limit. Short names are returned as-is; long
 * names are replaced with `s-<16-char-sha256-prefix>` (18 chars total).
 * Both the CLI client and daemon use this to agree on the same socket path. */
export function shortenSession(session: string): string {
  if (session.length <= MAX_SESSION_LEN) return session;
  const hash = crypto.createHash("sha256").update(session).digest("hex").slice(0, 16);
  return `s-${hash}`;
}

export function getSocketPath(session: string): string {
  return `${SOCKET_PREFIX}${shortenSession(session)}.sock`;
}

/** PID file path for a session (mirrors socket path, uses .pid extension). */
export function getPidPath(session: string): string {
  return `${SOCKET_PREFIX}${shortenSession(session)}.pid`;
}

function sendCommand(sockPath: string, command: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(sockPath, () => {
      client.end(JSON.stringify(command) + "\n");
    });

    let data = "";
    client.on("data", (chunk) => { data += chunk.toString(); });
    client.on("end", () => {
      try { resolve(JSON.parse(data)); }
      catch (e) { reject(new Error(`Invalid response: ${data}`)); }
    });
    client.on("error", reject);
  });
}

function spawnDaemon(session: string, headed: boolean, timeout: number, persistent: string | null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null, viewport: [number, number] | null = null): Promise<void> {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const daemonPath = path.join(__dirname, "daemon.js");

  const args = ["--session", session, "--timeout", String(timeout)];
  if (headed) args.push("--headed");
  if (persistent) args.push("--persistent", persistent);
  if (proxy) args.push("--proxy", proxy);
  if (!geoip) args.push("--no-geoip");
  if (locale) args.push("--locale", locale);
  if (viewport) args.push("--viewport", `${viewport[0]}x${viewport[1]}`);

  spawn("node", [daemonPath, ...args], {
    detached: true,
    stdio: "ignore",
  }).unref();

  const sockPath = getSocketPath(session);
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      if (fs.existsSync(sockPath)) return resolve();
      attempts++;
      if (attempts >= 50) return reject(new Error("Daemon did not start within 5 seconds"));
      setTimeout(check, 100);
    };
    check();
  });
}

/** Probe a running daemon's mode via the `info` action. Returns null if the
 * daemon can't be reached or doesn't answer (caller falls back to reuse). */
async function queryDaemonInfo(sockPath: string): Promise<{ headless: boolean; session: string } | null> {
  try {
    const resp = await sendCommand(sockPath, { id: "r1", action: "info", params: {} });
    if (!resp.success) return null;
    const data = resp.data as Record<string, unknown> | undefined;
    if (!data) return null;
    return { headless: Boolean(data.headless), session: String(data.session ?? "") };
  } catch { return null; }
}

/** Tear down a live daemon so a fresh one can take its socket — used when the
 * caller wants a different headed mode than the running daemon (headless is
 * fixed at spawn time). Sends `close` (graceful), then force-kills the pid and
 * removes socket/pid if it doesn't exit promptly. Best-effort, never throws. */
async function killDaemon(session: string): Promise<void> {
  const sockPath = getSocketPath(session);
  const pidPath = getPidPath(session);
  try { await sendCommand(sockPath, { id: "r1", action: "close", params: {} }); } catch {}
  // Wait for graceful exit (shutdown unlinks socket + pid, then process.exit(0)).
  // 8s (was 1s): shutdown() awaits manager.close() → context.close() which must
  // let Playwright fully kill camoufox-bin. Firefox context close routinely takes
  // 2-5s; the old 1s budget SIGKILL'd daemon.js mid-close, orphaning camoufox-bin.
  // 30 orphaned Firefox processes from repeated headed↔headless mode switches
  // OOM'd the box on 2026-07-17 22:34 (see memory 26/24).
  for (let i = 0; i < 160; i++) {
    if (!fs.existsSync(sockPath)) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  // Force kill if still alive (a hung command may block graceful shutdown).
  // Kill the whole process GROUP (-pid): daemon.js is spawned detached:true so
  // it's its own pgid leader, and camoufox-bin + content procs are its children.
  // Killing only the daemon pid leaves camoufox-bin orphaned holding the profile
  // lock + RAM. Fall back to plain pid if the group kill misses (ESRCH).
  if (fs.existsSync(pidPath)) {
    try {
      const pid = parseInt(fs.readFileSync(pidPath, "utf-8").trim(), 10);
      if (pid) {
        try { process.kill(-pid, "SIGKILL"); } catch { try { process.kill(pid, "SIGKILL"); } catch {} }
      }
    } catch {}
  }
  for (const p of [sockPath, pidPath]) { try { fs.unlinkSync(p); } catch {} }
  await new Promise((r) => setTimeout(r, 200));
}

async function ensureDaemon(session: string, headed: boolean, timeout: number, persistent: string | null, proxy: string | null = null, geoip: boolean = true, locale: string | null = null, viewport: [number, number] | null = null): Promise<void> {
  const sockPath = getSocketPath(session);
  if (fs.existsSync(sockPath)) {
    // Verify daemon is alive
    let alive = false;
    try {
      await new Promise<void>((resolve, reject) => {
        const s = net.createConnection(sockPath, () => { s.destroy(); resolve(); });
        s.on("error", reject);
        s.setTimeout(2000, () => { s.destroy(); reject(new Error("timeout")); });
      });
      alive = true;
    } catch {
      try { fs.unlinkSync(sockPath); } catch {}
    }

    if (alive) {
      // headless is fixed at daemon spawn time, so reusing a live daemon
      // silently drops a conflicting `--headed`/headless request. When the
      // caller now wants a different mode than the running daemon, tear the old
      // one down and spawn fresh so the flag actually takes effect. This is the
      // fix for the "11:59 死机" incident (see memory 24-camoufox-cli-daemon-
      // flag-gotcha): the agent's `--headed` was silently swallowed by a
      // headless daemon, so it kept spawning headed windows that never
      // attached. If we can't determine the running mode, reuse as before
      // (don't thrash on an unresponsive daemon).
      const info = await queryDaemonInfo(sockPath);
      const wantHeadless = !headed;
      if (info && info.headless !== wantHeadless) {
        process.stderr.write(`[camoufox-cli] Daemon running headless=${info.headless} but caller requested headless=${wantHeadless}; restarting daemon to apply mode change\n`);
        await killDaemon(session);
        await evictForCap(session);
        await spawnDaemon(session, headed, timeout, persistent, proxy, geoip, locale, viewport);
        return;
      }
      return;
    }
  }
  // Backstop: don't let runaway callers accumulate live daemons past the cap.
  await evictForCap(session);
  await spawnDaemon(session, headed, timeout, persistent, proxy, geoip, locale, viewport);
}

export function listSessions(): string[] {
  const sessions: string[] = [];
  try {
    for (const name of fs.readdirSync("/tmp")) {
      if (name.startsWith("camoufox-cli-") && name.endsWith(".sock")) {
        sessions.push(name.slice("camoufox-cli-".length, -".sock".length));
      }
    }
  } catch {}
  return sessions.sort();
}

// Hard cap on concurrently live daemons. Each daemon holds a full Firefox
// instance (~200-400MB + several content processes); on a 13GB machine a
// runaway agent can freeze the box in minutes by opening dozens of uniquely-
// named sessions and never closing them (see memory 23-smart-search-session-
// leak-crash: 72 open / 1 close). When a new daemon would exceed this cap we
// evict the oldest live daemon (its profile persists, so login state survives)
// before spawning. 6 leaves headroom for system + node gateway on 13GB
// (each Firefox ~200-400MB + several content processes; 6 × ~400MB ≈ 2.4GB).
const MAX_CONCURRENT_DAEMONS = 6;

/** Verify a session's daemon is actually alive by probing its socket. */
function daemonAlive(sockPath: string): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      const s = net.createConnection(sockPath, () => { s.destroy(); resolve(true); });
      s.on("error", () => resolve(false));
      s.setTimeout(1000, () => { s.destroy(); resolve(false); });
    } catch { resolve(false); }
  });
}

/** Before spawning a new daemon, if we're at the concurrent cap, close the
 * oldest live daemon (oldest socket mtime) to make room. Excludes the session
 * we're about to spawn. Best-effort — never throws. */
async function evictForCap(session: string): Promise<void> {
  const excludeSock = getSocketPath(session);
  const candidates: { session: string; mtime: number }[] = [];
  for (const s of listSessions()) {
    const sock = getSocketPath(s);
    if (sock === excludeSock) continue;
    if (!(await daemonAlive(sock))) continue;
    try {
      const st = fs.statSync(sock);
      candidates.push({ session: s, mtime: st.mtimeMs });
    } catch {}
  }
  if (candidates.length < MAX_CONCURRENT_DAEMONS) return;
  candidates.sort((a, b) => a.mtime - b.mtime);
  const oldest = candidates[0];
  process.stderr.write(`[camoufox-cli] Concurrent daemon cap (${MAX_CONCURRENT_DAEMONS}) reached, evicting oldest session ${oldest.session}\n`);
  try {
    await sendCommand(getSocketPath(oldest.session), { id: "r1", action: "close", params: {} });
  } catch (e: any) {
    process.stderr.write(`[camoufox-cli] Eviction close failed: ${e.message}\n`);
  }
  await new Promise((r) => setTimeout(r, 300));
}

// ---------------------------------------------------------------------------
// Arg parsing
// ---------------------------------------------------------------------------

export interface Flags {
  session: string;
  headed: boolean;
  timeout: number;
  json: boolean;
  persistent: string | null;
  proxy: string | null;
  geoip: boolean;
  locale: string | null;
  viewport: [number, number] | null;
}

export function parseArgs(argv: string[]): { flags: Flags; command: Record<string, unknown> } {
  // Flag precedence: command line > config file (per-session block, then the
  // `default` block) > built-in defaults. Only flags explicitly passed on the
  // command line are collected here, so they always win over config.
  const builtin: Flags = { session: "default", headed: false, timeout: 60, json: false, persistent: null, proxy: null, geoip: true, locale: null, viewport: null };
  const cli: Partial<Flags> = {};
  const rest: string[] = [];

  let i = 0;
  while (i < argv.length) {
    switch (argv[i]) {
      case "--session":
        cli.session = argv[++i] ?? (process.stderr.write("Error: --session requires a value\n"), process.exit(1), "");
        break;
      case "--headed":
        cli.headed = true;
        break;
      case "--timeout":
        cli.timeout = parseInt(argv[++i] ?? "60", 10);
        break;
      case "--json":
        cli.json = true;
        break;
      case "--persistent": {
        // Optional value: if next arg looks like a path, use it; otherwise use default
        const next = argv[i + 1];
        if (next && (next.includes("/") || next.startsWith(".") || next.startsWith("~"))) {
          cli.persistent = argv[++i];
        } else {
          cli.persistent = "";
        }
        break;
      }
      case "--proxy":
        cli.proxy = argv[++i] ?? null;
        break;
      case "--no-geoip":
        cli.geoip = false;
        break;
      case "--locale":
        cli.locale = argv[++i] ?? (process.stderr.write("Error: --locale requires a value\n"), process.exit(1), "");
        break;
      case "--viewport": {
        const vp = parseViewport(argv[++i]);
        if (!Array.isArray(vp)) { process.stderr.write("Error: --viewport requires a value like 1920x1080\n"); process.exit(1); }
        cli.viewport = vp;
        break;
      }
      default:
        rest.push(argv[i]);
    }
    i++;
  }

  if (rest.length === 0) {
    process.stderr.write(USAGE + "\n");
    process.exit(1);
  }

  // session selects which config block applies, so it comes only from the CLI.
  const session = cli.session ?? builtin.session;
  const flags: Flags = { ...builtin, ...loadDefaults(session), ...cli };

  const command = buildCommand(rest[0], rest);
  return { flags, command };
}

function require_(args: string[], idx: number, usage: string): string {
  if (idx >= args.length) {
    process.stderr.write(usage + "\n");
    process.exit(1);
  }
  return args[idx];
}

export function buildCommand(action: string, rest: string[]): Record<string, unknown> {
  switch (action) {
    case "open":
      return { id: "r1", action: "open", params: { url: require_(rest, 1, "Usage: camoufox-cli open <url>") } };
    case "back":
      return { id: "r1", action: "back", params: {} };
    case "forward":
      return { id: "r1", action: "forward", params: {} };
    case "reload":
      return { id: "r1", action: "reload", params: {} };
    case "url":
      return { id: "r1", action: "url", params: {} };
    case "title":
      return { id: "r1", action: "title", params: {} };
    case "close":
      return { id: "r1", action: "close", params: { all: rest.includes("--all") } };

    case "snapshot": {
      const interactive = rest.includes("-i");
      let selector: string | undefined;
      const sIdx = rest.indexOf("-s");
      if (sIdx >= 0) selector = require_(rest, sIdx + 1, "Usage: camoufox-cli snapshot -s <selector>");
      const params: Record<string, unknown> = { interactive };
      if (selector) params.selector = selector;
      return { id: "r1", action: "snapshot", params };
    }

    case "click":
      return { id: "r1", action: "click", params: { ref: require_(rest, 1, "Usage: camoufox-cli click @e1") } };
    case "fill":
      return { id: "r1", action: "fill", params: { ref: require_(rest, 1, 'Usage: camoufox-cli fill @e1 "text"'), text: require_(rest, 2, 'Usage: camoufox-cli fill @e1 "text"') } };
    case "type":
      return { id: "r1", action: "type", params: { ref: require_(rest, 1, 'Usage: camoufox-cli type @e1 "text"'), text: require_(rest, 2, 'Usage: camoufox-cli type @e1 "text"') } };
    case "select":
      return { id: "r1", action: "select", params: { ref: require_(rest, 1, 'Usage: camoufox-cli select @e1 "option"'), value: require_(rest, 2, 'Usage: camoufox-cli select @e1 "option"') } };
    case "check":
      return { id: "r1", action: "check", params: { ref: require_(rest, 1, "Usage: camoufox-cli check @e1") } };
    case "hover":
      return { id: "r1", action: "hover", params: { ref: require_(rest, 1, "Usage: camoufox-cli hover @e1") } };
    case "press":
      return { id: "r1", action: "press", params: { key: require_(rest, 1, "Usage: camoufox-cli press Enter") } };

    case "text":
      return { id: "r1", action: "text", params: { target: require_(rest, 1, "Usage: camoufox-cli text @e1") } };
    case "eval":
      return { id: "r1", action: "eval", params: { expression: require_(rest, 1, 'Usage: camoufox-cli eval "document.title"') } };
    case "screenshot": {
      const params: Record<string, unknown> = {};
      for (const arg of rest.slice(1)) {
        if (arg === "--full") params.full_page = true;
        else params.path = arg;
      }
      return { id: "r1", action: "screenshot", params };
    }
    case "pdf":
      return { id: "r1", action: "pdf", params: { path: require_(rest, 1, "Usage: camoufox-cli pdf output.pdf") } };

    case "scroll":
      return { id: "r1", action: "scroll", params: { direction: require_(rest, 1, "Usage: camoufox-cli scroll down [px]"), amount: rest.length > 2 ? parseInt(rest[2], 10) : 500 } };
    case "wait": {
      const target = require_(rest, 1, 'Usage: camoufox-cli wait @e1 | camoufox-cli wait 2000 | camoufox-cli wait --url "pattern"');
      if (target === "--url") return { id: "r1", action: "wait", params: { url: require_(rest, 2, 'Usage: camoufox-cli wait --url "*/dashboard"') } };
      if (target.startsWith("@")) return { id: "r1", action: "wait", params: { ref: target } };
      if (/^\d/.test(target)) return { id: "r1", action: "wait", params: { ms: parseInt(target, 10) } };
      return { id: "r1", action: "wait", params: { selector: target } };
    }

    case "tabs":
      return { id: "r1", action: "tabs", params: {} };
    case "switch":
      return { id: "r1", action: "switch", params: { index: parseInt(require_(rest, 1, "Usage: camoufox-cli switch <tab-index>"), 10) } };
    case "close-tab":
      return { id: "r1", action: "close-tab", params: {} };

    case "sessions":
      return { id: "r1", action: "sessions", params: {} };
    case "info":
      return { id: "r1", action: "info", params: {} };
    case "install":
      return { id: "r1", action: "install", params: { with_deps: rest.includes("--with-deps") } };
    case "cookies": {
      if (rest.length > 1 && rest[1] === "import")
        return { id: "r1", action: "cookies", params: { op: "import", path: require_(rest, 2, "Usage: camoufox-cli cookies import file.json") } };
      if (rest.length > 1 && rest[1] === "export")
        return { id: "r1", action: "cookies", params: { op: "export", path: require_(rest, 2, "Usage: camoufox-cli cookies export file.json") } };
      return { id: "r1", action: "cookies", params: { op: "list" } };
    }
    case "identity": {
      if (rest.length > 1 && rest[1] === "export")
        return { id: "r1", action: "identity", params: { op: "export", path: require_(rest, 2, "Usage: camoufox-cli identity export file.json") } };
      return { id: "r1", action: "identity", params: { op: "show" } };
    }
    case "upload": {
      const target = require_(rest, 1, "Usage: camoufox-cli upload @ref|selector <file> [more files...]");
      const paths = rest.slice(2);
      if (paths.length === 0) {
        process.stderr.write("Usage: camoufox-cli upload @ref|selector <file> [more files...]\n");
        process.exit(1);
      }
      const params: Record<string, unknown> = { paths };
      if (target.startsWith("@")) params.ref = target;
      else params.selector = target;
      return { id: "r1", action: "upload", params };
    }

    default:
      process.stderr.write(`Unknown command: ${action}\n${USAGE}\n`);
      process.exit(1);
  }
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

export function printResponse(response: Record<string, unknown>, jsonMode: boolean): void {
  if (jsonMode) {
    console.log(JSON.stringify(response, null, 2));
    return;
  }

  if (!response.success) {
    process.stderr.write(`Error: ${response.error || "Unknown error"}\n`);
    process.exit(1);
  }

  const data = response.data as Record<string, unknown> | undefined;
  if (!data) return;

  if ("snapshot" in data) {
    console.log(data.snapshot);
  } else if ("text" in data) {
    console.log(data.text);
  } else if ("result" in data) {
    const v = data.result;
    console.log(v === null ? "null" : typeof v === "string" ? v : JSON.stringify(v));
  } else if (data.closed) {
    // silent
  } else if ("url" in data) {
    if ("title" in data) console.log(data.title);
    console.log(data.url);
  } else if ("title" in data) {
    console.log(data.title);
  } else {
    console.log(JSON.stringify(data, null, 2));
  }
}

// ---------------------------------------------------------------------------
// System dependencies
// ---------------------------------------------------------------------------

const APT_DEPS = [
  "libxcb-shm0", "libx11-xcb1", "libx11-6", "libxcb1", "libxext6",
  "libxrandr2", "libxcomposite1", "libxcursor1", "libxdamage1", "libxfixes3",
  "libxi6", "libgtk-3-0", "libpangocairo-1.0-0", "libpango-1.0-0",
  "libatk1.0-0", "libcairo-gobject2", "libcairo2", "libgdk-pixbuf-2.0-0",
  "libxrender1", "libfreetype6", "libfontconfig1", "libdbus-1-3",
  "libnss3", "libnspr4", "libatk-bridge2.0-0", "libdrm2", "libxkbcommon0",
  "libatspi2.0-0", "libcups2", "libxshmfence1", "libgbm1",
];

const DNF_DEPS = [
  "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
  "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
  "alsa-lib", "libxkbcommon", "libxcb", "libX11-xcb", "libX11",
  "libXext", "libXcursor", "libXfixes", "libXi", "gtk3", "cairo-gobject",
];

const YUM_DEPS = [
  "nss", "nspr", "atk", "at-spi2-atk", "cups-libs", "libdrm",
  "libXcomposite", "libXdamage", "libXrandr", "mesa-libgbm", "pango",
  "alsa-lib", "libxkbcommon",
];

function resolveAptLibasound(): string {
  try {
    execFileSync("dpkg", ["-l", "libasound2t64"], { stdio: "pipe" });
    return "libasound2t64";
  } catch {
    return "libasound2";
  }
}

function installSystemDeps(): void {
  if (os.platform() !== "linux") {
    process.stderr.write("[camoufox-cli] System dependencies are only needed on Linux, skipping.\n");
    return;
  }

  process.stderr.write("[camoufox-cli] Installing system dependencies...\n");

  if (fs.existsSync("/usr/bin/apt-get")) {
    const deps = [...APT_DEPS, resolveAptLibasound()];
    execFileSync("sudo", ["apt-get", "update", "-y"], { stdio: "inherit" });
    execFileSync("sudo", ["apt-get", "install", "-y", ...deps], { stdio: "inherit" });
  } else if (fs.existsSync("/usr/bin/dnf")) {
    execFileSync("sudo", ["dnf", "install", "-y", ...DNF_DEPS], { stdio: "inherit" });
  } else if (fs.existsSync("/usr/bin/yum")) {
    execFileSync("sudo", ["yum", "install", "-y", ...YUM_DEPS], { stdio: "inherit" });
  } else {
    process.stderr.write("[camoufox-cli] Could not detect a supported package manager (apt-get, dnf, yum).\n");
    process.exit(1);
  }

  process.stderr.write("[camoufox-cli] System dependencies installed.\n");
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const argv = process.argv.slice(2);
  const { flags, command } = parseArgs(argv);

  // Resolve default persistent path
  if (flags.persistent === "") {
    flags.persistent = path.join(os.homedir(), ".camoufox-cli", "profiles", flags.session);
  }

  const action = command.action as string;

  // Client-side: install
  if (action === "install") {
    process.stderr.write("[camoufox-cli] Downloading browser...\n");
    const { installBrowser } = await import("./install.js");
    await installBrowser();
    process.stderr.write("[camoufox-cli] Browser installed.\n");
    if ((command.params as any)?.with_deps) {
      installSystemDeps();
    }
    return;
  }

  // Client-side: sessions
  if (action === "sessions") {
    const sessions = listSessions();
    if (flags.json) {
      console.log(JSON.stringify(sessions, null, 2));
    } else if (sessions.length === 0) {
      console.log("No active sessions.");
    } else {
      sessions.forEach((s) => console.log(s));
    }
    return;
  }

  // Client-side: info — probe a session's daemon mode without spawning one.
  if (action === "info") {
    const sockPath = getSocketPath(flags.session);
    const info = await queryDaemonInfo(sockPath);
    if (!info) {
      if (flags.json) console.log(JSON.stringify({ session: flags.session, running: false }, null, 2));
      else console.log(`No active daemon for session ${flags.session}.`);
      return;
    }
    if (flags.json) {
      console.log(JSON.stringify({ session: info.session, headless: info.headless, headed: !info.headless, running: true }, null, 2));
    } else {
      console.log(`session=${info.session} headless=${info.headless} headed=${!info.headless}`);
    }
    return;
  }

  // Client-side: close --all
  if (action === "close" && (command.params as any)?.all) {
    const sessions = listSessions();
    if (sessions.length === 0) { console.log("No active sessions."); return; }
    const closeCmd = { id: "r1", action: "close", params: {} };
    for (const session of sessions) {
      try { await sendCommand(getSocketPath(session), closeCmd); }
      catch (e: any) { process.stderr.write(`Failed to close session ${session}: ${e.message}\n`); }
    }
    return;
  }

  // Ensure daemon is running
  await ensureDaemon(flags.session, flags.headed, flags.timeout, flags.persistent, flags.proxy, flags.geoip, flags.locale, flags.viewport);

  const sockPath = getSocketPath(flags.session);

  // Send command with retry
  let lastErr = "";
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      const response = await sendCommand(sockPath, command);
      printResponse(response, flags.json);
      return;
    } catch (e: any) {
      lastErr = e.message || String(e);
      if (attempt < 4) await new Promise((r) => setTimeout(r, 200 * (attempt + 1)));
    }
  }

  process.stderr.write(`Error: Failed to connect to daemon after 5 attempts: ${lastErr}\n`);
  process.exit(1);
}

const USAGE = `Usage: camoufox-cli [flags] <command> [args]

Navigation:
  open <url>              Navigate to URL
  back                    Go back
  forward                 Go forward
  reload                  Reload page
  url                     Print current URL
  title                   Print page title
  close [--all]           Close browser and daemon (--all: all sessions)

Snapshot:
  snapshot [-i] [-s sel]  Aria tree (-i interactive, -s scoped)

Interaction:
  click @ref              Click element
  fill @ref "text"        Clear + type into input
  type @ref "text"        Type without clearing
  select @ref "option"    Select dropdown option
  check @ref              Toggle checkbox
  hover @ref              Hover over element
  press <key>             Press key (e.g. Enter, Control+a)

Data:
  text @ref|selector      Get text content
  eval "js expression"    Execute JavaScript
  screenshot [--full] [f] Screenshot to file or stdout
  pdf <file>              Save page as PDF
  upload @ref|sel <f> [f…] Upload file(s) to an <input>

Scroll & Wait:
  scroll <dir> [px]       Scroll up/down (default 500px)
  wait <ms|@ref|--url p>  Wait for time/element/URL

Tabs:
  tabs                    List open tabs
  switch <index>          Switch to tab
  close-tab               Close current tab

Session:
  sessions                List active sessions
  info                    Show this session's daemon mode (headless/headed)
  cookies [import|export] Manage cookies
  identity [export <f>]   Show/export UA + fingerprint summary

Setup:
  install [--with-deps]   Download browser (--with-deps: system libs)

Flags:
  --session <name>     Session name (default: "default")
  --headed             Show browser window
  --timeout <secs>     Daemon idle timeout (default: 60, hard max 60 — daemons
                        self-exit when idle to avoid browser accumulation; login
                        state lives in the profile dir and survives exit)
  --json               Output as JSON
  --persistent [path]  Persistent identity — freeze fingerprint/OS/locale + store cookies/state (default: ~/.camoufox-cli/profiles/<session>)
  --proxy <url>        Proxy server (e.g. http://host:port or https://host:443)
  --no-geoip           Disable automatic GeoIP spoofing (auto-enabled with --proxy)
  --locale <tag>       Force browser locale (e.g. "en-US" or "en-US,zh-CN")
  --viewport <WxH>     Fixed window size, e.g. 1920x1080 (default: fingerprint-derived)

Config file:
  ~/.camoufox-cli/config.json sets defaults for the flags above (override the
  path with $CAMOUFOX_CLI_CONFIG). Command-line flags always take precedence.
  Use a "default" block plus optional per-session blocks under "sessions".`;

const isDirectRun = (() => {
  try {
    return process.argv[1] &&
      fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch { return false; }
})();
if (isDirectRun) main();
