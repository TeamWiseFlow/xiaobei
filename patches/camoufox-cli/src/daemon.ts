#!/usr/bin/env node
/** Entry point: daemon process (spawned by CLI). */

import { DaemonServer } from "./server.js";
import { parseViewport } from "./config.js";

const args = process.argv.slice(2);

function getArg(name: string, defaultValue: string): string {
  const idx = args.indexOf(name);
  return idx >= 0 && idx + 1 < args.length ? args[idx + 1] : defaultValue;
}

const session = getArg("--session", "default");
const headless = !args.includes("--headed");
const timeout = parseInt(getArg("--timeout", "60"), 10);
const persistent = args.includes("--persistent") ? getArg("--persistent", "") || null : null;
const proxy = args.includes("--proxy") ? getArg("--proxy", "") || null : null;
const geoip = !args.includes("--no-geoip");
const locale = args.includes("--locale") ? getArg("--locale", "") || null : null;
const viewportSpec = args.includes("--viewport") ? parseViewport(getArg("--viewport", "")) : null;
const viewport = Array.isArray(viewportSpec) ? viewportSpec : null;

const server = new DaemonServer({ session, headless, timeout, persistent, proxy, geoip, locale, viewport, forceExit: true });

process.stderr.write(`[camoufox-cli] Starting daemon session=${session} headless=${headless}\n`);
server.start().catch((err) => {
  process.stderr.write(`[camoufox-cli] Fatal: ${err}\n`);
  process.exit(1);
});
