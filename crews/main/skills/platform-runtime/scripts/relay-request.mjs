import { readFileSync } from 'node:fs';

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
  const response = await fetch(new URL('/api/v1/sign/platforms/v1', base), {
    method: 'POST', redirect: 'error', headers: { 'Content-Type': 'application/json', 'X-OFB-Key': key },
    body, signal: AbortSignal.timeout(35000),
  });
  const text = await response.text();
  if (text.length > 1024 * 1024) throw Error('SIGN_UNAVAILABLE');
  let value;
  try { value = JSON.parse(text); } catch { throw Error('SIGN_UNAVAILABLE'); }
  if (!response.ok || value.success !== true || !Object.hasOwn(value, 'data')) {
    const code = response.status === 429 ? 'RELAY_RATE_LIMITED' : response.status === 401 || response.status === 403 ? 'OFB_KEY_INVALID'
      : ['INVALID_INPUT', 'UNSUPPORTED_OPERATION', 'MATERIAL_UNAVAILABLE', 'SIGN_UNAVAILABLE'].includes(value.error) ? value.error : 'SIGN_UNAVAILABLE';
    result = { success: false, error: code, http_status: response.status };
  } else result = { success: true, data: value.data };
} catch (error) {
  result = { success: false, error: ['OFB_KEY_MISSING', 'RELAY_URL_INVALID', 'INVALID_INPUT'].includes(error.message) ? error.message : 'SIGN_UNAVAILABLE' };
}
process.stdout.write(JSON.stringify(result));
