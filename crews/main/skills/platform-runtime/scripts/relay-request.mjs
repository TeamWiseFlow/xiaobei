import { readFileSync } from 'node:fs';
import { acquireBudget, observeBudget, keyHash, retryDelay } from './relay-budget.mjs';

// 独立进程承接同步调用；凭据只经环境和请求头传递，不进入命令行或日志。
let result;
try {
  const body = readFileSync(0, 'utf8');
  if (Buffer.byteLength(body) > 512 * 1024) throw Error('INVALID_INPUT');
  const key = process.env.OFB_KEY;
  if (!key) throw Error('OFB_KEY_MISSING');
  const base = new URL(process.env.RELAY_BASE_URL || 'https://relay.openclaw-for-business.com');
  if (base.username || base.password || base.search || base.hash
      || !(base.protocol === 'https:' || base.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname))) throw Error('RELAY_URL_INVALID');
  const started = Date.now(), digest = keyHash(key);
  let response;
  for (let attempt = 0; attempt < 2; attempt++) {
    await acquireBudget(base, digest, { maxWaitMs: Math.max(0, Math.min(35000, 75000 - (Date.now() - started))) });
    const remaining = 75000 - (Date.now() - started);
    if (remaining <= 0) throw Object.assign(Error('RELAY_RATE_LIMITED'), { retryAfterSeconds: 1 });
    response = await fetch(new URL('/api/v1/sign/platforms/v1', base), {
    method: 'POST', redirect: 'error', headers: { 'Content-Type': 'application/json', 'X-OFB-Key': key },
    body, signal: AbortSignal.timeout(Math.min(35000, remaining)),
  });
    await observeBudget(base, digest, response.headers, response.status);
    if (response.status !== 429 || attempt) break;
    await response.body?.cancel();
  }
  const text = await response.text();
  if (text.length > 1024 * 1024) throw Error('SIGN_UNAVAILABLE');
  let value;
  try { value = JSON.parse(text); } catch { value = {}; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) value = {};
  if (!response.ok || value.success !== true || !Object.hasOwn(value, 'data')) {
    const code = response.status === 429 ? 'RELAY_RATE_LIMITED' : response.status === 401 || response.status === 403 ? 'OFB_KEY_INVALID'
      : ['INVALID_INPUT', 'UNSUPPORTED_OPERATION', 'MATERIAL_UNAVAILABLE', 'SIGN_UNAVAILABLE'].includes(value.error) ? value.error : 'SIGN_UNAVAILABLE';
    result = { success: false, error: code, http_status: response.status,
      ...(response.status === 429 ? { retry_after_seconds: Math.ceil(retryDelay(response.headers) / 1000) } : {}) };
  } else result = { success: true, data: value.data };
} catch (error) {
  result = { success: false, error: ['OFB_KEY_MISSING', 'RELAY_URL_INVALID', 'INVALID_INPUT', 'RELAY_RATE_LIMITED'].includes(error.message) ? error.message : 'SIGN_UNAVAILABLE',
    ...(error.retryAfterSeconds ? { retry_after_seconds: error.retryAfterSeconds } : {}),
    reason: error.name === 'TimeoutError' || error.name === 'AbortError' ? 'timeout' : error instanceof TypeError ? 'connection' : 'response_or_budget' };
}
process.stdout.write(JSON.stringify(result));
