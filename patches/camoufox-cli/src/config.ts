/**
 * Optional config file support.
 *
 * A JSON file at ~/.camoufox-cli/config.json (override with the
 * CAMOUFOX_CLI_CONFIG env var) supplies default values for daemon-launch
 * flags, so common settings (proxy, locale, persistent…) don't have to be
 * repeated on every invocation.
 *
 * Precedence: command-line flag > config `sessions.<name>` block >
 * config `default` block > built-in default.
 *
 * Only flags that affect daemon launch are honored. `session` itself is never
 * read from config — it selects which block to apply, so it can only come from
 * the command line. Per-command flags (--full, -i, …) are never read.
 *
 * The config only takes effect when a session's daemon first launches; an
 * already-running daemon is reused as-is (see ensureDaemon).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export interface ConfigDefaults {
  headed?: boolean;
  timeout?: number;
  json?: boolean;
  persistent?: string | null;
  proxy?: string | null;
  geoip?: boolean;
  locale?: string | null;
  viewport?: [number, number] | null;
}

/** Parse a viewport spec ("WxH" string or [W, H] tuple) into a [w, h] tuple.
 *  Returns null for null/undefined, or the INVALID sentinel for malformed input. */
export function parseViewport(value: unknown): [number, number] | null | typeof INVALID {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") {
    const m = /^(\d+)x(\d+)$/.exec(value.trim());
    if (m) return [parseInt(m[1], 10), parseInt(m[2], 10)];
    return INVALID;
  }
  if (Array.isArray(value) && value.length === 2
      && typeof value[0] === "number" && Number.isFinite(value[0])
      && typeof value[1] === "number" && Number.isFinite(value[1])) {
    return [Math.trunc(value[0]), Math.trunc(value[1])];
  }
  return INVALID;
}

// Flags a config file may set, grouped by the value type each one expects.
// "session" is intentionally absent — it selects which block to apply, so it
// must come from the command line.
const BOOL_KEYS = new Set(["headed", "geoip", "json"]);
const STR_KEYS = new Set(["proxy", "locale"]);
const ALLOWED_KEYS = new Set([...BOOL_KEYS, ...STR_KEYS, "timeout", "persistent", "viewport"]);
const INVALID = Symbol("invalid");

/** Resolved config path, read at call time so the env var can be overridden (incl. by tests). */
export function configPath(): string {
  return process.env.CAMOUFOX_CLI_CONFIG || path.join(os.homedir(), ".camoufox-cli", "config.json");
}

/**
 * Return config-derived flag defaults for `session`.
 *
 * Merges the top-level `default` block with the `sessions.<session>` block
 * (the latter wins). Returns `{}` when the file is absent or malformed — a
 * broken config never blocks a command, it is only ignored with a warning on
 * stderr.
 */
export function loadDefaults(session: string): ConfigDefaults {
  const p = configPath();
  if (!fs.existsSync(p)) return {};

  let raw: unknown;
  try {
    raw = JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e: any) {
    process.stderr.write(`[camoufox-cli] Ignoring config ${p}: ${e.message}\n`);
    return {};
  }

  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    process.stderr.write(`[camoufox-cli] Ignoring config ${p}: top level must be a JSON object\n`);
    return {};
  }

  const obj = raw as Record<string, unknown>;
  const merged: Record<string, unknown> = {};
  Object.assign(merged, clean(obj.default, p));

  const sessions = obj.sessions;
  if (typeof sessions === "object" && sessions !== null && !Array.isArray(sessions)) {
    Object.assign(merged, clean((sessions as Record<string, unknown>)[session], p));
  } else if (sessions !== undefined) {
    process.stderr.write(`[camoufox-cli] Ignoring config ${p}: "sessions" must be an object\n`);
  }

  return normalize(merged);
}

/** Keep only allowed keys from a block, warning on anything else. */
function clean(block: unknown, p: string): Record<string, unknown> {
  if (block === undefined || block === null) return {};
  if (typeof block !== "object" || Array.isArray(block)) {
    process.stderr.write(`[camoufox-cli] Ignoring config ${p}: blocks must be objects\n`);
    return {};
  }
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(block as Record<string, unknown>)) {
    if (ALLOWED_KEYS.has(key)) out[key] = value;
    else if (key === "session") process.stderr.write(`[camoufox-cli] Ignoring "session" in config — set it with --session on the command line\n`);
    else process.stderr.write(`[camoufox-cli] Ignoring unknown config key: ${key}\n`);
  }
  return out;
}

/**
 * Validate/coerce each config value to the type its flag expects.
 *
 * A value of the wrong type is dropped with a warning rather than passed
 * through, so a malformed config is always ignored, never fatal: a non-string
 * proxy/locale/persistent would crash daemon launch, a non-numeric timeout
 * would fail silently, and a non-bool toggle (e.g. the string "false") would
 * be silently truthy.
 */
function normalize(flags: Record<string, unknown>): ConfigDefaults {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(flags)) {
    const coerced = coerce(key, value);
    if (coerced === INVALID) {
      process.stderr.write(`[camoufox-cli] Ignoring invalid ${key} in config: ${JSON.stringify(value)}\n`);
    } else {
      out[key] = coerced;
    }
  }
  return out as ConfigDefaults;
}

/** Return the normalized value if it fits the flag's type, else the INVALID sentinel. */
function coerce(key: string, value: unknown): unknown {
  if (BOOL_KEYS.has(key)) return typeof value === "boolean" ? value : INVALID;
  // null is accepted as "unset" (falls back to the built-in default).
  if (STR_KEYS.has(key)) return value === null || typeof value === "string" ? value : INVALID;
  if (key === "timeout") {
    // a finite number only — excludes bool, string and null
    return typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : INVALID;
  }
  if (key === "persistent") {
    // true -> "" (default profile path, resolved in main); false -> null
    // (disabled); null/string kept as-is; anything else invalid.
    if (typeof value === "boolean") return value ? "" : null;
    return value === null || typeof value === "string" ? value : INVALID;
  }
  if (key === "viewport") return parseViewport(value);
  return value; // unreachable: clean already filtered to known keys
}
