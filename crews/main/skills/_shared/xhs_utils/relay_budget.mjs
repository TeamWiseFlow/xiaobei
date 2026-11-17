// Shared scheduling for actual Relay HTTP calls; never stores a key or signing input.
import { createHash, randomBytes } from 'node:crypto';
import { mkdir, readFile, writeFile, rename, rm, stat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const wait = ms => new Promise(done => setTimeout(done, ms));
export const keyHash = key => createHash('sha256').update(key).digest('hex');
function location(base, digest) {
  if (!/^[a-f0-9]{64}$/.test(digest)) throw Error('INVALID_BUDGET_KEY');
  const id = createHash('sha256').update(new URL(base).origin + '\0' + digest).digest('hex');
  const home = process.env.RELAY_BUDGET_HOME || join(process.env.OPENCLAW_HOME || join(homedir(), '.openclaw'), 'cache/relay-budget-v1');
  return join(home, id + '.json');
}
async function locked(file, action) {
  await mkdir(dirname(file), { recursive: true, mode: 0o700 });
  const lock = file + '.lock';
  let owned = false;
  for (let attempt = 0; attempt < 150; attempt++) {
    try {
      await mkdir(lock, { mode: 0o700 }); owned = true;
      await writeFile(join(lock, 'owner'), String(process.pid), { mode: 0o600 });
      break;
    } catch (error) {
      if (owned) { await rm(lock, { recursive: true, force: true }); throw error; }
      if (error.code !== 'EEXIST') throw error;
      try {
        const age = Date.now() - (await stat(lock)).mtimeMs;
        if (age > 2000) {
          let pid; try { pid = Number(await readFile(join(lock, 'owner'), 'utf8')); } catch {}
          let alive = Number.isInteger(pid) && pid > 0;
          if (alive) try { process.kill(pid, 0); } catch (failure) { alive = failure.code !== 'ESRCH'; }
          if (!alive) { await rm(lock, { recursive: true, force: true }); continue; }
        }
      } catch (failure) { if (failure.code !== 'ENOENT') throw failure; }
      await wait(20);
    }
  }
  if (!owned) throw Object.assign(Error('RELAY_RATE_LIMITED'), { retryAfterSeconds: 1 });
  try {
    let state = {};
    try { state = JSON.parse(await readFile(file, 'utf8')); } catch (error) { if (error.code !== 'ENOENT' && !(error instanceof SyntaxError)) throw error; }
    if (!state || typeof state !== 'object' || Array.isArray(state)) state = {};
    const result = await action(state);
    const tmp = file + '.' + process.pid + '.' + randomBytes(4).toString('hex');
    try { await writeFile(tmp, JSON.stringify(state), { mode: 0o600 }); await rename(tmp, file); }
    finally { await rm(tmp, { force: true }); }
    return result;
  } finally { await rm(lock, { recursive: true, force: true }); }
}
export function retryDelay(headers, now = Date.now()) {
  const get = name => typeof headers?.get === 'function' ? headers.get(name) : headers?.[name];
  const precise = Number(get('x-ofb-retry-after-ms'));
  if (get('x-ofb-retry-after-ms') != null && Number.isFinite(precise) && precise >= 0) return Math.min(300000, precise);
  const value = get('retry-after');
  if (value != null && /^\d+(?:\.\d+)?$/.test(String(value))) return Math.min(300000, Number(value) * 1000);
  const stamp = Date.parse(value);
  return Number.isFinite(stamp) ? Math.min(300000, Math.max(0, stamp - now)) : 2000;
}
export async function observeBudget(base, digest, headers, status) {
  const get = name => typeof headers?.get === 'function' ? headers.get(name) : headers?.[name];
  const cap = get('x-ofb-ratelimit-limit');
  const remaining = get('x-ofb-ratelimit-remaining');
  if (status !== 429 && cap == null) return;
  await locked(location(base, digest), state => {
    if (cap != null && /^\d+$/.test(String(cap))) state.server_rpm = Number(cap);
    if (status === 429) state.blocked_until = Math.max(Number(state.blocked_until) || 0, Date.now() + retryDelay(headers));
    else if (remaining === '0' && state.server_rpm > 0) state.blocked_until = Math.max(Number(state.blocked_until) || 0, Date.now() + Math.ceil(60000 / state.server_rpm));
    state.observed_at = Date.now();
  });
}
export async function acquireBudget(base, digest, { maxWaitMs = 35000 } = {}) {
  const file = location(base, digest), started = Date.now();
  let configured = process.env.RELAY_CLIENT_RPM === undefined ? 50 : Number(process.env.RELAY_CLIENT_RPM);
  if (!Number.isFinite(configured) || configured < 0 || configured > 6000) throw Error('INVALID_RELAY_CLIENT_RPM');
  for (;;) {
    const slot = await locked(file, state => {
      const now = Date.now();
      const learned = state.observed_at > now - 86400000 && state.server_rpm > 0 ? Math.max(1, Math.floor(state.server_rpm * 0.85)) : undefined;
      const rpm = configured === 0 ? 0 : Math.min(configured, learned ?? configured);
      const at = Math.max(now, Number(state.blocked_until) || 0, rpm ? Number(state.next_at) || 0 : 0);
      if (at - started > maxWaitMs) throw Object.assign(Error('RELAY_RATE_LIMITED'), { retryAfterSeconds: Math.ceil((at - now) / 1000) });
      if (rpm) state.next_at = at + Math.ceil(60000 / rpm);
      return at;
    });
    await wait(Math.max(0, slot - Date.now()));
    const blocked = await locked(file, state => Number(state.blocked_until) || 0);
    if (blocked <= Date.now()) return;
    if (Date.now() - started >= maxWaitMs) throw Object.assign(Error('RELAY_RATE_LIMITED'), { retryAfterSeconds: Math.ceil((blocked - Date.now()) / 1000) });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let input = ''; for await (const chunk of process.stdin) input += chunk;
  try {
    const args = JSON.parse(input);
    if (args.action === 'acquire') await acquireBudget(args.base, args.digest);
    else if (args.action === 'observe') await observeBudget(args.base, args.digest, args.headers, args.status);
    else throw Error('INVALID_BUDGET_ACTION');
    process.stdout.write(JSON.stringify({ ok: true }));
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: error.message === 'RELAY_RATE_LIMITED' ? error.message : 'RELAY_BUDGET_UNAVAILABLE', retry_after_seconds: error.retryAfterSeconds }));
    process.exitCode = 1;
  }
}
